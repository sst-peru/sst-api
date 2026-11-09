"""Registro estructurado de cada petición, con identificador de correlación (TS23).

Cada petición recibe un identificador: el que mande el cliente en X-Request-ID o uno nuevo.
Se devuelve en la respuesta y viaja en cada línea de log, así un error que reporta el usuario
se encuentra en los registros sin reproducirlo a ciegas.

Los registros salen en JSON, una línea por evento, que es lo que leen los agregadores de logs
(CloudWatch, Loki, Datadog) sin configurar expresiones regulares.
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Un identificador del cliente se acepta solo si es razonable: corto y sin caracteres raros,
# para que nadie meta texto arbitrario en los logs.
_LARGO_MAXIMO_ID = 64

logger = logging.getLogger("sst.requests")


def request_id_actual() -> str:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Agrega el identificador de la petición en curso a todo registro emitido durante ella."""

    def filter(self, record):
        record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """Una línea JSON por registro, con los campos extra que traiga."""

    CAMPOS_EXTRA = ("request_id", "user", "method", "path", "status", "duration_ms", "company")

    def format(self, record):
        datos = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for campo in self.CAMPOS_EXTRA:
            valor = getattr(record, campo, None)
            if valor is not None:
                datos[campo] = valor
        if record.exc_info:
            datos["exception"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False)


def _id_valido(valor: str | None) -> str | None:
    if not valor or len(valor) > _LARGO_MAXIMO_ID:
        return None
    if not all(c.isalnum() or c in "-_." for c in valor):
        return None
    return valor


class RequestLogMiddleware:
    """Asigna el identificador de correlación y registra método, ruta, estado y duración."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        identificador = _id_valido(request.headers.get("X-Request-ID")) or uuid.uuid4().hex
        token = _request_id.set(identificador)
        request.request_id = identificador
        inicio = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "Error no controlado",
                extra=self._extra(request, 500, inicio),
            )
            raise
        else:
            response["X-Request-ID"] = identificador
            nivel = logging.WARNING if response.status_code >= 500 else logging.INFO
            logger.log(
                nivel,
                f"{request.method} {request.path} {response.status_code}",
                extra=self._extra(request, response.status_code, inicio),
            )
            return response
        finally:
            _request_id.reset(token)

    @staticmethod
    def _extra(request, estado, inicio):
        usuario = getattr(request, "user", None)
        autenticado = bool(usuario and usuario.is_authenticated)
        return {
            "method": request.method,
            "path": request.path,
            "status": estado,
            "duration_ms": round((time.perf_counter() - inicio) * 1000, 1),
            # Solo el id: el nombre o el correo son datos personales y no hacen falta para
            # diagnosticar.
            "user": usuario.pk if autenticado else None,
            "company": getattr(usuario, "company_id", None) if autenticado else None,
        }
