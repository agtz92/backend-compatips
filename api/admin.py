from django.contrib import admin
from .models import Post, ProductoOferta

admin.site.register(Post)
@admin.register(ProductoOferta)
class ProductoOfertaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "precio_original", "descuento", "precio_oferta", "categoria", "fecha")
    search_fields = ("titulo", "categoria")
