from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, MttrView, ReportSummaryView, ReportViewSet

router = DefaultRouter()
router.register("reports", ReportViewSet, basename="report")
router.register("categories", CategoryViewSet, basename="category")

urlpatterns = [
    path("metrics/mttr/", MttrView.as_view(), name="metrics-mttr"),
    path("metrics/reports-summary/", ReportSummaryView.as_view(), name="metrics-reports-summary"),
    path("", include(router.urls)),
]
