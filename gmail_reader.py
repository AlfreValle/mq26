"""
gmail_reader.py — Lector de correos de brokers desde Gmail
Lee automáticamente:
  - Balanz: "Resumen de boletos de las operaciones del día"
  - Bull Market: "Operaciones del Dia: AAAA-MM-DD"
Convierte precio ARS por CEDEAR → PPC_USD usando CCL histórico estimado.
Genera un DataFrame con todo el historial de operaciones.
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RATIOS_CEDEAR as RATIOS
from core.logging_config import get_logger
from core.pricing_utils import (
    ccl_historico_por_fecha,
    es_accion_local,
    ppc_usd_desde_precio_ars,
)
from core.pricing_utils import (
    parsear_precio_ars as limpiar_ars,
)

logger = get_logger(__name__)


def get_ccl(fecha_str: str) -> float:
    """CCL estimado para el mes de la fecha dada."""
    return ccl_historico_por_fecha(fecha_str, fallback=1350.0)


def ars_to_usd(precio_ars: float, ticker: str, fecha: str) -> float:
    """Convierte precio ARS por CEDEAR a PPC_USD usando CCL histórico del mes."""
    ccl = get_ccl(fecha)
    return ppc_usd_desde_precio_ars(precio_ars, ticker, ccl)


# ─── PARSER BALANZ ────────────────────────────────────────────────────────────
def parse_balanz(body: str) -> list:
    """
    Extrae operaciones del cuerpo del correo Balanz.
    Patrón: Nro_Boleto COMPRA/VENTA TICKER ... Cantidad $ Precio $ Bruto $ Ar $ IVA $ Der $ Neto Pesos DD/MM/AAAA
    """
    rows = []
    pattern = (
        r'([\d\.]+)\s+(COMPRA|VENTA)\s+([A-Z0-9]+)\s+'
        r'(?:[^$\d]+?)\s+(\d+)\s+'
        r'\$\s*([\d\.,]+)\s+'    # precio
        r'\$\s*([\d\.,]+)\s+'    # bruto
        r'\$\s*([\d\.,]+)\s+'    # arancel
        r'\$\s*([\d\.,]+)\s+'    # IVA
        r'\$\s*([\d\.,]+)\s+'    # der mercado
        r'\$\s*([\d\.,]+)\s+'    # neto
        r'Pesos\s+(\d{2}/\d{2}/\d{4})'
    )
    for m in re.finditer(pattern, body):
        boleto   = m.group(1).replace('.','')
        tipo     = m.group(2)
        ticker   = m.group(3).upper().strip()
        cantidad = int(m.group(4))
        precio   = limpiar_ars(m.group(5))
        neto     = limpiar_ars(m.group(10))
        fecha_dd = m.group(11)
        p = fecha_dd.split('/')
        fecha    = f"{p[2]}-{p[1]}-{p[0]}"

        rows.append({
            'Broker':      'Balanz',
            'Fecha':       fecha,
            'Tipo_Op':     tipo,
            'Ticker':      ticker,
            'Tipo_Activo': 'Acción' if es_accion_local(ticker) else 'Cedears',
            'Cantidad':    cantidad,
            'Precio_ARS':  precio,
            'Neto_ARS':    neto,
            'Ratio':       RATIOS.get(ticker, 1),
            'CCL_dia':     get_ccl(fecha),
            'PPC_USD':     ars_to_usd(precio, ticker, fecha),
            'Boleto':      boleto,
        })
    return rows


# ─── PARSER BULL MARKET ───────────────────────────────────────────────────────
def parse_bullmarket(body: str) -> list:
    """
    Formato:
    TICKER  AAAA-MM-DD  Compra Normal  N.NN  PPPP.PP  MMMM.MM
    """
    rows = []
    # Palabras que no son tickers
    NO_TICKER = {'EL','LA','DE','LOS','LAS','UN','UNA','EN','CON','POR','QUE',
                 'SU','SE','AL','DEL','ADS','INC','CORP','SA','SAB','ETF'}
    pattern = (
        r'\b([A-Z]{2,6})\s+'
        r'(\d{4}-\d{2}-\d{2})\s+'
        r'(Compra Normal|Venta Normal|Compra|Venta)\s+'
        r'([\d\.]+)\s+'
        r'([\d\.]+)\s+'
        r'([\d\.]+)'
    )
    for m in re.finditer(pattern, body):
        ticker   = m.group(1).upper()
        if ticker in NO_TICKER:
            continue
        fecha    = m.group(2)
        tipo_raw = m.group(3)
        tipo     = 'COMPRA' if 'Compra' in tipo_raw else 'VENTA'
        try:
            cantidad = int(float(m.group(4)))
            precio   = float(m.group(5))
            neto     = float(m.group(6))
        except (ValueError, IndexError, AttributeError):
            continue

        rows.append({
            'Broker':      'Bull Market',
            'Fecha':       fecha,
            'Tipo_Op':     tipo,
            'Ticker':      ticker,
            'Tipo_Activo': 'Acción' if es_accion_local(ticker) else 'Cedears',
            'Cantidad':    cantidad,
            'Precio_ARS':  precio,
            'Neto_ARS':    neto,
            'Ratio':       RATIOS.get(ticker, 1),
            'CCL_dia':     get_ccl(fecha),
            'PPC_USD':     ars_to_usd(precio, ticker, fecha),
            'Boleto':      '',
        })
    return rows


# ─── LECTOR GMAIL (usa credenciales del sistema) ──────────────────────────────
def leer_todos_los_correos(mensajes_balanz: list, mensajes_bull: list) -> pd.DataFrame:
    """
    Recibe listas de mensajes ya leídos (body como string) y parsea todos.
    mensajes_balanz: [{'body': str, 'fecha': str}, ...]
    mensajes_bull:   [{'body': str, 'fecha': str}, ...]
    """
    todas = []
    for msg in mensajes_balanz:
        rows = parse_balanz(msg['body'])
        todas.extend(rows)
    for msg in mensajes_bull:
        rows = parse_bullmarket(msg['body'])
        todas.extend(rows)

    if not todas:
        return pd.DataFrame()

    df = pd.DataFrame(todas)
    df = df.sort_values('Fecha').reset_index(drop=True)
    # Eliminar duplicados (mismo boleto)
    if 'Boleto' in df.columns:
        df = df.drop_duplicates(subset=['Boleto','Ticker','Fecha','Tipo_Op','Cantidad'],
                                keep='first')
    return df


def exportar_a_excel(df: pd.DataFrame, ruta_salida: Path) -> None:
    """Exporta el historial de operaciones a Excel con formato."""
    with pd.ExcelWriter(ruta_salida, engine='openpyxl') as writer:
        # Hoja 1: Historial completo
        df.to_excel(writer, sheet_name='Historial Completo', index=False)

        # Hoja 2: Solo 2025-2026
        df_reciente = df[df['Fecha'] >= '2025-01-01']
        df_reciente.to_excel(writer, sheet_name='2025-2026', index=False)

        # Hoja 3: Resumen por ticker
        resumen = df.groupby(['Ticker','Tipo_Op']).agg(
            Cant_Total=('Cantidad','sum'),
            Neto_ARS_Total=('Neto_ARS','sum'),
            Operaciones=('Cantidad','count'),
        ).reset_index()
        resumen.to_excel(writer, sheet_name='Resumen por Ticker', index=False)

    logger.info("Historial exportado a Excel: %s (%d filas)", ruta_salida, len(df))


def construir_maestra_desde_historial(df: pd.DataFrame, propietario_map: dict) -> pd.DataFrame:
    """
    Convierte el historial de operaciones en el formato Maestra_Inversiones.xlsx
    propietario_map: {'Balanz': {'propietario': 'Alfredo y Andrea', 'cartera': 'Retiro'},
                      'Bull Market': {'propietario': 'Alfredo', 'cartera': 'Reto 2026'}}
    """
    rows = []
    for _, op in df.iterrows():
        broker = op['Broker']
        info   = propietario_map.get(broker, {'propietario':'Desconocido','cartera':'Sin Cartera'})
        cant   = int(op['Cantidad']) if op['Tipo_Op'] == 'COMPRA' else -int(op['Cantidad'])
        rows.append({
            'Propietario':  info['propietario'],
            'Cartera':      info['cartera'],
            'Ticker':       op['Ticker'],
            'Cantidad':     cant,
            'PPC_USD':      op['PPC_USD'],
            'FECHA_INICIAL':op['Fecha'],
            'Tipo':         op['Tipo_Activo'],
        })
    return pd.DataFrame(rows)
