from django.db import models
from datetime import datetime
from decimal import Decimal

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