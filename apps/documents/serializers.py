from rest_framework import serializers

from apps.accounts.permissions import validar_de_la_empresa

from .models import AnnualPlan, Document, DocumentVersion, PlanActivity, VersionStatus


def _empresa(serializer):
    return serializer.context["request"].user.company_id


def _nombre(usuario) -> str | None:
    if usuario is None:
        return None
    return usuario.get_full_name() or usuario.username


class DocumentVersionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    receipt_count = serializers.SerializerMethodField()

    class Meta:
        model = DocumentVersion
        fields = (
            "id", "document", "number", "content", "file", "approved_by", "approved_on",
            "change_summary", "status", "status_display", "valid_from", "valid_until",
            "created_by_name", "created_at", "receipt_count",
        )
        read_only_fields = ("number", "status", "valid_from", "valid_until", "created_at")

    def get_created_by_name(self, version) -> str | None:
        return _nombre(version.created_by)

    def get_receipt_count(self, version) -> int:
        return version.receipts.count()

    def validate_document(self, documento):
        validar_de_la_empresa(documento, _empresa(self), "document", "El documento")
        return documento

    def validate(self, attrs):
        # Lo vigente y lo histórico es evidencia: no se corrige, se publica otra versión.
        if self.instance and self.instance.status != VersionStatus.BORRADOR:
            raise serializers.ValidationError(
                {"detail": "Solo se edita un borrador. Crea una nueva versión."}
            )
        return attrs


class DocumentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    current_version = serializers.SerializerMethodField()
    received_by_me = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id", "kind", "kind_display", "title", "code", "requires_receipt",
            "current_version", "received_by_me",
        )

    def get_current_version(self, documento) -> dict | None:
        version = documento.current_version
        return DocumentVersionSerializer(version, context=self.context).data if version else None

    def get_received_by_me(self, documento) -> bool | None:
        version = documento.current_version
        if not documento.requires_receipt or version is None:
            return None
        return version.receipts.filter(worker=self.context["request"].user).exists()


class PlanActivitySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    responsible_name = serializers.SerializerMethodField()

    class Meta:
        model = PlanActivity
        fields = (
            "id", "plan", "objective", "description", "responsible", "responsible_name",
            "planned_month", "status", "status_display", "executed_on", "evidence",
        )

    def get_responsible_name(self, actividad) -> str | None:
        return _nombre(actividad.responsible)

    def validate(self, attrs):
        empresa = _empresa(self)
        validar_de_la_empresa(attrs.get("plan"), empresa, "plan", "El plan")
        validar_de_la_empresa(attrs.get("responsible"), empresa, "responsible", "El responsable")
        return attrs


class AnnualPlanSerializer(serializers.ModelSerializer):
    activities = PlanActivitySerializer(many=True, read_only=True)

    class Meta:
        model = AnnualPlan
        fields = ("id", "year", "objectives", "approved_on", "activities")
