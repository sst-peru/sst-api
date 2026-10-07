import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Area, Company, Role

User = get_user_model()


@pytest.fixture
def company(db):
    return Company.objects.create(name="Los Andes SAC", ruc="20100000004", worker_count=45)


@pytest.fixture
def otra_empresa(db):
    return Company.objects.create(name="Otra SAC", ruc="20100000005", worker_count=10)


@pytest.fixture
def area(company):
    return Area.objects.create(company=company, name="Obra Civil")


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


def test_registro_publico_con_ruc(company, area):
    response = APIClient().post(
        reverse("register"),
        {
            "username": "nuevo",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "first_name": "Juan",
            "last_name": "Perez",
            "company_ruc": company.ruc,
            "area": area.id,
        },
        format="json",
    )
    assert response.status_code == 201
    creado = User.objects.get(username="nuevo")
    assert creado.company_id == company.id
    assert creado.role == Role.OPERARIO


def test_el_registro_publico_no_permite_elegir_rol(company):
    """Seguridad: si el cliente manda role=ADMIN, se ignora y entra como operario.

    De lo contrario cualquiera podría registrarse como supervisor y cerrar sus propios
    hallazgos, rompiendo la separación que exige la Ley 29783.
    """
    response = APIClient().post(
        reverse("register"),
        {
            "username": "colado",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "company_ruc": company.ruc,
            "role": "ADMIN",
        },
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.get(username="colado").role == Role.OPERARIO


def test_registro_con_ruc_inexistente_falla(db):
    response = APIClient().post(
        reverse("register"),
        {
            "username": "x",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "company_ruc": "20999999999",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "company_ruc" in response.data


def test_registro_rechaza_area_de_otra_empresa(company, otra_empresa):
    ajena = Area.objects.create(company=otra_empresa, name="Ajena")
    response = APIClient().post(
        reverse("register"),
        {
            "username": "y",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "company_ruc": company.ruc,
            "area": ajena.id,
        },
        format="json",
    )
    assert response.status_code == 400


def test_contrasenas_distintas_fallan(company):
    response = APIClient().post(
        reverse("register"),
        {
            "username": "z",
            "password": "ClaveSegura123",
            "password_confirm": "OtraClave456",
            "company_ruc": company.ruc,
        },
        format="json",
    )
    assert response.status_code == 400


def test_operario_no_lista_usuarios(operario):
    response = auth(operario).get(reverse("user-list"))
    assert response.status_code == 403


def test_supervisor_solo_ve_usuarios_de_su_empresa(supervisor, operario, otra_empresa):
    User.objects.create_user(
        username="ajeno", password="x", company=otra_empresa, role=Role.OPERARIO
    )
    response = auth(supervisor).get(reverse("user-list"))
    assert response.status_code == 200
    usernames = {u["username"] for u in response.data["results"]}
    assert usernames == {"sup", "op"}


def test_manager_puede_crear_un_supervisor(supervisor, area):
    response = auth(supervisor).post(
        reverse("user-list"),
        {
            "username": "nuevo_sup",
            "password": "ClaveSegura123",
            "first_name": "Ana",
            "last_name": "Torres",
            "role": Role.SUPERVISOR,
            "area": area.id,
        },
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.get(username="nuevo_sup").role == Role.SUPERVISOR


EMPRESA_NUEVA = {
    "name": "Constructora del Sur SAC",
    "ruc": "20600000001",
    "address": "Av. Industrial 455, Lima",
    "worker_count": 32,
    "username": "duena",
    "first_name": "Carmen",
    "last_name": "Rojas",
    "password": "ClaveSegura123",
    "password_confirm": "ClaveSegura123",
}


def test_registro_de_empresa_crea_la_empresa_y_su_administrador(db):
    response = APIClient().post(reverse("register-company"), EMPRESA_NUEVA, format="json")

    assert response.status_code == 201
    empresa = Company.objects.get(ruc="20600000001")
    assert empresa.name == "Constructora del Sur SAC"
    # Con 32 trabajadores la ley exige comité, no supervisor.
    assert empresa.requires_committee is True

    admin = User.objects.get(username="duena")
    assert admin.company_id == empresa.id
    assert admin.role == Role.ADMIN
    assert admin.check_password("ClaveSegura123")
    assert response.data["company"]["ruc"] == "20600000001"
    assert response.data["user"]["role"] == Role.ADMIN


def test_registro_de_empresa_rechaza_un_ruc_ya_registrado(company):
    datos = EMPRESA_NUEVA | {"ruc": company.ruc}
    response = APIClient().post(reverse("register-company"), datos, format="json")

    assert response.status_code == 400
    assert "ruc" in response.data
    # No se creó un usuario huérfano al rechazar la empresa.
    assert not User.objects.filter(username="duena").exists()


def test_registro_de_empresa_rechaza_un_ruc_que_no_sea_de_once_digitos(db):
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"ruc": "2060ABC"}, format="json"
    )
    assert response.status_code == 400
    assert "ruc" in response.data


def test_registro_de_empresa_rechaza_un_usuario_ya_tomado(company, operario):
    datos = EMPRESA_NUEVA | {"username": operario.username}
    response = APIClient().post(reverse("register-company"), datos, format="json")

    assert response.status_code == 400
    assert "username" in response.data
    # La transacción revirtió la empresa: su RUC sigue libre para reintentar.
    assert not Company.objects.filter(ruc="20600000001").exists()


def test_el_administrador_recien_registrado_puede_iniciar_sesion(db):
    APIClient().post(reverse("register-company"), EMPRESA_NUEVA, format="json")

    response = APIClient().post(
        reverse("login"), {"username": "duena", "password": "ClaveSegura123"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["user"]["role"] == Role.ADMIN


# --- Validación del número de trabajadores ---
#
# El dato no es cosmético: la Ley 29783 cambia la obligación según el tamaño de la empresa
# (comité paritario desde 20 trabajadores, supervisor por debajo), así que un 0 o un texto
# dejarían el sistema de gestión sin poder decidir qué órgano le corresponde.


@pytest.mark.parametrize(
    "valor,fragmento_esperado",
    [
        (0, "al menos 1 trabajador"),
        (-5, "al menos 1 trabajador"),
        (1_000_001, "máximo admitido"),
        ("muchos", "número entero"),
    ],
)
def test_registro_de_empresa_rechaza_un_numero_de_trabajadores_invalido(
    db, valor, fragmento_esperado
):
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"worker_count": valor}, format="json"
    )

    assert response.status_code == 400
    assert "worker_count" in response.data
    assert fragmento_esperado in str(response.data["worker_count"][0])
    # Nada quedó a medias: ni la empresa ni el usuario se crearon.
    assert not Company.objects.filter(ruc=EMPRESA_NUEVA["ruc"]).exists()
    assert not User.objects.filter(username=EMPRESA_NUEVA["username"]).exists()


def test_registro_de_empresa_exige_el_numero_de_trabajadores(db):
    datos = {k: v for k, v in EMPRESA_NUEVA.items() if k != "worker_count"}
    response = APIClient().post(reverse("register-company"), datos, format="json")

    assert response.status_code == 400
    assert "Indica cuántos trabajadores" in str(response.data["worker_count"][0])


@pytest.mark.parametrize(
    "trabajadores,exige_comite",
    [(1, False), (19, False), (20, True), (45, True)],
)
def test_el_numero_de_trabajadores_define_si_la_empresa_necesita_comite(
    db, trabajadores, exige_comite
):
    """El umbral de 20 del artículo 29 de la Ley 29783, comprobado en la frontera."""
    response = APIClient().post(
        reverse("register-company"),
        EMPRESA_NUEVA | {"worker_count": trabajadores},
        format="json",
    )

    assert response.status_code == 201
    assert Company.objects.get(ruc=EMPRESA_NUEVA["ruc"]).requires_committee is exige_comite
    assert response.data["company"]["requires_committee"] is exige_comite


# --- Validación de la forma del RUC ---


@pytest.mark.parametrize(
    "ruc,fragmento_esperado",
    [
        ("20-12345678", "solo admite dígitos"),
        ("2060ABC1234", "solo admite dígitos"),
        ("206000000", "exactamente 11 dígitos"),
        ("206000000012", "exactamente 11 dígitos"),
        ("99999999999", "empiezan en 10, 15, 16, 17 o 20"),
        ("00600000001", "empiezan en 10, 15, 16, 17 o 20"),
    ],
)
def test_registro_de_empresa_rechaza_un_ruc_mal_formado(db, ruc, fragmento_esperado):
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"ruc": ruc}, format="json"
    )

    assert response.status_code == 400
    assert fragmento_esperado in str(response.data["ruc"][0])


