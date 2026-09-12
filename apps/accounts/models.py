from django.contrib.auth.models import AbstractUser
from django.db import models


class Company(models.Model):
    """Empresa obligada a tener un SGSST (Ley 29783)."""

    name = models.CharField("razón social", max_length=200)
    ruc = models.CharField("RUC", max_length=11, unique=True)
    address = models.CharField("dirección", max_length=255, blank=True)
    # Con menos de 20 trabajadores la ley pide supervisor en vez de comité.
    worker_count = models.PositiveIntegerField("número de trabajadores", default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def requires_committee(self) -> bool:
        return self.worker_count >= 20


class Area(models.Model):
    """Área, sede o frente de trabajo donde se ubican los peligros."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField("nombre", max_length=150)
    description = models.CharField("descripción", max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "área"
        verbose_name_plural = "áreas"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("company", "name"), name="unique_area_per_company"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.company.name})"


class Role(models.TextChoices):
    OPERARIO = "OPERARIO", "Operario / trabajador de campo"
    SUPERVISOR = "SUPERVISOR", "Supervisor de SST"
    COMITE = "COMITE", "Miembro del comité de SST"
    ADMIN = "ADMIN", "Administrador"


class User(AbstractUser):
    """Usuario del sistema. El rol define qué puede hacer en web y móvil."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )
    area = models.ForeignKey(
        Area, on_delete=models.SET_NULL, related_name="users", null=True, blank=True
    )
    role = models.CharField("rol", max_length=20, choices=Role.choices, default=Role.OPERARIO)
    dni = models.CharField("DNI", max_length=8, blank=True)
    phone = models.CharField("teléfono", max_length=20, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def can_manage(self) -> bool:
        """Puede asignar responsables y cerrar hallazgos."""
        return self.role in {Role.SUPERVISOR, Role.COMITE, Role.ADMIN}
