"""Documentos del Sistema de Gestión de SST y plan anual.

La Ley N° 29783 obliga a tener por escrito la política de SST (art. 22), el Reglamento Interno
de SST con su entrega a cada trabajador (art. 34) y el plan y programa anual de SST (art. 32 del
reglamento). Los documentos se versionan: la versión vigente no se edita, se publica una nueva y
la anterior queda como histórica, que es lo que un auditor pide revisar.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone


class DocumentKind(models.TextChoices):
    POLITICA = "POLITICA", "Política de SST"
    RISST = "RISST", "Reglamento Interno de SST"
    PROCEDIMIENTO = "PROCEDIMIENTO", "Procedimiento"
    PROGRAMA = "PROGRAMA", "Programa"
    OTRO = "OTRO", "Otro documento"


class Document(models.Model):
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="sgsst_documents"
    )
    kind = models.CharField("tipo", max_length=16, choices=DocumentKind.choices)
    title = models.CharField("título", max_length=200)
    code = models.CharField("código", max_length=40, blank=True)
    # Si el trabajador debe confirmar que lo recibió (el RISST lo exige por ley).
    requires_receipt = models.BooleanField("exige constancia de recepción", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "documento del SGSST"
        verbose_name_plural = "documentos del SGSST"
        ordering = ("kind", "title")

    def __str__(self) -> str:
        return self.title

    @property
    def current_version(self):
        return self.versions.filter(status=VersionStatus.VIGENTE).first()


class VersionStatus(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    VIGENTE = "VIGENTE", "Vigente"
    HISTORICA = "HISTORICA", "Histórica"


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField("versión", editable=False)
    content = models.TextField("contenido", blank=True)
    file = models.FileField("archivo firmado", upload_to="sgsst_docs/%Y/%m/", blank=True)
    approved_by = models.CharField(
        "aprobado por", max_length=150, blank=True,
        help_text="Cargo y nombre de quien firma: la política la aprueba la alta dirección.",
    )
    approved_on = models.DateField("fecha de aprobación", null=True, blank=True)
    change_summary = models.CharField("cambios respecto a la anterior", max_length=255, blank=True)
    status = models.CharField(
        "estado", max_length=10, choices=VersionStatus.choices, default=VersionStatus.BORRADOR
    )
    valid_from = models.DateField("vigente desde", null=True, blank=True)
    valid_until = models.DateField("vigente hasta", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "versión de documento"
        verbose_name_plural = "versiones de documento"
        ordering = ("-number",)
        constraints = [
            models.UniqueConstraint(
                fields=("document", "number"), name="document_version_unique_number"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document.title} v{self.number}"

    def save(self, *args, **kwargs):
        if self.number is None:
            ultimo = self.document.versions.aggregate(models.Max("number"))["number__max"]
            self.number = (ultimo or 0) + 1
        super().save(*args, **kwargs)

    def publish(self):
        """Deja esta versión vigente y pasa la anterior a histórica."""
        hoy = timezone.localdate()
        with transaction.atomic():
            self.document.versions.filter(status=VersionStatus.VIGENTE).exclude(
                pk=self.pk
            ).update(status=VersionStatus.HISTORICA, valid_until=hoy)
            self.status = VersionStatus.VIGENTE
            self.valid_from = hoy
            self.valid_until = None
            self.save(update_fields=["status", "valid_from", "valid_until"])


class DocumentReceipt(models.Model):
    """Constancia de que un trabajador recibió una versión concreta del documento."""

    version = models.ForeignKey(
        DocumentVersion, on_delete=models.CASCADE, related_name="receipts"
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_receipts"
    )
    received_at = models.DateTimeField("recibido el", auto_now_add=True)

    class Meta:
        verbose_name = "constancia de recepción"
        verbose_name_plural = "constancias de recepción"
        constraints = [
            models.UniqueConstraint(fields=("version", "worker"), name="receipt_unique_per_version"),
        ]

    def __str__(self) -> str:
        return f"{self.worker} recibió {self.version}"


class AnnualPlan(models.Model):
    """Plan anual de SST: objetivos del año y las actividades con que se cumplen."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="sst_plans"
    )
    year = models.PositiveSmallIntegerField("año")
    objectives = models.TextField("objetivos")
    approved_on = models.DateField("aprobado el", null=True, blank=True)

    class Meta:
        verbose_name = "plan anual de SST"
        verbose_name_plural = "planes anuales de SST"
        ordering = ("-year",)
        constraints = [
            models.UniqueConstraint(fields=("company", "year"), name="plan_unique_per_year"),
        ]

    def __str__(self) -> str:
        return f"Plan anual de SST {self.year}"


class ActivityStatus(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    EJECUTADA = "EJECUTADA", "Ejecutada"
    REPROGRAMADA = "REPROGRAMADA", "Reprogramada"


class PlanActivity(models.Model):
    plan = models.ForeignKey(AnnualPlan, on_delete=models.CASCADE, related_name="activities")
    objective = models.CharField("objetivo al que aporta", max_length=200, blank=True)
    description = models.CharField("actividad", max_length=255)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    planned_month = models.PositiveSmallIntegerField(
        "mes programado", validators=[MinValueValidator(1), MaxValueValidator(12)]
    )
    status = models.CharField(
        "estado", max_length=12, choices=ActivityStatus.choices, default=ActivityStatus.PENDIENTE
    )
    executed_on = models.DateField("ejecutada el", null=True, blank=True)
    evidence = models.CharField("evidencia", max_length=255, blank=True)

    class Meta:
        verbose_name = "actividad del plan"
        verbose_name_plural = "actividades del plan"
        ordering = ("planned_month", "id")

    def __str__(self) -> str:
        return self.description
