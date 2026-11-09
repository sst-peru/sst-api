"""Pruebas del programa de capacitación, la inducción y los simulacros."""
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Area, Company, Role
from apps.training.models import (
    Drill,
    Induction,
    TrainingAttendance,
    TrainingSession,
    TrainingStatus,
    sumar_meses,
)

User = get_user_model()


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
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR,
        first_name="Ana", last_name="Torres",
    )


@pytest.fixture
def operario(empresa):
    return User.objects.create_user(
        username="op", password="x", company=empresa, role=Role.OPERARIO,
        first_name="Jose", last_name="Quispe",
    )


@pytest.fixture
def operario2(empresa):
    return User.objects.create_user(
        username="op2", password="x", company=empresa, role=Role.OPERARIO,
        first_name="Rosa", last_name="Mamani",
    )


def cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def crear_sesion(user, **extra):
    datos = {
        "topic": "Trabajo en altura",
        "planned_date": str(timezone.localdate()),
        "audience": "Operarios de obra",
        "validity_months": 12,
    }
    datos.update(extra)
    return cliente(user).post(reverse("training-session-list"), datos, format="json")


def test_sumar_meses_respeta_el_fin_de_mes():
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert sumar_meses(date(2026, 11, 15), 12) == date(2027, 11, 15)


def test_el_supervisor_programa_una_capacitacion(supervisor):
    respuesta = crear_sesion(supervisor, responsible=supervisor.id, trainer="Bomberos Lima")

    assert respuesta.status_code == 201
    assert respuesta.data["status"] == TrainingStatus.PROGRAMADA
    assert respuesta.data["responsible_name"] == "Ana Torres"


def test_el_operario_consulta_el_programa_pero_no_lo_modifica(supervisor, operario):
    crear_sesion(supervisor)

    assert cliente(operario).get(reverse("training-session-list")).data["count"] == 1
    assert crear_sesion(operario).status_code == 403


def test_no_se_asigna_un_area_de_otra_empresa(supervisor, otra_empresa):
    ajena = Area.objects.create(company=otra_empresa, name="Ajena")

    assert crear_sesion(supervisor, area=ajena.id).status_code == 400


def test_registrar_asistencia_da_la_sesion_por_realizada(supervisor, operario, operario2):
    sesion_id = crear_sesion(supervisor).data["id"]
    url = reverse("training-session-attendance", args=[sesion_id])

    respuesta = cliente(supervisor).post(
        url, {"workers": [operario.id, operario2.id]}, format="json"
    )

    assert respuesta.status_code == 200
    assert len(respuesta.data) == 2
    sesion = TrainingSession.objects.get()
    assert sesion.status == TrainingStatus.REALIZADA
    assert sesion.held_on == timezone.localdate()


def test_registrar_dos_veces_no_duplica_la_asistencia(supervisor, operario):
    sesion_id = crear_sesion(supervisor).data["id"]
    url = reverse("training-session-attendance", args=[sesion_id])

    cliente(supervisor).post(url, {"workers": [operario.id]}, format="json")
    cliente(supervisor).post(url, {"workers": [operario.id]}, format="json")

    assert TrainingAttendance.objects.count() == 1


def test_no_se_registra_asistencia_de_otra_empresa(supervisor, otra_empresa):
    ajeno = User.objects.create_user(username="ajeno", password="x", company=otra_empresa)
    sesion_id = crear_sesion(supervisor).data["id"]

    respuesta = cliente(supervisor).post(
        reverse("training-session-attendance", args=[sesion_id]),
        {"workers": [ajeno.id]}, format="json",
    )

    assert respuesta.status_code == 400


def test_el_resumen_compara_con_el_minimo_anual(supervisor, operario):
    for _ in range(4):
        sesion_id = crear_sesion(supervisor).data["id"]
        cliente(supervisor).post(
            reverse("training-session-attendance", args=[sesion_id]),
            {"workers": [operario.id]}, format="json",
        )
    crear_sesion(supervisor)

    datos = cliente(supervisor).get(reverse("training-summary")).data

    assert datos["planned"] == 5
    assert datos["held"] == 4
    assert datos["meets_minimum"] is True


def test_la_alerta_lista_a_quien_no_tiene_capacitacion_vigente(supervisor, operario, operario2):
    hace_dos_anios = timezone.localdate() - timedelta(days=730)
    vencida = TrainingSession.objects.create(
        company=supervisor.company, topic="Antigua", planned_date=hace_dos_anios,
        audience="Todos", status=TrainingStatus.REALIZADA, held_on=hace_dos_anios,
    )
    TrainingAttendance.objects.create(session=vencida, worker=operario)
    vigente = TrainingSession.objects.create(
        company=supervisor.company, topic="Reciente", planned_date=timezone.localdate(),
        audience="Todos", status=TrainingStatus.REALIZADA, held_on=timezone.localdate(),
    )
    TrainingAttendance.objects.create(session=vigente, worker=supervisor)

    pendientes = {
        p["worker"]: p for p in cliente(supervisor).get(reverse("training-pending")).data
    }

    assert pendientes[operario.id]["reason"] == "VENCIDA"
    assert pendientes[operario2.id]["reason"] == "SIN_CAPACITACION"
    assert supervisor.id not in pendientes


def test_el_trabajador_ve_sus_capacitaciones_con_vigencia(supervisor, operario):
    sesion_id = crear_sesion(supervisor).data["id"]
    cliente(supervisor).post(
        reverse("training-session-attendance", args=[sesion_id]),
        {"workers": [operario.id]}, format="json",
    )

    datos = cliente(operario).get(reverse("training-mine")).data

    assert datos["trainings"][0]["is_valid"] is True
    assert datos["induction_on"] is None


def test_la_induccion_habilita_al_trabajador_y_sale_de_pendientes(supervisor, operario):
    pendientes = cliente(supervisor).get(reverse("induction-pending")).data
    assert operario.id in [p["worker"] for p in pendientes]

    respuesta = cliente(supervisor).post(
        reverse("induction-list"),
        {"worker": operario.id, "topics": "Peligros del almacén y rutas de evacuación"},
        format="json",
    )

    assert respuesta.status_code == 201
    assert Induction.objects.get().given_by == supervisor
    pendientes = cliente(supervisor).get(reverse("induction-pending")).data
    assert operario.id not in [p["worker"] for p in pendientes]


def test_no_se_registra_dos_veces_la_induccion(supervisor, operario):
    datos = {"worker": operario.id}
    cliente(supervisor).post(reverse("induction-list"), datos, format="json")

    assert cliente(supervisor).post(reverse("induction-list"), datos, format="json").status_code == 400


def test_el_supervisor_registra_un_simulacro(supervisor, area):
    respuesta = cliente(supervisor).post(
        reverse("drill-list"),
        {
            "kind": "SISMO", "held_on": str(timezone.localdate()), "area": area.id,
            "participants": 42, "evacuation_seconds": 185,
            "observations": "La salida 2 estuvo bloqueada por cajas.",
        },
        format="json",
    )

    assert respuesta.status_code == 201
    assert respuesta.data["kind_display"] == "Sismo"
    assert Drill.objects.get().registered_by == supervisor


def test_los_simulacros_no_se_ven_entre_empresas(supervisor, otra_empresa):
    Drill.objects.create(
        company=otra_empresa, kind="INCENDIO", held_on=timezone.localdate(), participants=5
    )

    assert cliente(supervisor).get(reverse("drill-list")).data["count"] == 0
