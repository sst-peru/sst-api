"""Pruebas del correo transaccional y de la recuperación de contraseña (TS19)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from apps.notifications.email import enviar_correo
from apps.notifications.models import EmailLog, EmailStatus

User = get_user_model()


@pytest.fixture(autouse=True)
def _correo_en_memoria(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_URL = "https://app.resguardo.pe"


@pytest.fixture
def usuario(db):
    empresa = Company.objects.create(name="Obras SAC", ruc="20500000001", worker_count=5)
    return User.objects.create_user(
        username="op", password="clave-anterior-123", email="op@obras.pe",
        company=empresa, role=Role.OPERARIO,
    )


def test_el_envio_queda_registrado(db):
    assert enviar_correo(kind="prueba", to="a@b.pe", subject="Hola", body="Cuerpo") is True

    assert len(mail.outbox) == 1
    assert EmailLog.objects.get().status == EmailStatus.ENVIADO


def test_un_fallo_del_proveedor_queda_registrado_sin_romper(db, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = "127.0.0.1"
    settings.EMAIL_PORT = 1  # nadie escucha ahí
    settings.EMAIL_TIMEOUT = 1

    assert enviar_correo(kind="prueba", to="a@b.pe", subject="Hola", body="x") is False
    registro = EmailLog.objects.get()
    assert registro.status == EmailStatus.FALLIDO
    assert registro.error


def _pedir_enlace(correo):
    return APIClient().post(reverse("password-reset"), {"email": correo}, format="json")


def test_la_recuperacion_envia_un_enlace_y_permite_cambiar_la_clave(usuario):
    assert _pedir_enlace("OP@obras.pe").status_code == 204

    enlace = next(x for x in mail.outbox[0].body.splitlines() if x.startswith("https://"))
    assert enlace.startswith("https://app.resguardo.pe/restablecer?")
    datos = {k: v[0] for k, v in parse_qs(urlsplit(enlace).query).items()}

    respuesta = APIClient().post(
        reverse("password-reset-confirm"),
        {**datos, "new_password": "Nueva-clave-segura-2026"},
        format="json",
    )

    assert respuesta.status_code == 204
    usuario.refresh_from_db()
    assert usuario.check_password("Nueva-clave-segura-2026")

    # El enlace es de un solo uso: con la clave cambiada, el token deja de valer.
    repetido = APIClient().post(
        reverse("password-reset-confirm"),
        {**datos, "new_password": "Otra-clave-segura-2026"},
        format="json",
    )
    assert repetido.status_code == 400


def test_un_correo_desconocido_responde_igual_y_no_envia_nada(db):
    assert _pedir_enlace("nadie@ninguna.pe").status_code == 204
    assert mail.outbox == []


def test_un_token_falso_se_rechaza(usuario):
    respuesta = APIClient().post(
        reverse("password-reset-confirm"),
        {"uid": "MQ", "token": "falso", "new_password": "Nueva-clave-segura-2026"},
        format="json",
    )

    assert respuesta.status_code == 400


def test_una_clave_debil_se_rechaza(usuario):
    _pedir_enlace("op@obras.pe")
    enlace = next(x for x in mail.outbox[0].body.splitlines() if x.startswith("https://"))
    datos = {k: v[0] for k, v in parse_qs(urlsplit(enlace).query).items()}

    respuesta = APIClient().post(
        reverse("password-reset-confirm"), {**datos, "new_password": "12345678"}, format="json"
    )

    assert respuesta.status_code == 400
    assert "new_password" in respuesta.data
