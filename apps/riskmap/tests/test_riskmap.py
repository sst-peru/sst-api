"""Pruebas del mapa de riesgos y del inventario de señalización."""
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Area, Company, Role
from apps.riskmap.models import RiskMap, SafetySign

User = get_user_model()


@pytest.fixture(autouse=True)
def _media_temporal(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Obras del Norte SAC", ruc="20500000001", worker_count=50)


@pytest.fixture
def otra_empresa(db):
    return Company.objects.create(name="Ajena SAC", ruc="20500000002", worker_count=10)


@pytest.fixture
def area(empresa):
    return Area.objects.create(company=empresa, name="Almacén")


@pytest.fixture
def supervisor(empresa):
    return User.objects.create_user(
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR
    )


@pytest.fixture
def operario(empresa):
    return User.objects.create_user(
        username="op", password="x", company=empresa, role=Role.OPERARIO
    )


def cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def plano():
    buffer = BytesIO()
    Image.new("RGB", (40, 30), "white").save(buffer, format="PNG")
    return SimpleUploadedFile("plano.png", buffer.getvalue(), content_type="image/png")


def publicar(user, area, titulo="Plano del almacén"):
    return cliente(user).post(
        reverse("risk-map-list"),
        {"area": area.id, "title": titulo, "plan": plano()},
        format="multipart",
    )


def test_el_supervisor_publica_el_mapa_de_un_area(supervisor, area):
    respuesta = publicar(supervisor, area)

    assert respuesta.status_code == 201
    assert respuesta.data["is_current"] is True
    assert respuesta.data["plan"].endswith(".png")


def test_el_operario_consulta_el_mapa_pero_no_lo_publica(supervisor, operario, area):
    publicar(supervisor, area)

    assert cliente(operario).get(reverse("risk-map-list")).data["count"] == 1
    assert publicar(operario, area).status_code == 403


def test_publicar_otro_mapa_deja_el_anterior_como_historico(supervisor, area):
    primero = publicar(supervisor, area, "Versión 1").data["id"]
    segundo = publicar(supervisor, area, "Versión 2").data["id"]

    vigentes = cliente(supervisor).get(reverse("risk-map-list"), {"current": "true"}).data

    assert [m["id"] for m in vigentes["results"]] == [segundo]
    assert RiskMap.objects.get(id=primero).is_current is False


def test_se_ubican_los_riesgos_sobre_el_plano(supervisor, area):
    mapa_id = publicar(supervisor, area).data["id"]

    respuesta = cliente(supervisor).put(
        reverse("risk-map-markers", args=[mapa_id]),
        [
            {"kind": "ELECTRICO", "label": "Tablero eléctrico", "x": "12.5", "y": "40"},
            {"kind": "CAIDA", "label": "Desnivel en la rampa", "x": "70", "y": "85.25"},
        ],
        format="json",
    )

    assert respuesta.status_code == 200
    assert len(respuesta.data) == 2
    assert respuesta.data[0]["kind_display"] == "Eléctrico"


def test_una_posicion_fuera_del_plano_se_rechaza(supervisor, area):
    mapa_id = publicar(supervisor, area).data["id"]

    respuesta = cliente(supervisor).put(
        reverse("risk-map-markers", args=[mapa_id]),
        [{"kind": "CAIDA", "label": "Fuera", "x": "120", "y": "10"}],
        format="json",
    )

    assert respuesta.status_code == 400


def test_no_se_publica_el_mapa_de_un_area_ajena(supervisor, otra_empresa):
    ajena = Area.objects.create(company=otra_empresa, name="Ajena")

    assert publicar(supervisor, ajena).status_code == 400


def test_el_inventario_resume_lo_que_falta_y_lo_observado(supervisor, area):
    for estado in ("BUENO", "BUENO", "DETERIORADA", "FALTANTE"):
        cliente(supervisor).post(
            reverse("sign-list"),
            {"area": area.id, "kind": "EVACUACION", "description": "Salida", "status": estado},
            format="json",
        )

    resumen = cliente(supervisor).get(reverse("signs-summary")).data

    assert resumen == [
        {"area": area.id, "area_name": "Almacén", "expected": 4, "installed": 3, "observed": 2}
    ]


def test_el_inventario_no_se_ve_entre_empresas(supervisor, otra_empresa):
    ajena = Area.objects.create(company=otra_empresa, name="Ajena")
    SafetySign.objects.create(area=ajena, kind="OBLIGACION", description="Use casco")

    assert cliente(supervisor).get(reverse("sign-list")).data["count"] == 0
