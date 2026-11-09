from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports.models import Report, ReportAction, ReportKind
from apps.reports.serializers import ReportSerializer

from .models import Inspection, InspectionSchedule, InspectionStatus
from .serializers import (
    GenerateReportSerializer,
    InspectionScheduleSerializer,
    InspectionSerializer,
)


@extend_schema(tags=["Inspecciones periódicas"])
class InspectionScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = InspectionScheduleSerializer
    filterset_fields = ("area", "frequency", "is_active")

    def get_queryset(self):
        return InspectionSchedule.objects.filter(
            company=self.request.user.company_id
        ).select_related("area")

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    @action(detail=True, methods=["post"], url_path="generate-next")
    def generate_next(self, request, pk=None):
        inspection = self.get_object().generate_next()
        return Response(InspectionSerializer(inspection).data, status=201)


@extend_schema(tags=["Inspecciones periódicas"])
class InspectionViewSet(viewsets.ModelViewSet):
    serializer_class = InspectionSerializer
    filterset_fields = ("schedule", "status", "schedule__area")

    def get_queryset(self):
        return Inspection.objects.filter(
            schedule__company=self.request.user.company_id
        ).select_related("schedule__area")

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        inspection = self.get_object()
        inspection.status = InspectionStatus.REALIZADA
        inspection.performed_at = timezone.now()
        inspection.performed_by = request.user
        inspection.findings = request.data.get("findings", inspection.findings)
        inspection.results = request.data.get("results", inspection.results)
        inspection.save()
        return Response(InspectionSerializer(inspection).data)

    @extend_schema(request=GenerateReportSerializer, responses=ReportSerializer)
    @action(detail=True, methods=["post"], url_path="generate-report")
    def generate_report(self, request, pk=None):
        """Convierte una observación de la inspección en un hallazgo (US120).

        El hallazgo nace como condición insegura del área inspeccionada, queda enlazado a la
        inspección y entra al mismo ciclo de asignación y cierre que un reporte de campo.
        """
        inspection = self.get_object()
        if inspection.status != InspectionStatus.REALIZADA:
            raise ValidationError(
                {"detail": "Primero registra la inspección como realizada."}
            )
        datos = GenerateReportSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        item = datos.validated_data.get("item", "").strip()
        descripcion = datos.validated_data["description"].strip()
        if item:
            descripcion = f"[{item}] {descripcion}"
        with transaction.atomic():
            reporte = Report.objects.create(
                company=request.user.company,
                reported_by=request.user,
                kind=ReportKind.CONDICION,
                area=inspection.schedule.area,
                description=descripcion,
                severity=datos.validated_data["severity"],
                occurred_at=inspection.performed_at or timezone.now(),
                source_inspection=inspection,
            )
            ReportAction.objects.create(
                report=reporte,
                author=request.user,
                note=f"Hallazgo generado desde la inspección «{inspection.schedule.title}».",
                new_status=reporte.status,
            )
        return Response(
            ReportSerializer(reporte, context={"request": request}).data, status=201
        )


@extend_schema(tags=["Indicadores del SGSST"])
class InspectionComplianceView(APIView):
    """Tasa de cumplimiento: inspecciones realizadas a tiempo / programadas.

    Segunda métrica del curso. ?days=90 acota la ventana.
    """

    def get(self, request):
        days = int(request.query_params.get("days", 90))
        since = timezone.localdate() - timedelta(days=days)
        qs = Inspection.objects.filter(
            schedule__company=request.user.company_id, due_date__gte=since
        )
        totals = qs.aggregate(
            scheduled=Count("id"),
            done=Count("id", filter=Q(status=InspectionStatus.REALIZADA)),
            on_time=Count(
                "id",
                filter=Q(status=InspectionStatus.REALIZADA, performed_at__date__lte=timezone.now()),
            ),
            pending=Count("id", filter=Q(status=InspectionStatus.PENDIENTE)),
        )
        overdue = qs.filter(
            status=InspectionStatus.PENDIENTE, due_date__lt=timezone.localdate()
        ).count()
        scheduled = totals["scheduled"] or 0
        rate = round(totals["done"] / scheduled * 100, 2) if scheduled else None
        return Response(
            {
                "window_days": days,
                "scheduled": scheduled,
                "performed": totals["done"],
                "pending": totals["pending"],
                "overdue": overdue,
                "compliance_rate_pct": rate,
                "by_area": list(
                    qs.values(area=F("schedule__area__name"))
                    .annotate(
                        scheduled=Count("id"),
                        performed=Count("id", filter=Q(status=InspectionStatus.REALIZADA)),
                    )
                ),
            }
        )
