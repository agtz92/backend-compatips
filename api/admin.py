from django.contrib import admin
from .models import Post, ProductoOferta, AdsReportSnapshot, Factura, MovimientoBanco, ReglaCuenta

admin.site.register(Post)
@admin.register(ProductoOferta)
class ProductoOfertaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "precio_original", "descuento", "precio_oferta", "categoria", "fecha")
    search_fields = ("titulo", "categoria")

@admin.register(AdsReportSnapshot)
class AdsReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ("account", "report_date", "created_at", "is_auto_saved", "has_metrics")
    list_filter = ("account", "is_auto_saved", "report_date")
    search_fields = ("raw_report", "analysis")
    readonly_fields = ("created_at",)

    def has_metrics(self, obj):
        return bool(obj.campaign_metrics)
    has_metrics.boolean = True


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ("folio", "fecha", "cliente", "total", "estatus",
                    "movimiento_pago", "confianza_coincidencia")
    list_filter = ("estatus", "fecha")
    search_fields = ("folio", "cliente", "concepto")
    readonly_fields = ("creado_en", "actualizado_en")


@admin.register(MovimientoBanco)
class MovimientoBancoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "empresa", "cuenta", "monto", "referencia", "descripcion", "tipo")
    list_filter = ("empresa", "cuenta", "fecha", "tipo")
    search_fields = ("referencia", "descripcion")
    readonly_fields = ("creado_en",)


@admin.register(ReglaCuenta)
class ReglaCuentaAdmin(admin.ModelAdmin):
    list_display = ("empresa", "cuenta", "prefijos_folio", "descripcion")
    list_filter = ("empresa",)
    search_fields = ("empresa", "cuenta")
