import strawberry
from strawberry_django import type
from .models import Post, ProductoOferta

@type(Post)
class PostType:
    id: strawberry.ID
    title: str
    content: str
    created_at: str
    
@type(ProductoOferta)
class ProductoOfertaType:
    id: strawberry.ID
    titulo: str
    precio_original: float
    descuento: float
    precio_oferta: float
    url_imagen: str
    link_referidos: str
    fecha: str
    categoria: str