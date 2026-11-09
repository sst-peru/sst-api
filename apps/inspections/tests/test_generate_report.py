"""Pruebas de la generación de un hallazgo desde una observación de la inspección (US120)."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Area, Company, Role
from apps.inspections.models import Inspection, InspectionSchedule, InspectionStatus
from apps.reports.models import Report, ReportKind, ReportStatus

User = get_user_model()


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Obras del Norte SAC", ruc="20500000001", worker_count=50)


@pytest.fixture
def area(empresa):
    return Area.objects.create(company=empresa, name="Almacén")


@pytest.fixture
def supervisor(empresa):
    return User.objects.create_user(
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR
    )


@pytest.fixture
def inspeccion(empresa, area):
    programa = InspectionSchedule.objects.create(
        company=empresa, area=area, title="Orden y limpieza", frequency="MENSUAL",
        checklist=["Pasillos despejados", "Extintor accesible"],
    )
    return Inspection.objects.create(schedule=programa, due_date=timezone.localdate())


def cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def generar(user, inspeccion, **extra):
    datos = {
        "item": "Extintor accesible",
        "description": "El extintor está tapado por cajas.",
        "severity": "ALTA",
    }
    datos.update(extra)
    return cliente(user).post(
        reverse("inspection-generate-report", args=[inspeccion.id]), datos, format="json"
    )


def realizar(user, inspeccion):
    cliente(user).post(
        reverse("inspection-complete", args=[inspeccion.id]),
        {"findings": "Extintor tapado", "results": {"Extintor accesible": False}},
        format="json",
    )


def test_la_observacion_se_convierte_en_hallazgo_enlazado(supervisor, inspeccion, area):
    realizar(supervisor, inspeccion)

    respuesta = generar(supervisor, inspeccion)

    assert respuesta.status_code == 201
    reporte = Report.objects.get()
    assert reporte.source_inspection == inspeccion
    assert reporte.kind == ReportKind.CONDICION
    assert reporte.area == area
    assert reporte.status == ReportStatus.ABIERTO
    assert reporte.description.startswith("[Extintor accesible]")
    assert respuesta.data["source_inspection_label"].startswith("Orden y limpieza del")
    assert reporte.actions.count() == 1


def test_la_inspeccion_lista_los_hallazgos_que_genero(supervisor, inspeccion):
    realizar(supervisor, inspeccion)
    generar(supervisor, inspeccion)
    generar(supervisor, inspeccion, item="", description="Pasillo con derrame de aceite.")

    datos = cliente(supervisor).get(reverse("inspection-detail", args=[inspeccion.id])).data

    assert len(datos["generated_reports"]) == 2


def test_no_se_genera_hallazgo_de_una_inspeccion_sin_realizar(supervisor, inspeccion):
    assert generar(supervisor, inspeccion).status_code == 400
    assert inspeccion.status == InspectionStatus.PENDIENTE


def test_la_descripcion_es_obligatoria(supervisor, inspeccion):
    realizar(supervisor, inspeccion)

    assert generar(supervisor, inspeccion, description="").status_code == 400
