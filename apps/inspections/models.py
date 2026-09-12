from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Frequency(models.TextChoices):
    SEMANAL = "SEMANAL", "Semanal"
    QUINCENAL = "QUINCENAL", "Quincenal"
    MENSUAL = "MENSUAL", "Mensual"
    TRIMESTRAL = "TRIMESTRAL", "Trimestral"

    @staticmethod
    def days(value: str) -> int:
        return {"SEMANAL": 7, "QUINCENAL": 15, "MENSUAL": 30, "TRIMESTRAL": 90}[value]


class InspectionStatus(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    REALIZADA = "REALIZADA", "Realizada"
    VENCIDA = "VENCIDA", "Vencida"


class InspectionSchedule(models.Model):
    """Programa de inspecciones: qué se inspecciona, cada cuánto y quién."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="inspection_schedules"
    )
    area = models.ForeignKey(
        "accounts.Area", on_delete=models.CASCADE, related_name="inspection_schedules"
    )
    title = models.CharField("título", max_length=200)
    checklist = models.JSONField("checklist", default=list, blank=True)
    frequency = models.CharField("frecuencia", max_length=12, choices=Frequency.choices)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "programa de inspección"
        verbose_name_plural = "programas de inspección"
        ordering = ("title",)

    def __str__(self) -> str:
        return f"{self.title} ({self.get_frequency_display()})"

    def generate_next(self) -> "Inspection":
        """Crea la siguiente inspección pendiente según la frecuencia."""
        last = self.inspections.order_by("-due_date").first()
        base = last.due_date if last else timezone.localdate()
        return Inspection.objects.create(
            schedule=self, due_date=base + timedelta(days=Frequency.days(self.frequency))
        )


class Inspection(models.Model):
    """Ocurrencia concreta de una inspección programada."""

    schedule = models.ForeignKey(
        InspectionSchedule, on_delete=models.CASCADE, related_name="inspections"
    )
    due_date = models.DateField("fecha programada")
    performed_at = models.DateTimeField("realizada el", null=True, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(
        "estado", max_length=12, choices=InspectionStatus.choices,
        default=InspectionStatus.PENDIENTE,
    )
    findings = models.TextField("hallazgos", blank=True)
    results = models.JSONField("resultados del checklist", default=dict, blank=True)

    class Meta:
        verbose_name = "inspección"
        verbose_name_plural = "inspecciones"
        ordering = ("-due_date",)

    def __str__(self) -> str:
        return f"{self.schedule.title} — {self.due_date}"

    @property
    def is_overdue(self) -> bool:
        return self.status == InspectionStatus.PENDIENTE and self.due_date < timezone.localdate()
