"""Errores no controlados que reportan la web y la app móvil (TS24).

Se guarda lo necesario para diagnosticar —mensaje, traza, versión, plataforma y ruta— y nada
del contenido que el usuario estaba registrando: un reporte de acto inseguro puede nombrar a un
compañero, y eso no tiene por qué terminar en un panel de errores.
"""
from django.conf import settings
from django.db import models


class Platform(models.TextChoices):
    WEB = "WEB", "Web"
    ANDROID = "ANDROID", "Android"


class ClientError(models.Model):
    platform = models.CharField("plataforma", max_length=10, choices=Platform.choices)
    app_version = models.CharField("versión", max_length=40, blank=True)
    message = models.CharField("mensaje", max_length=500)
    stack = models.TextField("traza", blank=True)
    # Solo la ruta, sin la cadena de consulta: ahí suelen viajar filtros con datos.
    path = models.CharField("ruta", max_length=255, blank=True)
    user_agent = models.CharField("navegador o dispositivo", max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    request_id = models.CharField("identificador de correlación", max_length=64, blank=True)
    created_at = models.DateTimeField("registrado el", auto_now_add=True)

    class Meta:
        verbose_name = "error de cliente"
        verbose_name_plural = "errores de clientes"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("platform", "-created_at"))]

    def __str__(self) -> str:
        return f"[{self.platform} {self.app_version}] {self.message[:80]}"
