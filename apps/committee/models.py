from django.conf import settings
from django.db import models


class MemberRole(models.TextChoices):
    PRESIDENTE = "PRESIDENTE", "Presidente"
    SECRETARIO = "SECRETARIO", "Secretario"
    TITULAR = "TITULAR", "Miembro titular"
    SUPLENTE = "SUPLENTE", "Miembro suplente"
    SUPERVISOR = "SUPERVISOR", "Supervisor de SST"


class Represents(models.TextChoices):
    EMPLEADOR = "EMPLEADOR", "Representante del empleador"
    TRABAJADORES = "TRABAJADORES", "Representante de los trabajadores"


class Committee(models.Model):
    """Comité de SST de la empresa, o el supervisor si tiene menos de 20 trabajadores.

    La Ley 29783 exige comité paritario (mitad empleador, mitad trabajadores) desde 20
    trabajadores; por debajo basta un supervisor de SST elegido por los trabajadores.
    """

    company = models.OneToOneField(
        "accounts.Company", on_delete=models.CASCADE, related_name="committee"
    )
    period_start = models.DateField("inicio del periodo")
    period_end = models.DateField("fin del periodo")
    is_supervisor_mode = models.BooleanField(
        "modo supervisor (empresa con menos de 20 trabajadores)", default=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "comité de SST"
        verbose_name_plural = "comités de SST"

    def __str__(self) -> str:
        return f"Comité SST {self.company.name} ({self.period_start.year})"

    @property
    def member_count(self) -> int:
        return self.members.filter(is_active=True).count()

    @property
    def quorum_required(self) -> int:
        """Mitad más uno de los miembros titulares activos."""
        titulares = self.members.filter(
            is_active=True, role__in=[MemberRole.PRESIDENTE, MemberRole.SECRETARIO, MemberRole.TITULAR]
        ).count()
        return titulares // 2 + 1 if titulares else 0

    @property
    def is_paritario(self) -> bool:
        """Verifica que haya igual número de representantes de cada parte."""
        activos = self.members.filter(is_active=True)
        empleador = activos.filter(represents=Represents.EMPLEADOR).count()
        trabajadores = activos.filter(represents=Represents.TRABAJADORES).count()
        return empleador == trabajadores and empleador > 0


class CommitteeMember(models.Model):
    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="committee_memberships"
    )
    role = models.CharField("cargo", max_length=12, choices=MemberRole.choices)
    represents = models.CharField("representa a", max_length=14, choices=Represents.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "miembro del comité"
        verbose_name_plural = "miembros del comité"
        ordering = ("role", "user__last_name")
        constraints = [
            models.UniqueConstraint(
                fields=("committee", "user"), name="unique_member_per_committee"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.get_role_display()}"


class Meeting(models.Model):
    """Acta de reunión del comité. Es el documento que SUNAFIL pide ver en una inspección."""

    committee = models.ForeignKey(Committee, on_delete=models.CASCADE, related_name="meetings")
    number = models.PositiveIntegerField("número de acta")
    date = models.DateField("fecha de la reunión")
    place = models.CharField("lugar", max_length=200, blank=True)
    is_extraordinary = models.BooleanField("extraordinaria", default=False)
    agenda = models.TextField("agenda", blank=True)
    minutes = models.TextField("desarrollo del acta", blank=True)
    attendees = models.ManyToManyField(
        CommitteeMember, related_name="meetings_attended", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "acta de reunión"
        verbose_name_plural = "actas de reunión"
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=("committee", "number"), name="unique_meeting_number_per_committee"
            ),
        ]

    def __str__(self) -> str:
        return f"Acta N° {self.number} — {self.date}"

    @property
    def attendee_count(self) -> int:
        return self.attendees.count()

    @property
    def quorum_reached(self) -> bool:
        """Sin quórum el acta no es válida: la reunión se reprograma."""
        required = self.committee.quorum_required
        return bool(required) and self.attendee_count >= required


class AgreementStatus(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    EN_PROCESO = "EN_PROCESO", "En proceso"
    CUMPLIDO = "CUMPLIDO", "Cumplido"
    NO_CUMPLIDO = "NO_CUMPLIDO", "No cumplido"


class Agreement(models.Model):
    """Acuerdo tomado en una reunión, con responsable y plazo.

    Puede colgar de un reporte concreto: así el acuerdo del comité queda trazado hasta el
    hallazgo que lo originó, que es justo lo que hoy se pierde en el cuaderno de actas.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="agreements")
    description = models.TextField("acuerdo")
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="committee_agreements",
    )
    due_date = models.DateField("plazo", null=True, blank=True)
    status = models.CharField(
        "estado", max_length=12, choices=AgreementStatus.choices,
        default=AgreementStatus.PENDIENTE,
    )
    related_report = models.ForeignKey(
        "reports.Report", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="committee_agreements",
    )
    related_iperc_entry = models.ForeignKey(
        "iperc.IpercEntry", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="committee_agreements",
    )

    class Meta:
        verbose_name = "acuerdo"
        verbose_name_plural = "acuerdos"
        ordering = ("due_date",)

    def __str__(self) -> str:
        return self.description[:60]
