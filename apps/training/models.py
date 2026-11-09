"""Capacitación, inducción y simulacros: los registros de formación que exige la Ley N° 29783.

El artículo 35 obliga al empleador a capacitar al trabajador al contratarlo, durante el
desempeño de su labor y cuando cambian las tecnologías; el reglamento pide al menos cuatro
capacitaciones al año en el programa anual. El artículo 33 incluye entre los registros
obligatorios el de inducción, capacitación, entrenamiento y simulacros de emergencia.
"""
import calendar
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone

# Mínimo anual que fija el reglamento (D.S. N° 005-2012-TR, art. 27).
CAPACITACIONES_MINIMAS_POR_ANIO = 4


def sumar_meses(fecha: date, meses: int) -> date:
    """Suma meses de calendario; si el día no existe en el mes destino, toma el último."""
    total = fecha.month - 1 + meses
    anio, mes = fecha.year + total // 12, total % 12 + 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))


class TrainingStatus(models.TextChoices):
    PROGRAMADA = "PROGRAMADA", "Programada"
    REALIZADA = "REALIZADA", "Realizada"
    CANCELADA = "CANCELADA", "Cancelada"


class TrainingSession(models.Model):
    """Capacitación del programa anual: qué se dicta, cuándo, quién y para quién."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="training_sessions"
    )
    topic = models.CharField("tema", max_length=200)
    planned_date = models.DateField("fecha prevista")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="trainings_responsible",
    )
    # El capacitador puede ser externo (un bombero, una clínica): por eso es texto y no usuario.
    trainer = models.CharField("capacitador", max_length=150, blank=True)
    audience = models.CharField("público objetivo", max_length=200)
    area = models.ForeignKey(
        "accounts.Area", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="training_sessions",
    )
    duration_hours = models.DecimalField(
        "duración (horas)", max_digits=4, decimal_places=1, default=1
    )
    # Cuántos meses vale la capacitación antes de tener que repetirla.
    validity_months = models.PositiveSmallIntegerField("vigencia (meses)", default=12)
    status = models.CharField(
        "estado", max_length=12, choices=TrainingStatus.choices,
        default=TrainingStatus.PROGRAMADA,
    )
    held_on = models.DateField("realizada el", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "capacitación"
        verbose_name_plural = "capacitaciones"
        ordering = ("planned_date", "id")

    def __str__(self) -> str:
        return f"{self.topic} ({self.planned_date})"

    @property
    def expires_on(self):
        """Fecha hasta la que vale lo aprendido. Sin realizarse, no hay vigencia que contar."""
        if not self.held_on:
            return None
        return sumar_meses(self.held_on, self.validity_months)


class TrainingAttendance(models.Model):
    """Asistencia de un trabajador a una capacitación: reemplaza la hoja de firmas."""

    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name="attendances"
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="training_attendances"
    )
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+",
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "asistencia a capacitación"
        verbose_name_plural = "asistencias a capacitación"
        constraints = [
            models.UniqueConstraint(
                fields=("session", "worker"), name="attendance_unique_per_session"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.worker} en {self.session}"


class Induction(models.Model):
    """Inducción de un trabajador nuevo. Sin ella no debería empezar a trabajar."""

    worker = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="induction"
    )
    completed_on = models.DateField("realizada el", default=timezone.localdate)
    given_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    topics = models.TextField(
        "temas tratados", blank=True,
        help_text="Peligros del puesto, uso de EPP, rutas de evacuación, RISST.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "inducción"
        verbose_name_plural = "inducciones"
        ordering = ("-completed_on",)

    def __str__(self) -> str:
        return f"Inducción de {self.worker} ({self.completed_on})"


class DrillKind(models.TextChoices):
    SISMO = "SISMO", "Sismo"
    INCENDIO = "INCENDIO", "Incendio"
    DERRAME = "DERRAME", "Derrame de sustancias peligrosas"
    PRIMEROS_AUXILIOS = "PRIMEROS_AUXILIOS", "Primeros auxilios"
    EVACUACION = "EVACUACION", "Evacuación general"
    OTRO = "OTRO", "Otro"


class Drill(models.Model):
    """Simulacro de emergencia con sus resultados."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="drills"
    )
    kind = models.CharField("tipo", max_length=20, choices=DrillKind.choices)
    held_on = models.DateField("fecha")
    area = models.ForeignKey(
        "accounts.Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="drills"
    )
    participants = models.PositiveIntegerField("participantes")
    # En segundos para no perder precisión; la interfaz lo muestra en minutos y segundos.
    evacuation_seconds = models.PositiveIntegerField(
        "tiempo de evacuación (s)", null=True, blank=True
    )
    observations = models.TextField("observaciones", blank=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "simulacro"
        verbose_name_plural = "simulacros"
        ordering = ("-held_on", "-id")

    def __str__(self) -> str:
        return f"Simulacro de {self.get_kind_display().lower()} ({self.held_on})"
