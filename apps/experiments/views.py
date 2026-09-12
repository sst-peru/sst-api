from django.db.models import Avg, Count, F
from django.db.models.functions import TruncDate
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports.models import Report

from .models import Assignment, Experiment
from .serializers import AssignmentSerializer, ExperimentSerializer


class ExperimentViewSet(viewsets.ModelViewSet):
    queryset = Experiment.objects.all()
    serializer_class = ExperimentSerializer
    lookup_field = "key"


class MyVariantView(APIView):
    """Qué variante le toca al usuario actual. La app móvil y la web llaman esto al entrar."""

    @extend_schema(
        parameters=[OpenApiParameter("key", str, description="Clave del experimento")],
        responses=AssignmentSerializer,
    )
    def get(self, request):
        key = request.query_params.get("key", Experiment.KEY_REPORT_FORM)
        experiment = get_object_or_404(Experiment, key=key, is_active=True)
        assignment, _ = Assignment.objects.get_or_create(
            experiment=experiment,
            user=request.user,
            defaults={"variant": experiment.variant_for(request.user.id)},
        )
        return Response(AssignmentSerializer(assignment).data)


class ExperimentResultsView(APIView):
    """Resultados del A/B test: reportes por usuario en cada variante.

    La métrica de la hipótesis es reports_per_user: si el flujo rápido gana,
    debería estar cerca del doble que el largo.
    """

    def get(self, request, key: str):
        experiment = get_object_or_404(Experiment, key=key)
        results = []
        for variant in experiment.variants or []:
            user_ids = list(
                Assignment.objects.filter(experiment=experiment, variant=variant).values_list(
                    "user_id", flat=True
                )
            )
            reports = Report.objects.filter(
                company=request.user.company_id, reported_by_id__in=user_ids
            )
            total = reports.count()
            users = len(user_ids)
            closed = reports.filter(closed_at__isnull=False).annotate(
                resolution=F("closed_at") - F("created_at")
            )
            avg = closed.aggregate(a=Avg("resolution"))["a"]
            results.append(
                {
                    "variant": variant,
                    "users": users,
                    "reports": total,
                    "reports_per_user": round(total / users, 2) if users else None,
                    "reports_with_photo": reports.filter(photo__isnull=False)
                    .exclude(photo="")
                    .count(),
                    "mttr_hours": round(avg.total_seconds() / 3600, 2) if avg else None,
                    "daily": list(
                        reports.annotate(day=TruncDate("created_at"))
                        .values("day")
                        .annotate(total=Count("id"))
                        .order_by("day")
                    ),
                }
            )
        lift = None
        if len(results) == 2 and results[1]["reports_per_user"]:
            base = results[1]["reports_per_user"]
            lift = round((results[0]["reports_per_user"] - base) / base * 100, 2)
        return Response(
            {
                "experiment": ExperimentSerializer(experiment).data,
                "results": results,
                "lift_pct_first_vs_second": lift,
            }
        )
