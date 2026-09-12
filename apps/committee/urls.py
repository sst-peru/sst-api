from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgreementViewSet,
    CommitteeComplianceView,
    CommitteeMemberViewSet,
    MeetingViewSet,
)
from .views import CommitteeViewSet

router = DefaultRouter()
router.register("committee/members", CommitteeMemberViewSet, basename="committee-member")
router.register("committee/meetings", MeetingViewSet, basename="committee-meeting")
router.register("committee/agreements", AgreementViewSet, basename="committee-agreement")
router.register("committee", CommitteeViewSet, basename="committee")

urlpatterns = [
    path(
        "committee-compliance/",
        CommitteeComplianceView.as_view(),
        name="committee-compliance",
    ),
    path("", include(router.urls)),
]
