from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
import json
from .models import ProductoOferta
from .webhooks import send_botize_webhook_async
from datetime import datetime
from decimal import Decimal
from django.conf import settings
import requests, os
import logging

def health_check(request):
    return JsonResponse({"status": "ok"})


def ads_analyst_html(request):
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ads-analyst.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return HttpResponse(content, content_type='text/html')


@csrf_exempt
def ads_analyst_chat(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    auth = request.headers.get('Authorization', '')
    app_password = os.getenv('APP_PASSWORD', '')
    if auth != f'Bearer {app_password}':
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            data=request.body,
            timeout=60,
        )
        return JsonResponse(response.json(), status=response.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

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

        # Send Botize webhook in background thread (non-blocking)
        send_botize_webhook_async(producto)

        return JsonResponse({"status": "ok", "id": producto.id})

    except Exception as e:
        print(f"❌ Error general: {e}")
        return JsonResponse({"error": str(e)}, status=500)

