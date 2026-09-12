from django.conf import settings
from django.db import models


class MatrixStatus(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    VIGENTE = "VIGENTE", "Vigente"
    HISTORICA = "HISTORICA", "Histórica"


class IpercMatrix(models.Model):
    """Versión de la matriz IPERC. Se versiona para poder mostrar el histórico a SUNAFIL."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="iperc_matrices"
    )
    version = models.PositiveIntegerField("versión", default=1)
    status = models.CharField(
        "estado", max_length=12, choices=MatrixStatus.choices, default=MatrixStatus.BORRADOR
    )
    valid_from = models.DateField("vigente desde", null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "matriz IPERC"
        verbose_name_plural = "matrices IPERC"
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=("company", "version"), name="unique_iperc_version_per_company"
            ),
        ]

    def __str__(self) -> str:
        return f"IPERC v{self.version} — {self.company.name}"


class IpercEntry(models.Model):
    """Fila de la matriz: peligro identificado en un puesto/área y cómo se controla."""

    PROBABILITY = [(1, "Baja"), (2, "Media"), (3, "Alta")]
    CONSEQUENCE = [(1, "Ligeramente dañino"), (2, "Dañino"), (3, "Extremadamente dañino")]

    matrix = models.ForeignKey(IpercMatrix, on_delete=models.CASCADE, related_name="entries")
    area = models.ForeignKey("accounts.Area", on_delete=models.CASCADE, related_name="iperc_entries")
    job_position = models.CharField("puesto / tarea", max_length=150)
    hazard = models.CharField("peligro", max_length=255)
    risk = models.CharField("riesgo", max_length=255)
    probability = models.PositiveSmallIntegerField("probabilidad", choices=PROBABILITY, default=2)
    consequence = models.PositiveSmallIntegerField("consecuencia", choices=CONSEQUENCE, default=2)
    existing_controls = models.TextField("controles existentes", blank=True)
    proposed_controls = models.TextField("controles propuestos", blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    # Trazabilidad: esta fila nació de un reporte real del campo, no de una revisión anual.
    source_report = models.ForeignKey(
        "reports.Report",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="iperc_entries",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "entrada IPERC"
        verbose_name_plural = "entradas IPERC"
        ordering = ("area__name", "job_position")

    def __str__(self) -> str:
        return f"{self.job_position}: {self.hazard}"

    @property
    def risk_score(self) -> int:
        return self.probability * self.consequence

    @property
    def risk_level(self) -> str:
        score = self.risk_score
        if score <= 2:
            return "TRIVIAL"
        if score <= 4:
            return "TOLERABLE"
        if score <= 6:
            return "MODERADO"
        return "IMPORTANTE" if score <= 8 else "INTOLERABLE"
