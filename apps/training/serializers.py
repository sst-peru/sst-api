from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.permissions import validar_de_la_empresa

from .models import Drill, Induction, TrainingAttendance, TrainingSession

User = get_user_model()


def _empresa(serializer):
    return serializer.context["request"].user.company_id


def _nombre(usuario) -> str | None:
    if usuario is None:
        return None
    return usuario.get_full_name() or usuario.username


class TrainingSessionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    responsible_name = serializers.SerializerMethodField()
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)
    expires_on = serializers.DateField(read_only=True)
    attendance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TrainingSession
        fields = (
            "id", "topic", "planned_date", "responsible", "responsible_name", "trainer",
            "audience", "area", "area_name", "duration_hours", "validity_months",
            "status", "status_display", "held_on", "expires_on", "attendance_count",
        )
        read_only_fields = ("status", "held_on")

    def get_responsible_name(self, sesion) -> str | None:
        return _nombre(sesion.responsible)

    def validate(self, attrs):
        empresa = _empresa(self)
        validar_de_la_empresa(attrs.get("area"), empresa, "area", "El área")
        validar_de_la_empresa(attrs.get("responsible"), empresa, "responsible", "El responsable")
        return attrs


class TrainingAttendanceSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()

    class Meta:
        model = TrainingAttendance
        fields = ("id", "session", "worker", "worker_name", "registered_at")

    def get_worker_name(self, asistencia) -> str | None:
        return _nombre(asistencia.worker)


class AttendanceInputSerializer(serializers.Serializer):
    """Lista de asistentes que marca el capacitador al terminar la sesión."""

    workers = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    held_on = serializers.DateField(required=False)


class InductionSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    given_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Induction
        fields = (
            "id", "worker", "worker_name", "completed_on", "given_by", "given_by_name",
            "topics",
        )
        read_only_fields = ("given_by",)

    def get_worker_name(self, induccion) -> str | None:
        return _nombre(induccion.worker)

    def get_given_by_name(self, induccion) -> str | None:
        return _nombre(induccion.given_by)

    def validate_worker(self, trabajador):
        validar_de_la_empresa(trabajador, _empresa(self), "worker", "El trabajador")
        return trabajador


class DrillSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True, default=None)

    class Meta:
        model = Drill
        fields = (
            "id", "kind", "kind_display", "held_on", "area", "area_name", "participants",
            "evacuation_seconds", "observations",
        )

    def validate(self, attrs):
        validar_de_la_empresa(attrs.get("area"), _empresa(self), "area", "El área")
        return attrs