def test_el_registro_de_trabajador_valida_la_forma_del_ruc(db):
    """La misma validación corre en los dos registros: un RUC con letras no llega a la base."""
    response = APIClient().post(
        reverse("register"),
        {
            "username": "w",
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "company_ruc": "20ABC456789",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "solo admite dígitos" in str(response.data["company_ruc"][0])


# --- Validación de la razón social y del DNI ---


def test_registro_de_empresa_rechaza_una_razon_social_muy_corta(db):
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"name": "AB"}, format="json"
    )

    assert response.status_code == 400
    assert "al menos 3 caracteres" in str(response.data["name"][0])


@pytest.mark.parametrize("dni", ["1234567", "123456789", "1234567A"])
def test_registro_de_empresa_rechaza_un_dni_que_no_tenga_ocho_digitos(db, dni):
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"dni": dni}, format="json"
    )

    assert response.status_code == 400
    assert "exactamente 8 dígitos" in str(response.data["dni"][0])


def test_el_dni_sigue_siendo_opcional_en_el_registro_de_empresa(db):
    """Opcional de verdad: vacío pasa, y solo se valida cuando el usuario escribe algo."""
    response = APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"dni": ""}, format="json"
    )

    assert response.status_code == 201
    assert User.objects.get(username=EMPRESA_NUEVA["username"]).dni == ""


