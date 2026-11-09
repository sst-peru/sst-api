from django.contrib import admin

from .models import AnnualPlan, Document, DocumentVersion, PlanActivity


class VersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = ("number", "status", "approved_by", "valid_from", "valid_until")
    readonly_fields = ("number",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "kind", "requires_receipt")
    list_filter = ("kind",)
    inlines = (VersionInline,)


class ActivityInline(admin.TabularInline):
    model = PlanActivity
    extra = 0


@admin.register(AnnualPlan)
class AnnualPlanAdmin(admin.ModelAdmin):
    list_display = ("year", "company", "approved_on")
    inlines = (ActivityInline,)
