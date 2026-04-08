from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
import json
import re
import threading
from .models import ProductoOferta, AdsReportSnapshot
from .webhooks import send_botize_webhook_async
from datetime import datetime, date
from decimal import Decimal
from django.conf import settings
import requests, os
import logging

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract structured campaign metrics from this Google Ads report.
Return ONLY valid JSON array, no markdown, no explanation.
Schema: [{"campaign_name": str, "campaign_id": str or null, "spend": float,
"conversions": float, "cost_per_conversion": float, "ctr": float,
"clicks": int, "impressions": int, "impression_share": float or null,
"keywords": [{"text": str, "match_type": str, "quality_score": int or null,
"cpc": float or null, "spend": float or null, "conversions": float or null}]}]
Use 0 or null for missing values. Amounts in MXN. If no data can be extracted, return [].

Report:
"""


def _check_ads_auth(request):
    """Check Bearer token auth for ads-analyst endpoints. Returns error response or None."""
    auth = request.headers.get('Authorization', '')
    app_password = os.getenv('APP_PASSWORD', '')
    if auth != f'Bearer {app_password}':
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    return None


def looks_like_report(text):
    """Heuristic: is this user message a pasted Google Ads report?"""
    if len(text) < 200:
        return False
    indicators = [
        bool(re.search(r'\$[\d,]+', text)),
        bool(re.search(r'\d+\.\d+%', text)),
        bool(re.search(r'(?i)campaign|campaña', text)),
        bool(re.search(r'(?i)impression|impresion', text)),
        bool(re.search(r'(?i)click|clic', text)),
        bool(re.search(r'(?i)conversion|conversión|conv', text)),
        bool(re.search(r'(?i)CTR|CPC|CPA', text)),
    ]
    return sum(indicators) >= 3


def _extract_and_save_metrics(snapshot_id, raw_report, api_key):
    """Background: ask Claude to extract structured metrics, update snapshot."""
    try:
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 2000,
                'messages': [{'role': 'user', 'content': EXTRACTION_PROMPT + raw_report}]
            },
            timeout=30,
        )
        data = response.json()
        text = data['content'][0]['text']
        metrics = json.loads(text)
        AdsReportSnapshot.objects.filter(id=snapshot_id).update(campaign_metrics=metrics)
        logger.info("Metrics extracted for snapshot %s", snapshot_id)
    except Exception as e:
        logger.error("Metric extraction failed for snapshot %s: %s", snapshot_id, e)


def _detect_account(system_prompt):
    """Detect account from the system prompt content."""
    if not system_prompt:
        return 'both'
    if 'MatMarkt' in system_prompt and 'Cortina Hawaiana' in system_prompt:
        if 'dos cuentas' in system_prompt or 'ambas' in system_prompt.lower():
            return 'both'
    if 'MatMarkt' in system_prompt:
        return 'matmarkt'
    if 'Cortina Hawaiana' in system_prompt:
        return 'cortina'
    return 'both'


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

    auth_error = _check_ads_auth(request)
    if auth_error:
        return auth_error

    try:
        body = json.loads(request.body.decode('utf-8'))
        api_key = os.getenv('ANTHROPIC_API_KEY', '')

        # Extract account field (sent by frontend), remove before forwarding
        account = body.pop('account', None)
        if not account:
            account = _detect_account(body.get('system', ''))

        # Forward to Anthropic
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'Content-Type': 'application/json',
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
            },
            json=body,
            timeout=60,
        )

        response_data = response.json()

        # Auto-save if the last user message looks like a report
        snapshot_id = None
        if response.status_code == 200:
            messages = body.get('messages', [])
            last_user_msg = ''
            for msg in reversed(messages):
                if msg.get('role') == 'user':
                    last_user_msg = msg.get('content', '')
                    break

            if looks_like_report(last_user_msg):
                analysis = ''
                content = response_data.get('content', [])
                if content and content[0].get('text'):
                    analysis = content[0]['text']

                snapshot = AdsReportSnapshot.objects.create(
                    account=account,
                    report_date=date.today(),
                    raw_report=last_user_msg,
                    analysis=analysis,
                    is_auto_saved=True,
                )
                snapshot_id = snapshot.id

                # Extract structured metrics in background
                thread = threading.Thread(
                    target=_extract_and_save_metrics,
                    args=(snapshot.id, last_user_msg, api_key),
                    daemon=True,
                )
                thread.start()

        if snapshot_id:
            response_data['snapshot_id'] = snapshot_id

        return JsonResponse(response_data, status=response.status_code)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def ads_snapshots_list_create(request):
    """GET: list snapshots, POST: manual save."""
    auth_error = _check_ads_auth(request)
    if auth_error:
        return auth_error

    if request.method == 'GET':
        account = request.GET.get('account')
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))

        qs = AdsReportSnapshot.objects.all()
        if account:
            qs = qs.filter(account=account)

        snapshots = qs[offset:offset + limit]
        data = [{
            'id': s.id,
            'account': s.account,
            'account_display': s.get_account_display(),
            'report_date': s.report_date.isoformat(),
            'created_at': s.created_at.isoformat(),
            'analysis_preview': s.analysis[:150] + '...' if len(s.analysis) > 150 else s.analysis,
            'has_metrics': bool(s.campaign_metrics),
            'is_auto_saved': s.is_auto_saved,
        } for s in snapshots]

        return JsonResponse({'snapshots': data, 'count': qs.count()})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body.decode('utf-8'))
            report_date_str = body.get('report_date', date.today().isoformat())
            try:
                report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
            except ValueError:
                report_date = date.today()

            snapshot = AdsReportSnapshot.objects.create(
                account=body.get('account', 'both'),
                report_date=report_date,
                raw_report=body.get('raw_report', ''),
                analysis=body.get('analysis', ''),
                is_auto_saved=False,
            )

            # Extract metrics in background if there's a report
            if snapshot.raw_report:
                api_key = os.getenv('ANTHROPIC_API_KEY', '')
                thread = threading.Thread(
                    target=_extract_and_save_metrics,
                    args=(snapshot.id, snapshot.raw_report, api_key),
                    daemon=True,
                )
                thread.start()

            return JsonResponse({'id': snapshot.id, 'status': 'saved'}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def ads_snapshot_detail(request, snapshot_id):
    """GET: full snapshot detail."""
    auth_error = _check_ads_auth(request)
    if auth_error:
        return auth_error

    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        s = AdsReportSnapshot.objects.get(pk=snapshot_id)
        return JsonResponse({
            'id': s.id,
            'account': s.account,
            'account_display': s.get_account_display(),
            'report_date': s.report_date.isoformat(),
            'created_at': s.created_at.isoformat(),
            'raw_report': s.raw_report,
            'analysis': s.analysis,
            'campaign_metrics': s.campaign_metrics,
            'has_metrics': bool(s.campaign_metrics),
            'is_auto_saved': s.is_auto_saved,
        })
    except AdsReportSnapshot.DoesNotExist:
        return JsonResponse({'error': 'Snapshot not found'}, status=404)


@csrf_exempt
def ads_snapshot_compare(request):
    """GET: compare two snapshots side-by-side with deltas."""
    auth_error = _check_ads_auth(request)
    if auth_error:
        return auth_error

    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    id1 = request.GET.get('id1')
    id2 = request.GET.get('id2')
    if not id1 or not id2:
        return JsonResponse({'error': 'Both id1 and id2 are required'}, status=400)

    try:
        s1 = AdsReportSnapshot.objects.get(pk=id1)
        s2 = AdsReportSnapshot.objects.get(pk=id2)
    except AdsReportSnapshot.DoesNotExist:
        return JsonResponse({'error': 'Snapshot not found'}, status=404)

    # Build lookup by campaign name for each snapshot
    metrics1 = {m['campaign_name']: m for m in (s1.campaign_metrics or [])}
    metrics2 = {m['campaign_name']: m for m in (s2.campaign_metrics or [])}

    all_campaigns = set(list(metrics1.keys()) + list(metrics2.keys()))
    comparison = []

    for campaign in sorted(all_campaigns):
        m1 = metrics1.get(campaign, {})
        m2 = metrics2.get(campaign, {})
        delta = {}
        for field in ['spend', 'conversions', 'cost_per_conversion', 'ctr', 'clicks', 'impressions']:
            v1 = m1.get(field, 0) or 0
            v2 = m2.get(field, 0) or 0
            delta[field] = round(v2 - v1, 2)

        comparison.append({
            'campaign_name': campaign,
            'snapshot_1': m1,
            'snapshot_2': m2,
            'delta': delta,
        })

    return JsonResponse({
        'snapshot_1': {
            'id': s1.id, 'report_date': s1.report_date.isoformat(), 'account': s1.account
        },
        'snapshot_2': {
            'id': s2.id, 'report_date': s2.report_date.isoformat(), 'account': s2.account
        },
        'campaigns': comparison,
    })


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
