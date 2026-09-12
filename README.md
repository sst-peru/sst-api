# sst-api

API de la plataforma de gestión de **Seguridad y Salud en el Trabajo** (Ley 29783 — Perú).
Es el único backend: lo consumen tanto el panel web (`sst-web`) como la app Android (`sst-mobile`).

## Qué resuelve

El dato de seguridad hoy vive en papel o en un Excel que nadie actualiza. Esta API centraliza:

- **Reportes de actos y condiciones inseguras** con foto, GPS y fecha real de ocurrencia, creados desde el celular del operario en segundos (incluso sin señal, sincronizando después).
- **Seguimiento del hallazgo**: asignación de responsable, bitácora de acciones y cierre con la acción correctiva aplicada. Esto es la evidencia ante SUNAFIL.
- **Matriz IPERC versionada**, que se alimenta de los reportes reales en vez de una revisión anual que se hace tarde.
- **Control de EPP**: catálogo, entregas y vencimientos.
- **Inspecciones periódicas** programadas por frecuencia, con su tasa de cumplimiento.
- **Experimentos A/B** para el trabajo del curso.

## Stack

Python 3.11 · Django 5.1 · Django REST Framework · SimpleJWT · drf-spectacular · PostgreSQL (SQLite en desarrollo)

## Levantarlo en local

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo          # datos de prueba
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
bash scripts/setup-hooks.sh         # activa la validación de commits
```

- API: http://localhost:8000/api/v1/
- **Documentación Swagger: http://localhost:8000/api/docs/**
- Admin de Django: http://localhost:8000/admin/

Usuarios del `seed_demo` (clave `demo12345`): `supervisor`, `comite1`, `operario1` … `operario4`.

> **Desde el emulador de Android** el backend no es `localhost` sino `http://10.0.2.2:8000`.
> Desde un celular físico, la IP de tu PC en la red (`192.168.x.x`), y agrégala a `ALLOWED_HOSTS`.

## Endpoints principales

### Autenticación (`/api/v1/auth/`)

| Método | Ruta         | Qué hace |
|--------|--------------|----------|
| POST   | `register/`  | Registro de usuario — **el mismo endpoint que usan web y móvil** |
| POST   | `login/`     | Devuelve `access`, `refresh` y los datos del usuario |
| POST   | `refresh/`   | Renueva el access token |
| GET    | `me/`        | Perfil del usuario autenticado |
| CRUD   | `areas/`     | Áreas / frentes de trabajo de la empresa |

### Reportes (`/api/v1/`)

| Método | Ruta                          | Qué hace |
|--------|-------------------------------|----------|
| GET    | `reports/`                    | Lista filtrable por `kind`, `status`, `severity`, `area`, `category` |
| POST   | `reports/`                    | Crea un reporte. **Idempotente por `client_uuid`** (ver offline) |
| GET    | `reports/{id}/`               | Detalle con la bitácora de acciones |
| POST   | `reports/{id}/assign/`        | Asigna responsable → pasa a `EN_PROCESO` |
| POST   | `reports/{id}/close/`         | Cierra el hallazgo con la acción correctiva |
| POST   | `reports/{id}/change-status/` | Cambia el estado manualmente |
| CRUD   | `categories/`                 | Categorías de peligro por empresa |

### IPERC, EPP e inspecciones

`iperc/matrices/`, `iperc/entries/`, `epp/items/`, `epp/deliveries/`,
`inspections/schedules/`, `inspections/`, `inspections/{id}/complete/`

### Métricas del curso

| Ruta | Qué devuelve |
|------|--------------|
| `metrics/mttr/?days=90` | **MTTR**: horas promedio entre reporte y cierre, total y por severidad |
| `metrics/inspection-compliance/?days=90` | **Tasa de cumplimiento** de inspecciones, total y por área |
| `metrics/reports-summary/` | Conteos por estado, tipo, severidad y área (para los tableros) |

### Experimento A/B

| Ruta | Qué hace |
|------|----------|
| `experiments/my-variant/?key=report_form` | Variante asignada al usuario actual (`rapido` o `largo`) |
| `experiments/report_form/results/` | Reportes por usuario en cada variante, MTTR y lift % |

## Dos decisiones que conviene conocer

**Sincronización offline sin duplicados.** El cliente móvil genera un `client_uuid` *antes* de
enviar. Si la conexión se corta y reintenta, `POST /reports/` detecta el uuid y devuelve `200`
con el reporte ya existente en vez de crear otro. Además `occurred_at` lo manda el cliente, así
que un reporte hecho el lunes en la mina y sincronizado el miércoles conserva su fecha real.

**Asignación determinística del A/B test.** La variante se calcula con un hash estable de
`experiment_key + user_id`, no con `random`. Así el mismo usuario cae siempre en la misma
variante, la app puede recalcularla offline y el experimento es reproducible al sustentarlo.

## Tests

```bash
pytest -q
ruff check .
```

## Roles

| Rol | Puede |
|-----|-------|
| `OPERARIO` | Crear reportes y ver **solo los suyos**; ver sus EPP |
| `SUPERVISOR` | Todo lo de la empresa: asignar, cerrar, IPERC, inspecciones, métricas |
| `COMITE` | Igual que supervisor |
| `ADMIN` | Además, configuración de la empresa |

## Cómo contribuir

Ramas, Conventional Commits y merges: ver [CONTRIBUTING.md](CONTRIBUTING.md).
