from django.contrib import admin

from .models import Category, Report, ReportAction


class ReportActionInline(admin.TabularInline):
    model = ReportAction
    extra = 0


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "severity", "status", "area", "reported_by", "created_at")
    list_filter = ("kind", "status", "severity", "company", "form_variant")
    search_fields = ("description",)
    date_hierarchy = "created_at"
    inlines = (ReportActionInline,)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "company", "is_active")
    list_filter = ("company", "kind", "is_active")
