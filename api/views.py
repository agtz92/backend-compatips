from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
import json
import re
import threading
from .models import ProductoOferta, AdsReportSnapshot, Factura, MovimientoBanco
from .webhooks import send_botize_webhook_async
from . import excel_parser, reconciliation, sheets_sync
from django.utils import timezone
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
def recibir_ads_report(request):
    """Receive Google Ads campaign data from Google Ads Scripts."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    auth_error = _check_ads_auth(request)
    if auth_error:
        return auth_error

    try:
        body = json.loads(request.body.decode('utf-8'))
        account = body.get('account', '')
        if account not in ('matmarkt', 'cortina'):
            return JsonResponse({'error': 'Invalid account. Use "matmarkt" or "cortina".'}, status=400)

        campaigns = body.get('campaigns', [])
        if not campaigns:
            return JsonResponse({'error': 'No campaign data provided'}, status=400)

        report_date_str = body.get('report_date', date.today().isoformat())
        try:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except ValueError:
            report_date = date.today()

        # Build raw_report text from structured data for the analysis field
        raw_lines = [f"Google Ads Report — {account} — {report_date.isoformat()}", ""]
        for c in campaigns:
            raw_lines.append(f"Campaign: {c.get('campaign_name', 'Unknown')}")
            raw_lines.append(f"  Spend: ${c.get('spend', 0):,.2f}")
            raw_lines.append(f"  Clicks: {c.get('clicks', 0)}")
            raw_lines.append(f"  Impressions: {c.get('impressions', 0)}")
            raw_lines.append(f"  CTR: {c.get('ctr', 0):.2f}%")
            raw_lines.append(f"  Conversions: {c.get('conversions', 0)}")
            raw_lines.append(f"  Cost/Conv: ${c.get('cost_per_conversion', 0):,.2f}")
            kws = c.get('keywords', [])
            if kws:
                raw_lines.append("  Keywords:")
                for kw in kws:
                    raw_lines.append(f"    - {kw.get('text', '')} (CPC: ${kw.get('cpc', 0):.2f}, QS: {kw.get('quality_score', '-')})")
            raw_lines.append("")
        raw_report = "\n".join(raw_lines)

        # Normalize campaign_metrics to match expected schema
        campaign_metrics = []
        for c in campaigns:
            campaign_metrics.append({
                'campaign_name': c.get('campaign_name', 'Unknown'),
                'campaign_id': c.get('campaign_id'),
                'spend': float(c.get('spend', 0)),
                'conversions': float(c.get('conversions', 0)),
                'cost_per_conversion': float(c.get('cost_per_conversion', 0)),
                'ctr': float(c.get('ctr', 0)),
                'clicks': int(c.get('clicks', 0)),
                'impressions': int(c.get('impressions', 0)),
                'impression_share': c.get('impression_share'),
                'keywords': c.get('keywords', []),
            })

        snapshot = AdsReportSnapshot.objects.create(
            account=account,
            report_date=report_date,
            raw_report=raw_report,
            analysis='Auto-imported from Google Ads Script',
            campaign_metrics=campaign_metrics,
            is_auto_saved=True,
        )

        logger.info("Ads report snapshot created via webhook: id=%s account=%s", snapshot.id, account)
        return JsonResponse({'status': 'ok', 'snapshot_id': snapshot.id}, status=201)

    except Exception as e:
        logger.error("Error receiving ads report: %s", e)
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


# ---------- Facturación + Conciliación bancaria ----------

def _check_facturas_auth(request):
    auth = request.headers.get('Authorization', '')
    app_password = os.getenv('APP_PASSWORD', '')
    if not app_password or auth != f'Bearer {app_password}':
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    return None


def _factura_to_dict(f):
    pago = None
    if f.movimiento_pago_id:
        m = f.movimiento_pago
        pago = {
            'id': m.id,
            'fecha': m.fecha.isoformat(),
            'monto': float(m.monto),
            'referencia': m.referencia,
            'descripcion': m.descripcion,
        }
    return {
        'id': f.id,
        'folio': f.folio,
        'fecha': f.fecha.isoformat(),
        'empresa': f.empresa,
        'cliente': f.cliente,
        'concepto': f.concepto,
        'total': float(f.total),
        'estatus': f.estatus,
        'estatus_display': f.get_estatus_display(),
        'confianza_coincidencia': f.confianza_coincidencia,
        'override_manual': f.override_manual,
        'comentario_override': f.comentario_override,
        'pago': pago,
    }


def _sheets_sync_async(facturas_payload, empresa):
    """Fire-and-forget sync de facturas a Google Sheets. Loggea resultado o error."""
    if not facturas_payload:
        return

    def _run():
        try:
            resumen = sheets_sync.sync_facturas_a_sheets(facturas_payload, empresa=empresa)
            logger.info("Sheets sync OK (empresa=%s): %s", empresa, resumen)
        except Exception as e:
            logger.error("Sheets sync (async) falló (empresa=%s): %s", empresa, e)

    threading.Thread(target=_run, daemon=True).start()


@csrf_exempt
def facturas_html(request):
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'facturas.html')
    with open(html_path, 'r', encoding='utf-8') as fh:
        return HttpResponse(fh.read(), content_type='text/html')


@csrf_exempt
def upload_facturas(request):
    """POST multipart con `file` Excel. Persiste solo facturas nuevas y, si
    está configurado, las sincroniza a Google Sheets."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error

    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({'error': 'Falta el archivo `file`'}, status=400)

    empresa = request.POST.get('empresa', '').strip()

    try:
        registros = excel_parser.parse_facturas(upload)
    except Exception as e:
        return JsonResponse({'error': f'No se pudo leer el Excel: {e}'}, status=400)

    # Pre-fetch facturas existentes que coinciden con (folio, fecha, empresa)
    folios = {r['folio'] for r in registros}
    fechas = {r['fecha'] for r in registros}
    existentes_map = {}
    if folios and fechas:
        for f in Factura.objects.filter(
            empresa=empresa, folio__in=folios, fecha__in=fechas,
        ):
            existentes_map[(f.folio, f.fecha)] = f

    nuevas_objs = []
    actualizadas_upload = []
    seen_keys = set()
    for r in registros:
        key = (r['folio'], r['fecha'])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        existing = existentes_map.get(key)
        if existing is not None:
            existing.cliente = r['cliente']
            existing.concepto = r['concepto']
            existing.total = r['total']
            existing.fila_origen = r['fila_origen']
            actualizadas_upload.append(existing)
        else:
            nuevas_objs.append(Factura(
                folio=r['folio'],
                fecha=r['fecha'],
                empresa=empresa,
                cliente=r['cliente'],
                concepto=r['concepto'],
                total=r['total'],
                fila_origen=r['fila_origen'],
            ))

    try:
        if nuevas_objs:
            Factura.objects.bulk_create(
                nuevas_objs, ignore_conflicts=True, batch_size=500,
            )
        if actualizadas_upload:
            Factura.objects.bulk_update(
                actualizadas_upload,
                ['cliente', 'concepto', 'total', 'fila_origen'],
                batch_size=500,
            )
    except Exception as e:
        logger.error("Error guardando facturas: %s", e)
        return JsonResponse({'error': f'Error guardando facturas: {e}'}, status=500)

    # Refetch las nuevas para asegurar que tengan PK (bulk_create con
    # ignore_conflicts no garantiza PKs en todos los casos)
    nuevas = []
    if nuevas_objs:
        nuevas_keys = {(o.folio, o.fecha) for o in nuevas_objs}
        candidatas = Factura.objects.filter(
            empresa=empresa,
            folio__in=[k[0] for k in nuevas_keys],
            fecha__in=[k[1] for k in nuevas_keys],
        )
        nuevas = [f for f in candidatas if (f.folio, f.fecha) in nuevas_keys]

    sync_facturas = nuevas + actualizadas_upload
    if sync_facturas and (os.getenv('FACTURACION_SHEET_ID') or empresa):
        _sheets_sync_async(
            [_factura_to_dict(f) for f in sync_facturas],
            empresa,
        )

    try:
        return JsonResponse({
            'status': 'ok',
            'leidas': len(registros),
            'nuevas': len(nuevas),
            'actualizadas': len(actualizadas_upload),
            'sheets': None,
            'sheets_error': None,
            'facturas': [_factura_to_dict(f) for f in nuevas],
        })
    except Exception as e:
        logger.error("Error serializando respuesta: %s", e)
        return JsonResponse({'error': f'Error interno: {e}'}, status=500)


