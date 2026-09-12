import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportKind(models.TextChoices):
    ACTO = "ACTO", "Acto inseguro (lo que hace la persona)"
    CONDICION = "CONDICION", "Condición insegura (lo que hay en el ambiente)"


class Severity(models.TextChoices):
    BAJA = "BAJA", "Baja"
    MEDIA = "MEDIA", "Media"
    ALTA = "ALTA", "Alta"
    CRITICA = "CRITICA", "Crítica"


class ReportStatus(models.TextChoices):
    ABIERTO = "ABIERTO", "Abierto"
    EN_PROCESO = "EN_PROCESO", "En proceso"
    CERRADO = "CERRADO", "Cerrado"
    DESCARTADO = "DESCARTADO", "Descartado"


class Category(models.Model):
    """Categorías de peligro configurables por empresa (caída, eléctrico, orden y limpieza...)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("aplica a", max_length=12, choices=ReportKind.choices)
    icon = models.CharField("icono", max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Report(models.Model):
    """Reporte de un acto o condición insegura, creado desde móvil o web."""

    # Lo genera el cliente móvil antes de enviar: permite reintentar la sincronización
    # offline sin crear duplicados.
    client_uuid = models.UUIDField("uuid del cliente", default=uuid.uuid4, unique=True)

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="reports"
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports_created"
    )
    kind = models.CharField("tipo", max_length=12, choices=ReportKind.choices)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    area = models.ForeignKey(
        "accounts.Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    description = models.TextField("descripción", blank=True)
    severity = models.CharField(
        "severidad", max_length=10, choices=Severity.choices, default=Severity.MEDIA
    )
    photo = models.ImageField("foto", upload_to="reports/%Y/%m/", null=True, blank=True)
    latitude = models.DecimalField(
        "latitud", max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        "longitud", max_digits=9, decimal_places=6, null=True, blank=True
    )

    status = models.CharField(
        "estado", max_length=12, choices=ReportStatus.choices, default=ReportStatus.ABIERTO
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_assigned",
    )
    closure_note = models.TextField("acción correctiva aplicada", blank=True)

    # occurred_at lo manda el cliente: en offline puede ser días antes del created_at.
    occurred_at = models.DateTimeField("ocurrió el", default=timezone.now)
    created_at = models.DateTimeField("registrado el", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_at = models.DateTimeField("asignado el", null=True, blank=True)
    closed_at = models.DateTimeField("cerrado el", null=True, blank=True)

    # Variante del formulario con que se creó: insumo del experimento A/B.
    form_variant = models.CharField("variante de formulario", max_length=20, blank=True)
    synced_offline = models.BooleanField("llegó por sincronización offline", default=False)

    class Meta:
        verbose_name = "reporte"
        verbose_name_plural = "reportes"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("company", "status")),
            models.Index(fields=("company", "-created_at")),
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.get_kind_display()} — {self.get_status_display()}"

    @property
    def resolution_hours(self) -> float | None:
        """Horas entre el reporte y su cierre. Insumo del MTTR."""
        if not self.closed_at:
            return None
        return (self.closed_at - self.created_at).total_seconds() / 3600

    @property
    def is_open(self) -> bool:
        return self.status in {ReportStatus.ABIERTO, ReportStatus.EN_PROCESO}

    def close(self, *, note: str = "") -> None:
        self.status = ReportStatus.CERRADO
        self.closure_note = note
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closure_note", "closed_at", "updated_at"])


class ReportAction(models.Model):
    """Bitácora del hallazgo: quién hizo qué y cuándo. Es la evidencia ante SUNAFIL."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="actions")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="report_actions"
    )
    note = models.TextField("comentario")
    new_status = models.CharField(
        "estado resultante", max_length=12, choices=ReportStatus.choices, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acción del reporte"
        verbose_name_plural = "acciones del reporte"
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{self.report_id} — {self.author}"
