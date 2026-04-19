from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_adsreportsnapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="MovimientoBanco",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("fecha", models.DateField(db_index=True)),
                ("descripcion", models.TextField(blank=True, default="")),
                (
                    "referencia",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=255
                    ),
                ),
                ("monto", models.DecimalField(decimal_places=2, max_digits=14)),
                ("tipo", models.CharField(blank=True, default="", max_length=20)),
                ("fila_origen", models.JSONField(blank=True, default=dict)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-fecha", "-creado_en"],
            },
        ),
        migrations.AddConstraint(
            model_name="movimientobanco",
            constraint=models.UniqueConstraint(
                fields=("fecha", "monto", "referencia", "descripcion"),
                name="unique_movimiento",
            ),
        ),
        migrations.AddIndex(
            model_name="movimientobanco",
            index=models.Index(
                fields=["fecha", "monto"], name="api_movimi_fecha_8a6a4d_idx"
            ),
        ),
        migrations.CreateModel(
            name="Factura",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("folio", models.CharField(db_index=True, max_length=100)),
                ("fecha", models.DateField(db_index=True)),
                ("cliente", models.CharField(blank=True, default="", max_length=255)),
                ("concepto", models.TextField(blank=True, default="")),
                ("total", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "estatus",
                    models.CharField(
                        choices=[
                            ("pendiente", "Pendiente"),
                            ("pagada", "Pagada"),
                            ("coincidencia", "Por coincidencia"),
                        ],
                        db_index=True,
                        default="pendiente",
                        max_length=20,
                    ),
                ),
                ("confianza_coincidencia", models.FloatField(blank=True, null=True)),
                ("fila_origen", models.JSONField(blank=True, default=dict)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "movimiento_pago",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="facturas_pagadas",
                        to="api.movimientobanco",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha", "-creado_en"],
            },
        ),
        migrations.AddConstraint(
            model_name="factura",
            constraint=models.UniqueConstraint(
                fields=("folio", "fecha"), name="unique_factura_folio_fecha"
            ),
        ),
        migrations.AddIndex(
            model_name="factura",
            index=models.Index(
                fields=["fecha", "estatus"], name="api_factura_fecha_b9c1e2_idx"
            ),
        ),
    ]
