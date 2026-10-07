"""Registro de accidentes de trabajo, incidentes peligrosos y enfermedades ocupacionales.

Son tres de los registros obligatorios del Sistema de Gestión que exige el artículo 28 de la
Ley N° 29783. A diferencia del reporte de actos y condiciones inseguras —que previene—, este
módulo documenta el hecho que ya ocurrió, su investigación de causa raíz y las medidas
correctivas con responsable y plazo, que es lo que una fiscalización de SUNAFIL revisa.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# Artículo 82 de la Ley N° 29783: el empleador notifica al Ministerio de Trabajo los
# accidentes de trabajo mortales y los incidentes peligrosos dentro de las 24 horas de
# ocurridos. El resto se declara en el plazo mensual ordinario.
HORAS_PARA_AVISO_INMEDIATO = 24


class AccidentKind(models.TextChoices):
    ACCIDENTE = "ACCIDENTE", "Accidente de trabajo"
    INCIDENTE_PELIGROSO = "INCIDENTE_PELIGROSO", "Incidente peligroso"


class AccidentSeverity(models.TextChoices):
    """Clasificación del D.S. N° 005-2012-TR. De ella depende el plazo de notificación."""

    LEVE = "LEVE", "Leve"
    INCAPACITANTE = "INCAPACITANTE", "Incapacitante"
    MORTAL = "MORTAL", "Mortal"


class AccidentStatus(models.TextChoices):
    REGISTRADO = "REGISTRADO", "Registrado"
    EN_INVESTIGACION = "EN_INVESTIGACION", "En investigación"
    CERRADO = "CERRADO", "Cerrado"


class Accident(models.Model):
    """Un accidente de trabajo o un incidente peligroso ocurrido en la empresa."""

    # Igual que en los reportes: lo genera el cliente antes de enviar, para que un reintento
    # de sincronización no registre el accidente dos veces.
    client_uuid = models.UUIDField("uuid del cliente", default=uuid.uuid4, unique=True)

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="accidents"
    )
    kind = models.CharField("tipo", max_length=20, choices=AccidentKind.choices)
    severity = models.CharField(
        "gravedad", max_length=15, choices=AccidentSeverity.choices,
        default=AccidentSeverity.LEVE,
    )
    status = models.CharField(
        "estado", max_length=18, choices=AccidentStatus.choices,
        default=AccidentStatus.REGISTRADO,
    )

    area = models.ForeignKey(
        "accounts.Area", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="accidents",
    )
    place = models.CharField("lugar exacto", max_length=200, blank=True)
    description = models.TextField("descripción del hecho")
    injury_description = models.TextField("lesión o daño", blank=True)
    immediate_actions = models.TextField("acciones inmediatas tomadas", blank=True)

    # El accidentado puede no tener cuenta en el sistema (un contratista, un visitante), así
    # que se guarda la referencia si existe y, si no, su nombre y documento.
    injured_person = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="accidents_suffered", verbose_name="trabajador accidentado",
    )
    injured_name = models.CharField("nombre del accidentado", max_length=150, blank=True)
    injured_dni = models.CharField("DNI del accidentado", max_length=8, blank=True)
    lost_days = models.PositiveIntegerField("días perdidos", default=0)

    # Trazabilidad: si el peligro ya había sido reportado y nadie le hizo seguimiento, el
    # vínculo lo demuestra. Es el caso que la Ley 29783 quiere evitar.
    origin_report = models.ForeignKey(
        "reports.Report", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="accidents", verbose_name="hallazgo previo relacionado",
    )

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="accidents_reported"
    )

    # Aviso al Ministerio de Trabajo.
    mtpe_notified_at = models.DateTimeField("avisado al MTPE el", null=True, blank=True)
    mtpe_notice_code = models.CharField("cargo o constancia del aviso", max_length=80, blank=True)

    occurred_at = models.DateTimeField("ocurrió el")
    created_at = models.DateTimeField("registrado el", auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField("cerrado el", null=True, blank=True)

    class Meta:
        verbose_name = "accidente"
        verbose_name_plural = "accidentes"
        ordering = ("-occurred_at",)
        indexes = [
            models.Index(fields=("company", "status")),
            models.Index(fields=("company", "-occurred_at")),
        ]

    def __str__(self) -> str:
        return "%s del %s" % (self.get_kind_display(), self.occurred_at.date())

    @property
    def injured_label(self) -> str:
        if self.injured_person_id:
            return self.injured_person.get_full_name() or self.injured_person.username
        return self.injured_name

    @property
    def requires_immediate_notice(self) -> bool:
        """Solo el accidente mortal y el incidente peligroso tienen el plazo de 24 horas."""
        return (
            self.severity == AccidentSeverity.MORTAL
            or self.kind == AccidentKind.INCIDENTE_PELIGROSO
        )

    @property
    def notice_deadline(self):
        if not self.requires_immediate_notice:
            return None
        return self.occurred_at + timedelta(hours=HORAS_PARA_AVISO_INMEDIATO)

    @property
    def notice_hours_left(self):
        """Horas que quedan para avisar. Negativo si el plazo ya venció."""
        if self.notice_deadline is None or self.mtpe_notified_at is not None:
            return None
        restante = self.notice_deadline - timezone.now()
        return round(restante.total_seconds() / 3600, 1)

    @property
    def notice_overdue(self) -> bool:
        """El plazo legal venció sin aviso: es la situación que genera la sanción."""
        if self.notice_deadline is None or self.mtpe_notified_at is not None:
            return False
        return timezone.now() > self.notice_deadline

    @property
    def notified_late(self) -> bool:
        """Se avisó, pero después del plazo. Queda como evidencia del incumplimiento."""
        if self.notice_deadline is None or self.mtpe_notified_at is None:
            return False
        return self.mtpe_notified_at > self.notice_deadline


class InvestigationMethod(models.TextChoices):
    ARBOL_DE_CAUSAS = "ARBOL_DE_CAUSAS", "Árbol de causas"
    CINCO_POR_QUE = "CINCO_POR_QUE", "Cinco por qué"
    ISHIKAWA = "ISHIKAWA", "Diagrama de Ishikawa"
    OTRA = "OTRA", "Otra"


class Investigation(models.Model):
    """Investigación del accidente. Uno a uno: un accidente se investiga una vez.

    Se separan causas inmediatas, causas básicas y causa raíz porque es la estructura que
    pide el registro oficial: quedarse en la causa inmediata —«el trabajador se distrajo»—
    es justo lo que la fiscalización observa.
    """

    accident = models.OneToOneField(
        Accident, on_delete=models.CASCADE, related_name="investigation"
    )
    method = models.CharField(
        "metodología", max_length=20, choices=InvestigationMethod.choices,
        default=InvestigationMethod.CINCO_POR_QUE,
    )
    immediate_causes = models.TextField("causas inmediatas", blank=True)
    basic_causes = models.TextField("causas básicas", blank=True)
    root_cause = models.TextField("causa raíz")
    conclusions = models.TextField("conclusiones", blank=True)
    participants = models.CharField("participantes", max_length=255, blank=True)

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="investigations"
    )
    performed_at = models.DateTimeField("investigado el", default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "investigación"
        verbose_name_plural = "investigaciones"

    def __str__(self) -> str:
        return "Investigación de %s" % self.accident


class ControlKind(models.TextChoices):
    """Jerarquía de controles del artículo 21 de la Ley N° 29783, de mayor a menor eficacia.

    El orden importa: entregar un EPP es el último recurso, no el primero, y el campo deja
    constancia de qué nivel de control eligió la empresa.
    """

    ELIMINACION = "ELIMINACION", "Eliminación del peligro"
    SUSTITUCION = "SUSTITUCION", "Sustitución"
    INGENIERIA = "INGENIERIA", "Control de ingeniería"
    ADMINISTRATIVO = "ADMINISTRATIVO", "Control administrativo o señalización"
    EPP = "EPP", "Equipo de protección personal"


class MeasureStatus(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente"
    EN_PROCESO = "EN_PROCESO", "En proceso"
    IMPLEMENTADA = "IMPLEMENTADA", "Implementada"
    VERIFICADA = "VERIFICADA", "Verificada"


class CorrectiveMeasure(models.Model):
    """Medida correctiva derivada del accidente, con responsable y plazo.

    Sin responsable y sin fecha una medida correctiva no es verificable, y una medida que no
    se puede verificar no sirve como evidencia de gestión.
    """

    accident = models.ForeignKey(
        Accident, on_delete=models.CASCADE, related_name="measures"
    )
    description = models.TextField("medida")
    control_kind = models.CharField(
        "nivel de control", max_length=15, choices=ControlKind.choices,
        default=ControlKind.ADMINISTRATIVO,
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="measures_responsible"
    )
    due_date = models.DateField("plazo")
    status = models.CharField(
        "estado", max_length=15, choices=MeasureStatus.choices, default=MeasureStatus.PENDIENTE
    )
    completed_at = models.DateTimeField("implementada el", null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="measures_verified",
    )
    verified_at = models.DateTimeField("verificada el", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "medida correctiva"
        verbose_name_plural = "medidas correctivas"
        ordering = ("due_date",)

    def __str__(self) -> str:
        return self.description[:60]

    @property
    def overdue(self) -> bool:
        return (
            self.status in {MeasureStatus.PENDIENTE, MeasureStatus.EN_PROCESO}
            and self.due_date < timezone.localdate()
        )


class DiseaseStatus(models.TextChoices):
    SOSPECHA = "SOSPECHA", "Sospecha"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    DESCARTADA = "DESCARTADA", "Descartada"


class OccupationalDisease(models.Model):
    """Registro de enfermedades ocupacionales.

    Va en su propio modelo y no como un tipo de accidente porque el dato es distinto: no hay
    un instante de ocurrencia sino una exposición sostenida a un agente, y lo que se registra
    es el diagnóstico y el agente causal.
    """

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="occupational_diseases"
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="diseases", verbose_name="trabajador",
    )
    worker_name = models.CharField("nombre del trabajador", max_length=150, blank=True)
    area = models.ForeignKey(
        "accounts.Area", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="occupational_diseases",
    )
    diagnosis = models.CharField("diagnóstico", max_length=200)
    cie10_code = models.CharField("código CIE-10", max_length=10, blank=True)
    causal_agent = models.CharField("agente causal", max_length=150, blank=True)
    exposure_months = models.PositiveIntegerField("meses de exposición", null=True, blank=True)
    diagnosed_on = models.DateField("diagnosticada el")
    status = models.CharField(
        "estado", max_length=12, choices=DiseaseStatus.choices, default=DiseaseStatus.SOSPECHA
    )
    rest_days = models.PositiveIntegerField("días de descanso médico", default=0)
    notes = models.TextField("observaciones", blank=True)

    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="diseases_reported"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "enfermedad ocupacional"
        verbose_name_plural = "enfermedades ocupacionales"
        ordering = ("-diagnosed_on",)

    def __str__(self) -> str:
        return "%s (%s)" % (self.diagnosis, self.diagnosed_on)

    @property
    def worker_label(self) -> str:
        if self.worker_id:
            return self.worker.get_full_name() or self.worker.username
        return self.worker_name
