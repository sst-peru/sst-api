"""Endpoints del registro de accidentes, incidentes peligrosos y enfermedades ocupacionales."""
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Accident,
    AccidentSeverity,
    AccidentStatus,
    CorrectiveMeasure,
    MeasureStatus,
    OccupationalDisease,
)
from .serializers import (
    AccidentCreateSerializer,
    AccidentNoticeSerializer,
    AccidentSerializer,
    CorrectiveMeasureSerializer,
    InvestigationSerializer,
    OccupationalDiseaseSerializer,
)

ETIQUETA = "Accidentes y enfermedades ocupacionales"

# Jornada supuesta para estimar las horas-hombre cuando la empresa no las informa.
HORAS_POR_JORNADA = 8
DIAS_LABORABLES_POR_SEMANA = 6


class _ManagerWriteMixin:
    """Leer lo puede la empresa; registrar la investigación o cerrar, solo un manager.

    Es la misma separación que exige la ley para los hallazgos: quien reporta no decide.
    """

    def _require_manager(self):
        if not self.request.user.can_manage:
            raise PermissionDenied(
                "Solo supervisor, comité de SST o administrador puede hacer esto."
            )


@extend_schema(tags=[ETIQUETA])
class AccidentViewSet(_ManagerWriteMixin, viewsets.ModelViewSet):
    """Accidentes de trabajo e incidentes peligrosos.

    El registro lo puede crear cualquier trabajador —desde la web o desde el celular, que es
    donde ocurre el hecho—, pero la investigación, el aviso al MTPE y el cierre quedan
    reservados a supervisor, comité o administrador.
    """

    serializer_class = AccidentSerializer
    filterset_fields = ("kind", "severity", "status", "area")
    search_fields = ("description", "place", "injured_name")
    ordering_fields = ("occurred_at", "created_at", "lost_days")

    def get_queryset(self):
        user = self.request.user
        qs = (
            Accident.objects.filter(company=user.company_id)
            .select_related("area", "reported_by", "injured_person", "investigation")
            .prefetch_related("measures__responsible")
        )
        # Un accidente nombra a una persona lesionada: el resto de la plantilla no tiene
        # por qué ver el expediente completo de sus compañeros.
        if not user.can_manage:
            qs = qs.filter(Q(reported_by=user) | Q(injured_person=user))
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return AccidentCreateSerializer
        return AccidentSerializer

    def create(self, request, *args, **kwargs):
        """Idempotente por client_uuid, igual que los reportes: un reintento no duplica."""
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existente = Accident.objects.filter(client_uuid=client_uuid).first()
            if existente is not None:
                return Response(AccidentSerializer(existente).data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accidente = serializer.save(reported_by=request.user, company=request.user.company)
        return Response(AccidentSerializer(accidente).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_destroy(self, instance):
        raise PermissionDenied(
            "Un accidente registrado no se elimina: es un registro obligatorio del sistema "
            "de gestión. Si fue un error, documéntalo en la investigación."
        )

    @extend_schema(request=InvestigationSerializer, responses=AccidentSerializer)
    @action(detail=True, methods=["post"])
    def investigate(self, request, pk=None):
        """Registra la investigación de causa raíz y pasa el accidente a «en investigación»."""
        self._require_manager()
        accidente = self.get_object()
        if hasattr(accidente, "investigation"):
            raise ValidationError(
                {"detail": "Este accidente ya tiene investigación registrada; edítala en su lugar."}
            )
        serializer = InvestigationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(accident=accidente, performed_by=request.user)
        if accidente.status == AccidentStatus.REGISTRADO:
            accidente.status = AccidentStatus.EN_INVESTIGACION
            accidente.save(update_fields=["status", "updated_at"])
        accidente.refresh_from_db()
        return Response(AccidentSerializer(accidente).data)

    @extend_schema(request=AccidentNoticeSerializer, responses=AccidentSerializer)
    @action(detail=True, methods=["post"], url_path="notify-mtpe")
    def notify_mtpe(self, request, pk=None):
        """Deja constancia del aviso al Ministerio de Trabajo y de su plazo de 24 horas."""
        self._require_manager()
        accidente = self.get_object()
        if not accidente.requires_immediate_notice:
            raise ValidationError(
                {
                    "detail": (
                        "Este hecho no requiere aviso dentro de 24 horas: el plazo del "
                        "artículo 82 aplica al accidente mortal y al incidente peligroso."
                    )
                }
            )
        serializer = AccidentNoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        accidente.mtpe_notified_at = serializer.validated_data.get("notified_at") or timezone.now()
        accidente.mtpe_notice_code = serializer.validated_data.get("notice_code", "")
        accidente.save(update_fields=["mtpe_notified_at", "mtpe_notice_code", "updated_at"])
        return Response(AccidentSerializer(accidente).data)

    @extend_schema(request=None, responses=AccidentSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Cierra el expediente. Exige investigación y que no queden medidas sin verificar."""
        self._require_manager()
        accidente = self.get_object()
        if not hasattr(accidente, "investigation"):
            raise ValidationError(
                {"detail": "No se puede cerrar un accidente sin investigación de causa raíz."}
            )
        pendientes = accidente.measures.exclude(status=MeasureStatus.VERIFICADA).count()
        if pendientes:
            raise ValidationError(
                {
                    "detail": (
                        "Quedan %d medidas correctivas sin verificar. Cerrar el expediente "
                        "con medidas abiertas es lo que convierte un accidente en reincidente."
                        % pendientes
                    )
                }
            )
        accidente.status = AccidentStatus.CERRADO
        accidente.closed_at = timezone.now()
        accidente.save(update_fields=["status", "closed_at", "updated_at"])
        return Response(AccidentSerializer(accidente).data)


@extend_schema(tags=[ETIQUETA])
class CorrectiveMeasureViewSet(_ManagerWriteMixin, viewsets.ModelViewSet):
    """Medidas correctivas de los accidentes, con responsable, plazo y verificación."""

    serializer_class = CorrectiveMeasureSerializer
    filterset_fields = ("accident", "status", "control_kind", "responsible")
    ordering_fields = ("due_date", "created_at")

    def get_queryset(self):
        return CorrectiveMeasure.objects.filter(
            accident__company=self.request.user.company_id
        ).select_related("accident", "responsible", "verified_by")

    def perform_create(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_update(self, serializer):
        self._require_manager()
        serializer.save()

    @extend_schema(request=None, responses=CorrectiveMeasureSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """La marca el responsable cuando la implementa. No la da por verificada."""
        medida = self.get_object()
        if request.user != medida.responsible and not request.user.can_manage:
            raise PermissionDenied("Solo el responsable de la medida o un manager puede marcarla.")
        medida.status = MeasureStatus.IMPLEMENTADA
        medida.completed_at = timezone.now()
        medida.save(update_fields=["status", "completed_at"])
        return Response(CorrectiveMeasureSerializer(medida).data)

    @extend_schema(request=None, responses=CorrectiveMeasureSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """La verifica un manager distinto del responsable: quien ejecuta no se autoaprueba."""
        self._require_manager()
        medida = self.get_object()
        if medida.status == MeasureStatus.PENDIENTE:
            raise ValidationError(
                {"detail": "No se puede verificar una medida que todavía no se implementó."}
            )
        if medida.responsible_id == request.user.id:
            raise ValidationError(
                {
                    "detail": (
                        "La verificación la hace alguien distinto del responsable de "
                        "ejecutarla; es la separación que pide la Ley 29783."
                    )
                }
            )
        medida.status = MeasureStatus.VERIFICADA
        medida.verified_by = request.user
        medida.verified_at = timezone.now()
        medida.save(update_fields=["status", "verified_by", "verified_at"])
        return Response(CorrectiveMeasureSerializer(medida).data)


@extend_schema(tags=[ETIQUETA])
class OccupationalDiseaseViewSet(viewsets.ModelViewSet):
    """Registro de enfermedades ocupacionales.

    Es dato de salud, así que solo lo ven y lo escriben supervisor, comité y administrador;
    el trabajador no accede al registro de sus compañeros.
    """

    serializer_class = OccupationalDiseaseSerializer
    filterset_fields = ("status", "area", "worker")
    search_fields = ("diagnosis", "causal_agent", "worker_name")
    ordering_fields = ("diagnosed_on", "rest_days")

    def get_queryset(self):
        if not self.request.user.can_manage:
            raise PermissionDenied(
                "El registro de enfermedades ocupacionales contiene datos de salud y solo "
                "lo consulta supervisor, comité de SST o administrador."
            )
        return OccupationalDisease.objects.filter(
            company=self.request.user.company_id
        ).select_related("worker", "area")

    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user, company=self.request.user.company)


@extend_schema(
    tags=["Indicadores del SGSST"],
    parameters=[
        OpenApiParameter("days", int, description="Ventana en días. Por defecto 90."),
        OpenApiParameter(
            "hours_worked", int,
            description=(
                "Horas-hombre trabajadas en la ventana. Si se omite se estiman con la "
                "plantilla declarada, 8 horas por jornada y 6 días por semana."
            ),
        ),
    ],
)
class AccidentRatesView(APIView):
    """Índices de accidentabilidad según la R.M. N° 050-2013-TR.

    - Índice de frecuencia  = accidentes incapacitantes y mortales × 1 000 000 / HHT
    - Índice de gravedad    = días perdidos × 1 000 000 / HHT
    - Índice de accidentabilidad = (frecuencia × gravedad) / 1000

    Las horas-hombre trabajadas (HHT) las informa la empresa; si no lo hace, se estiman con
    la plantilla declarada y se dice en la respuesta que el valor es estimado, porque un
    índice calculado sobre una base supuesta no sirve como declaración oficial.
    """

    def get(self, request):
        empresa = request.user.company
        try:
            days = int(request.query_params.get("days", 90))
        except ValueError:
            raise ValidationError({"days": "La ventana debe ser un número de días."}) from None
        if days < 1:
            raise ValidationError({"days": "La ventana debe ser de al menos un día."})

        desde = timezone.now() - timedelta(days=days)
        qs = Accident.objects.filter(company=empresa, occurred_at__gte=desde)
        totales = qs.aggregate(
            total=Count("id"),
            mortales=Count("id", filter=Q(severity=AccidentSeverity.MORTAL)),
            incapacitantes=Count("id", filter=Q(severity=AccidentSeverity.INCAPACITANTE)),
            leves=Count("id", filter=Q(severity=AccidentSeverity.LEVE)),
            dias_perdidos=Sum("lost_days"),
        )
        dias_perdidos = totales["dias_perdidos"] or 0
        con_baja = totales["incapacitantes"] + totales["mortales"]

        informadas = request.query_params.get("hours_worked")
        if informadas:
            try:
                hht = int(informadas)
            except ValueError:
                raise ValidationError(
                    {"hours_worked": "Las horas-hombre deben ser un número entero."}
                ) from None
            if hht < 1:
                raise ValidationError({"hours_worked": "Las horas-hombre deben ser positivas."})
            estimadas = False
        else:
            jornadas = days * DIAS_LABORABLES_POR_SEMANA / 7
            hht = int(empresa.worker_count * HORAS_POR_JORNADA * jornadas)
            estimadas = True

        frecuencia = round(con_baja * 1_000_000 / hht, 2) if hht else None
        gravedad = round(dias_perdidos * 1_000_000 / hht, 2) if hht else None
        accidentabilidad = (
            round(frecuencia * gravedad / 1000, 2)
            if frecuencia is not None and gravedad is not None
            else None
        )

        vencidos = [a for a in qs if a.notice_overdue]
        return Response(
            {
                "window_days": days,
                "accidents": totales["total"],
                "minor": totales["leves"],
                "disabling": totales["incapacitantes"],
                "fatal": totales["mortales"],
                "lost_days": dias_perdidos,
                "hours_worked": hht,
                "hours_worked_estimated": estimadas,
                "frequency_index": frecuencia,
                "severity_index": gravedad,
                "accident_rate_index": accidentabilidad,
                "overdue_notices": len(vencidos),
                "diseases": OccupationalDisease.objects.filter(
                    company=empresa, diagnosed_on__gte=desde.date()
                ).count(),
            }
        )
