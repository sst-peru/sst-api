from rest_framework import serializers

from .models import Category, Report, ReportAction, ReportStatus


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
    reported_by_name = serializers.CharField(source="reported_by.get_full_name", read_only=True)
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
            "resolution_hours", "form_variant", "synced_offline", "actions",
        )
        read_only_fields = (
            "reported_by", "created_at", "closed_at", "resolution_hours", "actions",
        )


class ReportCreateSerializer(serializers.ModelSerializer):
    """Entrada mínima: es lo único que el flujo rápido de 3-4 taps necesita mandar."""

    class Meta:
        model = Report
        fields = (
            "client_uuid", "kind", "category", "area", "description", "severity",
            "photo", "latitude", "longitude", "occurred_at", "form_variant",
            "synced_offline",
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
