import strawberry
from typing import List, Optional
from .models import Post, ProductoOferta
from .types import PostType, ProductoOfertaType
from .webhooks import send_botize_webhook_async
from django.db.models import Q
from django.core.cache import cache
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

# ✅ QUERIES
@strawberry.type
class Query:
    @strawberry.field
    def posts(self, limit: int = 20, offset: int = 0) -> List[PostType]:
        return Post.objects.all()[offset:offset + limit]

    @strawberry.field
    def productos(self, limit: Optional[int] = None, offset: int = 0) -> List[ProductoOfertaType]:
        queryset = ProductoOferta.objects.order_by('-fecha')
        if limit is not None:
            return queryset[offset:offset + limit]
        return queryset[offset:]


    @strawberry.field
    def productos_filtrados(
        self,
        categoria: Optional[str] = None,
        search: Optional[str] = None,
        ordenar_por: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[ProductoOfertaType]:
        limite = date.today() - timedelta(weeks=2)
        queryset = ProductoOferta.objects.filter(fecha__gte=limite)

        if categoria:
            queryset = queryset.filter(categoria__iexact=categoria)

        if search:
            queryset = queryset.filter(titulo__icontains=search)

        if ordenar_por:
            queryset = queryset.order_by(ordenar_por)
        else:
            queryset = queryset.order_by('-fecha')

        if limit is not None:
            return queryset[offset:offset + limit]
        return queryset[offset:]


    @strawberry.field
    def producto_por_id(self, id: strawberry.ID) -> ProductoOfertaType:
        return ProductoOferta.objects.get(pk=id)
    
    @strawberry.field
    def categorias_unicas(self) -> List[str]:
        cache_key = 'categorias_unicas'
        categorias = cache.get(cache_key)
        if categorias is None:
            categorias = list(
                ProductoOferta.objects.order_by()
                .values_list('categoria', flat=True)
                .distinct()
            )
            cache.set(cache_key, categorias, timeout=600)  # 10 minutes
        return categorias



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

        # Invalidate categories cache on new product
        cache.delete('categorias_unicas')

        # Send Botize webhook in background thread (non-blocking)
        send_botize_webhook_async(producto)

        return producto


# ✅ SCHEMA FINAL
schema = strawberry.Schema(query=Query, mutation=Mutation)
