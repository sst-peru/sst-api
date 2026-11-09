from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnualPlanViewSet,
    DocumentVersionViewSet,
    DocumentViewSet,
    PlanActivityViewSet,
)

router = DefaultRouter()
router.register("documents", DocumentViewSet, basename="document")
router.register("document-versions", DocumentVersionViewSet, basename="document-version")
router.register("sst-plans", AnnualPlanViewSet, basename="sst-plan")
router.register("sst-plan-activities", PlanActivityViewSet, basename="sst-plan-activity")

urlpatterns = [path("", include(router.urls))]
