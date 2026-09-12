import hashlib

from django.conf import settings
from django.db import models


class Experiment(models.Model):
    """Experimento A/B. El del curso: formulario rápido vs formulario largo."""

    KEY_REPORT_FORM = "report_form"

    key = models.SlugField("clave", max_length=60, unique=True)
    name = models.CharField("nombre", max_length=150)
    description = models.TextField("hipótesis", blank=True)
    variants = models.JSONField("variantes", default=list)  # ej: ["rapido", "largo"]
    is_active = models.BooleanField("activo", default=True)
    started_at = models.DateTimeField("inicio", null=True, blank=True)
    ended_at = models.DateTimeField("fin", null=True, blank=True)

    class Meta:
        verbose_name = "experimento"
        verbose_name_plural = "experimentos"

    def __str__(self) -> str:
        return self.name

    def variant_for(self, user_id: int) -> str:
        """Asignación determinística: el mismo usuario cae siempre en la misma variante.

        Usamos un hash estable (no random) para que la app móvil pueda recalcularlo
        offline y para que el experimento sea reproducible al sustentar el trabajo.
        """
        variants = self.variants or ["control", "tratamiento"]
        digest = hashlib.sha256(f"{self.key}:{user_id}".encode()).hexdigest()
        return variants[int(digest, 16) % len(variants)]


class Assignment(models.Model):
    """Asignación persistida, para poder auditar el experimento después."""

    experiment = models.ForeignKey(
        Experiment, on_delete=models.CASCADE, related_name="assignments"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="experiment_assignments"
    )
    variant = models.CharField("variante", max_length=40)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "asignación"
        verbose_name_plural = "asignaciones"
        constraints = [
            models.UniqueConstraint(
                fields=("experiment", "user"), name="unique_assignment_per_user"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.variant}"
