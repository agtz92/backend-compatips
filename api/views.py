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
        return JsonResponse({"error": "Método no permitido"}, status=405)

    try:
        body_unicode = request.body.decode('utf-8')
        body = json.loads(body_unicode)

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

        # ✅ Enviar a Botize
        try:
            import requests
            import json
            webhook_url = "https://botize.com/webhook/agtz92@2ea6e9221b445044c5c5d91de7227b97ae51e5b2c9bf1fd88056b9aaff8af976/24"

            payload = {
                "titulo": producto.titulo,
                "imagen": producto.url_imagen,
                "precio original": str(producto.precio_original),
                "precio descuento": str(producto.precio_oferta) if producto.precio_oferta else "",
                "url": f"https://frontend-compatips-x8tl.vercel.app/producto/{producto.id}"
            }

            print("📦 Enviando JSON a Botize:")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

            response = requests.post(webhook_url, json=payload)
            response.raise_for_status()
        except Exception as e:
            print(f"❌ Error enviando webhook a Botize: {e}")

        return JsonResponse({"status": "ok", "id": producto.id})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
