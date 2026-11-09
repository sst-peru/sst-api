"""python manage.py probar_restauracion — restaura el último respaldo en una base aparte (TS21).

Sale con error si la copia no se puede descifrar o si algún modelo no quedó con la misma
cantidad de registros, para que la tarea programada lo marque como fallido.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from apps.monitoring.backups import RespaldoError, probar_restauracion
from apps.monitoring.models import BackupKind, BackupLog


class Command(BaseCommand):
    help = "Restaura el último respaldo en una base temporal y verifica los conteos."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", help="Ruta del respaldo a probar; por defecto el último.")

    def handle(self, *args, **options):
        try:
            resultado = probar_restauracion(options.get("archivo"))
        except RespaldoError as error:
            BackupLog.objects.create(kind=BackupKind.PRUEBA, ok=False, detail=str(error))
            raise CommandError(str(error)) from error
        BackupLog.objects.create(
            kind=BackupKind.PRUEBA,
            ok=resultado["ok"],
            file=resultado["file"],
            detail=json.dumps(resultado, ensure_ascii=False),
        )
        if not resultado["ok"]:
            raise CommandError(f"La restauración no coincide: {resultado['differences']}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Restauración verificada: {resultado['records']} registros de "
                f"{resultado['models']} modelos desde {resultado['file']}"
            )
        )
