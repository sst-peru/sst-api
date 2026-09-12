from django.db.models import Max
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Agreement, Committee, CommitteeMember, Meeting
from .serializers import (
    AgreementSerializer,
    CommitteeMemberSerializer,
    CommitteeSerializer,
    MeetingSerializer,
)


class ManagerOnlyMixin:
    """Solo supervisor, comité o admin pueden escribir. El operario puede leer las actas."""

    def perform_create(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_update(self, serializer):
        self._require_manager()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_manager()
        instance.delete()

    def _require_manager(self):
        if not self.request.user.can_manage:
            raise PermissionDenied("Solo supervisor o comité de SST puede hacer esto.")


class CommitteeViewSet(ManagerOnlyMixin, viewsets.ModelViewSet):
    serializer_class = CommitteeSerializer

    def get_queryset(self):
        return Committee.objects.filter(
            company=self.request.user.company_id
        ).prefetch_related("members__user")

    def perform_create(self, serializer):
        self._require_manager()
        company = self.request.user.company
        if Committee.objects.filter(company=company).exists():
            raise ValidationError("La empresa ya tiene un comité registrado.")
        serializer.save(
            company=company,
            is_supervisor_mode=not company.requires_committee,
        )


class CommitteeMemberViewSet(ManagerOnlyMixin, viewsets.ModelViewSet):
    serializer_class = CommitteeMemberSerializer
    filterset_fields = ("role", "represents", "is_active")

    def get_queryset(self):
        return CommitteeMember.objects.filter(
            committee__company=self.request.user.company_id
        ).select_related("user")


class MeetingViewSet(ManagerOnlyMixin, viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    filterset_fields = ("is_extraordinary",)
    search_fields = ("agenda", "minutes")

    def get_queryset(self):
        return Meeting.objects.filter(
            committee__company=self.request.user.company_id
        ).prefetch_related("agreements__responsible", "attendees")

    def perform_create(self, serializer):
        self._require_manager()
        committee = Committee.objects.filter(company=self.request.user.company_id).first()
        if committee is None:
            raise ValidationError("Primero hay que registrar el comité de SST.")
        # El número de acta es consecutivo por comité: lo calcula el servidor, no el usuario.
        last = committee.meetings.aggregate(m=Max("number"))["m"] or 0
        serializer.save(committee=committee, number=last + 1)


class AgreementViewSet(ManagerOnlyMixin, viewsets.ModelViewSet):
    serializer_class = AgreementSerializer
    filterset_fields = ("status", "responsible", "meeting")

    def get_queryset(self):
        return Agreement.objects.filter(
            meeting__committee__company=self.request.user.company_id
        ).select_related("responsible", "meeting")


class CommitteeComplianceView(APIView):
    """Cumplimiento del comité: reuniones del año y acuerdos cerrados.

    La ley pide reunión mensual; este endpoint dice cuántas de las 12 se hicieron y cuántos
    acuerdos quedaron sin cumplir, que es lo que una inspección va a mirar.
    """

    def get(self, request):
        committee = Committee.objects.filter(company=request.user.company_id).first()
        if committee is None:
            return Response({"has_committee": False})

        meetings = committee.meetings.all()
        agreements = Agreement.objects.filter(meeting__committee=committee)
        total_agreements = agreements.count()
        cumplidos = agreements.filter(status="CUMPLIDO").count()

        return Response(
            {
                "has_committee": True,
                "is_supervisor_mode": committee.is_supervisor_mode,
                "is_paritario": committee.is_paritario,
                "members": committee.member_count,
                "quorum_required": committee.quorum_required,
                "meetings_total": meetings.count(),
                "meetings_with_quorum": sum(1 for m in meetings if m.quorum_reached),
                "agreements_total": total_agreements,
                "agreements_done": cumplidos,
                "agreements_pending": agreements.exclude(status="CUMPLIDO").count(),
                "agreements_compliance_pct": (
                    round(cumplidos / total_agreements * 100, 2) if total_agreements else None
                ),
            }
        )