# --- Tope de cuentas por RUC ---
#
# El número de trabajadores que declara la empresa no es solo informativo: es el cupo de
# cuentas que admite su RUC. Sin el tope, cualquiera con el RUC —que está en la boleta y
# en el cartel de obra— podría abrir cuentas indefinidas en una empresa ajena.


def registrar_trabajador(ruc, username):
    return APIClient().post(
        reverse("register"),
        {
            "username": username,
            "password": "ClaveSegura123",
            "password_confirm": "ClaveSegura123",
            "first_name": "Trabajador",
            "last_name": username.upper(),
            "company_ruc": ruc,
        },
        format="json",
    )


@pytest.mark.parametrize("declarados", [1, 2, 3])
def test_el_ruc_admite_exactamente_las_cuentas_declaradas(db, declarados):
    empresa = Company.objects.create(name="Tope SAC", ruc="20700000001", worker_count=declarados)

    for n in range(declarados):
        assert registrar_trabajador(empresa.ruc, "t%d" % n).status_code == 201

    sobrante = registrar_trabajador(empresa.ruc, "sobrante")
    assert sobrante.status_code == 400
    assert "company_ruc" in sobrante.data
    assert "ya tiene esas cuentas registradas" in str(sobrante.data["company_ruc"][0])
    assert empresa.users.count() == declarados


def test_el_administrador_no_ocupa_una_plaza_de_trabajador(db):
    """Si declaro 1 trabajador aparte de mí, ese trabajador tiene que poder registrarse."""
    APIClient().post(
        reverse("register-company"), EMPRESA_NUEVA | {"worker_count": 1}, format="json"
    )

    assert registrar_trabajador(EMPRESA_NUEVA["ruc"], "unico").status_code == 201
    assert registrar_trabajador(EMPRESA_NUEVA["ruc"], "segundo").status_code == 400


