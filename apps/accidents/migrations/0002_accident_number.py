"""Número correlativo del accidente dentro de su empresa.

Se agrega en tres pasos porque los accidentes ya registrados necesitan su número antes de
que el campo sea obligatorio: se crea admitiendo vacío, se numeran los existentes por
empresa en el orden en que se registraron —el mismo que sigue un registro nuevo—, y recién
entonces se exige.
"""
from django.db import migrations, models


def numerar_accidentes_existentes(apps, schema_editor):
    Accident = apps.get_model("accidents", "Accident")
    siguiente_por_empresa = {}
    for accidente in Accident.objects.order_by("company_id", "created_at", "id"):
        numero = siguiente_por_empresa.get(accidente.company_id, 0) + 1
        siguiente_por_empresa[accidente.company_id] = numero
        accidente.number = numero
        accidente.save(update_fields=["number"])


class Migration(migrations.Migration):

    dependencies = [
        ("accidents", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="accident",
            name="number",
            field=models.PositiveIntegerField(
                editable=False, null=True, verbose_name="número correlativo"
            ),
        ),
        migrations.RunPython(numerar_accidentes_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="accident",
            name="number",
            field=models.PositiveIntegerField(editable=False, verbose_name="número correlativo"),
        ),
        migrations.AddConstraint(
            model_name="accident",
            constraint=models.UniqueConstraint(
                fields=("company", "number"), name="accident_number_unique_per_company"
            ),
        ),
    ]
