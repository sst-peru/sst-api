"""Pruebas de los documentos del SGSST, su versionado, la entrega del RISST y el plan anual."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from apps.documents.models import (
    AnnualPlan,
    Document,
    DocumentVersion,
    PlanActivity,
    VersionStatus,
)

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
def supervisor(empresa):
    return User.objects.create_user(
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR,
        first_name="Ana", last_name="Torres",
    )


@pytest.fixture
def operario(empresa):
    return User.objects.create_user(
        username="op", password="x", company=empresa, role=Role.OPERARIO,
        first_name="Jose", last_name="Quispe",
    )


def cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def crear_documento(user, **extra):
    datos = {"kind": "POLITICA", "title": "Política de SST"}
    datos.update(extra)
    return cliente(user).post(reverse("document-list"), datos, format="json")


def crear_version(user, documento_id, contenido="Nos comprometemos a proteger la vida."):
    return cliente(user).post(
        reverse("document-version-list"),
        {
            "document": documento_id, "content": contenido,
            "approved_by": "Gerente General, Luis Pérez",
            "approved_on": str(timezone.localdate()),
        },
        format="json",
    )


def publicar(user, version_id):
    return cliente(user).post(reverse("document-version-publish", args=[version_id]))


def test_la_politica_publicada_es_visible_para_todos(supervisor, operario):
    doc = crear_documento(supervisor).data["id"]
    version = crear_version(supervisor, doc).data["id"]

    # Mientras es borrador, el trabajador no la ve.
    assert cliente(operario).get(reverse("document-list")).data["count"] == 0

    assert publicar(supervisor, version).status_code == 200
    datos = cliente(operario).get(reverse("document-list")).data["results"][0]
    assert datos["current_version"]["approved_by"] == "Gerente General, Luis Pérez"
    assert datos["current_version"]["valid_from"] == str(timezone.localdate())


def test_el_operario_no_publica_documentos(operario):
    assert crear_documento(operario).status_code == 403


def test_publicar_una_version_nueva_deja_la_anterior_historica(supervisor):
    doc = crear_documento(supervisor).data["id"]
    v1 = crear_version(supervisor, doc).data
    publicar(supervisor, v1["id"])
    v2 = crear_version(supervisor, doc, "Texto revisado.").data
    publicar(supervisor, v2["id"])

    assert v2["number"] == 2
    anterior = DocumentVersion.objects.get(id=v1["id"])
    assert anterior.status == VersionStatus.HISTORICA
    assert anterior.valid_until == timezone.localdate()
    historial = cliente(supervisor).get(reverse("document-version-list"), {"document": doc})
    assert [v["number"] for v in historial.data["results"]] == [2, 1]


def test_una_version_vigente_no_se_edita(supervisor):
    doc = crear_documento(supervisor).data["id"]
    version = crear_version(supervisor, doc).data["id"]
    publicar(supervisor, version)

    respuesta = cliente(supervisor).patch(
        reverse("document-version-detail", args=[version]), {"content": "cambio"}, format="json"
    )

    assert respuesta.status_code == 400


def test_no_se_publica_una_version_vacia(supervisor):
    doc = crear_documento(supervisor).data["id"]
    version = crear_version(supervisor, doc, contenido="").data["id"]

    assert publicar(supervisor, version).status_code == 400


def test_el_trabajador_deja_constancia_de_recibir_el_risst(supervisor, operario):
    doc = crear_documento(supervisor, kind="RISST", title="RISST", requires_receipt=True).data["id"]
    publicar(supervisor, crear_version(supervisor, doc).data["id"])

    antes = cliente(supervisor).get(reverse("document-receipts", args=[doc])).data
    assert operario.id in [p["worker"] for p in antes["pending"]]

    respuesta = cliente(operario).post(reverse("document-acknowledge", args=[doc]))

    assert respuesta.status_code == 200
    assert respuesta.data["received_by_me"] is True
    despues = cliente(supervisor).get(reverse("document-receipts", args=[doc])).data
    assert despues["version"] == 1
    assert operario.id in [r["worker"] for r in despues["received"]]
    assert operario.id not in [p["worker"] for p in despues["pending"]]


def test_no_se_versiona_un_documento_de_otra_empresa(supervisor, otra_empresa):
    ajeno = Document.objects.create(company=otra_empresa, kind="POLITICA", title="Ajena")

    assert crear_version(supervisor, ajeno.id).status_code == 400


def test_el_plan_anual_mide_lo_ejecutado_frente_a_lo_programado(supervisor):
    anio = timezone.localdate().year
    mes = timezone.localdate().month
    plan = cliente(supervisor).post(
        reverse("sst-plan-list"),
        {"year": anio, "objectives": "Reducir accidentes incapacitantes en 20 %."},
        format="json",
    ).data
    for i, estado in enumerate(("EJECUTADA", "PENDIENTE")):
        cliente(supervisor).post(
            reverse("sst-plan-activity-list"),
            {"plan": plan["id"], "description": f"Actividad {i}", "planned_month": 1,
             "status": estado},
            format="json",
        )
    PlanActivity.objects.create(
        plan=AnnualPlan.objects.get(), description="Futura", planned_month=12
    )

    avance = cliente(supervisor).get(reverse("sst-plan-progress", args=[plan["id"]])).data

    assert avance["total"] == 3
    assert avance["programmed_to_date"] == (3 if mes == 12 else 2)
    assert avance["executed"] == 1


def test_marcar_ejecutada_registra_la_fecha(supervisor):
    plan = AnnualPlan.objects.create(company=supervisor.company, year=2026, objectives="x")
    actividad = PlanActivity.objects.create(plan=plan, description="Auditoría", planned_month=3)

    cliente(supervisor).patch(
        reverse("sst-plan-activity-detail", args=[actividad.id]),
        {"status": "EJECUTADA"}, format="json",
    )

    actividad.refresh_from_db()
    assert actividad.executed_on == timezone.localdate()


def test_no_hay_dos_planes_para_el_mismo_anio(supervisor):
    datos = {"year": 2026, "objectives": "x"}
    cliente(supervisor).post(reverse("sst-plan-list"), datos, format="json")

    assert cliente(supervisor).post(reverse("sst-plan-list"), datos, format="json").status_code == 400
