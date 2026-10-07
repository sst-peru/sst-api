"""Pruebas del experimento A/B: asignación determinista e intervalo de confianza."""
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Company, Role
from apps.experiments.models import Assignment, Experiment
from apps.reports.models import Report, ReportKind, Severity

User = get_user_model()


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Pruebas SAC", ruc="20400000001", worker_count=40)


@pytest.fixture
def experimento(db):
    return Experiment.objects.create(
        key=Experiment.KEY_REPORT_FORM,
        name="Formulario rápido vs formulario largo",
        variants=["rapido", "largo"],
        is_active=True,
    )


@pytest.fixture
def supervisor(empresa):
    return User.objects.create_user(
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR
    )


def cliente(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def poblar(experimento, empresa, variante, reportes_por_usuario):
    """Crea un usuario por entrada y le asigna la variante con esa cantidad de reportes."""
    for indice, cantidad in enumerate(reportes_por_usuario):
        user = User.objects.create_user(
            username="%s%d" % (variante, indice), password="x",
            company=empresa, role=Role.OPERARIO,
        )
        Assignment.objects.create(experiment=experimento, user=user, variant=variante)
        for _ in range(cantidad):
            Report.objects.create(
                company=empresa, reported_by=user, kind=ReportKind.CONDICION,
                severity=Severity.MEDIA, form_variant=variante,
            )


# --- Asignación ---


def test_la_asignacion_es_determinista(experimento):
    """El mismo usuario cae siempre en la misma variante: es lo que hace reproducible el A/B."""
    primera = experimento.variant_for(42)
    assert all(experimento.variant_for(42) == primera for _ in range(20))


def test_la_asignacion_reparte_entre_las_dos_variantes(experimento):
    asignadas = {experimento.variant_for(i) for i in range(200)}
    assert asignadas == {"rapido", "largo"}


def test_my_variant_persiste_la_asignacion_y_no_la_cambia(experimento, supervisor):
    primera = cliente(supervisor).get(reverse("my-variant")).data["variant"]
    segunda = cliente(supervisor).get(reverse("my-variant")).data["variant"]

    assert primera == segunda
    assert Assignment.objects.filter(experiment=experimento, user=supervisor).count() == 1


# --- Permisos del experimento ---


def test_un_operario_no_puede_borrar_el_experimento(experimento, empresa):
    operario = User.objects.create_user(
        username="op", password="x", company=empresa, role=Role.OPERARIO
    )
    response = cliente(operario).delete(
        reverse("experiment-detail", args=[experimento.key])
    )

    assert response.status_code == 403
    assert Experiment.objects.filter(key=experimento.key).exists()


def test_un_operario_si_puede_leer_el_experimento(experimento, empresa):
    operario = User.objects.create_user(
        username="op2", password="x", company=empresa, role=Role.OPERARIO
    )
    assert cliente(operario).get(reverse("experiment-list")).status_code == 200


def test_un_administrador_puede_editar_el_experimento(experimento, empresa):
    admin = User.objects.create_user(
        username="adm", password="x", company=empresa, role=Role.ADMIN
    )
    response = cliente(admin).patch(
        reverse("experiment-detail", args=[experimento.key]),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200


# --- Resultados e intervalo de confianza ---


def test_los_usuarios_sin_reportes_cuentan_como_cero(experimento, empresa, supervisor):
    """Un asignado que no reportó nada es la observación que la hipótesis busca."""
    poblar(experimento, empresa, "rapido", [3, 0, 0])
    poblar(experimento, empresa, "largo", [1, 1])

    datos = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data
    rapido = next(r for r in datos["results"] if r["variant"] == "rapido")

    assert rapido["users"] == 3
    assert rapido["reports"] == 3
    assert rapido["reports_per_user"] == 1.0  # 3 reportes / 3 usuarios, no 3/1


def test_un_reporte_sin_variante_no_se_atribuye_a_ninguna(experimento, empresa, supervisor):
    """Los reportes anteriores al experimento no deben ensuciar la comparación."""
    poblar(experimento, empresa, "rapido", [2])
    autor = User.objects.get(username="rapido0")
    Report.objects.create(
        company=empresa, reported_by=autor, kind=ReportKind.ACTO,
        severity=Severity.BAJA, form_variant="",
    )

    datos = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data
    rapido = next(r for r in datos["results"] if r["variant"] == "rapido")

    assert rapido["reports"] == 2


def test_una_diferencia_pequena_sale_como_no_concluyente(experimento, empresa, supervisor):
    poblar(experimento, empresa, "rapido", [2, 1, 3])
    poblar(experimento, empresa, "largo", [1, 2, 2])

    comparacion = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data["comparison"]

    assert comparacion["conclusive"] is False
    assert comparacion["ci_low"] < 0 < comparacion["ci_high"]
    assert "no se distingue del azar" in comparacion["reading"]


def test_una_diferencia_grande_y_consistente_sale_como_concluyente(
    experimento, empresa, supervisor
):
    poblar(experimento, empresa, "rapido", [9, 10, 11, 10, 9, 10, 11, 10])
    poblar(experimento, empresa, "largo", [1, 0, 1, 1, 0, 1, 1, 0])

    comparacion = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data["comparison"]

    assert comparacion["conclusive"] is True
    assert comparacion["ci_low"] > 0
    assert comparacion["difference"] > 8


def test_con_un_solo_sujeto_por_variante_no_se_calcula_intervalo(
    experimento, empresa, supervisor
):
    poblar(experimento, empresa, "rapido", [5])
    poblar(experimento, empresa, "largo", [1])

    comparacion = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data["comparison"]

    assert comparacion["conclusive"] is False
    assert comparacion["difference"] is None
    assert "al menos dos sujetos" in comparacion["reading"]


def test_los_resultados_avisan_cuando_la_muestra_es_insuficiente(
    experimento, empresa, supervisor
):
    poblar(experimento, empresa, "rapido", [1, 1])
    poblar(experimento, empresa, "largo", [1, 1])

    datos = cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data

    assert datos["sample_sufficient"] is False
    assert datos["min_users_per_variant"] == 20


def test_los_resultados_avisan_si_la_empresa_es_de_demostracion(
    experimento, empresa, supervisor
):
    assert cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data["demo_data"] is False

    empresa.is_demo = True
    empresa.save()

    assert cliente(supervisor).get(
        reverse("experiment-results", args=[experimento.key])
    ).data["demo_data"] is True
