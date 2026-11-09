from django.contrib import admin

from .models import RiskMap, RiskMarker, SafetySign


class MarkerInline(admin.TabularInline):
    model = RiskMarker
    extra = 0


@admin.register(RiskMap)
class RiskMapAdmin(admin.ModelAdmin):
    list_display = ("title", "area", "published_at")
    inlines = (MarkerInline,)


@admin.register(SafetySign)
class SafetySignAdmin(admin.ModelAdmin):
    list_display = ("description", "area", "kind", "status", "last_checked_on")
    list_filter = ("kind", "status")