@csrf_exempt
def upload_movimientos(request):
    """POST multipart con `file` Excel de movimientos bancarios. Guarda los
    movimientos nuevos y ejecuta conciliación contra todas las facturas
    pendientes/coincidencia."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error

    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({'error': 'Falta el archivo `file`'}, status=400)

    empresa = request.POST.get('empresa', '').strip()
    cuenta = request.POST.get('cuenta', '').strip()

    nombre = (upload.name or '').lower()
    es_texto = nombre.endswith('.txt') or nombre.endswith('.csv') or nombre.endswith('.tsv')
    try:
        if es_texto:
            registros = excel_parser.parse_movimientos_txt(upload)
        else:
            registros = excel_parser.parse_movimientos(upload)
    except Exception as e:
        return JsonResponse({'error': f'No se pudo leer el archivo: {e}'}, status=400)

    # Pre-fetch movimientos existentes en las fechas del archivo para detectar
    # duplicados sin pegarle a la DB por cada fila
    fechas = {r['fecha'] for r in registros}
    existing_keys = set()
    if fechas:
        for fecha_e, monto_e, ref_e, desc_e in MovimientoBanco.objects.filter(
            empresa=empresa, cuenta=cuenta, fecha__in=fechas,
        ).values_list('fecha', 'monto', 'referencia', 'descripcion'):
            existing_keys.add((fecha_e, monto_e, ref_e, desc_e))

    nuevos_objs = []
    duplicados = 0
    for r in registros:
        key = (r['fecha'], r['monto'], r['referencia'], r['descripcion'])
        if key in existing_keys:
            duplicados += 1
            continue
        existing_keys.add(key)
        nuevos_objs.append(MovimientoBanco(
            fecha=r['fecha'],
            empresa=empresa,
            cuenta=cuenta,
            descripcion=r['descripcion'],
            referencia=r['referencia'],
            monto=r['monto'],
            tipo=r['tipo'],
            fila_origen=r['fila_origen'],
        ))

    try:
        if nuevos_objs:
            MovimientoBanco.objects.bulk_create(
                nuevos_objs, ignore_conflicts=True, batch_size=500,
            )
    except Exception as e:
        logger.error("Error guardando movimientos: %s", e)
        return JsonResponse({'error': f'Error guardando movimientos: {e}'}, status=500)

    movs_nuevos_count = len(nuevos_objs)

    # Filtrar facturas por prefijos de folio si hay regla para esta cuenta
    from .models import ReglaCuenta
    from django.db.models import Q
    facturas_qs = Factura.objects.filter(
        estatus__in=['pendiente', 'coincidencia'],
        empresa=empresa,
        override_manual=False,
    )
    prefijos = []
    if cuenta:
        try:
            regla = ReglaCuenta.objects.get(empresa=empresa, cuenta=cuenta)
            prefijos = regla.prefijos_folio
        except ReglaCuenta.DoesNotExist:
            pass
    if prefijos:
        filtro_prefijos = Q()
        for p in prefijos:
            filtro_prefijos |= Q(folio__istartswith=p)
        facturas_qs = facturas_qs.filter(filtro_prefijos)

    facturas = list(facturas_qs)
    movimientos = list(MovimientoBanco.objects.filter(empresa=empresa, cuenta=cuenta))
    resumen = reconciliation.conciliar(facturas, movimientos)

    actualizadas = []
    if facturas:
        ahora = timezone.now()
        for f in facturas:
            f.actualizado_en = ahora
        try:
            Factura.objects.bulk_update(
                facturas,
                ['estatus', 'movimiento_pago', 'confianza_coincidencia', 'actualizado_en'],
                batch_size=500,
            )
        except Exception as e:
            logger.error("Error actualizando facturas tras conciliación: %s", e)
            return JsonResponse({'error': f'Error actualizando facturas: {e}'}, status=500)
        actualizadas = [_factura_to_dict(f) for f in facturas]

    if actualizadas and (os.getenv('FACTURACION_SHEET_ID') or empresa):
        _sheets_sync_async(actualizadas, empresa)

    return JsonResponse({
        'status': 'ok',
        'empresa': empresa,
        'cuenta': cuenta,
        'prefijos_aplicados': prefijos,
        'movimientos_leidos': len(registros),
        'movimientos_nuevos': movs_nuevos_count,
        'movimientos_duplicados': duplicados,
        'conciliacion': resumen,
        'sheets': None,
        'sheets_error': None,
    })


@csrf_exempt
def facturas_list(request):
    """GET: lista facturas con su estado de conciliación."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error

    estatus = request.GET.get('estatus')
    empresa = request.GET.get('empresa', '')
    mes = request.GET.get('mes', '')  # formato YYYY-MM
    qs = Factura.objects.select_related('movimiento_pago').order_by('-fecha', '-id')
    if estatus:
        qs = qs.filter(estatus=estatus)
    if empresa:
        qs = qs.filter(empresa=empresa)
    if mes:
        try:
            anio, month = mes.split('-')
            qs = qs.filter(fecha__year=int(anio), fecha__month=int(month))
        except ValueError:
            pass
    limit = int(request.GET.get('limit', 100))
    offset = int(request.GET.get('offset', 0))
    total = qs.count()
    items = [_factura_to_dict(f) for f in qs[offset:offset + limit]]
    return JsonResponse({'count': total, 'facturas': items})


