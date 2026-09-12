import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Area, Company, Role
from apps.reports.models import Report, ReportStatus

User = get_user_model()


@pytest.fixture
def company(db):
    return Company.objects.create(name="Demo SAC", ruc="20100000001", worker_count=30)


@pytest.fixture
def area(company):
    return Area.objects.create(company=company, name="Obra Civil")


@pytest.fixture
def operario(company, area):
    return User.objects.create_user(
        username="op1", password="x", company=company, area=area, role=Role.OPERARIO
    )


@pytest.fixture
def supervisor(company):
    return User.objects.create_user(
        username="sup", password="x", company=company, role=Role.SUPERVISOR
    )


def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_operario_crea_reporte_minimo(operario, area):
    """El flujo rápido manda lo mínimo: tipo, área y foto. Nada más es obligatorio."""
    client = auth_client(operario)
    response = client.post(
        reverse("report-list"),
        {"kind": "CONDICION", "area": area.id, "form_variant": "rapido"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["status"] == ReportStatus.ABIERTO
    assert response.data["reported_by"] == operario.id


def test_sincronizacion_offline_no_duplica(operario, area):
    """Reenviar el mismo client_uuid devuelve el reporte existente, no crea otro."""
    client = auth_client(operario)
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "kind": "ACTO",
        "area": area.id,
        "synced_offline": True,
    }
    first = client.post(reverse("report-list"), payload, format="json")
    second = client.post(reverse("report-list"), payload, format="json")
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["id"] == second.data["id"]
    assert Report.objects.count() == 1


def test_operario_no_ve_reportes_de_otros(operario, supervisor, area, company):
    Report.objects.create(company=company, reported_by=supervisor, kind="ACTO", area=area)
    response = auth_client(operario).get(reverse("report-list"))
    assert response.status_code == 200
    assert response.data["count"] == 0


def test_operario_no_puede_cerrar(operario, area, company):
    report = Report.objects.create(company=company, reported_by=operario, kind="ACTO", area=area)
    response = auth_client(operario).post(
        reverse("report-close", args=[report.id]), {"closure_note": "listo"}, format="json"
    )
    assert response.status_code == 403


def test_supervisor_cierra_y_calcula_mttr(supervisor, operario, area, company):
    report = Report.objects.create(company=company, reported_by=operario, kind="ACTO", area=area)
    client = auth_client(supervisor)
    close = client.post(
        reverse("report-close", args=[report.id]),
        {"closure_note": "Se cambió el andamio"},
        format="json",
    )
    assert close.status_code == 200
    report.refresh_from_db()
    assert report.status == ReportStatus.CERRADO
    assert report.closed_at is not None
    assert report.resolution_hours is not None

    metrics = client.get(reverse("metrics-mttr"))
    assert metrics.status_code == 200
    assert metrics.data["closed_reports"] == 1
    assert metrics.data["mttr_hours"] is not None


def test_asignar_pasa_a_en_proceso(supervisor, operario, area, company):
    report = Report.objects.create(company=company, reported_by=operario, kind="ACTO", area=area)
    response = auth_client(supervisor).post(
        reverse("report-assign", args=[report.id]),
        {"assigned_to": supervisor.id, "note": "Lo veo hoy"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == ReportStatus.EN_PROCESO
    assert len(response.data["actions"]) == 1


def test_variante_es_estable_por_usuario(operario, db):
    from apps.experiments.models import Experiment

    exp = Experiment.objects.create(
        key="report_form", name="A/B", variants=["rapido", "largo"], is_active=True
    )
    primera = exp.variant_for(operario.id)
    assert primera in {"rapido", "largo"}
    assert primera == exp.variant_for(operario.id)


def test_occurred_at_puede_ser_anterior_al_registro(operario, area, company):
    """Caso offline real: el reporte ocurrió ayer en la mina y sincroniza hoy."""
    ayer = timezone.now() - timezone.timedelta(days=1)
    report = Report.objects.create(
        company=company, reported_by=operario, kind="CONDICION", area=area, occurred_at=ayer
    )
    assert report.occurred_at < report.created_at
