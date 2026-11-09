from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    DrillViewSet,
    InductionViewSet,
    MyTrainingView,
    TrainingPendingView,
    TrainingProgramSummaryView,
    TrainingSessionViewSet,
)

router = DefaultRouter()
router.register("training/sessions", TrainingSessionViewSet, basename="training-session")
router.register("training/inductions", InductionViewSet, basename="induction")
router.register("training/drills", DrillViewSet, basename="drill")

urlpatterns = [
    path("training/summary/", TrainingProgramSummaryView.as_view(), name="training-summary"),
    path("training/pending/", TrainingPendingView.as_view(), name="training-pending"),
    path("training/mine/", MyTrainingView.as_view(), name="training-mine"),
    path("", include(router.urls)),
]
