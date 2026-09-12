from django.contrib import admin

from .models import Assignment, Experiment


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "is_active", "started_at", "ended_at")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("experiment", "user", "variant", "assigned_at")
    list_filter = ("experiment", "variant")
