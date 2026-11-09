from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RiskMapViewSet, SafetySignViewSet, SignageSummaryView

router = DefaultRouter()
router.register("risk-maps", RiskMapViewSet, basename="risk-map")
router.register("signs", SafetySignViewSet, basename="sign")

urlpatterns = [
    path("signs-summary/", SignageSummaryView.as_view(), name="signs-summary"),
    path("", include(router.urls)),
]