def test_el_mensaje_del_tope_nombra_la_empresa_y_lo_declarado(db):
    empresa = Company.objects.create(name="Tope SAC", ruc="20700000009", worker_count=1)
    registrar_trabajador(empresa.ruc, "primero")

    detalle = str(registrar_trabajador(empresa.ruc, "segundo").data["company_ruc"][0])
    assert "Tope SAC" in detalle
    assert "1 trabajador y" in detalle  # singular, no "1 trabajadores"
    assert "administrador de SST" in detalle  # dice qué hacer, no solo que no se puede


def test_el_alta_desde_el_panel_tambien_respeta_el_tope(db):
    empresa = Company.objects.create(name="Tope SAC", ruc="20700000002", worker_count=1)
    sup = User.objects.create_user(
        username="sup_tope", password="x", company=empresa, role=Role.SUPERVISOR
    )

    # El supervisor ya ocupa la única plaza declarada.
    response = auth(sup).post(
        reverse("user-list"),
        {
            "username": "extra",
            "password": "ClaveSegura123",
            "first_name": "Extra",
            "last_name": "Extra",
            "role": Role.OPERARIO,
        },
        format="json",
    )
    assert response.status_code == 400
    assert "role" in response.data
    assert not User.objects.filter(username="extra").exists()


def test_subir_el_numero_de_trabajadores_libera_el_registro(db):
    empresa = Company.objects.create(name="Tope SAC", ruc="20700000003", worker_count=1)
    admin = User.objects.create_user(
        username="admin_tope", password="x", company=empresa, role=Role.ADMIN
    )

    assert registrar_trabajador(empresa.ruc, "uno").status_code == 201
    assert registrar_trabajador(empresa.ruc, "dos").status_code == 400

    subida = auth(admin).patch(reverse("company"), {"worker_count": 2}, format="json")
    assert subida.status_code == 200
    assert subida.data["worker_slots_available"] == 1

    assert registrar_trabajador(empresa.ruc, "dos").status_code == 201


def test_no_se_puede_declarar_menos_trabajadores_que_cuentas_registradas(db):
    empresa = Company.objects.create(name="Tope SAC", ruc="20700000004", worker_count=3)
    admin = User.objects.create_user(
        username="admin_baja", password="x", company=empresa, role=Role.ADMIN
    )
    registrar_trabajador(empresa.ruc, "uno")
    registrar_trabajador(empresa.ruc, "dos")

    response = auth(admin).patch(reverse("company"), {"worker_count": 1}, format="json")
    assert response.status_code == 400
    assert "no puedes declarar menos de 2" in str(response.data["worker_count"][0])


# --- Datos de la empresa ---


def test_la_empresa_informa_su_cupo_de_cuentas(company, supervisor, operario):
    response = auth(supervisor).get(reverse("company"))

    assert response.status_code == 200
    assert response.data["worker_count"] == 45
    assert response.data["worker_accounts"] == 2  # supervisor y operario
    assert response.data["worker_slots_available"] == 43
    assert response.data["requires_committee"] is True


def test_el_operario_ve_los_datos_de_su_empresa_pero_no_los_edita(operario):
    assert auth(operario).get(reverse("company")).status_code == 200

    response = auth(operario).patch(reverse("company"), {"worker_count": 999}, format="json")
    assert response.status_code == 403


def test_el_ruc_de_la_empresa_no_se_puede_cambiar(company, supervisor):
    """El RUC es la llave con la que se registra la plantilla: se ignora si lo mandan."""
    response = auth(supervisor).patch(
        reverse("company"), {"ruc": "20888888888"}, format="json"
    )

    assert response.status_code == 200
    company.refresh_from_db()
    assert company.ruc == "20100000004"
