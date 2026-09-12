from rest_framework import serializers

from .models import IpercEntry, IpercMatrix


class IpercEntrySerializer(serializers.ModelSerializer):
    risk_score = serializers.IntegerField(read_only=True)
    risk_level = serializers.CharField(read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)

    class Meta:
        model = IpercEntry
        fields = (
            "id", "matrix", "area", "area_name", "job_position", "hazard", "risk",
            "probability", "consequence", "risk_score", "risk_level",
            "existing_controls", "proposed_controls", "responsible", "source_report",
            "updated_at",
        )


class IpercMatrixSerializer(serializers.ModelSerializer):
    entries = IpercEntrySerializer(many=True, read_only=True)
    entry_count = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = IpercMatrix
        fields = (
            "id", "version", "status", "valid_from", "approved_by",
            "created_at", "entry_count", "entries",
        )
        read_only_fields = ("version", "created_at")
