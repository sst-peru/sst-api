"""Pruebas del reporte de errores de los clientes (TS24)."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from apps.monitoring.models import ClientError

User = get_user_model()


@pytest.fixture
def operario(db):
    empresa = Company.objects.create(name="Obras SAC", ruc="20500000001", worker_count=5)
    return User.objects.create_user(
        username="op", password="x", company=empresa, role=Role.OPERARIO
    )


def reportar(cliente, **extra):
    datos = {
        "platform": "WEB",
        "app_version": "0.1.0",
        "message": "TypeError: x is undefined",
        "stack": "at ReportsPage (ReportsPage.tsx:42)",
        "url": "http://localhost:5173/reportes?search=Juan%20Perez",
    }
    datos.update(extra)
    return cliente.post(reverse("client-errors"), datos, format="json")


def test_el_error_queda_registrado_con_version_plataforma_y_traza(operario):
    c = APIClient()
    c.force_authenticate(user=operario)

    respuesta = reportar(c, HTTP_USER_AGENT="Firefox")

    assert respuesta.status_code == 204
    error = ClientError.objects.get()
    assert error.platform == "WEB"
    assert error.app_version == "0.1.0"
    assert "ReportsPage.tsx:42" in error.stack
    assert error.user == operario
    assert error.company == operario.company


def test_no_se_guarda_la_cadena_de_consulta(operario):
    reportar(APIClient())

    assert ClientError.objects.get().path == "/reportes"


def test_se_acepta_un_error_antes_de_iniciar_sesion(db):
    assert reportar(APIClient(), platform="ANDROID").status_code == 204
    assert ClientError.objects.get().user is None


def test_una_plataforma_desconocida_se_rechaza(db):
    assert reportar(APIClient(), platform="IOS").status_code == 400


def test_la_traza_larga_se_recorta(db):
    reportar(APIClient(), stack="x" * 20000)

    assert len(ClientError.objects.get().stack) == 8000
