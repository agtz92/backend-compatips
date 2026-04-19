"""Conciliación de facturas vs movimientos bancarios.

Reglas:
- Exacta ('pagada'): el monto del movimiento coincide con el total de la
  factura Y el folio (o el cliente) aparece en la descripción/referencia del
  movimiento. La fecha del movimiento debe ser igual o posterior a la factura
  (con tolerancia hacia atrás de 3 días para cargos preautorizados).
- Coincidencia ('coincidencia'): el monto coincide (con tolerancia mínima)
  pero NO se identifica por folio/cliente, dentro de una ventana de fechas.
"""
from decimal import Decimal
from datetime import timedelta
import re
import unicodedata

# Tolerancia absoluta en pesos para considerar montos "iguales"
TOLERANCIA_MONTO = Decimal('0.01')
# Ventana de días alrededor de la fecha de factura para coincidencias
VENTANA_DIAS = 7
# Tolerancia hacia atrás para match exacto (cargos pre-autorizados)
DIAS_PREVIO_EXACTO = 3


def _normalize(text):
    if not text:
        return ''
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text).strip()


def _haystack(mov):
    """Texto donde buscar identificadores (folio/cliente) del movimiento."""
    parts = [mov.descripcion, mov.referencia]
    if mov.fila_origen:
        parts.extend(str(v) for v in mov.fila_origen.values())
    return _normalize(' '.join(p for p in parts if p))


def _factura_identifica(factura, haystack):
    """¿El folio o el nombre del cliente aparece en el texto del movimiento?"""
    folio = _normalize(factura.folio)
    if folio and len(folio) >= 4 and folio in haystack:
        return True
    cliente = _normalize(factura.cliente)
    if cliente and len(cliente) >= 4:
        # Considerar match si al menos una palabra significativa del cliente
        # (>=4 letras) aparece en el texto.
        for token in cliente.split():
            if len(token) >= 4 and token in haystack:
                return True
    return False


def _monto_match(a, b):
    return abs(Decimal(a) - Decimal(b)) <= TOLERANCIA_MONTO


def conciliar(facturas, movimientos):
    """Asigna movimientos a facturas in-place.

    facturas: queryset/lista de Factura (mutable)
    movimientos: queryset/lista de MovimientoBanco

    Modifica cada factura en memoria asignando estatus, movimiento_pago y
    confianza_coincidencia. NO guarda en DB (caller decide).

    Devuelve un dict con conteos: {'pagadas': n, 'coincidencias': n, 'pendientes': n}.
    """
    # Pre-calcular haystack por movimiento
    movs = list(movimientos)
    info_movs = [(m, _haystack(m)) for m in movs]
    usados = set()  # ids de movimientos ya asignados

    pagadas = coincidencias = pendientes = 0

    # PASO 1: matches exactos (monto + identificador textual)
    for f in facturas:
        f.estatus = 'pendiente'
        f.movimiento_pago = None
        f.confianza_coincidencia = None
        for mov, hay in info_movs:
            if mov.pk in usados:
                continue
            if not _monto_match(mov.monto, f.total):
                continue
            # ventana de fechas: la mayoría de pagos llegan después de la
            # factura; permitimos algo previo por cargos preautorizados
            delta = (mov.fecha - f.fecha).days
            if delta < -DIAS_PREVIO_EXACTO or delta > VENTANA_DIAS * 4:
                continue
            if _factura_identifica(f, hay):
                f.estatus = 'pagada'
                f.movimiento_pago = mov
                f.confianza_coincidencia = 1.0
                usados.add(mov.pk)
                pagadas += 1
                break

    # PASO 2: coincidencias por monto (sin identificador) dentro de ventana
    for f in facturas:
        if f.estatus != 'pendiente':
            continue
        candidato = None
        mejor_delta = None
        for mov, _hay in info_movs:
            if mov.pk in usados:
                continue
            if not _monto_match(mov.monto, f.total):
                continue
            delta = abs((mov.fecha - f.fecha).days)
            if delta > VENTANA_DIAS:
                continue
            if mejor_delta is None or delta < mejor_delta:
                candidato = mov
                mejor_delta = delta
        if candidato is not None:
            f.estatus = 'coincidencia'
            f.movimiento_pago = candidato
            # confianza inversamente proporcional a la distancia en días
            f.confianza_coincidencia = round(
                max(0.3, 1 - (mejor_delta / (VENTANA_DIAS + 1))), 2
            )
            usados.add(candidato.pk)
            coincidencias += 1

    pendientes = sum(1 for f in facturas if f.estatus == 'pendiente')
    return {
        'pagadas': pagadas,
        'coincidencias': coincidencias,
        'pendientes': pendientes,
    }
