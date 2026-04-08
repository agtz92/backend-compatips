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

    def __str__(self):
        return f"{self.get_account_display()} — {self.report_date}"