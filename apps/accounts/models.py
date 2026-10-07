from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

# Version vigente de la politica de privacidad. Al publicar una nueva se sube esta
# constante y el consentimiento anterior deja de valer: la Ley N° 29733 exige que el
# consentimiento sea informado, y no lo es si la politica cambio despues de darlo.
POLITICA_PRIVACIDAD_VERSION = "2026-10"


class Company(models.Model):
    """Empresa obligada a tener un SGSST (Ley 29783)."""

    name = models.CharField("razón social", max_length=200)
    ruc = models.CharField("RUC", max_length=11, unique=True)
    address = models.CharField("dirección", max_length=255, blank=True)
    # Con menos de 20 trabajadores la ley pide supervisor en vez de comité.
    worker_count = models.PositiveIntegerField("número de trabajadores", default=1)
    # Marca la empresa que carga el comando seed_demo. La usan las pantallas de
    # metricas para advertir que lo que se ve no es una operacion real.
    is_demo = models.BooleanField("datos de demostración", default=False)
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

    @property
    def worker_accounts(self) -> int:
        """Cuentas de trabajador ya registradas en la empresa.

        El administrador no cuenta: su cuenta nace junto con la empresa y es la que
        gestiona el sistema, no una plaza de trabajador.
        """
        return self.users.exclude(role=Role.ADMIN).count()

    @property
    def worker_slots_available(self) -> int:
        return max(self.worker_count - self.worker_accounts, 0)

    @property
    def accepts_new_worker(self) -> bool:
        """El RUC admite una cuenta más solo si quedan plazas declaradas sin usar.

        Sin este tope, cualquiera con el RUC —que está en la boleta y en el cartel de
        obra— podría abrir cuentas indefinidas en una empresa ajena.
        """
        return self.worker_slots_available > 0


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

    # La ubicacion del hallazgo es util pero no imprescindible: el trabajador puede
    # apagarla cuando quiera y el API deja de guardarla desde ese momento. Arranca
    # activa porque ubicar el peligro es parte del valor del reporte, y el
    # consentimiento de privacidad la menciona expresamente antes de pedirla.
    location_sharing = models.BooleanField("comparte su ubicación", default=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def can_manage(self) -> bool:
        """Puede asignar responsables y cerrar hallazgos."""
        return self.role in {Role.SUPERVISOR, Role.COMITE, Role.ADMIN}

    @property
    def privacy_consent(self):
        """Consentimiento vigente para la version actual de la politica, si existe."""
        return (
            self.consents.filter(
                policy_version=POLITICA_PRIVACIDAD_VERSION, revoked_at__isnull=True
            )
            .order_by("-granted_at")
            .first()
        )

    @property
    def has_accepted_privacy_policy(self) -> bool:
        return self.privacy_consent is not None


class PrivacyConsent(models.Model):
    """Consentimiento informado para el tratamiento de datos personales.

    La Ley N° 29733 pide que el consentimiento sea previo, informado, expreso e
    inequivoco, y que se pueda probar. Por eso no es un booleano en el usuario sino un
    registro con fecha, version de la politica y origen: queda el historial de cuando se
    dio y cuando se revoco, que es lo unico que sirve como prueba.
    """

    class Source(models.TextChoices):
        WEB = "WEB", "Panel web"
        ANDROID = "ANDROID", "Aplicación Android"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="consents"
    )
    policy_version = models.CharField("versión de la política", max_length=20)
    granted_at = models.DateTimeField("otorgado el", default=timezone.now)
    revoked_at = models.DateTimeField("revocado el", null=True, blank=True)
    source = models.CharField(
        "origen", max_length=10, choices=Source.choices, default=Source.WEB
    )

    class Meta:
        verbose_name = "consentimiento de privacidad"
        verbose_name_plural = "consentimientos de privacidad"
        ordering = ("-granted_at",)

    def __str__(self) -> str:
        return "%s · %s" % (self.user, self.policy_version)
