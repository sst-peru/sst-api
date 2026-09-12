from datetime import timedelta

from django.db.models import Avg, Count, F, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Report, ReportAction, ReportStatus
from .serializers import (
    CategorySerializer,
    ReportAssignSerializer,
    ReportCloseSerializer,
    ReportCreateSerializer,
    ReportSerializer,
    ReportStatusSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.filter(company=self.request.user.company_id, is_active=True)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class ReportViewSet(viewsets.ModelViewSet):
    """Reportes de actos y condiciones inseguras. Mismo endpoint para web y móvil."""

    serializer_class = ReportSerializer
    filterset_fields = ("kind", "status", "severity", "area", "category", "assigned_to")
    search_fields = ("description", "closure_note")
    ordering_fields = ("created_at", "closed_at", "severity")

    def get_queryset(self):
        user = self.request.user
        qs = (
            Report.objects.filter(company=user.company_id)
            .select_related("reported_by", "assigned_to", "category", "area")
            .prefetch_related("actions__author")
        )
        # El operario solo ve lo suyo; supervisor y comité ven toda la empresa.
        if not user.can_manage:
            qs = qs.filter(reported_by=user)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ReportCreateSerializer
        return ReportSerializer

    def create(self, request, *args, **kwargs):
        """Idempotente por client_uuid: reintentar una sincronización no duplica el reporte."""
        client_uuid = request.data.get("client_uuid")
        if client_uuid:
            existing = Report.objects.filter(client_uuid=client_uuid).first()
            if existing is not None:
                return Response(ReportSerializer(existing).data, status=status.HTTP_200_OK)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save(
            reported_by=request.user, company=request.user.company
        )
        return Response(ReportSerializer(report).data, status=status.HTTP_201_CREATED)

    def _require_manager(self):
        if not self.request.user.can_manage:
            raise PermissionDenied("Solo supervisor o comité de SST puede hacer esto.")

    @extend_schema(request=ReportAssignSerializer, responses=ReportSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        self._require_manager()
        report = self.get_object()
        serializer = ReportAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report.assigned_to_id = serializer.validated_data["assigned_to"]
        report.assigned_at = timezone.now()
        if report.status == ReportStatus.ABIERTO:
            report.status = ReportStatus.EN_PROCESO
        report.save(update_fields=["assigned_to", "assigned_at", "status", "updated_at"])
        ReportAction.objects.create(
            report=report,
            author=request.user,
            note=serializer.validated_data.get("note", "") or "Responsable asignado.",
            new_status=report.status,
        )
        return Response(ReportSerializer(report).data)

    @extend_schema(request=ReportCloseSerializer, responses=ReportSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        self._require_manager()
        report = self.get_object()
        serializer = ReportCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = serializer.validated_data["closure_note"]
        report.close(note=note)
        ReportAction.objects.create(
            report=report, author=request.user, note=note, new_status=ReportStatus.CERRADO
        )
        return Response(ReportSerializer(report).data)

    @extend_schema(request=ReportStatusSerializer, responses=ReportSerializer)
    @action(detail=True, methods=["post"], url_path="change-status")
    def change_status(self, request, pk=None):
        self._require_manager()
        report = self.get_object()
        serializer = ReportStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        report.status = new_status
        report.closed_at = timezone.now() if new_status == ReportStatus.CERRADO else None
        report.save(update_fields=["status", "closed_at", "updated_at"])
        ReportAction.objects.create(
            report=report,
            author=request.user,
            note=serializer.validated_data.get("note", ""),
            new_status=new_status,
        )
        return Response(ReportSerializer(report).data)


class MttrView(APIView):
    """MTTR: promedio de horas entre el reporte de un peligro y su cierre.

    Métrica principal del curso. Se puede filtrar por días (?days=30) y segmentar
    por severidad y por variante del formulario (para el A/B test).
    """

    def get(self, request):
        days = int(request.query_params.get("days", 90))
        since = timezone.now() - timedelta(days=days)
        closed = Report.objects.filter(
            company=request.user.company_id,
            closed_at__isnull=False,
            created_at__gte=since,
        ).annotate(resolution=F("closed_at") - F("created_at"))

        overall = closed.aggregate(avg=Avg("resolution"), total=Count("id"))
        avg_hours = (
            overall["avg"].total_seconds() / 3600 if overall["avg"] is not None else None
        )

        by_severity = {}
        for row in closed.values("severity").annotate(avg=Avg("resolution"), total=Count("id")):
            by_severity[row["severity"]] = {
                "mttr_hours": round(row["avg"].total_seconds() / 3600, 2),
                "closed": row["total"],
            }

        open_qs = Report.objects.filter(
            company=request.user.company_id,
            status__in=[ReportStatus.ABIERTO, ReportStatus.EN_PROCESO],
        )
        return Response(
            {
                "window_days": days,
                "closed_reports": overall["total"],
                "open_reports": open_qs.count(),
                "mttr_hours": round(avg_hours, 2) if avg_hours is not None else None,
                "by_severity": by_severity,
            }
        )


class ReportSummaryView(APIView):
    """Conteos para los tableros de la web: por estado, tipo, área y severidad."""

    def get(self, request):
        qs = Report.objects.filter(company=request.user.company_id)
        return Response(
            {
                "total": qs.count(),
                "by_status": list(qs.values("status").annotate(total=Count("id"))),
                "by_kind": list(qs.values("kind").annotate(total=Count("id"))),
                "by_severity": list(qs.values("severity").annotate(total=Count("id"))),
                "by_area": list(
                    qs.values("area", name=F("area__name")).annotate(total=Count("id"))
                ),
                "overdue_critical": qs.filter(
                    Q(severity="CRITICA") & Q(status__in=["ABIERTO", "EN_PROCESO"])
                ).count(),
            }
        )
