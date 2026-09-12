from rest_framework import serializers

from .models import Inspection, InspectionSchedule


class InspectionSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="schedule.title", read_only=True)
    area_name = serializers.CharField(source="schedule.area.name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Inspection
        fields = (
            "id", "schedule", "title", "area_name", "due_date", "performed_at",
            "performed_by", "status", "findings", "results", "is_overdue",
        )
        read_only_fields = ("performed_by",)


class InspectionScheduleSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = InspectionSchedule
        fields = (
            "id", "title", "area", "area_name", "checklist", "frequency",
            "responsible", "is_active",
        )
