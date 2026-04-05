import threading
import requests
import json
import logging

logger = logging.getLogger(__name__)

BOTIZE_WEBHOOK_URL = "https://botize.com/webhook/agtz92@2ea6e9221b445044c5c5d91de7227b97ae51e5b2c9bf1fd88056b9aaff8af976/24"


def _send_botize_webhook(payload):
    """Send webhook payload to Botize. Runs in a background thread."""
    try:
        logger.info("Sending webhook to Botize: %s", json.dumps(payload, indent=2, ensure_ascii=False))
        response = requests.post(BOTIZE_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Botize responded with: %s", response.status_code)
    except requests.RequestException as e:
        logger.error("Error sending Botize webhook: %s", e)


def send_botize_webhook_async(producto):
    """Fire-and-forget webhook notification to Botize for a new product."""
    payload = {
        "title": producto.titulo,
        "img": producto.url_imagen,
        "originalprice": str(producto.precio_original),
        "discountprice": str(producto.precio_oferta) if producto.precio_oferta else "",
        "url": f"https://www.compatips.com/producto/{producto.id}"
    }
    thread = threading.Thread(target=_send_botize_webhook, args=(payload,), daemon=True)
    thread.start()
