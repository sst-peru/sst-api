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
            "company_ruc": "99999999999",
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
