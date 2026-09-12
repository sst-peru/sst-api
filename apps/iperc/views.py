from django.db.models import Max
from rest_framework import viewsets

from .models import IpercEntry, IpercMatrix
from .serializers import IpercEntrySerializer, IpercMatrixSerializer


class IpercMatrixViewSet(viewsets.ModelViewSet):
    serializer_class = IpercMatrixSerializer
    filterset_fields = ("status",)

    def get_queryset(self):
        return IpercMatrix.objects.filter(
            company=self.request.user.company_id
        ).prefetch_related("entries__area")

    def perform_create(self, serializer):
        company = self.request.user.company
        last = IpercMatrix.objects.filter(company=company).aggregate(m=Max("version"))["m"] or 0
        serializer.save(company=company, version=last + 1)


class IpercEntryViewSet(viewsets.ModelViewSet):
    serializer_class = IpercEntrySerializer
    filterset_fields = ("matrix", "area", "probability", "consequence")
    search_fields = ("hazard", "risk", "job_position")

    def get_queryset(self):
        return IpercEntry.objects.filter(
            matrix__company=self.request.user.company_id
        ).select_related("area", "matrix")
