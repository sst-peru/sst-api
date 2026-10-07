"""Configuración común de las pruebas. Lo único que hace es acelerarlas.

Con los ajustes de producción la suite tardaba casi tres minutos, y la mayor parte del
tiempo no se iba en la lógica del sistema sino en hashear contraseñas. PBKDF2 está
calibrado a propósito para que probar una contraseña robada sea caro: Django usa cientos de
miles de iteraciones, y cada create_user, cada set_password y cada inicio de sesión de los
tests paga ese costo completo. En la base de pruebas, que se crea y se destruye en cada
corrida, no hay ninguna contraseña que proteger.

Por eso aquí se cambia el hasher por MD5 —rápido y, justamente por eso, inservible en
producción— solo durante las pruebas. El cambio va con override_settings y no con una
asignación directa porque Django guarda en caché la lista de hashers y únicamente la
invalida al recibir la señal setting_changed, que es lo que override_settings emite.
"""
import pytest
from django.test import override_settings


@pytest.fixture(autouse=True, scope="session")
def _contrasenas_rapidas():
    with override_settings(
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
    ):
        yield
