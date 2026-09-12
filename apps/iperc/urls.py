from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IpercEntryViewSet, IpercMatrixViewSet

router = DefaultRouter()
router.register("iperc/matrices", IpercMatrixViewSet, basename="iperc-matrix")
router.register("iperc/entries", IpercEntryViewSet, basename="iperc-entry")

urlpatterns = [path("", include(router.urls))]
