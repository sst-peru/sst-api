"""Mapa de riesgos y señalización de seguridad.

El artículo 35 de la Ley N° 29783 obliga al empleador a elaborar un mapa de riesgos y
exhibirlo en un lugar visible. La señalización de seguridad sigue la NTP 399.010-1: cada área
debe tener las señales que corresponden a sus peligros, y una señal deteriorada o ausente es
una observación típica de la fiscalización.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class RiskKind(models.TextChoices):
    MECANICO = "MECANICO", "Mecánico"
    ELECTRICO = "ELECTRICO", "Eléctrico"
    CAIDA = "CAIDA", "Caída de altura o a nivel"
    QUIMICO = "QUIMICO", "Químico"
    FISICO = "FISICO", "Físico (ruido, temperatura, radiación)"
    BIOLOGICO = "BIOLOGICO", "Biológico"
    ERGONOMICO = "ERGONOMICO", "Ergonómico"
    INCENDIO = "INCENDIO", "Incendio o explosión"
    LOCATIVO = "LOCATIVO", "Locativo"


class RiskMap(models.Model):
    """Plano de un área con sus riesgos ubicados. El más reciente de cada área es el vigente."""

    area = models.ForeignKey(
        "accounts.Area", on_delete=models.CASCADE, related_name="risk_maps"
    )
    title = models.CharField("título", max_length=200)
    plan = models.ImageField("plano", upload_to="risk_maps/%Y/%m/")
    published_at = models.DateTimeField("publicado el", auto_now_add=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )

    class Meta:
        verbose_name = "mapa de riesgos"
        verbose_name_plural = "mapas de riesgos"
        ordering = ("-published_at", "-id")

    def __str__(self) -> str:
        return f"{self.title} ({self.area.name})"

    @property
    def company_id(self):
        return self.area.company_id

    @property
    def is_current(self) -> bool:
        ultimo = self.area.risk_maps.order_by("-published_at", "-id").first()
        return ultimo is not None and ultimo.pk == self.pk


class RiskMarker(models.Model):
    """Riesgo señalado sobre el plano. La posición va en porcentaje para no depender del tamaño."""

    risk_map = models.ForeignKey(RiskMap, on_delete=models.CASCADE, related_name="markers")
    kind = models.CharField("tipo de riesgo", max_length=12, choices=RiskKind.choices)
    label = models.CharField("descripción", max_length=200)
    x = models.DecimalField(
        "posición horizontal (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    y = models.DecimalField(
        "posición vertical (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = "riesgo en el mapa"
        verbose_name_plural = "riesgos en el mapa"
        ordering = ("id",)

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.label}"


class SignKind(models.TextChoices):
    PROHIBICION = "PROHIBICION", "Prohibición"
    OBLIGACION = "OBLIGACION", "Obligación"
    ADVERTENCIA = "ADVERTENCIA", "Advertencia"
    EVACUACION = "EVACUACION", "Evacuación y emergencia"
    CONTRA_INCENDIO = "CONTRA_INCENDIO", "Equipos contra incendio"


class SignStatus(models.TextChoices):
    BUENO = "BUENO", "En buen estado"
    DETERIORADA = "DETERIORADA", "Deteriorada"
    FALTANTE = "FALTANTE", "Falta instalar"


class SafetySign(models.Model):
    """Señal que el área debe tener, con su estado en la última revisión."""

    area = models.ForeignKey("accounts.Area", on_delete=models.CASCADE, related_name="signs")
    kind = models.CharField("tipo", max_length=16, choices=SignKind.choices)
    description = models.CharField("señal", max_length=200)
    location = models.CharField("ubicación", max_length=200, blank=True)
    status = models.CharField(
        "estado", max_length=12, choices=SignStatus.choices, default=SignStatus.FALTANTE
    )
    last_checked_on = models.DateField("última revisión", null=True, blank=True)
    notes = models.CharField("observaciones", max_length=255, blank=True)

    class Meta:
        verbose_name = "señal de seguridad"
        verbose_name_plural = "señales de seguridad"
        ordering = ("area__name", "kind", "description")

    def __str__(self) -> str:
        return f"{self.description} ({self.area.name})"

    @property
    def company_id(self):
        return self.area.company_id

    @property
    def is_observed(self) -> bool:
        return self.status != SignStatus.BUENO