@csrf_exempt
def facturas_override(request):
    """POST: marca/desmarca una factura como pagada manualmente.

    Body JSON: { "factura_id": int, "comentario": str, "quitar": bool }
    - quitar=false (default): estatus='pagada', override_manual=True
    - quitar=true: restaura estatus='pendiente', override_manual=False
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error
    import json as _json
    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    factura_id = body.get('factura_id')
    comentario = body.get('comentario', '').strip()
    quitar = bool(body.get('quitar', False))
    try:
        f = Factura.objects.get(pk=factura_id)
    except Factura.DoesNotExist:
        return JsonResponse({'error': 'Factura no encontrada'}, status=404)
    estatus_target = body.get('estatus', 'pagada')
    if quitar or estatus_target == 'pendiente':
        f.override_manual = False
        f.comentario_override = ''
        f.estatus = 'pendiente'
        f.movimiento_pago = None
        f.confianza_coincidencia = None
    else:
        f.override_manual = True
        f.comentario_override = comentario
        f.estatus = 'pagada'
        f.movimiento_pago = None
        f.confianza_coincidencia = 1.0
    f.save()
    empresa = f.empresa
    if os.getenv('FACTURACION_SHEET_ID') or empresa:
        try:
            sheets_sync.sync_facturas_a_sheets([_factura_to_dict(f)], empresa=empresa)
        except Exception as e:
            logger.warning("Sheets sync (override) falló: %s", e)
    return JsonResponse({'status': 'ok', 'factura': _factura_to_dict(f)})


@csrf_exempt
def facturas_empresas(request):
    """GET: lista de empresas únicas registradas en la DB."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error
    empresas = list(
        Factura.objects.values_list('empresa', flat=True)
        .distinct()
        .order_by('empresa')
    )
    return JsonResponse({'empresas': empresas})


@csrf_exempt
def facturas_config(request):
    """GET: configuración por empresa (URL de Google Sheets)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    auth_error = _check_facturas_auth(request)
    if auth_error:
        return auth_error
    empresa = request.GET.get('empresa', '').strip()
    sheet_id = None
    if empresa:
        sheet_id = os.getenv(f'FACTURACION_SHEET_ID_{empresa.upper()}')
    if not sheet_id:
        sheet_id = os.getenv('FACTURACION_SHEET_ID', '')
    sheets_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}' if sheet_id else None
    return JsonResponse({'sheets_url': sheets_url})
