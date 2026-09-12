from django.contrib import admin

from .models import EppDelivery, EppItem


@admin.register(EppItem)
class EppItemAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "lifespan_days", "stock", "is_active")
    list_filter = ("company", "is_active")


@admin.register(EppDelivery)
class EppDeliveryAdmin(admin.ModelAdmin):
    list_display = ("item", "worker", "delivered_at", "expires_at", "acknowledged")
    list_filter = ("item__company", "acknowledged")
