from django.db import models
from datetime import datetime
from decimal import Decimal
from django.utils import timezone

class Post(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class ProductoOferta(models.Model):
    titulo = models.CharField(max_length=255, db_index=True)

    precio_original = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=5, decimal_places=2)  # percentage
    precio_oferta = models.DecimalField(max_digits=10, decimal_places=2)

    url_imagen = models.URLField()
    link_referidos = models.URLField()

    fecha = models.DateField(db_index=True)
    categoria = models.CharField(max_length=100, db_index=True)

    def __str__(self):
        return f"{self.titulo} - ${self.precio_oferta:.2f}"


class Factura(models.Model):
    ESTATUS_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('coincidencia', 'Por coincidencia'),
    ]

    folio = models.CharField(max_length=100, db_index=True)
    fecha = models.DateField(db_index=True)
    empresa = models.CharField(max_length=100, blank=True, default='', db_index=True)
    cliente = models.CharField(max_length=255, blank=True, default='')
    concepto = models.TextField(blank=True, default='')
    total = models.DecimalField(max_digits=14, decimal_places=2)

    estatus = models.CharField(
        max_length=20, choices=ESTATUS_CHOICES, default='pendiente', db_index=True
    )
    movimiento_pago = models.ForeignKey(
        'MovimientoBanco', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='facturas_pagadas',
    )
    confianza_coincidencia = models.FloatField(null=True, blank=True)

    override_manual = models.BooleanField(default=False, db_index=True)
    comentario_override = models.TextField(blank=True, default='')

    fila_origen = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha', '-creado_en']
        constraints = [
            models.UniqueConstraint(fields=['folio', 'fecha', 'empresa'], name='unique_factura_folio_fecha_empresa'),
        ]
        indexes = [
            models.Index(fields=['fecha', 'estatus']),
        ]

    def __str__(self):
        return f"{self.folio} — {self.fecha} — ${self.total:.2f}"


class MovimientoBanco(models.Model):
    fecha = models.DateField(db_index=True)
    empresa = models.CharField(max_length=100, blank=True, default='', db_index=True)
    cuenta = models.CharField(max_length=100, blank=True, default='', db_index=True)
    descripcion = models.TextField(blank=True, default='')
    referencia = models.CharField(max_length=255, blank=True, default='', db_index=True)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    tipo = models.CharField(max_length=100, blank=True, default='')

    fila_origen = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-creado_en']
        constraints = [
            models.UniqueConstraint(
                fields=['fecha', 'monto', 'referencia', 'descripcion', 'empresa', 'cuenta'],
                name='unique_movimiento_empresa_cuenta',
            ),
        ]
        indexes = [
            models.Index(fields=['fecha', 'monto']),
        ]

    def __str__(self):
        return f"{self.fecha} — ${self.monto:.2f} — {self.referencia or self.descripcion[:40]}"


class AdsReportSnapshot(models.Model):
    ACCOUNT_CHOICES = [
        ('matmarkt', 'MatMarkt'),
        ('cortina', 'Cortina Hawaiana'),
        ('both', 'Both'),
    ]

    account = models.CharField(max_length=20, choices=ACCOUNT_CHOICES, db_index=True)
    report_date = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    raw_report = models.TextField()
    analysis = models.TextField(blank=True, default='')

    # Structured metrics extracted by Claude, stored as JSON
    # Schema: [{ "campaign_name": str, "campaign_id": str|null, "spend": float,
    #            "conversions": float, "cost_per_conversion": float,
    #            "ctr": float, "clicks": int, "impressions": int,
    #            "impression_share": float|null,
    #            "keywords": [{ "text": str, "match_type": str,
    #                           "quality_score": int|null, "cpc": float|null,
    #                           "spend": float|null, "conversions": float|null }]
    #          }]
    campaign_metrics = models.JSONField(default=list, blank=True)

    is_auto_saved = models.BooleanField(default=True)

    class Meta:
        ordering = ['-report_date', '-created_at']
        indexes = [
            models.Index(fields=['account', 'report_date']),
        ]


class ReglaCuenta(models.Model):
    empresa = models.CharField(max_length=100, db_index=True)
    cuenta = models.CharField(max_length=100)
    prefijos_folio = models.JSONField(default=list)
    descripcion = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['empresa', 'cuenta']
        constraints = [
            models.UniqueConstraint(fields=['empresa', 'cuenta'],
                                    name='unique_regla_empresa_cuenta'),
        ]

    def __str__(self):
        return f"{self.empresa} / {self.cuenta} → {self.prefijos_folio}"