from rest_framework import serializers

from apps.accounts.permissions import validar_de_la_empresa

from .models import RiskMap, RiskMarker, SafetySign


def _empresa(serializer):
    return serializer.context["request"].user.company_id


class RiskMarkerSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = RiskMarker
        fields = ("id", "kind", "kind_display", "label", "x", "y")


class RiskMapSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)
    published_by_name = serializers.SerializerMethodField()
    markers = RiskMarkerSerializer(many=True, read_only=True)
    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = RiskMap
        fields = (
            "id", "area", "area_name", "title", "plan", "published_at", "published_by",
            "published_by_name", "is_current", "markers",
        )
        read_only_fields = ("published_at", "published_by")

    def get_published_by_name(self, mapa) -> str | None:
        if mapa.published_by is None:
            return None
        return mapa.published_by.get_full_name() or mapa.published_by.username

    def validate_area(self, area):
        validar_de_la_empresa(area, _empresa(self), "area", "El área")
        return area


class SafetySignSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    area_name = serializers.CharField(source="area.name", read_only=True)
    is_observed = serializers.BooleanField(read_only=True)

    class Meta:
        model = SafetySign
        fields = (
            "id", "area", "area_name", "kind", "kind_display", "description", "location",
            "status", "status_display", "is_observed", "last_checked_on", "notes",
        )

    def validate_area(self, area):
        validar_de_la_empresa(area, _empresa(self), "area", "El área")
        return area
