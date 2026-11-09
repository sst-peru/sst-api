"""Recuperación de contraseña por correo.

El enlace lleva el id del usuario codificado y un token de un solo uso que Django invalida en
cuanto la contraseña cambia o pasa el plazo de PASSWORD_RESET_TIMEOUT.
"""
from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.email import enviar_correo

User = get_user_model()
ETIQUETA = "Autenticación y sesión"


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


@extend_schema(tags=[ETIQUETA], request=PasswordResetRequestSerializer, responses=None)
class PasswordResetRequestView(APIView):
    """Envía el enlace para restablecer la contraseña.

    Responde lo mismo exista o no la cuenta: si no, cualquiera podría averiguar qué correos
    están registrados.
    """

    permission_classes = (AllowAny,)
    throttle_scope = "login"

    def post(self, request):
        datos = PasswordResetRequestSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        correo = datos.validated_data["email"]
        for usuario in User.objects.filter(email__iexact=correo, is_active=True):
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = default_token_generator.make_token(usuario)
            enlace = f"{settings.FRONTEND_URL}/restablecer?uid={uid}&token={token}"
            enviar_correo(
                kind="password_reset",
                to=usuario.email,
                subject="Restablece tu contraseña de Resguardo",
                body=(
                    f"Hola {usuario.first_name or usuario.username}:\n\n"
                    "Recibimos una solicitud para restablecer tu contraseña. Entra a este "
                    f"enlace para elegir una nueva:\n\n{enlace}\n\n"
                    "Si no lo pediste, ignora este correo: tu contraseña no cambia."
                ),
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=[ETIQUETA], request=PasswordResetConfirmSerializer, responses=None)
class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)
    throttle_scope = "login"

    def post(self, request):
        datos = PasswordResetConfirmSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        try:
            usuario = User.objects.get(pk=force_str(urlsafe_base64_decode(d["uid"])))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            usuario = None
        if usuario is None or not default_token_generator.check_token(usuario, d["token"]):
            return Response(
                {"detail": "El enlace no es válido o ya venció. Solicita uno nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            password_validation.validate_password(d["new_password"], usuario)
        except Exception as error:  # ValidationError de Django: se traduce al formato de DRF
            return Response(
                {"new_password": list(getattr(error, "messages", [str(error)]))},
                status=status.HTTP_400_BAD_REQUEST,
            )
        usuario.set_password(d["new_password"])
        usuario.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
