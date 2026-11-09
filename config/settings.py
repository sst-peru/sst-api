"""Configuración de Django para la plataforma SST (Ley 29783)."""
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-insecure-key")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1,10.0.2.2", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
    # Propias
    "apps.accounts",
    "apps.reports",
    "apps.accidents",
    "apps.iperc",
    "apps.epp",
    "apps.inspections",
    "apps.experiments",
    "apps.committee",
    "apps.exports",
    "apps.training",
    "apps.riskmap",
    "apps.documents",
    "apps.monitoring",
    "apps.notifications",
]

MIDDLEWARE = [
    # Primero, para que el identificador de correlación cubra toda la petición.
    "config.observability.RequestLogMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

_database_url = config("DATABASE_URL", default="")
if _database_url:
    DATABASES = {"default": dj_database_url.parse(_database_url, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Almacenamiento de archivos (TS22). Con un bucket configurado, las fotos, planos y documentos
# van a un servicio de objetos compatible con S3 (AWS S3, Cloudflare R2, MinIO) y el API
# entrega enlaces firmados que vencen; sin bucket, se guardan en disco, como en desarrollo.
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
if AWS_STORAGE_BUCKET_NAME:
    _ALMACENAMIENTO_ARCHIVOS = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "access_key": config("AWS_ACCESS_KEY_ID", default=""),
            "secret_key": config("AWS_SECRET_ACCESS_KEY", default=""),
            "region_name": config("AWS_S3_REGION_NAME", default="us-east-1"),
            "endpoint_url": config("AWS_S3_ENDPOINT_URL", default="") or None,
            # Bucket privado: cada enlace va firmado y vence, nunca es público.
            "default_acl": None,
            "querystring_auth": True,
            "signature_version": "s3v4",
            "querystring_expire": config("AWS_QUERYSTRING_EXPIRE", default=3600, cast=int),
            "file_overwrite": False,
        },
    }
else:
    _ALMACENAMIENTO_ARCHIVOS = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _ALMACENAMIENTO_ARCHIVOS,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Respaldos (TS21): la copia se cifra con esta clave Fernet antes de guardarse. Sin ella, el
# comando de respaldo se niega a correr: un respaldo sin cifrar del expediente de SST es un
# riesgo mayor que no tenerlo.
BACKUP_ENCRYPTION_KEY = config("BACKUP_ENCRYPTION_KEY", default="")
BACKUP_RETENTION = config("BACKUP_RETENTION", default=14, cast=int)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Límite de tasa (TS25): un cliente defectuoso que reintenta en bucle no puede degradar el
    # servicio de las demás empresas. Al pasarlo, el API responde 429 con Retry-After.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="60/min"),
        "user": config("THROTTLE_USER", default="600/min"),
        # El inicio de sesión aparte y más estricto: es el blanco de quien prueba contraseñas.
        "login": config("THROTTLE_LOGIN", default="10/min"),
        "client_errors": config("THROTTLE_CLIENT_ERRORS", default="30/min"),
    },
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    # Largo a propósito: el operario puede estar días sin señal en obra o mina.
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API Resguardo — Sistema de Gestión de SST (Ley N° 29783)",
    "DESCRIPTION": (
        "API REST que sostiene el panel web y la aplicación Android de Resguardo, la "
        "plataforma con la que una empresa peruana lleva su Sistema de Gestión de "
        "Seguridad y Salud en el Trabajo conforme a la Ley N° 29783 y su Reglamento "
        "(D.S. N° 005-2012-TR).\n\n"
        "**Autenticación.** Todos los endpoints exigen un token JWT en la cabecera "
        "`Authorization: Bearer <access>`, salvo los de registro y de inicio de sesión. "
        "El token se obtiene en `POST /api/v1/auth/login/` y se renueva en "
        "`POST /api/v1/auth/refresh/` sin volver a pedir la contraseña.\n\n"
        "**Aislamiento por empresa.** Cada respuesta está limitada a la empresa del "
        "usuario autenticado: no existe forma de leer ni escribir datos de otra empresa, "
        "aunque se conozca el identificador del recurso.\n\n"
        "**Roles.** `OPERARIO` reporta y consulta lo suyo; `SUPERVISOR` y `COMITE` "
        "gestionan hallazgos, registros e indicadores; `ADMIN` administra además la "
        "empresa, sus áreas y sus cuentas. La separación es un requisito legal: quien "
        "reporta un hallazgo no puede cerrarlo.\n\n"
        "Las secciones que siguen agrupan los endpoints por el proceso del sistema de "
        "gestión al que pertenecen."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {"name": "Equipo Resguardo", "url": "https://github.com/sst-peru"},
    "LICENSE": {"name": "Uso académico — UPC 1ASI0732"},
    # El orden de esta lista es el orden en que Swagger muestra las secciones. Se declara
    # a mano porque el alfabetico mezclaria los procesos y dejaria el registro al final.
    "TAGS": [
        {
            "name": "Registro",
            "description": (
                "Alta de una empresa con la cuenta de su administrador, y alta de "
                "trabajadores que se suman a una empresa ya registrada usando su RUC. "
                "Son los dos únicos endpoints que no exigen token."
            ),
        },
        {
            "name": "Autenticación y sesión",
            "description": (
                "Obtención, renovación y verificación del token JWT, y datos del usuario "
                "de la sesión en curso."
            ),
        },
        {
            "name": "Empresa, áreas y usuarios",
            "description": (
                "Datos de la empresa y su cupo de cuentas, áreas o frentes de trabajo "
                "donde se ubican los peligros, y alta y mantenimiento de las cuentas de "
                "la plantilla."
            ),
        },
        {
            "name": "Reportes de actos y condiciones inseguras",
            "description": (
                "El ciclo de vida del hallazgo: registro desde campo con evidencia, "
                "ubicación y fecha real de ocurrencia; asignación de responsable; cierre "
                "con acción correctiva; y la bitácora que deja constancia de cada paso."
            ),
        },
        {
            "name": "Accidentes y enfermedades ocupacionales",
            "description": (
                "Registro de accidentes de trabajo, incidentes peligrosos y enfermedades "
                "ocupacionales; investigación de causa raíz; medidas correctivas con "
                "responsable, plazo y verificación; y control del plazo de 24 horas para "
                "avisar al Ministerio de Trabajo que fija el artículo 82 de la ley."
            ),
        },
        {
            "name": "Matriz IPERC",
            "description": (
                "Identificación de peligros, evaluación de riesgos y controles, "
                "versionada: la matriz vigente no se edita, se publica una versión nueva "
                "y la anterior queda como evidencia histórica."
            ),
        },
        {
            "name": "Equipos de protección personal",
            "description": (
                "Catálogo de EPP con stock, registro de entregas y conformidad del "
                "trabajador, que es la constancia que exige la fiscalización."
            ),
        },
        {
            "name": "Inspecciones periódicas",
            "description": (
                "Programación de inspecciones por área y frecuencia, y su ejecución con "
                "checklist."
            ),
        },
        {
            "name": "Capacitación y simulacros",
            "description": (
                "Programa anual de capacitación con su asistencia, inducción del personal "
                "nuevo, alerta de capacitación vencida y registro de simulacros de "
                "emergencia: los registros de formación del artículo 33 de la ley."
            ),
        },
        {
            "name": "Mapa de riesgos y señalización",
            "description": (
                "Mapa de riesgos de cada área con los peligros ubicados sobre el plano, e inventario de la señalización de seguridad con su estado."
            ),
        },
        {
            "name": "Documentos y plan anual del SGSST",
            "description": (
                "Política de SST, Reglamento Interno con la constancia de entrega a cada trabajador, control de versiones de los documentos y plan anual de SST con su avance."
            ),
        },
        {
            "name": "Comité de SST",
            "description": (
                "Constitución del comité paritario, sus miembros, las actas de reunión "
                "con verificación de quórum y los acuerdos con responsable y plazo."
            ),
        },
        {
            "name": "Indicadores del SGSST",
            "description": (
                "Métricas de gestión: MTTR de cierre de hallazgos, resumen por estado, "
                "cumplimiento del programa de inspecciones y cumplimiento de los "
                "acuerdos del comité."
            ),
        },
        {
            "name": "Privacidad y datos personales",
            "description": (
                "Consentimiento informado para el tratamiento de datos personales y "
                "control del uso de la ubicación, conforme a la Ley N° 29733. El "
                "consentimiento queda con fecha, versión de la política y origen, y se "
                "revoca con la misma facilidad con que se otorga."
            ),
        },
        {
            "name": "Experimento A/B",
            "description": (
                "Soporte del experimento del curso: asignación determinista de variante "
                "por usuario y resultados comparados entre el formulario rápido de tres "
                "pasos y el formulario extenso."
            ),
        },
        {
            "name": "Exportaciones para SUNAFIL",
            "description": (
                "Descarga en Excel de los registros obligatorios, en el formato en que "
                "se presentan ante una fiscalización."
            ),
        },
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        # Secciones colapsadas al abrir: con once secciones, expandirlas todas obliga a
        # desplazarse mucho antes de encontrar lo que se busca.
        "docExpansion": "none",
        "filter": True,
        "tryItOutEnabled": True,
    },
    # Sin esto Swagger reordena las operaciones por alfabeto y rompe el orden de las rutas.
    "SORT_OPERATIONS": False,
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173", cast=Csv())
# El cliente puede leer el identificador de correlación para mostrarlo al reportar un error.
CORS_EXPOSE_HEADERS = ["X-Request-ID", "Retry-After"]

# Correo transaccional (TS19). Sin configurar, los correos salen por consola: sirve en
# desarrollo y no envía nada por error. En producción basta definir el backend SMTP y sus
# credenciales en el entorno (o el backend del proveedor que se use).
EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="Resguardo <no-responder@resguardo.pe>")
# Dirección de la web: los enlaces de los correos apuntan ahí.
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
# El enlace para restablecer la contraseña vale un día.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Registros estructurados (TS23): JSON por línea con el identificador de la petición.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "config.observability.RequestIdFilter"}},
    "formatters": {"json": {"()": "config.observability.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "sst": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
