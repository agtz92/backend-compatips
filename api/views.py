from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
import json
from .models import ProductoOferta
from datetime import datetime
from decimal import Decimal
from django.conf import settings
import requests, json
import logging

def health_check(request):
    return JsonResponse({"status": "ok"})

@csrf_exempt
def recibir_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
        print("RAW BODY:", body)

        producto = ProductoOferta.objects.create(
            titulo=body["titulo"],
            precio_original=float(body["precio_original"]),
            descuento=float(body["descuento"]),
            precio_oferta=float(body["precio_oferta"]),
            url_imagen=body["url_imagen"],
            link_referidos=body["link_referidos"],
            fecha=datetime.strptime(body["fecha"], "%d-%m-%Y").date(),
            categoria=body["categoria"]
        )

        # Enviar a Botize
        try:
            webhook_url = "https://botize.com/webhook/agtz92@2ea6e9221b445044c5c5d91de7227b97ae51e5b2c9bf1fd88056b9aaff8af976/24"
            payload = {
                "title": producto.titulo,
                "img": producto.url_imagen,
                "originalprice": str(producto.precio_original),
                "discountprice": str(producto.precio_oferta) if producto.precio_oferta else "",
                "url": f"https://frontend-compatips-x8tl.vercel.app/producto/{producto.id}"
            }

            print("📦 Payload a enviar a Botize:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            response = requests.post(webhook_url, json=payload)
            print(f"✅ Botize respondió con: {response.status_code} - {response.text}")
            response.raise_for_status()

        except Exception as e:
            print(f"❌ Error al enviar a Botize: {e}")
            return JsonResponse({"error_botize": str(e)}, status=500)

        return JsonResponse({"status": "ok", "id": producto.id})

    except Exception as e:
        print(f"❌ Error general: {e}")
        return JsonResponse({"error": str(e)}, status=500)

