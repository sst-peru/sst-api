"""Pruebas del respaldo cifrado, su restauración verificada (TS21) y el almacenamiento (TS22)."""
import gzip

import pytest
from cryptography.fernet import Fernet
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from storages.backends.s3 import S3Storage

from apps.accounts.models import Area, Company
from apps.monitoring.backups import ultimo_respaldo
from apps.monitoring.models import BackupKind, BackupLog

CLAVE = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _entorno(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.BACKUP_ENCRYPTION_KEY = CLAVE
    settings.BACKUP_RETENTION = 2


@pytest.fixture
def datos(db):
    empresa = Company.objects.create(name="Obras SAC", ruc="20500000001", worker_count=5)
    Area.objects.create(company=empresa, name="Almacén")
    Area.objects.create(company=empresa, name="Taller")
    return empresa


def test_el_respaldo_se_guarda_cifrado(datos):
    call_command("respaldar", verbosity=0)

    ruta = ultimo_respaldo()
    contenido = default_storage.open(ruta, "rb").read()
    assert b"Obras SAC" not in contenido
    claro = gzip.decompress(Fernet(CLAVE).decrypt(contenido))
    assert b"Obras SAC" in claro
    assert BackupLog.objects.get(kind=BackupKind.RESPALDO).ok is True


@pytest.mark.django_db(transaction=True)
def test_la_restauracion_se_verifica_en_una_base_aparte(datos):
    call_command("respaldar", verbosity=0)

    call_command("probar_restauracion", verbosity=0)

    prueba = BackupLog.objects.get(kind=BackupKind.PRUEBA)
    assert prueba.ok is True
    assert '"accounts.area": ' not in prueba.detail  # sin diferencias
    # La base de producción no se tocó.
    assert Area.objects.count() == 2


def test_sin_clave_no_hay_respaldo(datos, settings):
    settings.BACKUP_ENCRYPTION_KEY = ""

    with pytest.raises(CommandError, match="BACKUP_ENCRYPTION_KEY"):
        call_command("respaldar", verbosity=0)
    assert BackupLog.objects.get().ok is False


def test_con_otra_clave_la_prueba_falla(datos, settings):
    call_command("respaldar", verbosity=0)
    settings.BACKUP_ENCRYPTION_KEY = Fernet.generate_key().decode()

    with pytest.raises(CommandError, match="descifrar"):
        call_command("probar_restauracion", verbosity=0)


def test_se_conservan_solo_los_ultimos_respaldos(datos):
    from apps.monitoring import backups

    for marca in ("20260101-000000", "20260102-000000", "20260103-000000"):
        default_storage.save(f"backups/sst-{marca}.json.gz.enc", __import__("io").BytesIO(b"x"))
    backups._aplicar_retencion()

    assert backups._respaldos() == [
        "backups/sst-20260102-000000.json.gz.enc",
        "backups/sst-20260103-000000.json.gz.enc",
    ]


def test_el_servicio_de_objetos_entrega_enlaces_firmados_que_vencen():
    """TS22: con bucket configurado, la URL de un archivo es temporal y firmada."""
    almacenamiento = S3Storage(
        bucket_name="resguardo-evidencias",
        access_key="AKIAEJEMPLO",
        secret_key="secreto-de-ejemplo",
        region_name="us-east-1",
        querystring_auth=True,
        querystring_expire=600,
        signature_version="s3v4",
    )

    url = almacenamiento.url("reports/2026/11/foto.jpg")

    assert "resguardo-evidencias" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=600" in url
