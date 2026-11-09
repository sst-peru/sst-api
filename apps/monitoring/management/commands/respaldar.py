"""python manage.py respaldar — genera un respaldo cifrado de la base (TS21).

Se programa en la ventana de respaldo del entorno (cron del servidor o tarea programada del
proveedor), por ejemplo cada noche a las 03:00.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.backups import RespaldoError, crear_respaldo
from apps.monitoring.models import BackupKind, BackupLog


class Command(BaseCommand):
    help = "Genera un respaldo cifrado de la base en el almacenamiento configurado."

    def handle(self, *args, **options):
        try:
            ruta, registros = crear_respaldo()
        except RespaldoError as error:
            BackupLog.objects.create(kind=BackupKind.RESPALDO, ok=False, detail=str(error))
            raise CommandError(str(error)) from error
        BackupLog.objects.create(
            kind=BackupKind.RESPALDO, ok=True, file=ruta, detail=f"{registros} registros"
        )
        self.stdout.write(self.style.SUCCESS(f"Respaldo {ruta} ({registros} registros)"))
