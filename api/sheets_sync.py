"""Sincronización con Google Sheets para facturación.

Crea (o reutiliza) una pestaña por mes (formato YYYY-MM) y agrega únicamente
las facturas que aún no estén presentes en la pestaña, comparando por folio.
"""
import json
import logging
import os
from datetime import date

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

HEADERS = ['Folio', 'Fecha', 'Cliente', 'Concepto', 'Total', 'Estatus',
           'Pago: Fecha', 'Pago: Monto', 'Pago: Referencia',
           'Confianza', 'Nota']


MONTH_NAMES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
    7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre',
    11: 'Noviembre', 12: 'Diciembre',
}


def _sheet_id_for_empresa(empresa=''):
    """Resuelve el spreadsheet_id para una empresa dada.

    Busca FACTURACION_SHEET_ID_{EMPRESA} primero; cae en FACTURACION_SHEET_ID.
    """
    if empresa:
        slug = empresa.upper().replace('-', '_').replace(' ', '_')
        sid = os.getenv(f'FACTURACION_SHEET_ID_{slug}', '')
        if sid:
            return sid
    return os.getenv('FACTURACION_SHEET_ID', '')


def _get_client():
    """Construye un cliente de gspread a partir de credenciales en env."""
    raw = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', '')
    if not raw:
        raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_JSON no está configurado.')
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _tab_name_for(d):
    """Nombre de la pestaña: 'YYYY-MM Mes'."""
    return f"{d.year}-{d.month:02d} {MONTH_NAMES_ES[d.month]}"


def _get_or_create_worksheet(spreadsheet, tab_name):
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=200, cols=len(HEADERS))
        ws.append_row(HEADERS, value_input_option='USER_ENTERED')
        return ws
    # Asegurar header si la hoja existe pero está vacía
    first = ws.row_values(1)
    if not first:
        ws.append_row(HEADERS, value_input_option='USER_ENTERED')
    return ws


def _existing_folios(ws):
    """Mapa {folio: numero_de_fila} de las facturas ya presentes (columna A)."""
    col = ws.col_values(1)
    return {v.strip(): i + 2 for i, v in enumerate(col[1:]) if v and v.strip()}


def _col_letter(n):
    """1->A, 2->B, ...; suficiente para los <26 columnas que usamos."""
    return chr(ord('A') + n - 1)


def _row_for(factura):
    """Construye fila para Sheets a partir de un dict de factura.

    `factura` puede ser un dict del parser o un Factura ORM serializado.
    """
    pago = factura.get('pago') or {}
    estatus = factura.get('estatus', 'pendiente')
    if estatus == 'pagada':
        estatus_label = '✓ Pagada'
        nota = ''
    elif estatus == 'coincidencia':
        estatus_label = '⚠ Por coincidencia'
        nota = 'Coincidencia por monto — sin referencia identificada. Verificar manualmente.'
    else:
        estatus_label = 'Pendiente'
        nota = ''
    return [
        factura['folio'],
        factura['fecha'].isoformat() if isinstance(factura['fecha'], date)
            else str(factura['fecha']),
        factura.get('cliente', ''),
        factura.get('concepto', ''),
        float(factura['total']),
        estatus_label,
        pago.get('fecha', ''),
        pago.get('monto', ''),
        pago.get('referencia', ''),
        factura.get('confianza_coincidencia', '') or '',
        nota,
    ]


def sync_facturas_a_sheets(facturas, spreadsheet_id=None, empresa=''):
    """Agrega facturas nuevas a Google Sheets agrupadas por mes.

    facturas: iterable de dicts con folio/fecha/cliente/concepto/total y
        opcionalmente estatus/pago/confianza_coincidencia.
    spreadsheet_id: opcional. Si no se da, resuelve por empresa o usa
        env FACTURACION_SHEET_ID.
    empresa: slug de empresa para resolver el sheet_id (ej: 'hpkabr').

    Retorna {tab_name: cantidad_agregada}.
    """
    spreadsheet_id = spreadsheet_id or _sheet_id_for_empresa(empresa)
    if not spreadsheet_id:
        raise RuntimeError('No hay FACTURACION_SHEET_ID configurado para esta empresa.')

    client = _get_client()
    ss = client.open_by_key(spreadsheet_id)

    por_mes = {}
    for f in facturas:
        tab = _tab_name_for(f['fecha'])
        por_mes.setdefault(tab, []).append(f)

    resumen = {}
    last_col = _col_letter(len(HEADERS))
    for tab_name, items in por_mes.items():
        ws = _get_or_create_worksheet(ss, tab_name)
        existentes = _existing_folios(ws)
        nuevas = [f for f in items if f['folio'] not in existentes]
        actualizadas = [f for f in items if f['folio'] in existentes]

        if nuevas:
            nuevas.sort(key=lambda f: (f['fecha'], f['folio']))
            ws.append_rows(
                [_row_for(f) for f in nuevas],
                value_input_option='USER_ENTERED',
            )

        if actualizadas:
            updates = []
            for f in actualizadas:
                row_num = existentes[f['folio']]
                rng = f"A{row_num}:{last_col}{row_num}"
                updates.append({'range': rng, 'values': [_row_for(f)]})
            ws.batch_update(updates, value_input_option='USER_ENTERED')

        resumen[tab_name] = {'nuevas': len(nuevas), 'actualizadas': len(actualizadas)}
        logger.info(
            "Sheets sync '%s': %s nuevas, %s actualizadas",
            tab_name, len(nuevas), len(actualizadas),
        )

    return resumen
