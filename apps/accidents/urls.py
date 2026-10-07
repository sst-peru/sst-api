from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccidentRatesView,
    AccidentViewSet,
    CorrectiveMeasureViewSet,
    OccupationalDiseaseViewSet,
)

router = DefaultRouter()
router.register("accidents", AccidentViewSet, basename="accident")
router.register("corrective-measures", CorrectiveMeasureViewSet, basename="corrective-measure")
router.register(
    "occupational-diseases", OccupationalDiseaseViewSet, basename="occupational-disease"
)

urlpatterns = [
    path("metrics/accident-rates/", AccidentRatesView.as_view(), name="metrics-accident-rates"),
    path("", include(router.urls)),
]
