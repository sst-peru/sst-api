"""Registro de los correos que envía el sistema (TS19).

Cada envío queda con su estado: si el proveedor lo rechazó, el error se guarda para revisarlo,
en vez de perderse en la consola del servidor.
"""
from django.db import models


class EmailStatus(models.TextChoices):
    ENVIADO = "ENVIADO", "Enviado"
    FALLIDO = "FALLIDO", "Falló"


class EmailLog(models.Model):
    kind = models.CharField("tipo", max_length=40)
    to = models.EmailField("destinatario")
    subject = models.CharField("asunto", max_length=200)
    status = models.CharField("estado", max_length=10, choices=EmailStatus.choices)
    error = models.TextField("error", blank=True)
    created_at = models.DateTimeField("enviado el", auto_now_add=True)

    class Meta:
        verbose_name = "correo enviado"
        verbose_name_plural = "correos enviados"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.kind} → {self.to} ({self.get_status_display()})"
