import strawberry
from strawberry_django import type
from .models import ProductoOferta, Post
from datetime import datetime, timedelta, date
from django.utils import timezone

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

    @strawberry.field
    def es_reciente(self) -> bool:
        try:
            if isinstance(self.fecha, str):
                fecha_dt = datetime.strptime(self.fecha, "%Y-%m-%d").date()
            else:
                fecha_dt = self.fecha
        except Exception:
            return False

        limite = date.today() - timedelta(weeks=2)
        return fecha_dt >= limite

