from django.contrib import admin

from .models import Inspection, InspectionSchedule


@admin.register(InspectionSchedule)
class InspectionScheduleAdmin(admin.ModelAdmin):
    list_display = ("title", "area", "frequency", "responsible", "is_active")
    list_filter = ("company", "frequency", "is_active")


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("schedule", "due_date", "status", "performed_at")
    list_filter = ("status", "schedule__company")
