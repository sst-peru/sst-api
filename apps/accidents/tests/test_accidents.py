"""Pruebas del registro de accidentes, su investigación y sus medidas correctivas.

El foco está en las reglas que vienen de la Ley N° 29783: el plazo de 24 horas para avisar
al Ministerio de Trabajo, la obligación de llegar a la causa raíz antes de cerrar y la
separación entre quien ejecuta una medida correctiva y quien la verifica.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accidents.models import (
    Accident,
    AccidentKind,
    AccidentSeverity,
    AccidentStatus,
    CorrectiveMeasure,
    MeasureStatus,
    OccupationalDisease,
)
from apps.accounts.models import Area, Company, Role

User = get_user_model()


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Obras del Norte SAC", ruc="20500000001", worker_count=50)


@pytest.fixture
def otra_empresa(db):
    return Company.objects.create(name="Ajena SAC", ruc="20500000002", worker_count=10)


@pytest.fixture
def area(empresa):
    return Area.objects.create(company=empresa, name="Obra Civil")


@pytest.fixture
def supervisor(empresa):
    return User.objects.create_user(
        username="sup", password="x", company=empresa, role=Role.SUPERVISOR,
        first_name="Ana", last_name="Torres",
    )


@pytest.fixture
def comite(empresa):
    return User.objects.create_user(
        username="com", password="x", company=empresa, role=Role.COMITE,
        first_name="Luis", last_name="Ramos",
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


def datos_accidente(**extra):
    base = {
        "kind": AccidentKind.ACCIDENTE,
        "severity": AccidentSeverity.INCAPACITANTE,
        "description": "Caída desde andamio sin línea de vida en el nivel 3.",
        "injured_name": "Pedro Huamán",
        "lost_days": 12,
        "occurred_at": (timezone.now() - timedelta(hours=3)).isoformat(),
    }
    base.update(extra)
    return base


def crear_accidente(user, **extra):
    return cliente(user).post(reverse("accident-list"), datos_accidente(**extra), format="json")


# --- Registro ---


def test_un_operario_puede_registrar_un_accidente(operario, area):
    """El hecho ocurre en campo, así que el registro no puede estar reservado al manager."""
    response = crear_accidente(operario, area=area.id)

    assert response.status_code == 201
    accidente = Accident.objects.get()
    assert accidente.company_id == operario.company_id
    assert accidente.reported_by_id == operario.id
    assert accidente.status == AccidentStatus.REGISTRADO
    assert response.data["injured_label"] == "Pedro Huamán"


def test_el_registro_es_idempotente_por_client_uuid(operario):
    """Reintentar la sincronización del celular no puede duplicar el accidente."""
    uuid = "5d2f7b3a-0000-4000-8000-000000000001"
    primera = crear_accidente(operario, client_uuid=uuid)
    segunda = crear_accidente(operario, client_uuid=uuid)

    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert Accident.objects.count() == 1


def test_no_se_admite_un_accidente_con_fecha_futura(operario):
    response = crear_accidente(operario, occurred_at=(timezone.now() + timedelta(days=1)).isoformat())

    assert response.status_code == 400
    assert "no puede estar en el futuro" in str(response.data["occurred_at"][0])


def test_un_incidente_peligroso_no_puede_ser_mortal(operario):
    """Por definición del reglamento es el suceso que pudo causar lesiones y no las causó."""
    response = crear_accidente(
        operario, kind=AccidentKind.INCIDENTE_PELIGROSO, severity=AccidentSeverity.MORTAL
    )

    assert response.status_code == 400
    assert "no puede ser mortal" in str(response.data["severity"][0])


def test_un_accidente_de_trabajo_exige_decir_quien_se_accidento(operario):
    datos = datos_accidente()
    datos.pop("injured_name")
    response = cliente(operario).post(reverse("accident-list"), datos, format="json")

    assert response.status_code == 400
    assert "Indica quién se accidentó" in str(response.data["injured_name"][0])


def test_un_accidente_con_dias_perdidos_no_puede_ser_leve(operario):
    response = crear_accidente(operario, severity=AccidentSeverity.LEVE, lost_days=5)

    assert response.status_code == 400
    assert "incapacitante o mortal" in str(response.data["severity"][0])


def test_un_incidente_peligroso_no_necesita_accidentado(operario):
    datos = datos_accidente(kind=AccidentKind.INCIDENTE_PELIGROSO, severity=AccidentSeverity.LEVE, lost_days=0)
    datos.pop("injured_name")
    response = cliente(operario).post(reverse("accident-list"), datos, format="json")

    assert response.status_code == 201


def test_el_dni_del_accidentado_debe_tener_ocho_digitos(operario):
    response = crear_accidente(operario, injured_dni="1234567")

    assert response.status_code == 400
    assert "8 dígitos" in str(response.data["injured_dni"][0])


def test_no_se_puede_referenciar_un_area_de_otra_empresa(operario, otra_empresa):
    ajena = Area.objects.create(company=otra_empresa, name="Ajena")
    response = crear_accidente(operario, area=ajena.id)

    assert response.status_code == 400
    assert "no pertenece a tu empresa" in str(response.data["area"][0])


def test_un_accidente_registrado_no_se_elimina(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = cliente(supervisor).delete(reverse("accident-detail", args=[accidente.id]))

    assert response.status_code == 403
    assert Accident.objects.filter(id=accidente.id).exists()


# --- Visibilidad ---


def test_el_operario_solo_ve_los_accidentes_que_lo_involucran(operario, supervisor, empresa):
    crear_accidente(operario)
    otro = User.objects.create_user(
        username="otro", password="x", company=empresa, role=Role.OPERARIO
    )
    crear_accidente(otro)

    assert len(cliente(operario).get(reverse("accident-list")).data["results"]) == 1
    assert len(cliente(supervisor).get(reverse("accident-list")).data["results"]) == 2


def test_un_accidente_de_otra_empresa_no_es_visible(supervisor, otra_empresa, operario):
    ajeno = User.objects.create_user(
        username="ajeno", password="x", company=otra_empresa, role=Role.OPERARIO
    )
    crear_accidente(ajeno)
    crear_accidente(operario)

    resultados = cliente(supervisor).get(reverse("accident-list")).data["results"]
    assert len(resultados) == 1


# --- Plazo de aviso al Ministerio de Trabajo (artículo 82) ---


@pytest.mark.parametrize(
    "kind,severity,exige_aviso",
    [
        (AccidentKind.ACCIDENTE, AccidentSeverity.MORTAL, True),
        (AccidentKind.INCIDENTE_PELIGROSO, AccidentSeverity.LEVE, True),
        (AccidentKind.ACCIDENTE, AccidentSeverity.INCAPACITANTE, False),
        (AccidentKind.ACCIDENTE, AccidentSeverity.LEVE, False),
    ],
)
def test_solo_el_mortal_y_el_incidente_peligroso_tienen_plazo_de_24_horas(
    operario, kind, severity, exige_aviso
):
    datos = datos_accidente(kind=kind, severity=severity, lost_days=0)
    response = cliente(operario).post(reverse("accident-list"), datos, format="json")

    assert response.status_code == 201
    assert response.data["requires_immediate_notice"] is exige_aviso
    assert (response.data["notice_deadline"] is not None) is exige_aviso


def test_el_plazo_vence_24_horas_despues_de_la_ocurrencia(operario):
    ocurrio = timezone.now() - timedelta(hours=2)
    crear_accidente(operario, severity=AccidentSeverity.MORTAL, occurred_at=ocurrio.isoformat())
    accidente = Accident.objects.get()

    assert accidente.notice_deadline == accidente.occurred_at + timedelta(hours=24)
    assert accidente.notice_overdue is False
    assert 21 < accidente.notice_hours_left < 23


def test_un_mortal_sin_aviso_pasadas_las_24_horas_queda_marcado_como_vencido(operario):
    crear_accidente(
        operario,
        severity=AccidentSeverity.MORTAL,
        occurred_at=(timezone.now() - timedelta(hours=30)).isoformat(),
    )
    accidente = Accident.objects.get()

    assert accidente.notice_overdue is True
    assert accidente.notice_hours_left < 0


def test_registrar_el_aviso_al_mtpe_apaga_la_alerta(supervisor, operario):
    crear_accidente(operario, severity=AccidentSeverity.MORTAL)
    accidente = Accident.objects.get()

    response = cliente(supervisor).post(
        reverse("accident-notify-mtpe", args=[accidente.id]),
        {"notice_code": "CARGO-2026-0041"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["mtpe_notice_code"] == "CARGO-2026-0041"
    assert response.data["notice_overdue"] is False
    accidente.refresh_from_db()
    assert accidente.mtpe_notified_at is not None


def test_un_aviso_fuera_de_plazo_queda_registrado_como_tardio(supervisor, operario):
    """Avisar tarde no borra el incumplimiento: queda la constancia."""
    crear_accidente(
        operario,
        severity=AccidentSeverity.MORTAL,
        occurred_at=(timezone.now() - timedelta(hours=40)).isoformat(),
    )
    accidente = Accident.objects.get()

    cliente(supervisor).post(
        reverse("accident-notify-mtpe", args=[accidente.id]), {}, format="json"
    )
    accidente.refresh_from_db()

    assert accidente.notified_late is True


def test_no_se_registra_aviso_de_24_horas_en_un_accidente_que_no_lo_requiere(supervisor, operario):
    crear_accidente(operario, severity=AccidentSeverity.INCAPACITANTE)
    accidente = Accident.objects.get()

    response = cliente(supervisor).post(
        reverse("accident-notify-mtpe", args=[accidente.id]), {}, format="json"
    )

    assert response.status_code == 400
    assert "artículo 82" in str(response.data["detail"])


def test_el_operario_no_registra_el_aviso_al_mtpe(operario):
    crear_accidente(operario, severity=AccidentSeverity.MORTAL)
    accidente = Accident.objects.get()

    response = cliente(operario).post(
        reverse("accident-notify-mtpe", args=[accidente.id]), {}, format="json"
    )

    assert response.status_code == 403


# --- Investigación de causa raíz ---


def investigar(user, accidente, **extra):
    datos = {"root_cause": "Falta de línea de vida y de supervisión del trabajo en altura."}
    datos.update(extra)
    return cliente(user).post(
        reverse("accident-investigate", args=[accidente.id]), datos, format="json"
    )


def test_la_investigacion_pasa_el_accidente_a_en_investigacion(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = investigar(supervisor, accidente, immediate_causes="Andamio sin anclaje.")

    assert response.status_code == 200
    assert response.data["status"] == AccidentStatus.EN_INVESTIGACION
    assert response.data["investigation"]["root_cause"].startswith("Falta de línea")
    assert response.data["investigation"]["performed_by"] == supervisor.id


def test_la_investigacion_exige_causa_raiz(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = cliente(supervisor).post(
        reverse("accident-investigate", args=[accidente.id]),
        {"immediate_causes": "El trabajador se distrajo."},
        format="json",
    )

    assert response.status_code == 400
    assert "causa raíz es obligatoria" in str(response.data["root_cause"][0])


def test_un_accidente_no_se_investiga_dos_veces(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    investigar(supervisor, accidente)

    response = investigar(supervisor, accidente)

    assert response.status_code == 400
    assert "ya tiene investigación" in str(response.data["detail"])


def test_el_operario_no_investiga(operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    assert investigar(operario, accidente).status_code == 403


# --- Medidas correctivas ---


def crear_medida(user, accidente, responsable, **extra):
    datos = {
        "accident": accidente.id,
        "description": "Instalar líneas de vida certificadas en los tres niveles.",
        "responsible": responsable.id,
        "due_date": (timezone.localdate() + timedelta(days=15)).isoformat(),
    }
    datos.update(extra)
    return cliente(user).post(reverse("corrective-measure-list"), datos, format="json")


def test_una_medida_correctiva_necesita_responsable_y_plazo(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = cliente(supervisor).post(
        reverse("corrective-measure-list"),
        {"accident": accidente.id, "description": "Capacitar al personal."},
        format="json",
    )

    assert response.status_code == 400
    assert "responsible" in response.data
    assert "due_date" in response.data


def test_el_plazo_no_puede_ser_anterior_al_accidente(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = crear_medida(
        supervisor, accidente, operario,
        due_date=(accidente.occurred_at.date() - timedelta(days=1)).isoformat(),
    )

    assert response.status_code == 400
    assert "anterior a la fecha del accidente" in str(response.data["due_date"][0])


def test_el_responsable_debe_ser_de_la_empresa(supervisor, operario, otra_empresa):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    ajeno = User.objects.create_user(
        username="ajeno2", password="x", company=otra_empresa, role=Role.SUPERVISOR
    )

    response = crear_medida(supervisor, accidente, ajeno)

    assert response.status_code == 400
    assert "no pertenece a tu empresa" in str(response.data["responsible"][0])


def test_el_operario_no_crea_medidas_correctivas(operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    assert crear_medida(operario, accidente, operario).status_code == 403


def test_el_responsable_marca_su_medida_como_implementada(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    crear_medida(supervisor, accidente, operario)
    medida = CorrectiveMeasure.objects.get()

    response = cliente(operario).post(reverse("corrective-measure-complete", args=[medida.id]))

    assert response.status_code == 200
    assert response.data["status"] == MeasureStatus.IMPLEMENTADA
    assert response.data["completed_at"] is not None


def test_quien_ejecuta_la_medida_no_la_verifica(supervisor, operario):
    """Separación de responsabilidades: nadie da por buena su propia medida."""
    crear_accidente(operario)
    accidente = Accident.objects.get()
    crear_medida(supervisor, accidente, supervisor)
    medida = CorrectiveMeasure.objects.get()
    cliente(supervisor).post(reverse("corrective-measure-complete", args=[medida.id]))

    response = cliente(supervisor).post(reverse("corrective-measure-verify", args=[medida.id]))

    assert response.status_code == 400
    assert "distinto del responsable" in str(response.data["detail"])


def test_no_se_verifica_una_medida_que_no_se_implemento(supervisor, comite, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    crear_medida(supervisor, accidente, operario)
    medida = CorrectiveMeasure.objects.get()

    response = cliente(comite).post(reverse("corrective-measure-verify", args=[medida.id]))

    assert response.status_code == 400
    assert "todavía no se implementó" in str(response.data["detail"])


def test_un_manager_distinto_verifica_la_medida(supervisor, comite, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    crear_medida(supervisor, accidente, operario)
    medida = CorrectiveMeasure.objects.get()
    cliente(operario).post(reverse("corrective-measure-complete", args=[medida.id]))

    response = cliente(comite).post(reverse("corrective-measure-verify", args=[medida.id]))

    assert response.status_code == 200
    assert response.data["status"] == MeasureStatus.VERIFICADA
    assert response.data["verified_by"] == comite.id


def test_una_medida_vencida_se_marca_como_tal(supervisor, operario):
    crear_accidente(operario, occurred_at=(timezone.now() - timedelta(days=30)).isoformat())
    accidente = Accident.objects.get()
    crear_medida(
        supervisor, accidente, operario,
        due_date=(timezone.localdate() - timedelta(days=3)).isoformat(),
    )

    assert CorrectiveMeasure.objects.get().overdue is True


# --- Cierre del expediente ---


def test_no_se_cierra_un_accidente_sin_investigacion(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()

    response = cliente(supervisor).post(reverse("accident-close", args=[accidente.id]))

    assert response.status_code == 400
    assert "sin investigación de causa raíz" in str(response.data["detail"])


def test_no_se_cierra_un_accidente_con_medidas_sin_verificar(supervisor, operario):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    investigar(supervisor, accidente)
    crear_medida(supervisor, accidente, operario)

    response = cliente(supervisor).post(reverse("accident-close", args=[accidente.id]))

    assert response.status_code == 400
    assert "sin verificar" in str(response.data["detail"])


def test_con_investigacion_y_medidas_verificadas_el_accidente_se_cierra(
    supervisor, comite, operario
):
    crear_accidente(operario)
    accidente = Accident.objects.get()
    investigar(supervisor, accidente)
    crear_medida(supervisor, accidente, operario)
    medida = CorrectiveMeasure.objects.get()
    cliente(operario).post(reverse("corrective-measure-complete", args=[medida.id]))
    cliente(comite).post(reverse("corrective-measure-verify", args=[medida.id]))

    response = cliente(supervisor).post(reverse("accident-close", args=[accidente.id]))

    assert response.status_code == 200
    assert response.data["status"] == AccidentStatus.CERRADO
    assert response.data["closed_at"] is not None


# --- Enfermedades ocupacionales ---


def datos_enfermedad(**extra):
    base = {
        "worker_name": "Rosa Flores",
        "diagnosis": "Hipoacusia neurosensorial inducida por ruido",
        "cie10_code": "H83.3",
        "causal_agent": "Ruido continuo sobre 85 dB",
        "exposure_months": 36,
        "diagnosed_on": timezone.localdate().isoformat(),
        "rest_days": 0,
    }
    base.update(extra)
    return base


def test_un_manager_registra_una_enfermedad_ocupacional(supervisor):
    response = cliente(supervisor).post(
        reverse("occupational-disease-list"), datos_enfermedad(), format="json"
    )

    assert response.status_code == 201
    enfermedad = OccupationalDisease.objects.get()
    assert enfermedad.company_id == supervisor.company_id
    assert enfermedad.reported_by_id == supervisor.id
    assert response.data["worker_label"] == "Rosa Flores"


def test_el_operario_no_accede_al_registro_de_enfermedades(operario):
    """Es dato de salud de sus compañeros."""
    response = cliente(operario).get(reverse("occupational-disease-list"))

    assert response.status_code == 403
    assert "datos de salud" in str(response.data["detail"])


def test_la_enfermedad_no_puede_tener_fecha_de_diagnostico_futura(supervisor):
    response = cliente(supervisor).post(
        reverse("occupational-disease-list"),
        datos_enfermedad(diagnosed_on=(timezone.localdate() + timedelta(days=2)).isoformat()),
        format="json",
    )

    assert response.status_code == 400
    assert "no puede estar en el futuro" in str(response.data["diagnosed_on"][0])


def test_la_enfermedad_exige_decir_de_que_trabajador_es(supervisor):
    datos = datos_enfermedad()
    datos.pop("worker_name")
    response = cliente(supervisor).post(
        reverse("occupational-disease-list"), datos, format="json"
    )

    assert response.status_code == 400
    assert "qué trabajador" in str(response.data["worker_name"][0])


# --- Índices de accidentabilidad (R.M. N° 050-2013-TR) ---


def test_los_indices_se_calculan_con_las_horas_hombre_informadas(supervisor, operario):
    """Con 1 incapacitante, 10 dias perdidos y 100 000 HHT los indices son exactos."""
    crear_accidente(operario, severity=AccidentSeverity.INCAPACITANTE, lost_days=10)

    response = cliente(supervisor).get(
        reverse("metrics-accident-rates"), {"days": 90, "hours_worked": 100000}
    )

    assert response.status_code == 200
    assert response.data["disabling"] == 1
    assert response.data["lost_days"] == 10
    assert response.data["hours_worked_estimated"] is False
    # 1 x 1 000 000 / 100 000 = 10 ; 10 x 1 000 000 / 100 000 = 100 ; 10 x 100 / 1000 = 1
    assert response.data["frequency_index"] == 10
    assert response.data["severity_index"] == 100
    assert response.data["accident_rate_index"] == 1


def test_sin_horas_informadas_los_indices_se_marcan_como_estimados(supervisor):
    response = cliente(supervisor).get(reverse("metrics-accident-rates"), {"days": 30})

    assert response.status_code == 200
    assert response.data["hours_worked_estimated"] is True
    assert response.data["hours_worked"] > 0


def test_los_accidentes_leves_no_entran_en_el_indice_de_frecuencia(supervisor, operario):
    """El indice cuenta accidentes con baja: incapacitantes y mortales."""
    crear_accidente(operario, severity=AccidentSeverity.LEVE, lost_days=0)

    response = cliente(supervisor).get(
        reverse("metrics-accident-rates"), {"hours_worked": 100000}
    )

    assert response.data["minor"] == 1
    assert response.data["frequency_index"] == 0


def test_los_indices_informan_los_avisos_vencidos(supervisor, operario):
    crear_accidente(
        operario,
        severity=AccidentSeverity.MORTAL,
        occurred_at=(timezone.now() - timedelta(hours=48)).isoformat(),
    )

    response = cliente(supervisor).get(
        reverse("metrics-accident-rates"), {"hours_worked": 100000}
    )

    assert response.data["fatal"] == 1
    assert response.data["overdue_notices"] == 1


@pytest.mark.parametrize("valor", ["0", "-5", "abc"])
def test_los_indices_rechazan_una_ventana_invalida(supervisor, valor):
    response = cliente(supervisor).get(reverse("metrics-accident-rates"), {"days": valor})

    assert response.status_code == 400
    assert "days" in response.data
