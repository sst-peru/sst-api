from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accidents", "0002_accident_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="investigation",
            name="management_causes",
            field=models.TextField(blank=True, verbose_name="causas de gestión"),
        ),
    ]
