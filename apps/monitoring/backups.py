"""Respaldo cifrado de la base y prueba de restauración en una base aparte (TS21).

El respaldo es un volcado JSON de todos los datos, comprimido y cifrado con Fernet (AES-128 en
modo CBC con HMAC), que se guarda en el almacenamiento configurado: el bucket en producción, el
disco en desarrollo. La prueba de restauración descifra la copia más reciente, la carga en una
base SQLite temporal recién migrada y compara, modelo por modelo, cuántos registros trae la
copia con cuántos quedaron restaurados. Un respaldo que nunca se probó no es un respaldo.
"""
import gzip
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import closing
from io import StringIO
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

CARPETA = "backups"
EXCLUIDOS = (
    "contenttypes",
    "auth.permission",
    "sessions",
    "admin.logentry",
)


class RespaldoError(Exception):
    pass


def _fernet() -> Fernet:
    clave = settings.BACKUP_ENCRYPTION_KEY
    if not clave:
        raise RespaldoError(
            "Falta BACKUP_ENCRYPTION_KEY. Genera una con: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(clave.encode() if isinstance(clave, str) else clave)
    except ValueError as error:
        raise RespaldoError("BACKUP_ENCRYPTION_KEY no es una clave Fernet válida.") from error


def crear_respaldo() -> tuple[str, int]:
    """Genera el respaldo cifrado. Devuelve la ruta en el almacenamiento y el n.° de registros."""
    fernet = _fernet()
    salida = StringIO()
    call_command(
        "dumpdata",
        exclude=list(EXCLUIDOS),
        natural_foreign=True,
        natural_primary=False,
        stdout=salida,
        verbosity=0,
    )
    volcado = salida.getvalue().encode("utf-8")
    registros = len(json.loads(volcado))
    cifrado = fernet.encrypt(gzip.compress(volcado))
    nombre = f"{CARPETA}/sst-{timezone.now():%Y%m%d-%H%M%S}.json.gz.enc"
    ruta = default_storage.save(nombre, ContentFile(cifrado))
    _aplicar_retencion()
    return ruta, registros


def _respaldos() -> list[str]:
    try:
        _, archivos = default_storage.listdir(CARPETA)
    except FileNotFoundError:
        return []
    return sorted(f"{CARPETA}/{a}" for a in archivos if a.endswith(".json.gz.enc"))


def _aplicar_retencion():
    sobrantes = _respaldos()[: -settings.BACKUP_RETENTION or None]
    for ruta in sobrantes:
        default_storage.delete(ruta)


def ultimo_respaldo() -> str | None:
    lista = _respaldos()
    return lista[-1] if lista else None


def probar_restauracion(ruta: str | None = None) -> dict:
    """Restaura el respaldo en una base temporal y verifica los conteos por modelo."""
    ruta = ruta or ultimo_respaldo()
    if not ruta:
        raise RespaldoError("No hay respaldos para probar.")
    with default_storage.open(ruta, "rb") as archivo:
        cifrado = archivo.read()
    try:
        volcado = gzip.decompress(_fernet().decrypt(cifrado))
    except InvalidToken as error:
        raise RespaldoError("No se pudo descifrar: la clave no corresponde a esta copia.") from error

    esperados = Counter(obj["model"] for obj in json.loads(volcado))

    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta) / "restauracion.sqlite3"
        fixture = Path(carpeta) / "respaldo.json"
        fixture.write_bytes(volcado)
        # La restauración corre en otro proceso, contra otra base: es el "entorno aparte" y
        # garantiza que la base en uso no se toque aunque algo falle a medio camino.
        entorno = {**os.environ, "DATABASE_URL": f"sqlite:///{base.as_posix()}"}
        manage = str(Path(settings.BASE_DIR) / "manage.py")
        for comando in (
            # La migración recrea los tipos de contenido y permisos, que no van en la copia
            # porque Django los regenera; el resto llega íntegro desde el respaldo.
            ["migrate", "--noinput", "-v", "0"],
            ["loaddata", str(fixture), "-v", "0"],
        ):
            proceso = subprocess.run(
                [sys.executable, manage, *comando],
                env=entorno, capture_output=True, text=True, timeout=600,
            )
            if proceso.returncode != 0:
                raise RespaldoError(
                    f"Falló '{comando[0]}' al restaurar: {proceso.stderr.strip()[-1000:]}"
                )
        diferencias = {}
        with closing(sqlite3.connect(base)) as conexion:
            for etiqueta, cantidad in esperados.items():
                tabla = apps.get_model(etiqueta)._meta.db_table
                (restaurados,) = conexion.execute(f'SELECT COUNT(*) FROM "{tabla}"').fetchone()
                if restaurados != cantidad:
                    diferencias[etiqueta] = {"respaldo": cantidad, "restaurados": restaurados}

    return {
        "file": ruta,
        "models": len(esperados),
        "records": sum(esperados.values()),
        "ok": not diferencias,
        "differences": diferencias,
    }
