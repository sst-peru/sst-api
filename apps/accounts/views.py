from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from .models import POLITICA_PRIVACIDAD_VERSION, Area, PrivacyConsent
from .serializers import (
    AreaSerializer,
    CompanyRegisterSerializer,
    CompanySerializer,
    PrivacyConsentWriteSerializer,
    PrivacyStateSerializer,
    RegisterSerializer,
    SSTTokenObtainPairSerializer,
    UserSerializer,
    UserWriteSerializer,
)

User = get_user_model()


@extend_schema(tags=["Autenticación y sesión"])
class SSTTokenObtainPairView(TokenObtainPairView):
    serializer_class = SSTTokenObtainPairSerializer


@extend_schema(tags=["Autenticación y sesión"])
class SSTTokenRefreshView(TokenRefreshView):
    """Renueva el token de acceso a partir del refresh, sin volver a pedir la contraseña."""


@extend_schema(tags=["Autenticación y sesión"])
class SSTTokenVerifyView(TokenVerifyView):
    """Comprueba que un token siga siendo válido."""


@extend_schema(tags=["Registro"])
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)
    queryset = User.objects.all()


@extend_schema(tags=["Registro"])
class CompanyRegisterView(generics.CreateAPIView):
    """Registro de empresa: crea la empresa y la cuenta de su administrador.

    Va aparte de RegisterView porque son dos altas distintas: aquí nace la empresa, allá
    un trabajador entra a una que ya existe.
    """

    serializer_class = CompanyRegisterSerializer
    permission_classes = (permissions.AllowAny,)


@extend_schema(tags=["Autenticación y sesión"])
class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Empresa, áreas y usuarios"])
class CompanyView(generics.RetrieveUpdateAPIView):
    """Datos de la empresa del usuario autenticado.

    Leerla la puede cualquiera de la empresa —el panel muestra la razón social y el cupo
    de cuentas—, pero escribir solo los managers: el número de trabajadores decide cuántas
    cuentas admite el RUC y si la ley exige comité o supervisor.
    """

    serializer_class = CompanySerializer

    def get_object(self):
        empresa = self.request.user.company
        if empresa is None:
            raise NotFound("Tu cuenta no está asociada a ninguna empresa.")
        if self.request.method not in permissions.SAFE_METHODS and not self.request.user.can_manage:
            raise PermissionDenied(
                "Solo supervisor, comité de SST o administrador puede editar los datos de la empresa."
            )
        return empresa


@extend_schema(tags=["Empresa, áreas y usuarios"])
class AreaViewSet(viewsets.ModelViewSet):
    serializer_class = AreaSerializer

    def get_queryset(self):
        return Area.objects.filter(company=self.request.user.company_id)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


@extend_schema(tags=["Empresa, áreas y usuarios"])
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
