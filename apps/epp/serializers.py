from rest_framework import serializers

from .models import EppDelivery, EppItem


class EppItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = EppItem
        fields = ("id", "name", "description", "lifespan_days", "stock", "is_active")


class EppDeliverySerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)
    worker_name = serializers.CharField(source="worker.get_full_name", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = EppDelivery
        fields = (
            "id", "item", "item_name", "worker", "worker_name", "delivered_by",
            "quantity", "delivered_at", "expires_at", "acknowledged", "notes", "is_expired",
        )
        read_only_fields = ("delivered_by", "expires_at")
