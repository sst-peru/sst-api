from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, viewsets
from rest_framework_simplejwt.views import TokenObtainPairView

from rest_framework.exceptions import PermissionDenied

from .models import Area
from .serializers import (
    AreaSerializer,
    RegisterSerializer,
    SSTTokenObtainPairSerializer,
    UserSerializer,
    UserWriteSerializer,
)

User = get_user_model()


class SSTTokenObtainPairView(TokenObtainPairView):
    serializer_class = SSTTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)
    queryset = User.objects.all()


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class AreaViewSet(viewsets.ModelViewSet):
    serializer_class = AreaSerializer

    def get_queryset(self):
        return Area.objects.filter(company=self.request.user.company_id)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class UserViewSet(viewsets.ModelViewSet):
    """Usuarios de la empresa.

    La web y el móvil lo necesitan para poblar el selector de responsable al asignar un
    hallazgo o un acuerdo del comité. Solo los managers pueden verlo y escribir en él: un
    operario no tiene por qué ver el directorio completo de la empresa.
    """

    filterset_fields = ("role", "area", "is_active")
    search_fields = ("first_name", "last_name", "username", "dni")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return UserWriteSerializer
        return UserSerializer

    def get_queryset(self):
        if not self.request.user.can_manage:
            raise PermissionDenied("Solo supervisor o comité de SST puede ver los usuarios.")
        return User.objects.filter(company=self.request.user.company_id).select_related("area")

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)
