from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from .models import Category, Report, ReportAction, ReportStatus


class CoordenadaField(serializers.DecimalField):
    """Campo de latitud o longitud tolerante con la precisión que manda el GPS.

    El GPS del navegador y el del celular devuelven cosas como -12.046374158283195:
    muchos más dígitos de los que el modelo acepta (9 en total, 6 decimales), y el
    API respondía "Asegúrese de que no haya más de 9 dígitos en total". Redondeamos
    aquí en vez de exigirle al cliente que lo haga, porque son tres clientes y el
    error se repetiría en cada uno. Seis decimales son unos 11 cm: más precisión que
    eso no significa nada para ubicar un andamio.
    """

    def to_internal_value(self, data):
        if data not in (None, ""):
            try:
                data = Decimal(str(data)).quantize(Decimal("0.000001"))
            except (InvalidOperation, ValueError, TypeError):
                pass
        return super().to_internal_value(data)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "kind", "icon", "is_active")


class ReportActionSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.get_full_name", read_only=True)

    class Meta:
        model = ReportAction
        fields = ("id", "note", "new_status", "author_name", "created_at")
        read_only_fields = ("created_at", "author_name")


class ReportSerializer(serializers.ModelSerializer):
    reported_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name", read_only=True, default=None
    )
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    actions = ReportActionSerializer(many=True, read_only=True)
    resolution_hours = serializers.FloatField(read_only=True)

    class Meta:
        model = Report
        fields = (
            "id", "client_uuid", "kind", "category", "category_name", "area", "area_name",
            "description", "severity", "photo", "latitude", "longitude",
            "status", "assigned_to", "assigned_to_name", "closure_note",
            "reported_by", "reported_by_name", "occurred_at", "created_at", "closed_at",
            "resolution_hours", "form_variant", "synced_offline", "is_anonymous", "actions",
        )
        read_only_fields = (
            "reported_by", "created_at", "closed_at", "resolution_hours", "actions",
            "is_anonymous",
        )

    def _es_el_autor(self, report) -> bool:
        peticion = self.context.get("request")
        return bool(peticion and peticion.user.id == report.reported_by_id)

    def get_reported_by_name(self, report) -> str:
        """Oculta al autor de un reporte anónimo, salvo para él mismo.

        El anonimato tiene que valer también para el supervisor y el comité: si el jefe
        del área puede ver quién lo reportó, la opción no sirve para nada.
        """
        if report.is_anonymous and not self._es_el_autor(report):
            return "Anónimo"
        return report.reported_by.get_full_name() or report.reported_by.username

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        if instance.is_anonymous and not self._es_el_autor(instance):
            # El id del autor identifica igual que el nombre: también se va.
            datos["reported_by"] = None
            for accion, origen in zip(datos.get("actions", []), instance.actions.all(), strict=False):
                if origen.author_id == instance.reported_by_id:
                    accion["author_name"] = "Anónimo"
        return datos


class ReportCreateSerializer(serializers.ModelSerializer):
    """Entrada mínima: es lo único que el flujo rápido de 3-4 taps necesita mandar."""

    latitude = CoordenadaField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = CoordenadaField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )

    class Meta:
        model = Report
        fields = (
            "client_uuid", "kind", "category", "area", "description", "severity",
            "photo", "latitude", "longitude", "occurred_at", "form_variant",
            "synced_offline", "is_anonymous",
        )
        extra_kwargs = {
            "client_uuid": {"required": False},
            "description": {"required": False},
        }


class ReportAssignSerializer(serializers.Serializer):
    assigned_to = serializers.IntegerField()
    note = serializers.CharField(required=False, allow_blank=True)


class ReportCloseSerializer(serializers.Serializer):
    closure_note = serializers.CharField()


class ReportStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ReportStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True)
