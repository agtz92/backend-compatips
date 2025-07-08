import strawberry
from typing import List, Optional
from .models import Post, ProductoOferta
from .types import PostType, ProductoOfertaType
from django.db.models import Q
from datetime import datetime
import requests, json
import logging

logger = logging.getLogger(__name__)

# ✅ QUERIES
@strawberry.type
class Query:
    @strawberry.field
    def posts(self) -> List[PostType]:
        return Post.objects.all()

    @strawberry.field
    def productos(self) -> List[ProductoOfertaType]:
        return ProductoOferta.objects.order_by('-fecha')


    @strawberry.field
    def productos_filtrados(
        self,
        categoria: Optional[str] = None,
        search: Optional[str] = None,
        ordenar_por: Optional[str] = None
    ) -> List[ProductoOfertaType]:
        queryset = ProductoOferta.objects.all()

        if categoria:
            queryset = queryset.filter(categoria__iexact=categoria)

        if search:
            queryset = queryset.filter(titulo__icontains=search)

        if ordenar_por:
            queryset = queryset.order_by(ordenar_por)
        else:
            queryset = queryset.order_by('-fecha')

        return queryset


    @strawberry.field
    def producto_por_id(self, id: strawberry.ID) -> ProductoOfertaType:
        return ProductoOferta.objects.get(pk=id)
    
    @strawberry.field
    def categorias_unicas(self) -> List[str]:
        return ProductoOferta.objects.order_by().values_list('categoria', flat=True).distinct()



# ✅ MUTATIONS
@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_post(self, title: str, content: str) -> PostType:
        post = Post.objects.create(title=title, content=content)
        return post

    @strawberry.mutation
    def create_producto(
        self,
        titulo: str,
        precio_original: float,
        descuento: float,
        url_imagen: str,
        link_referidos: str,
        fecha: str,  # DD-MM-YYYY
        categoria: str,
        precio_oferta: float = None
    ) -> ProductoOfertaType:
        fecha_parsed = datetime.strptime(fecha, "%d-%m-%Y").date()

        producto = ProductoOferta.objects.create(
            titulo=titulo,
            precio_original=precio_original,
            descuento=descuento,
            precio_oferta=precio_oferta,
            url_imagen=url_imagen,
            link_referidos=link_referidos,
            fecha=fecha_parsed,
            categoria=categoria
        )

        # 👉 Enviar POST al webhook de Botize
        try:
            webhook_url = "https://botize.com/webhook/agtz92@2ea6e9221b445044c5c5d91de7227b97ae51e5b2c9bf1fd88056b9aaff8af976/24"
            payload = {
                "title": producto.titulo,
                "img": producto.url_imagen,
                "originalprice": str(producto.precio_original),
                "discountprice": str(producto.precio_oferta),
                "url": f"https://frontend-compatips-x8tl.vercel.app/producto/{producto.id}"
            }
            logger.info("📦 JSON enviado a Botize:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"❌ Error al enviar webhook: {e}")

        return producto


# ✅ SCHEMA FINAL
schema = strawberry.Schema(query=Query, mutation=Mutation)
