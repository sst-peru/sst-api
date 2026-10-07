"""Serializers del registro de accidentes, su investigación y sus medidas correctivas.

Las validaciones de este módulo son casi todas de coherencia legal, no de formato: un
incidente peligroso no puede ser mortal porque por definición no hubo lesionado, y un
accidente con días perdidos no puede estar clasificado como leve.
"""
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Accident,
    AccidentKind,
    AccidentSeverity,
    CorrectiveMeasure,
    Investigation,
    OccupationalDisease,
)


def _validar_de_la_empresa(instancia, empresa_id, campo, etiqueta):
    """Impide referenciar un objeto de otra empresa aunque se conozca su id."""
    if instancia is not None and getattr(instancia, "company_id", None) != empresa_id:
        raise serializers.ValidationError({campo: "%s no pertenece a tu empresa." % etiqueta})


class CorrectiveMeasureSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(source="responsible.get_full_name", read_only=True)
    control_kind_display = serializers.CharField(source="get_control_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = CorrectiveMeasure
        fields = (
            "id", "accident", "description", "control_kind", "control_kind_display",
            "responsible", "responsible_name", "due_date", "status", "status_display",
            "completed_at", "verified_by", "verified_at", "overdue", "created_at",
        )
        read_only_fields = ("completed_at", "verified_by", "verified_at", "created_at")
        extra_kwargs = {
            "description": {
                "error_messages": {
                    "required": "Describe la medida correctiva.",
                    "blank": "Describe la medida correctiva.",
                }
            },
            "due_date": {
                "error_messages": {
                    "required": "Toda medida correctiva necesita un plazo: sin fecha no se puede verificar.",
                    "invalid": "El plazo debe ser una fecha con formato AAAA-MM-DD.",
                }
            },
            "responsible": {
                "error_messages": {
                    "required": "Asigna un responsable: una medida sin dueño no se cumple.",
                    "does_not_exist": "Ese responsable no existe.",
                }
            },
        }

    def validate(self, attrs):
        empresa_id = self.context["request"].user.company_id
        accidente = attrs.get("accident") or getattr(self.instance, "accident", None)
        _validar_de_la_empresa(accidente, empresa_id, "accident", "El accidente")
        _validar_de_la_empresa(
            attrs.get("responsible"), empresa_id, "responsible", "El responsable"
        )

        plazo = attrs.get("due_date") or getattr(self.instance, "due_date", None)
        if accidente is not None and plazo and plazo < accidente.occurred_at.date():
            raise serializers.ValidationError(
                {"due_date": "El plazo no puede ser anterior a la fecha del accidente."}
            )
        return attrs


class InvestigationSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.CharField(source="performed_by.get_full_name", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Investigation
        fields = (
            "id", "accident", "method", "method_display", "immediate_causes", "basic_causes",
            "root_cause", "conclusions", "participants", "performed_by", "performed_by_name",
            "performed_at", "created_at",
        )
        read_only_fields = ("accident", "performed_by", "created_at")
        extra_kwargs = {
            "root_cause": {
                "error_messages": {
                    "required": (
                        "La causa raíz es obligatoria: quedarse en la causa inmediata es la "
                        "observación más frecuente de una fiscalización."
                    ),
                    "blank": (
                        "La causa raíz es obligatoria: quedarse en la causa inmediata es la "
                        "observación más frecuente de una fiscalización."
                    ),
                }
            },
        }

    def validate_performed_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("La investigación no puede tener fecha futura.")
        return value


class AccidentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    reported_by_name = serializers.CharField(source="reported_by.get_full_name", read_only=True)
    injured_label = serializers.CharField(read_only=True)

    # Control del plazo del artículo 82: lo consume la alerta del panel.
    requires_immediate_notice = serializers.BooleanField(read_only=True)
    notice_deadline = serializers.DateTimeField(read_only=True)
    notice_hours_left = serializers.FloatField(read_only=True)
    notice_overdue = serializers.BooleanField(read_only=True)
    notified_late = serializers.BooleanField(read_only=True)

    investigation = InvestigationSerializer(read_only=True)
    measures = CorrectiveMeasureSerializer(many=True, read_only=True)

    class Meta:
        model = Accident
        fields = (
            "id", "client_uuid", "kind", "kind_display", "severity", "severity_display",
            "status", "status_display", "area", "area_name", "place", "description",
            "injury_description", "immediate_actions", "injured_person", "injured_name",
            "injured_dni", "injured_label", "lost_days", "origin_report",
            "reported_by", "reported_by_name", "occurred_at", "created_at", "closed_at",
            "mtpe_notified_at", "mtpe_notice_code", "requires_immediate_notice",
            "notice_deadline", "notice_hours_left", "notice_overdue", "notified_late",
            "investigation", "measures",
        )
        read_only_fields = (
            "status", "reported_by", "created_at", "closed_at",
            "mtpe_notified_at", "mtpe_notice_code",
        )


class AccidentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Accident
        fields = (
            "id", "client_uuid", "kind", "severity", "area", "place", "description",
            "injury_description", "immediate_actions", "injured_person", "injured_name",
            "injured_dni", "lost_days", "origin_report", "occurred_at",
        )
        extra_kwargs = {
            "description": {
                "error_messages": {
                    "required": "Describe qué ocurrió.",
                    "blank": "Describe qué ocurrió.",
                }
            },
            "occurred_at": {
                "error_messages": {
                    "required": "Indica cuándo ocurrió: de esa fecha depende el plazo legal de aviso.",
                    "invalid": "La fecha de ocurrencia no tiene un formato válido.",
                }
            },
        }

    def validate_occurred_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError(
                "La fecha de ocurrencia no puede estar en el futuro."
            )
        return value

    def validate_injured_dni(self, value):
        if value and (not value.isdigit() or len(value) != 8):
            raise serializers.ValidationError("El DNI debe tener exactamente 8 dígitos.")
        return value

    def validate(self, attrs):
        empresa_id = self.context["request"].user.company_id
        _validar_de_la_empresa(attrs.get("area"), empresa_id, "area", "El área")
        _validar_de_la_empresa(
            attrs.get("origin_report"), empresa_id, "origin_report", "El hallazgo"
        )
        persona = attrs.get("injured_person")
        if persona is not None and persona.company_id != empresa_id:
            raise serializers.ValidationError(
                {"injured_person": "El trabajador accidentado no pertenece a tu empresa."}
            )

        tipo = attrs.get("kind")
        gravedad = attrs.get("severity", AccidentSeverity.LEVE)
        dias = attrs.get("lost_days", 0)

        # Un incidente peligroso es, por definición del D.S. 005-2012-TR, el suceso que
        # pudo causar lesiones y no las causó. Clasificarlo como mortal es contradictorio.
        if tipo == AccidentKind.INCIDENTE_PELIGROSO and gravedad == AccidentSeverity.MORTAL:
            raise serializers.ValidationError(
                {
                    "severity": (
                        "Un incidente peligroso no puede ser mortal: si hubo un fallecido, "
                        "regístralo como accidente de trabajo."
                    )
                }
            )

        # Un accidente de trabajo supone un accidentado identificable; el aviso al MTPE y el
        # expediente de la investigación lo exigen.
        if tipo == AccidentKind.ACCIDENTE and not (persona or attrs.get("injured_name")):
            raise serializers.ValidationError(
                {
                    "injured_name": (
                        "Indica quién se accidentó: elige al trabajador o escribe su nombre "
                        "si no tiene cuenta en el sistema."
                    )
                }
            )

        if dias > 0 and gravedad == AccidentSeverity.LEVE:
            raise serializers.ValidationError(
                {
                    "severity": (
                        "Con días perdidos el accidente es incapacitante o mortal, no leve: "
                        "de esta clasificación salen los índices de accidentabilidad."
                    )
                }
            )
        return attrs


class AccidentNoticeSerializer(serializers.Serializer):
    """Registro del aviso al Ministerio de Trabajo."""

    notified_at = serializers.DateTimeField(
        required=False,
        help_text="Momento del aviso. Si se omite, se toma el instante actual.",
    )
    notice_code = serializers.CharField(
        max_length=80, required=False, allow_blank=True,
        help_text="Número de cargo o constancia que devuelve el MTPE.",
    )

    def validate_notified_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("El aviso no puede tener fecha futura.")
        return value


class OccupationalDiseaseSerializer(serializers.ModelSerializer):
    worker_label = serializers.CharField(read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = OccupationalDisease
        fields = (
            "id", "worker", "worker_name", "worker_label", "area", "area_name", "diagnosis",
            "cie10_code", "causal_agent", "exposure_months", "diagnosed_on", "status",
            "status_display", "rest_days", "notes", "reported_by", "created_at",
        )
        read_only_fields = ("reported_by", "created_at")
        extra_kwargs = {
            "diagnosis": {
                "error_messages": {
                    "required": "Escribe el diagnóstico.",
                    "blank": "Escribe el diagnóstico.",
                }
            },
            "diagnosed_on": {
                "error_messages": {
                    "required": "Indica la fecha del diagnóstico.",
                    "invalid": "La fecha del diagnóstico debe tener formato AAAA-MM-DD.",
                }
            },
        }

    def validate_diagnosed_on(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError(
                "La fecha del diagnóstico no puede estar en el futuro."
            )
        return value

    def validate(self, attrs):
        empresa_id = self.context["request"].user.company_id
        _validar_de_la_empresa(attrs.get("area"), empresa_id, "area", "El área")
        trabajador = attrs.get("worker")
        if trabajador is not None and trabajador.company_id != empresa_id:
            raise serializers.ValidationError(
                {"worker": "El trabajador no pertenece a tu empresa."}
            )
        if not (trabajador or attrs.get("worker_name") or getattr(self.instance, "worker_id", None)):
            raise serializers.ValidationError(
                {"worker_name": "Indica de qué trabajador es el diagnóstico."}
            )
        return attrs
