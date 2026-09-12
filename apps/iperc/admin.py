from django.contrib import admin

from .models import IpercEntry, IpercMatrix


class IpercEntryInline(admin.TabularInline):
    model = IpercEntry
    extra = 0


@admin.register(IpercMatrix)
class IpercMatrixAdmin(admin.ModelAdmin):
    list_display = ("version", "company", "status", "valid_from")
    list_filter = ("company", "status")
    inlines = (IpercEntryInline,)


@admin.register(IpercEntry)
class IpercEntryAdmin(admin.ModelAdmin):
    list_display = ("job_position", "hazard", "area", "risk_level")
    list_filter = ("matrix", "area")
    search_fields = ("hazard", "risk", "job_position")
