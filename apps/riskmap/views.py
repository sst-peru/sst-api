"""Endpoints del mapa de riesgos por área y del inventario de señalización."""
from django.db import transaction
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Area
from apps.accounts.permissions import ManagerEscribe

from .models import RiskMap, SafetySign, SignStatus
from .serializers import RiskMapSerializer, RiskMarkerSerializer, SafetySignSerializer

ETIQUETA = "Mapa de riesgos y señalización"


def _vigentes(empresa_id):
    """Id del mapa más reciente de cada área: ese es el que se exhibe."""
    ids = []
    for area in Area.objects.filter(company=empresa_id):
        mapa = area.risk_maps.order_by("-published_at", "-id").first()
        if mapa:
            ids.append(mapa.id)
    return ids


@extend_schema(
    tags=[ETIQUETA],
    parameters=[
        OpenApiParameter("current", bool, description="Solo el mapa vigente de cada área."),
    ],
)
class RiskMapViewSet(viewsets.ModelViewSet):
    """Mapas de riesgos (US85, US86). Publicar uno nuevo deja el anterior como histórico."""

    serializer_class = RiskMapSerializer
    permission_classes = (ManagerEscribe,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    filterset_fields = ("area",)

    def get_queryset(self):
        qs = (
            RiskMap.objects.filter(area__company=self.request.user.company_id)
            .select_related("area", "published_by")
            .prefetch_related("markers")
        )
        if self.request.query_params.get("current") in {"1", "true", "True"}:
            qs = qs.filter(id__in=_vigentes(self.request.user.company_id))
        return qs

    def perform_create(self, serializer):
        serializer.save(published_by=self.request.user)

    @extend_schema(
        request=RiskMarkerSerializer(many=True), responses=RiskMarkerSerializer(many=True)
    )
    @action(detail=True, methods=["put"], parser_classes=(JSONParser,))
    def markers(self, request, pk=None):
        """Reemplaza los riesgos señalados en el plano por la lista enviada."""
        mapa = self.get_object()
        datos = RiskMarkerSerializer(data=request.data, many=True)
        datos.is_valid(raise_exception=True)
        with transaction.atomic():
            mapa.markers.all().delete()
            datos.save(risk_map=mapa)
        return Response(RiskMarkerSerializer(mapa.markers.all(), many=True).data)


class PaginaDeInventario(PageNumberPagination):
    """El inventario se revisa completo, área por área: 20 por página lo partiría sin sentido."""

    page_size = 200


@extend_schema(tags=[ETIQUETA])
class SafetySignViewSet(viewsets.ModelViewSet):
    """Inventario de señalización por área (US87)."""

    serializer_class = SafetySignSerializer
    permission_classes = (ManagerEscribe,)
    pagination_class = PaginaDeInventario
    filterset_fields = ("area", "kind", "status")

    def get_queryset(self):
        return SafetySign.objects.filter(
            area__company=self.request.user.company_id
        ).select_related("area")


@extend_schema(tags=[ETIQUETA])
class SignageSummaryView(APIView):
    """Por área: cuántas señales debería haber, cuántas hay y cuántas están observadas."""

    def get(self, request):
        if not request.user.can_manage:
            raise PermissionDenied(ManagerEscribe.message)
        filas = (
            SafetySign.objects.filter(area__company=request.user.company_id)
            .values("area", "area__name")
            .annotate(
                expected=Count("id"),
                installed=Count("id", filter=~Q(status=SignStatus.FALTANTE)),
                observed=Count("id", filter=~Q(status=SignStatus.BUENO)),
            )
            .order_by("area__name")
        )
        return Response(
            [
                {
                    "area": f["area"],
                    "area_name": f["area__name"],
                    "expected": f["expected"],
                    "installed": f["installed"],
                    "observed": f["observed"],
                }
                for f in filas
            ]
        )
