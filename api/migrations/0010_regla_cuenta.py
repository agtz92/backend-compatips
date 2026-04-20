from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_movimientobanco_tipo_max_length"),
    ]

    operations = [
        # Campo cuenta en MovimientoBanco
        migrations.AddField(
            model_name="movimientobanco",
            name="cuenta",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        # Actualizar constraint único (incluye cuenta)
        migrations.RemoveConstraint(
            model_name="movimientobanco",
            name="unique_movimiento_empresa",
        ),
        migrations.AddConstraint(
            model_name="movimientobanco",
            constraint=models.UniqueConstraint(
                fields=("fecha", "monto", "referencia", "descripcion", "empresa", "cuenta"),
                name="unique_movimiento_empresa_cuenta",
            ),
        ),
        # Nuevo modelo ReglaCuenta
        migrations.CreateModel(
            name="ReglaCuenta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("empresa", models.CharField(db_index=True, max_length=100)),
                ("cuenta", models.CharField(max_length=100)),
                ("prefijos_folio", models.JSONField(default=list)),
                ("descripcion", models.CharField(blank=True, default="", max_length=255)),
            ],
            options={"ordering": ["empresa", "cuenta"]},
        ),
        migrations.AddConstraint(
            model_name="reglacuenta",
            constraint=models.UniqueConstraint(
                fields=("empresa", "cuenta"),
                name="unique_regla_empresa_cuenta",
            ),
        ),
    ]
