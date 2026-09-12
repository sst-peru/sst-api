from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InspectionComplianceView, InspectionScheduleViewSet, InspectionViewSet

router = DefaultRouter()
router.register("inspections/schedules", InspectionScheduleViewSet, basename="inspection-schedule")
router.register("inspections", InspectionViewSet, basename="inspection")

urlpatterns = [
    path(
        "metrics/inspection-compliance/",
        InspectionComplianceView.as_view(),
        name="metrics-inspection-compliance",
    ),
    path("", include(router.urls)),
]
