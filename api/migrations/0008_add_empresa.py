from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_factura_movimientobanco"),
    ]

    operations = [
        # --- MovimientoBanco ---
        migrations.AddField(
            model_name="movimientobanco",
            name="empresa",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.RemoveConstraint(
            model_name="movimientobanco",
            name="unique_movimiento",
        ),
        migrations.AddConstraint(
            model_name="movimientobanco",
            constraint=models.UniqueConstraint(
                fields=("fecha", "monto", "referencia", "descripcion", "empresa"),
                name="unique_movimiento_empresa",
            ),
        ),

        # --- Factura ---
        migrations.AddField(
            model_name="factura",
            name="empresa",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.RemoveConstraint(
            model_name="factura",
            name="unique_factura_folio_fecha",
        ),
        migrations.AddConstraint(
            model_name="factura",
            constraint=models.UniqueConstraint(
                fields=("folio", "fecha", "empresa"),
                name="unique_factura_folio_fecha_empresa",
            ),
        ),
    ]
