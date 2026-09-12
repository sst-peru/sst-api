from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Area, Company, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "ruc", "worker_count", "requires_committee")
    search_fields = ("name", "ruc")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_active")
    list_filter = ("company", "is_active")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "get_full_name", "role", "company", "area")
    list_filter = ("role", "company")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("SST", {"fields": ("company", "area", "role", "dni", "phone")}),
    )
