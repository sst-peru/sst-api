from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ExperimentResultsView, ExperimentViewSet, MyVariantView

router = DefaultRouter()
router.register("experiments", ExperimentViewSet, basename="experiment")

urlpatterns = [
    path("experiments/my-variant/", MyVariantView.as_view(), name="my-variant"),
    path(
        "experiments/<slug:key>/results/",
        ExperimentResultsView.as_view(),
        name="experiment-results",
    ),
    path("", include(router.urls)),
]
