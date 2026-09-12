from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class EppItem(models.Model):
    """Catálogo de EPP de la empresa (casco, guantes, arnés...)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="epp_items"
    )
    name = models.CharField("nombre", max_length=150)
    description = models.CharField("descripción", max_length=255, blank=True)
    # Vida útil en días: con esto el sistema avisa cuándo toca reponer.
    lifespan_days = models.PositiveIntegerField("vida útil (días)", default=180)
    stock = models.PositiveIntegerField("stock", default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "EPP"
        verbose_name_plural = "EPP"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class EppDelivery(models.Model):
    """Entrega de EPP a un trabajador. Es registro obligatorio de la Ley 29783."""

    item = models.ForeignKey(EppItem, on_delete=models.PROTECT, related_name="deliveries")
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="epp_deliveries"
    )
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="epp_handed_over"
    )
    quantity = models.PositiveIntegerField("cantidad", default=1)
    delivered_at = models.DateTimeField("entregado el", default=timezone.now)
    expires_at = models.DateField("vence el", null=True, blank=True)
    acknowledged = models.BooleanField("conforme del trabajador", default=False)
    notes = models.CharField("observaciones", max_length=255, blank=True)

    class Meta:
        verbose_name = "entrega de EPP"
        verbose_name_plural = "entregas de EPP"
        ordering = ("-delivered_at",)

    def __str__(self) -> str:
        return f"{self.item.name} → {self.worker}"

    def save(self, *args, **kwargs):
        if not self.expires_at and self.item_id:
            self.expires_at = (
                self.delivered_at + timedelta(days=self.item.lifespan_days)
            ).date()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.localdate())
