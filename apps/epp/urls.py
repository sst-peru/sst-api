from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EppDeliveryViewSet, EppItemViewSet

router = DefaultRouter()
router.register("epp/items", EppItemViewSet, basename="epp-item")
router.register("epp/deliveries", EppDeliveryViewSet, basename="epp-delivery")

urlpatterns = [path("", include(router.urls))]
