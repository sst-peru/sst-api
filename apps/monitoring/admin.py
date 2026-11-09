from django.contrib import admin

from .models import BackupLog, ClientError


@admin.register(ClientError)
class ClientErrorAdmin(admin.ModelAdmin):
    """Panel de errores de los clientes: se revisa por plataforma y versión."""

    list_display = ("created_at", "platform", "app_version", "message", "path", "company")
    list_filter = ("platform", "app_version", "company")
    search_fields = ("message", "path", "request_id")
    readonly_fields = [f.name for f in ClientError._meta.fields]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "ok", "file")
    list_filter = ("kind", "ok")
    readonly_fields = [f.name for f in BackupLog._meta.fields]

    def has_add_permission(self, request):
        return False
