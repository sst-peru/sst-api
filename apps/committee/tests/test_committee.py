from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from apps.committee.models import (
    AgreementStatus,
    Committee,
    CommitteeMember,
    Meeting,
    MemberRole,
    Represents,
)

User = get_user_model()


@pytest.fixture
def company(db):
    return Company.objects.create(name="Demo SAC", ruc="20100000002", worker_count=45)


@pytest.fixture
def supervisor(company):
    return User.objects.create_user(
        username="sup", password="x", company=company, role=Role.SUPERVISOR
    )


@pytest.fixture
def operario(company):
    return User.objects.create_user(
        username="op", password="x", company=company, role=Role.OPERARIO
    )


def auth(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def comite(company, supervisor):
    return Committee.objects.create(
        company=company,
        period_start=timezone.localdate(),
        period_end=timezone.localdate() + timedelta(days=730),
    )


def test_supervisor_registra_el_comite(supervisor):
    response = auth(supervisor).post(
        reverse("committee-list"),
        {
            "period_start": timezone.localdate().isoformat(),
            "period_end": (timezone.localdate() + timedelta(days=730)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 201
    # Con 45 trabajadores la ley pide comité, no supervisor único.
    assert response.data["is_supervisor_mode"] is False


def test_operario_no_registra_el_comite(operario):
    response = auth(operario).post(
        reverse("committee-list"),
        {
            "period_start": timezone.localdate().isoformat(),
            "period_end": (timezone.localdate() + timedelta(days=730)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 403


def test_no_se_puede_registrar_dos_comites(supervisor, comite):
    response = auth(supervisor).post(
        reverse("committee-list"),
        {
            "period_start": timezone.localdate().isoformat(),
            "period_end": (timezone.localdate() + timedelta(days=730)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 400


def test_numero_de_acta_es_consecutivo_y_lo_pone_el_servidor(supervisor, comite):
    client = auth(supervisor)
    primera = client.post(
        reverse("committee-meeting-list"),
        {"date": timezone.localdate().isoformat(), "number": 99, "agenda": "Primera"},
        format="json",
    )
    segunda = client.post(
        reverse("committee-meeting-list"),
        {"date": timezone.localdate().isoformat(), "agenda": "Segunda"},
        format="json",
    )
    assert primera.status_code == 201
    assert segunda.status_code == 201
    # El 99 que mandó el cliente se ignora: el consecutivo lo decide el servidor.
    assert primera.data["number"] == 1
    assert segunda.data["number"] == 2


def test_comite_paritario_y_quorum(comite, supervisor, operario, company):
    trabajador2 = User.objects.create_user(
        username="t2", password="x", company=company, role=Role.COMITE
    )
    empleador2 = User.objects.create_user(
        username="e2", password="x", company=company, role=Role.COMITE
    )
    for user, cargo, representa in [
        (supervisor, MemberRole.PRESIDENTE, Represents.EMPLEADOR),
        (empleador2, MemberRole.TITULAR, Represents.EMPLEADOR),
        (operario, MemberRole.SECRETARIO, Represents.TRABAJADORES),
        (trabajador2, MemberRole.TITULAR, Represents.TRABAJADORES),
    ]:
        CommitteeMember.objects.create(
            committee=comite, user=user, role=cargo, represents=representa
        )

    assert comite.is_paritario is True
    # 4 titulares -> quorum de 3 (mitad mas uno)
    assert comite.quorum_required == 3


def test_acta_sin_quorum_queda_marcada(comite, supervisor, operario, company):
    for user, cargo, representa in [
        (supervisor, MemberRole.PRESIDENTE, Represents.EMPLEADOR),
        (operario, MemberRole.SECRETARIO, Represents.TRABAJADORES),
    ]:
        CommitteeMember.objects.create(
            committee=comite, user=user, role=cargo, represents=representa
        )
    acta = Meeting.objects.create(committee=comite, number=1, date=timezone.localdate())
    assert acta.quorum_reached is False

    acta.attendees.set(comite.members.all())
    assert acta.quorum_reached is True


def test_cumplimiento_del_comite(supervisor, comite):
    client = auth(supervisor)
    acta = client.post(
        reverse("committee-meeting-list"),
        {"date": timezone.localdate().isoformat(), "agenda": "Revisión mensual"},
        format="json",
    ).data
    client.post(
        reverse("committee-agreement-list"),
        {
            "meeting": acta["id"],
            "description": "Reponer extintores vencidos",
            "status": AgreementStatus.CUMPLIDO,
        },
        format="json",
    )
    client.post(
        reverse("committee-agreement-list"),
        {
            "meeting": acta["id"],
            "description": "Capacitar en trabajo en altura",
            "status": AgreementStatus.PENDIENTE,
        },
        format="json",
    )

    response = client.get(reverse("committee-compliance"))
    assert response.status_code == 200
    assert response.data["has_committee"] is True
    assert response.data["meetings_total"] == 1
    assert response.data["agreements_total"] == 2
    assert response.data["agreements_done"] == 1
    assert response.data["agreements_compliance_pct"] == 50.0


def test_sin_comite_el_endpoint_lo_dice(supervisor):
    response = auth(supervisor).get(reverse("committee-compliance"))
    assert response.status_code == 200
    assert response.data["has_committee"] is False
