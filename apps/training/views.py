"""Endpoints del programa de capacitación, la inducción y los simulacros."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import ManagerEscribe

from .models import (
    CAPACITACIONES_MINIMAS_POR_ANIO,
    Drill,
    Induction,
    TrainingAttendance,
    TrainingSession,
    TrainingStatus,
)
from .serializers import (
    AttendanceInputSerializer,
    DrillSerializer,
    InductionSerializer,
    TrainingAttendanceSerializer,
    TrainingSessionSerializer,
)

ETIQUETA = "Capacitación y simulacros"
User = get_user_model()


def _trabajadores(empresa_id):
    """Plantilla que debe estar capacitada: todos menos la cuenta administradora."""
    return (
        User.objects.filter(company_id=empresa_id, is_active=True)
        .exclude(role=Role.ADMIN)
        .order_by("last_name", "first_name", "username")
    )


def _vigencias_por_trabajador(empresa_id):
    """Para cada trabajador, la fecha más lejana hasta la que tiene una capacitación vigente."""
    vigencias = {}
    asistencias = TrainingAttendance.objects.filter(
        session__company_id=empresa_id, session__status=TrainingStatus.REALIZADA
    ).select_related("session")
    for asistencia in asistencias:
        vence = asistencia.session.expires_on
        anterior = vigencias.get(asistencia.worker_id)
        if vence and (anterior is None or vence > anterior[0]):
            vigencias[asistencia.worker_id] = (vence, asistencia.session.held_on)
    return vigencias


@extend_schema(tags=[ETIQUETA])
class TrainingSessionViewSet(viewsets.ModelViewSet):
    """Programa anual de capacitación (US79) y registro de asistencia (US80)."""

    serializer_class = TrainingSessionSerializer
    permission_classes = (ManagerEscribe,)
    filterset_fields = ("status", "area")

    def get_queryset(self):
        qs = (
            TrainingSession.objects.filter(company=self.request.user.company_id)
            .select_related("responsible", "area")
            .annotate(attendance_count=Count("attendances"))
            .order_by("planned_date", "id")
        )
        anio = self.request.query_params.get("year")
        if anio and anio.isdigit():
            qs = qs.filter(planned_date__year=int(anio))
        return qs

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    @extend_schema(request=AttendanceInputSerializer, responses=TrainingAttendanceSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def attendance(self, request, pk=None):
        """GET lista a los asistentes; POST los registra y da la sesión por realizada."""
        sesion = self.get_object()
        if request.method == "POST":
            if not request.user.can_manage:
                raise PermissionDenied(ManagerEscribe.message)
            if sesion.status == TrainingStatus.CANCELADA:
                raise ValidationError({"detail": "La capacitación está cancelada."})
            datos = AttendanceInputSerializer(data=request.data)
            datos.is_valid(raise_exception=True)
            ids = set(datos.validated_data["workers"])
            validos = set(
                _trabajadores(request.user.company_id).filter(id__in=ids).values_list("id", flat=True)
            )
            if ids - validos:
                raise ValidationError(
                    {"workers": "Hay trabajadores que no pertenecen a tu empresa."}
                )
            with transaction.atomic():
                for trabajador_id in validos:
                    TrainingAttendance.objects.get_or_create(
                        session=sesion, worker_id=trabajador_id,
                        defaults={"registered_by": request.user},
                    )
                sesion.status = TrainingStatus.REALIZADA
                sesion.held_on = (
                    datos.validated_data.get("held_on") or sesion.held_on or timezone.localdate()
                )
                sesion.save(update_fields=["status", "held_on"])
        asistencias = sesion.attendances.select_related("worker").order_by("worker__last_name")
        return Response(TrainingAttendanceSerializer(asistencias, many=True).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sesion = self.get_object()
        if sesion.status == TrainingStatus.REALIZADA:
            raise ValidationError({"detail": "No se cancela una capacitación ya realizada."})
        sesion.status = TrainingStatus.CANCELADA
        sesion.save(update_fields=["status"])
        return Response(self.get_serializer(sesion).data)


@extend_schema(
    tags=[ETIQUETA],
    parameters=[OpenApiParameter("year", int, description="Año del programa; por defecto el actual.")],
)
class TrainingProgramSummaryView(APIView):
    """Avance del programa anual frente al mínimo de cuatro capacitaciones que fija la ley."""

    def get(self, request):
        anio = request.query_params.get("year")
        anio = int(anio) if anio and anio.isdigit() else timezone.localdate().year
        qs = TrainingSession.objects.filter(
            company=request.user.company_id, planned_date__year=anio
        )
        realizadas = qs.filter(status=TrainingStatus.REALIZADA).count()
        return Response(
            {
                "year": anio,
                "planned": qs.exclude(status=TrainingStatus.CANCELADA).count(),
                "held": realizadas,
                "minimum_required": CAPACITACIONES_MINIMAS_POR_ANIO,
                "meets_minimum": realizadas >= CAPACITACIONES_MINIMAS_POR_ANIO,
            }
        )


@extend_schema(tags=[ETIQUETA])
class TrainingPendingView(APIView):
    """Trabajadores sin capacitación vigente (US82): a reprogramar antes de una fiscalización."""

    def get(self, request):
        if not request.user.can_manage:
            raise PermissionDenied(ManagerEscribe.message)
        hoy = timezone.localdate()
        vigencias = _vigencias_por_trabajador(request.user.company_id)
        pendientes = []
        for trabajador in _trabajadores(request.user.company_id):
            vence, ultima = vigencias.get(trabajador.id, (None, None))
            if vence and vence >= hoy:
                continue
            pendientes.append(
                {
                    "worker": trabajador.id,
                    "worker_name": trabajador.get_full_name() or trabajador.username,
                    "last_training_on": ultima,
                    "expired_on": vence,
                    "reason": "VENCIDA" if vence else "SIN_CAPACITACION",
                }
            )
        return Response(pendientes)


@extend_schema(tags=[ETIQUETA])
class MyTrainingView(APIView):
    """Capacitaciones del trabajador autenticado, con su vigencia (US83)."""

    def get(self, request):
        hoy = timezone.localdate()
        asistencias = (
            TrainingAttendance.objects.filter(worker=request.user)
            .select_related("session")
            .order_by("-session__held_on")
        )
        induccion = Induction.objects.filter(worker=request.user).first()
        return Response(
            {
                "induction_on": induccion.completed_on if induccion else None,
                "trainings": [
                    {
                        "session": a.session_id,
                        "topic": a.session.topic,
                        "held_on": a.session.held_on,
                        "expires_on": a.session.expires_on,
                        "is_valid": bool(a.session.expires_on and a.session.expires_on >= hoy),
                    }
                    for a in asistencias
                ],
            }
        )


@extend_schema(tags=[ETIQUETA])
class InductionViewSet(viewsets.ModelViewSet):
    """Inducción del personal nuevo (US81). Una por trabajador."""

    serializer_class = InductionSerializer
    permission_classes = (ManagerEscribe,)
    http_method_names = ("get", "post", "patch", "head", "options")

    def get_queryset(self):
        qs = Induction.objects.filter(
            worker__company=self.request.user.company_id
        ).select_related("worker", "given_by")
        if not self.request.user.can_manage:
            qs = qs.filter(worker=self.request.user)
        return qs

    def perform_create(self, serializer):
        if Induction.objects.filter(worker=serializer.validated_data["worker"]).exists():
            raise ValidationError({"worker": "Este trabajador ya tiene su inducción registrada."})
        serializer.save(given_by=self.request.user)

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """Trabajadores que todavía no reciben inducción: no deberían estar operando."""
        if not request.user.can_manage:
            raise PermissionDenied(ManagerEscribe.message)
        sin_induccion = _trabajadores(request.user.company_id).filter(induction__isnull=True)
        return Response(
            [
                {
                    "worker": t.id,
                    "worker_name": t.get_full_name() or t.username,
                    "joined_on": t.date_joined.date(),
                }
                for t in sin_induccion
            ]
        )


@extend_schema(tags=[ETIQUETA])
class DrillViewSet(viewsets.ModelViewSet):
    """Registro de simulacros de emergencia (US84)."""

    serializer_class = DrillSerializer
    permission_classes = (ManagerEscribe,)
    filterset_fields = ("kind", "area")

    def get_queryset(self):
        return Drill.objects.filter(company=self.request.user.company_id).select_related("area")

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company, registered_by=self.request.user)
