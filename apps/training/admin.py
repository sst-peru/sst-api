from django.contrib import admin

from .models import Drill, Induction, TrainingAttendance, TrainingSession


class AttendanceInline(admin.TabularInline):
    model = TrainingAttendance
    extra = 0


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ("topic", "company", "planned_date", "status", "held_on")
    list_filter = ("company", "status")
    inlines = (AttendanceInline,)


@admin.register(Induction)
class InductionAdmin(admin.ModelAdmin):
    list_display = ("worker", "completed_on", "given_by")


@admin.register(Drill)
class DrillAdmin(admin.ModelAdmin):
    list_display = ("kind", "company", "held_on", "participants", "evacuation_seconds")
    list_filter = ("company", "kind")
