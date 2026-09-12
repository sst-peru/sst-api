from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Inspection, InspectionSchedule, InspectionStatus
from .serializers import InspectionScheduleSerializer, InspectionSerializer


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


class InspectionComplianceView(APIView):
    """Tasa de cumplimiento: inspecciones realizadas a tiempo / programadas.

    Segunda métrica del curso. ?days=90 acota la ventana.
    """

    def get(self, request):
        days = int(request.query_params.get("days", 90))
        since = timezone.localdate() - timezone.timedelta(days=days)
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
