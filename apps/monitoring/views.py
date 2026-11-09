"""Recepción de los errores no controlados de la web y del móvil (TS24)."""
from urllib.parse import urlsplit

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ClientError, Platform

LARGO_MAXIMO_TRAZA = 8000


class ClientErrorSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=Platform.choices)
    app_version = serializers.CharField(max_length=40, required=False, allow_blank=True)
    message = serializers.CharField()
    stack = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)
    request_id = serializers.CharField(max_length=64, required=False, allow_blank=True)


@extend_schema(tags=["Autenticación y sesión"], request=ClientErrorSerializer, responses=None)
class ClientErrorView(APIView):
    """Registra un error no controlado del cliente.

    No exige sesión porque el error puede ocurrir antes de iniciarla (en el login, por
    ejemplo); el límite de tasa propio impide usarlo para llenar la base.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "client_errors"

    def post(self, request):
        datos = ClientErrorSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        usuario = request.user if request.user.is_authenticated else None
        ClientError.objects.create(
            platform=d["platform"],
            app_version=d.get("app_version", ""),
            message=d["message"][:500],
            stack=d.get("stack", "")[:LARGO_MAXIMO_TRAZA],
            path=urlsplit(d.get("url", "")).path[:255],
            user_agent=request.headers.get("User-Agent", "")[:255],
            user=usuario,
            company_id=getattr(usuario, "company_id", None),
            request_id=d.get("request_id", ""),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
