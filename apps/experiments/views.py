"""Endpoints del experimento A/B del curso: formulario rápido contra formulario largo."""
import statistics
from math import sqrt

from django.db.models import Avg, Count, F
from django.db.models.functions import TruncDate
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, viewsets
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports.models import Report

from .models import Assignment, Experiment
from .serializers import AssignmentSerializer, ExperimentSerializer

# Nivel de confianza del 95 %: valor crítico de la normal estándar.
Z_95 = 1.96

# Por debajo de esta cantidad de sujetos por variante el intervalo sale tan ancho que no
# permite concluir nada. No es un umbral mágico; es el punto a partir del cual la
# aproximación normal empieza a ser razonable.
SUJETOS_MINIMOS_POR_VARIANTE = 20


class SoloAdminEscribe(permissions.BasePermission):
    """Leer el experimento lo puede cualquiera; crearlo o borrarlo, solo un administrador.

    Antes era un ModelViewSet abierto: cualquier operario podía borrar el experimento en
    curso y con él la trazabilidad de las asignaciones.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.role == "ADMIN")


@extend_schema(tags=["Experimento A/B"])
class ExperimentViewSet(viewsets.ModelViewSet):
    queryset = Experiment.objects.all().order_by("key")
    serializer_class = ExperimentSerializer
    lookup_field = "key"
    permission_classes = (SoloAdminEscribe,)


@extend_schema(tags=["Experimento A/B"])
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


@extend_schema(tags=["Experimento A/B"])
class ExperimentResultsView(APIView):
    """Resultados del experimento con su intervalo de confianza del 95 %.

    La métrica de la hipótesis es reports_per_user. El punto de esta vista no es dar un
    número sino decir si la diferencia entre variantes se distingue del azar: por eso
    devuelve el intervalo de confianza de la diferencia de medias y, cuando el intervalo
    contiene el cero, lo declara no concluyente en vez de presentar el lift como hallazgo.

    Los reportes se cuentan por la variante grabada en el propio reporte y no por la
    asignación del autor. Así un reporte creado antes de que el experimento empezara no se
    atribuye a ninguna variante.
    """

    def get(self, request, key: str):
        experiment = get_object_or_404(Experiment, key=key)
        empresa_id = request.user.company_id
        resultados = []

        for variant in experiment.variants or []:
            user_ids = list(
                Assignment.objects.filter(experiment=experiment, variant=variant).values_list(
                    "user_id", flat=True
                )
            )
            reports = Report.objects.filter(
                company=empresa_id, reported_by_id__in=user_ids, form_variant=variant
            )
            # Los ceros cuentan: un usuario asignado que no reportó nada es justamente la
            # observación que la hipótesis quiere capturar.
            por_usuario = dict(
                reports.values_list("reported_by_id").annotate(n=Count("id"))
            )
            conteos = [por_usuario.get(uid, 0) for uid in user_ids]

            closed = reports.filter(closed_at__isnull=False).annotate(
                resolution=F("closed_at") - F("created_at")
            )
            avg = closed.aggregate(a=Avg("resolution"))["a"]

            resultados.append(
                {
                    "variant": variant,
                    "users": len(user_ids),
                    "reports": sum(conteos),
                    "reports_per_user": round(statistics.fmean(conteos), 2) if conteos else None,
                    "reports_per_user_sd": (
                        round(statistics.stdev(conteos), 2) if len(conteos) > 1 else 0.0
                    ),
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
                    "_conteos": conteos,
                }
            )

        comparacion = self._comparar(resultados)
        for fila in resultados:
            fila.pop("_conteos", None)

        minimo = min((f["users"] for f in resultados), default=0)
        return Response(
            {
                "experiment": ExperimentSerializer(experiment).data,
                "results": resultados,
                "comparison": comparacion,
                # Aviso de datos de demostración: lo que se ve no es una operación real.
                "demo_data": bool(request.user.company and request.user.company.is_demo),
                "sample_sufficient": minimo >= SUJETOS_MINIMOS_POR_VARIANTE,
                "min_users_per_variant": SUJETOS_MINIMOS_POR_VARIANTE,
            }
        )

    @staticmethod
    def _comparar(resultados):
        """Diferencia de medias entre las dos primeras variantes, con su intervalo al 95 %.

        Se usa la aproximación normal de Welch sobre los reportes por usuario. Es el
        «simplest useful thing» del enunciado: con dos grupos pequeños e independientes no
        hace falta más, y cualquier cosa más fina daría una falsa sensación de precisión.
        """
        if len(resultados) < 2:
            return None
        a, b = resultados[0], resultados[1]
        na, nb = a["users"], b["users"]
        if na < 2 or nb < 2:
            return {
                "variants": [a["variant"], b["variant"]],
                "difference": None,
                "conclusive": False,
                "reading": (
                    "Hacen falta al menos dos sujetos por variante para calcular un "
                    "intervalo de confianza."
                ),
            }

        ma, mb = statistics.fmean(a["_conteos"]), statistics.fmean(b["_conteos"])
        sa, sb = statistics.stdev(a["_conteos"]), statistics.stdev(b["_conteos"])
        diferencia = ma - mb
        error = sqrt(sa**2 / na + sb**2 / nb)
        bajo, alto = diferencia - Z_95 * error, diferencia + Z_95 * error
        concluyente = error > 0 and (bajo > 0 or alto < 0)
        lift = round(diferencia / mb * 100, 2) if mb else None

        if error == 0:
            lectura = "Sin variación entre sujetos no se puede estimar el error."
        elif concluyente:
            lectura = (
                "La diferencia es distinguible del azar con 95 %% de confianza: la variante "
                "«%s» registra entre %.2f y %.2f reportes por usuario %s que «%s»."
                % (
                    a["variant"],
                    abs(min(abs(bajo), abs(alto))),
                    abs(max(abs(bajo), abs(alto))),
                    "más" if diferencia > 0 else "menos",
                    b["variant"],
                )
            )
        else:
            lectura = (
                "El intervalo contiene el cero, así que la diferencia observada no se "
                "distingue del azar. Con esta muestra el resultado no es concluyente: no "
                "prueba que las variantes sean iguales, solo que no alcanza para afirmar "
                "que son distintas."
            )

        return {
            "variants": [a["variant"], b["variant"]],
            "difference": round(diferencia, 2),
            "standard_error": round(error, 3),
            "confidence_level_pct": 95,
            "ci_low": round(bajo, 2),
            "ci_high": round(alto, 2),
            "conclusive": concluyente,
            "lift_pct": lift,
            "reading": lectura,
        }
