from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_add_empresa"),
    ]

    operations = [
        migrations.AlterField(
            model_name="movimientobanco",
            name="tipo",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
