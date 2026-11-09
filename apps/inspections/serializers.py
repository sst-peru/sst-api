from rest_framework import serializers

from apps.reports.models import Severity

from .models import Inspection, InspectionSchedule


class InspectionSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="schedule.title", read_only=True)
    area_name = serializers.CharField(source="schedule.area.name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    generated_reports = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Inspection
        fields = (
            "id", "schedule", "title", "area_name", "due_date", "performed_at",
            "performed_by", "status", "findings", "results", "is_overdue",
            "generated_reports",
        )
        read_only_fields = ("performed_by",)


class GenerateReportSerializer(serializers.Serializer):
    """Observación de la inspección que se convierte en hallazgo."""

    item = serializers.CharField(
        max_length=200, required=False, allow_blank=True,
        help_text="Ítem del checklist observado, si lo hay.",
    )
    description = serializers.CharField()
    severity = serializers.ChoiceField(choices=Severity.choices, default=Severity.MEDIA)


class InspectionScheduleSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = InspectionSchedule
        fields = (
            "id", "title", "area", "area_name", "checklist", "frequency",
            "responsible", "is_active",
        )
