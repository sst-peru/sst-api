from rest_framework import viewsets

from .models import EppDelivery, EppItem
from .serializers import EppDeliverySerializer, EppItemSerializer


class EppItemViewSet(viewsets.ModelViewSet):
    serializer_class = EppItemSerializer

    def get_queryset(self):
        return EppItem.objects.filter(company=self.request.user.company_id)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class EppDeliveryViewSet(viewsets.ModelViewSet):
    serializer_class = EppDeliverySerializer
    filterset_fields = ("item", "worker", "acknowledged")

    def get_queryset(self):
        user = self.request.user
        qs = EppDelivery.objects.filter(
            item__company=user.company_id
        ).select_related("item", "worker")
        if not user.can_manage:
            qs = qs.filter(worker=user)
        return qs

    def perform_create(self, serializer):
        serializer.save(delivered_by=self.request.user)
