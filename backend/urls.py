from django.contrib import admin
from django.urls import path
from strawberry.django.views import GraphQLView
from django.views.decorators.csrf import csrf_exempt
from api.schema import schema
from api.views import (
    health_check, recibir_webhook, recibir_ads_report,
    ads_analyst_html, ads_analyst_chat,
    ads_snapshots_list_create, ads_snapshot_detail, ads_snapshot_compare,
    facturas_html, upload_facturas, upload_movimientos, facturas_list, facturas_reset,
)


urlpatterns = [
    path('ads-analyst/api/snapshots/compare', ads_snapshot_compare),
    path('ads-analyst/api/snapshots/<int:snapshot_id>', ads_snapshot_detail),
    path('ads-analyst/api/snapshots', ads_snapshots_list_create),
    path('ads-analyst/api/chat', ads_analyst_chat),
    path('ads-analyst', ads_analyst_html),
    path('facturas/api/upload', upload_facturas),
    path('facturas/api/movimientos', upload_movimientos),
    path('facturas/api/list', facturas_list),
    path('facturas/api/reset', facturas_reset),
    path('facturas', facturas_html),
    path('', health_check),
    path('admin/', admin.site.urls),
    path("graphql/", csrf_exempt(GraphQLView.as_view(schema=schema))),
    path('webhook/', recibir_webhook),
    path('webhook/ads-report/', recibir_ads_report),
]
