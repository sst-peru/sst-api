"""Pruebas de la observabilidad (TS23), el límite de tasa (TS25) y el versionado del API (TS30)."""
import json
import logging

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from config.observability import JsonFormatter

User = get_user_model()


@pytest.fixture
def usuario(db):
    empresa = Company.objects.create(name="Obras SAC", ruc="20500000001", worker_count=5)
    return User.objects.create_user(
        username="sup", password="clave-segura-123", company=empresa, role=Role.SUPERVISOR
    )


def test_cada_respuesta_lleva_un_identificador_de_correlacion(usuario):
    c = APIClient()
    c.force_authenticate(user=usuario)

    respuesta = c.get(reverse("me"))

    assert len(respuesta["X-Request-ID"]) == 32


def test_se_respeta_el_identificador_que_manda_el_cliente(usuario):
    c = APIClient()
    c.force_authenticate(user=usuario)

    respuesta = c.get(reverse("me"), HTTP_X_REQUEST_ID="web-abc123")

    assert respuesta["X-Request-ID"] == "web-abc123"


def test_un_identificador_sospechoso_se_reemplaza(usuario):
    c = APIClient()
    c.force_authenticate(user=usuario)

    respuesta = c.get(reverse("me"), HTTP_X_REQUEST_ID="<script>alert(1)</script>")

    assert respuesta["X-Request-ID"] != "<script>alert(1)</script>"


def test_el_registro_incluye_usuario_ruta_estado_y_tiempo(usuario, caplog):
    c = APIClient()
    c.force_authenticate(user=usuario)

    with caplog.at_level(logging.INFO, logger="sst.requests"):
        respuesta = c.get(reverse("me"), HTTP_X_REQUEST_ID="corr-1")

    registro = next(r for r in caplog.records if r.name == "sst.requests")
    assert registro.status == 200
    assert registro.path == respuesta.wsgi_request.path
    assert registro.user == usuario.pk
    assert registro.duration_ms >= 0
    linea = json.loads(JsonFormatter().format(registro))
    assert linea["path"] == registro.path
    assert linea["status"] == 200


def test_el_inicio_de_sesion_responde_429_al_superar_el_limite(usuario, settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {"anon": "1000/min", "user": "1000/min", "login": "3/min"},
    }
    from rest_framework.throttling import ScopedRateThrottle

    ScopedRateThrottle.THROTTLE_RATES = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    try:
        c = APIClient()
        datos = {"username": "sup", "password": "incorrecta"}
        for _ in range(3):
            assert c.post(reverse("login"), datos, format="json").status_code == 401

        respuesta = c.post(reverse("login"), datos, format="json")

        assert respuesta.status_code == 429
        assert int(respuesta["Retry-After"]) > 0
    finally:
        from rest_framework.settings import api_settings

        ScopedRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES


def test_el_api_responde_bajo_su_version_de_ruta(usuario):
    """TS30: el contrato vive bajo /api/v1/; una versión nueva conviviría en /api/v2/."""
    assert reverse("me").startswith("/api/v1/")
    c = APIClient()
    c.force_authenticate(user=usuario)
    assert c.get("/api/v2/auth/me/").status_code == 404
