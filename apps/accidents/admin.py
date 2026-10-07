from django.contrib import admin

from .models import Accident, CorrectiveMeasure, Investigation, OccupationalDisease


class MeasureInline(admin.TabularInline):
    model = CorrectiveMeasure
    extra = 0


@admin.register(Accident)
class AccidentAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "kind", "severity", "status", "company", "notice_overdue")
    list_filter = ("kind", "severity", "status", "company")
    search_fields = ("description", "injured_name", "place")
    inlines = (MeasureInline,)


@admin.register(Investigation)
class InvestigationAdmin(admin.ModelAdmin):
    list_display = ("accident", "method", "performed_by", "performed_at")


@admin.register(OccupationalDisease)
class OccupationalDiseaseAdmin(admin.ModelAdmin):
    list_display = ("diagnosed_on", "diagnosis", "status", "company")
    list_filter = ("status", "company")
