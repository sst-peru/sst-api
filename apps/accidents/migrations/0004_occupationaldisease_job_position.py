from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accidents", "0003_investigation_management_causes"),
    ]

    operations = [
        migrations.AddField(
            model_name="occupationaldisease",
            name="job_position",
            field=models.CharField(blank=True, max_length=120, verbose_name="puesto de trabajo"),
        ),
    ]
