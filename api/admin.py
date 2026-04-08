from django.contrib import admin
from .models import Post, ProductoOferta, AdsReportSnapshot

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
