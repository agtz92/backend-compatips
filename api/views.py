from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
import json
from .models import ProductoOferta
from datetime import datetime
from decimal import Decimal
from django.conf import settings

def health_check(request):
    return JsonResponse({"status": "ok"})

@csrf_exempt
def recibir_webhook(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Método no permitido")

    try:
        print("RAW BODY:", request.body.decode("utf-8"))
        body = json.loads(request.body)

        activity = body.get("data", {}).get("activity", [])
        if not activity:
            raise ValueError("No hay actividad en el webhook")

        input_data = activity[0].get("input_data", {})

        fecha_str = input_data.get("fecha_hoy")
        if not fecha_str:
            raise ValueError("fecha_hoy no fue proporcionada")

        fecha = datetime.strptime(fecha_str, "%d-%m-%Y").date()

        producto = ProductoOferta.objects.create(
            titulo="Producto desde webhook",
            precio_original=Decimal("100.00"),
            descuento=Decimal("10.00"),
            precio_oferta=Decimal("90.00"),
            url_imagen="https://example.com/default.jpg",
            link_referidos="https://amazon.com/default",
            fecha=fecha,
            categoria="Automático"
        )

        return JsonResponse({"status": "ok", "id": producto.id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)