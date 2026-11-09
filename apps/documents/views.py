"""Endpoints de los documentos del SGSST, su control de versiones y el plan anual."""
from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import ManagerEscribe

from .models import (
    ActivityStatus,
    AnnualPlan,
    Document,
    DocumentReceipt,
    DocumentVersion,
    PlanActivity,
    VersionStatus,
)
from .serializers import (
    AnnualPlanSerializer,
    DocumentSerializer,
    DocumentVersionSerializer,
    PlanActivitySerializer,
)

ETIQUETA = "Documentos y plan anual del SGSST"
User = get_user_model()


@extend_schema(tags=[ETIQUETA])
class DocumentViewSet(viewsets.ModelViewSet):
    """Política (US89), RISST (US90) y demás documentos del sistema de gestión.

    El trabajador solo ve los documentos que tienen una versión vigente; el responsable de SST
    ve también los que están en preparación.
    """

    serializer_class = DocumentSerializer
    permission_classes = (ManagerEscribe,)
    filterset_fields = ("kind",)

    def get_queryset(self):
        qs = Document.objects.filter(company=self.request.user.company_id).prefetch_related(
            "versions"
        )
        if not self.request.user.can_manage:
            qs = qs.filter(versions__status=VersionStatus.VIGENTE).distinct()
        return qs

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    @action(detail=True, methods=["post"], permission_classes=(IsAuthenticated,))
    def acknowledge(self, request, pk=None):
        """El trabajador deja constancia de que recibió la versión vigente (US90)."""
        documento = self.get_object()
        version = documento.current_version
        if version is None:
            raise ValidationError({"detail": "El documento no tiene una versión vigente."})
        DocumentReceipt.objects.get_or_create(version=version, worker=request.user)
        return Response(self.get_serializer(documento).data)

    @action(detail=True, methods=["get"])
    def receipts(self, request, pk=None):
        """Quién recibió la versión vigente y quién falta."""
        if not request.user.can_manage:
            raise PermissionDenied(ManagerEscribe.message)
        documento = self.get_object()
        version = documento.current_version
        if version is None:
            return Response({"version": None, "received": [], "pending": []})
        recibidos = {
            r.worker_id: r.received_at
            for r in version.receipts.select_related("worker")
        }
        plantilla = (
            User.objects.filter(company=request.user.company_id, is_active=True)
            .exclude(role=Role.ADMIN)
            .order_by("last_name", "first_name")
        )
        recibido, pendiente = [], []
        for t in plantilla:
            fila = {"worker": t.id, "worker_name": t.get_full_name() or t.username}
            if t.id in recibidos:
                recibido.append({**fila, "received_at": recibidos[t.id]})
            else:
                pendiente.append(fila)
        return Response({"version": version.number, "received": recibido, "pending": pendiente})


@extend_schema(tags=[ETIQUETA])
class DocumentVersionViewSet(viewsets.ModelViewSet):
    """Control de versiones de los documentos (US92)."""

    serializer_class = DocumentVersionSerializer
    permission_classes = (ManagerEscribe,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    filterset_fields = ("document", "status")
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        qs = DocumentVersion.objects.filter(
            document__company=self.request.user.company_id
        ).select_related("document", "created_by")
        if not self.request.user.can_manage:
            qs = qs.exclude(status=VersionStatus.BORRADOR)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_destroy(self, instance):
        if instance.status != VersionStatus.BORRADOR:
            raise ValidationError({"detail": "Solo se elimina un borrador."})
        instance.delete()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        version = self.get_object()
        if version.status != VersionStatus.BORRADOR:
            raise ValidationError({"detail": "Solo se publica un borrador."})
        if not (version.content.strip() or version.file):
            raise ValidationError({"detail": "Antes de publicar, agrega el texto o el archivo."})
        version.publish()
        return Response(self.get_serializer(version).data)


@extend_schema(tags=[ETIQUETA])
class AnnualPlanViewSet(viewsets.ModelViewSet):
    """Plan anual de SST con su avance (US91)."""

    serializer_class = AnnualPlanSerializer
    permission_classes = (ManagerEscribe,)
    filterset_fields = ("year",)

    def get_queryset(self):
        return AnnualPlan.objects.filter(
            company=self.request.user.company_id
        ).prefetch_related("activities__responsible")

    def perform_create(self, serializer):
        empresa = self.request.user.company
        if AnnualPlan.objects.filter(company=empresa, year=serializer.validated_data["year"]).exists():
            raise ValidationError({"year": "Ya existe un plan para ese año."})
        serializer.save(company=empresa)

    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """Avance de lo ejecutado frente a lo programado hasta el mes en curso."""
        plan = self.get_object()
        hoy = timezone.localdate()
        if plan.year < hoy.year:
            mes_corte = 12
        elif plan.year > hoy.year:
            mes_corte = 0
        else:
            mes_corte = hoy.month
        actividades = list(plan.activities.all())
        programadas = [a for a in actividades if a.planned_month <= mes_corte]
        ejecutadas = [a for a in actividades if a.status == ActivityStatus.EJECUTADA]
        ejecutadas_a_tiempo = [a for a in programadas if a.status == ActivityStatus.EJECUTADA]
        return Response(
            {
                "year": plan.year,
                "cutoff_month": mes_corte,
                "total": len(actividades),
                "programmed_to_date": len(programadas),
                "executed": len(ejecutadas),
                "progress_pct": (
                    round(len(ejecutadas_a_tiempo) / len(programadas) * 100, 1)
                    if programadas else None
                ),
                "annual_progress_pct": (
                    round(len(ejecutadas) / len(actividades) * 100, 1) if actividades else None
                ),
            }
        )


@extend_schema(tags=[ETIQUETA])
class PlanActivityViewSet(viewsets.ModelViewSet):
    serializer_class = PlanActivitySerializer
    permission_classes = (ManagerEscribe,)
    filterset_fields = ("plan", "status", "planned_month")

    def get_queryset(self):
        return PlanActivity.objects.filter(
            plan__company=self.request.user.company_id
        ).select_related("responsible")

    def perform_update(self, serializer):
        estado = serializer.validated_data.get("status")
        if estado == ActivityStatus.EJECUTADA and not serializer.validated_data.get("executed_on"):
            serializer.save(executed_on=serializer.instance.executed_on or timezone.localdate())
            return
        serializer.save()
