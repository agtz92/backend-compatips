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
    if request.method != 'POST':
        return HttpResponseBadRequest("Método no permitido")
    
    # Validar token en headers
    token = request.headers.get("X-Webhook-Token")
    if token != settings.WEBHOOK_SECRET:
        return JsonResponse({"error": "Token inválido"}, status=403)

    try:
        data = json.loads(request.body)

        producto = ProductoOferta.objects.create(
            titulo=data['titulo'],
            precio_original=Decimal(str(data['precio_original'])),
            descuento=Decimal(str(data['descuento'])),
            precio_oferta=Decimal(str(data['precio_oferta'])),
            url_imagen=data['url_imagen'],
            link_referidos=data['link_referidos'],
            fecha=datetime.strptime(data['fecha'], "%d-%m-%Y").date(),
            categoria=data['categoria']
        )
        return JsonResponse({"status": "ok", "id": producto.id})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)