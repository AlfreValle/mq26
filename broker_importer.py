"""
broker_importer.py — Importador Universal de Comprobantes de Brokers
Soporta: Balanz | Bull Market Brokers | IOL (Invertir Online)
Detecta el formato automáticamente por las columnas.
Convierte precio ARS → PPC_USD usando CCL del día de la operación.
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.logging_config import get_logger
from core.pricing_utils import (
    es_accion_local,
)
from core.pricing_utils import (
    parsear_precio_ars as limpiar_precio_ars,
)
from core.pricing_utils import (
    ppc_usd_desde_precio_ars as precio_ars_to_ppc_usd,
)

logger = get_logger(__name__)


# ── PARSER IOL ────────────────────────────────────────────────────────────────


def _es_formato_iol(df: pd.DataFrame) -> bool:
    """IOL exporta con columnas en español: Especie, Cantidad, Precio promedio."""
    cols_lower = [str(c).lower().strip() for c in df.columns]
    return any(
        x in cols_lower
        for x in ("especie", "precio promedio", "cantidad tenencia")
    )


def parsear_iol(df_raw: pd.DataFrame, ccl: float = 1450.0) -> pd.DataFrame:
    """
    Parsea exportación IOL (Mi cartera → Tenencia → Exportar).

    Devuelve el mismo esquema que parsear_balanz() para encadenar con
    _dataframe_comprobante_final / Maestra.
    """
    import re

    rows: list[dict] = []
    try:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df.columns]

        col_map: dict[str, str] = {}
        for col in df.columns:
            cl = col.lower()
            if (
                "especie" in cl or "ticker" in cl or "activo" in cl
            ) and "TICKER_RAW" not in col_map:
                col_map["TICKER_RAW"] = col
            elif "cantidad" in cl and "CANTIDAD" not in col_map:
                col_map["CANTIDAD"] = col
            elif (
                "precio prom" in cl or "costo prom" in cl or "precio medio" in cl
            ) and "PPC_ARS_RAW" not in col_map:
                col_map["PPC_ARS_RAW"] = col
            elif (
                "tipo" in cl or "instrumento" in cl
            ) and "TIPO_RAW" not in col_map:
                col_map["TIPO_RAW"] = col

        if "TICKER_RAW" not in col_map or "CANTIDAD" not in col_map:
            return pd.DataFrame()

        today = date.today()
        fecha_str = today.strftime("%Y-%m-%d")

        for _, row in df.iterrows():
            ticker_raw = str(row.get(col_map["TICKER_RAW"], "") or "").strip().upper()
            if not ticker_raw or ticker_raw in ("NAN", "ESPECIE", "TOTAL", ""):
                continue

            cantidad = float(
                pd.to_numeric(row.get(col_map.get("CANTIDAD", ""), 0), errors="coerce")
                or 0.0
            )
            if cantidad == 0:
                continue

            ppc_ars = float(
                pd.to_numeric(row.get(col_map.get("PPC_ARS_RAW", ""), 0), errors="coerce")
                or 0.0
            )

            tipo_raw = str(row.get(col_map.get("TIPO_RAW", ""), "") or "").strip().upper()
            if not tipo_raw:
                tipo_raw = "BONO" if re.search(r"\d", ticker_raw) else "CEDEAR"

            tipo_norm = {
                "CEDEAR": "CEDEAR",
                "ACCION": "ACCION_LOCAL",
                "OBLIGACION": "ON_USD",
                "ON": "ON_USD",
                "BONO": "BONO_USD",
                "LETRA": "LETRA",
                "FCI": "FCI",
                "CAUCIONES": "CAUCION",
            }.get(tipo_raw, "CEDEAR")

            if tipo_norm == "CEDEAR":
                tipo_activo = "Cedears"
                precio_ars = ppc_ars
                ppc_usd = precio_ars_to_ppc_usd(precio_ars, ticker_raw, ccl)
            else:
                tipo_map = {
                    "ACCION_LOCAL": "Acción",
                    "ON_USD": "ON",
                    "BONO_USD": "Bonos",
                    "LETRA": "Letras",
                    "FCI": "FCI",
                    "CAUCION": "Cauciones",
                }
                tipo_activo = tipo_map.get(tipo_norm, tipo_norm)
                precio_ars = ppc_ars
                ppc_usd = precio_ars_to_ppc_usd(precio_ars, ticker_raw, ccl)

            neto_ars = cantidad * precio_ars
            cant_int = int(round(float(cantidad)))

            rows.append({
                "Tipo": "COMPRA",
                "Ticker": ticker_raw,
                "Cantidad": max(1, cant_int) if cant_int < 1 else cant_int,
                "Precio_ARS": precio_ars,
                "Neto_ARS": neto_ars,
                "PPC_USD": round(float(ppc_usd), 4),
                "Fecha": fecha_str,
                "Broker": "IOL",
                "Tipo_Activo": tipo_activo,
            })

        return pd.DataFrame(rows)
    except Exception as e:
        logger.debug("parsear_iol: %s", e)
        return pd.DataFrame()


def detectar_formato(df: pd.DataFrame) -> str:
    """Detecta si el DataFrame es formato Balanz, Bull Market o IOL."""
    if _es_formato_iol(df):
        return "iol"
    cols = [str(c).strip().lower() for c in df.columns]
    if '#boleto' in cols or 'boleto' in cols:
        return 'balanz'
    if any('cedear' in str(c).upper() for c in df.columns):
        return 'bullmarket'
    # Buscar en los datos
    for col in df.columns:
        vals = df[col].astype(str).str.upper()
        if vals.str.contains('COMPRA NORMAL|VENTA NORMAL').any():
            return 'bullmarket'
    return 'desconocido'


def parsear_balanz(df_raw: pd.DataFrame, ccl: float = 1450.0) -> pd.DataFrame:
    """Parsea el formato de comprobante Balanz."""
    # Limpiar fila vacía inicial si existe
    df = df_raw.dropna(subset=[c for c in df_raw.columns if 'ticker' in str(c).lower() or 'Ticker' in str(c)], how='all').copy()

    # Buscar columnas por nombre aproximado
    col_map = {}
    for c in df.columns:
        cl = str(c).strip().lower()
        if 'tipo' in cl:           col_map['tipo'] = c
        elif 'ticker' in cl:       col_map['ticker'] = c
        elif 'cant' in cl:         col_map['cantidad'] = c
        elif 'precio' in cl and 'bruto' not in cl and 'neto' not in cl: col_map['precio'] = c
        elif 'neto' in cl:         col_map['neto'] = c
        elif 'fecha' in cl or 'liqui' in cl: col_map['fecha'] = c

    rows = []
    for _, row in df.iterrows():
        ticker = str(row.get(col_map.get('ticker',''), '')).strip().upper()
        if not ticker or ticker == 'NAN' or ticker == 'TICKER':
            continue
        tipo      = str(row.get(col_map.get('tipo',''), '')).strip().upper()
        if tipo not in ('COMPRA', 'VENTA'):
            continue
        cantidad  = abs(int(pd.to_numeric(row.get(col_map.get('cantidad',''), 0), errors='coerce') or 0))
        precio_ars= limpiar_precio_ars(row.get(col_map.get('precio',''), 0))
        neto_ars  = limpiar_precio_ars(row.get(col_map.get('neto',''), 0))
        fecha_raw = row.get(col_map.get('fecha',''), date.today())
        fecha     = pd.to_datetime(fecha_raw, errors='coerce')
        fecha_str = fecha.strftime('%Y-%m-%d') if not pd.isna(fecha) else str(date.today())
        ppc_usd     = precio_ars_to_ppc_usd(precio_ars, ticker, ccl)
        tipo_activo = 'Acción' if es_accion_local(ticker) else 'Cedears'

        rows.append({
            'Tipo':       tipo,
            'Ticker':     ticker,
            'Cantidad':   cantidad,
            'Precio_ARS': precio_ars,
            'Neto_ARS':   neto_ars,
            'PPC_USD':    ppc_usd,
            'Fecha':      fecha_str,
            'Broker':     'Balanz',
            'Tipo_Activo':tipo_activo,
        })
    return pd.DataFrame(rows)


def parsear_bullmarket(df_raw: pd.DataFrame, ccl: float = 1450.0) -> pd.DataFrame:
    """Parsea el formato de comprobante Bull Market Brokers."""
    rows = []
    data = df_raw.values.tolist()

    for row in data:
        if len(row) < 4:
            continue
        c0 = str(row[0]).strip()
        c1 = str(row[1]).strip() if len(row) > 1 else ''
        c2 = str(row[2]).strip() if len(row) > 2 else ''
        c3 = str(row[3]).strip() if len(row) > 3 else ''
        c4 = str(row[4]).strip() if len(row) > 4 else ''
        c5 = str(row[5]).strip() if len(row) > 5 else ''

        # Fila de datos: ticker corto + tipo operación + cantidad numérica
        es_tipo_op = any(t in c2 for t in ['Compra', 'Venta', 'COMPRA', 'VENTA'])
        if not es_tipo_op:
            continue
        if c0 in ('Ticker', 'nan', ''):
            continue

        try:
            cantidad  = int(float(c3))
            precio_ars= float(c4) if c4 not in ('nan','') else 0.0
            neto_ars  = float(c5) if c5 not in ('nan','') else 0.0
            fecha     = pd.to_datetime(c1, errors='coerce')
            fecha_str = fecha.strftime('%Y-%m-%d') if not pd.isna(fecha) else str(date.today())
            tipo      = 'COMPRA' if 'Compra' in c2 else 'VENTA'
            ticker    = c0.upper().strip()
            ppc_usd     = precio_ars_to_ppc_usd(precio_ars, ticker, ccl)
            tipo_activo = 'Acción' if es_accion_local(ticker) else 'Cedears'

            rows.append({
                'Tipo':       tipo,
                'Ticker':     ticker,
                'Cantidad':   abs(cantidad),
                'Precio_ARS': precio_ars,
                'Neto_ARS':   neto_ars,
                'PPC_USD':    ppc_usd,
                'Fecha':      fecha_str,
                'Broker':     'Bull Market',
                'Tipo_Activo':tipo_activo,
            })
        except Exception:
            continue
    return pd.DataFrame(rows)


def normalizar_hoja_comprobante(df_raw: pd.DataFrame, ccl: float = 1450.0) -> pd.DataFrame:
    """Parsea una tabla suelta (CSV / una hoja) al formato interno de parsear_*."""
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()
    fmt = detectar_formato(df_raw)
    if fmt == "iol":
        return parsear_iol(df_raw, ccl=ccl)
    if fmt == "balanz":
        return parsear_balanz(df_raw, ccl=ccl)
    if fmt == "bullmarket":
        return parsear_bullmarket(df_raw, ccl=ccl)
    df_p = parsear_iol(df_raw, ccl=ccl)
    if df_p.empty:
        df_p = parsear_balanz(df_raw, ccl=ccl)
    if df_p.empty:
        df_p = parsear_bullmarket(df_raw, ccl=ccl)
    return df_p


def _dataframe_comprobante_final(
    df_parts: list[pd.DataFrame],
    propietario: str,
    cartera: str,
) -> pd.DataFrame:
    if not df_parts:
        return pd.DataFrame()
    df_final = pd.concat(df_parts, ignore_index=True)
    df_final = df_final.rename(columns={"Tipo": "Tipo_Op"})
    cols = [
        "Propietario", "Cartera", "Ticker", "Tipo_Activo", "Tipo_Op",
        "Cantidad", "Precio_ARS", "Neto_ARS", "PPC_USD", "Fecha", "Broker",
    ]
    cols = [c for c in cols if c in df_final.columns]
    return df_final[cols].sort_values("Fecha").reset_index(drop=True)


def importar_archivo_broker(
    uploaded_like,
    propietario: str,
    cartera: str,
    ccl: float = 1450.0,
) -> pd.DataFrame:
    """
    Acepta upload de Streamlit o BytesIO: .xlsx / .xls / .csv / .txt
    """
    import io

    name = str(getattr(uploaded_like, "name", "") or "").lower()
    raw = uploaded_like.read()
    if hasattr(uploaded_like, "seek"):
        try:
            uploaded_like.seek(0)
        except Exception:
            pass
    if name.endswith(".csv") or name.endswith(".txt"):
        try:
            df_raw = pd.read_csv(io.BytesIO(raw))
        except Exception:
            return pd.DataFrame()
        df_p = normalizar_hoja_comprobante(df_raw, ccl=ccl)
        if df_p.empty:
            return pd.DataFrame()
        df_p["Propietario"] = propietario
        df_p["Cartera"] = cartera
        return _dataframe_comprobante_final([df_p], propietario, cartera)
    bio = io.BytesIO(raw)
    try:
        xl = pd.ExcelFile(bio)
    except Exception:
        try:
            df_raw = pd.read_excel(io.BytesIO(raw))
        except Exception:
            return pd.DataFrame()
        df_p = normalizar_hoja_comprobante(df_raw, ccl=ccl)
        if df_p.empty:
            return pd.DataFrame()
        df_p["Propietario"] = propietario
        df_p["Cartera"] = cartera
        return _dataframe_comprobante_final([df_p], propietario, cartera)
    dfs = []
    for hoja in xl.sheet_names:
        df_raw = pd.read_excel(xl, sheet_name=hoja, header=0)
        if df_raw.empty:
            continue
        fmt = detectar_formato(df_raw)
        if fmt == "iol":
            df_parsed = parsear_iol(df_raw, ccl=ccl)
        elif fmt == "balanz":
            df_parsed = parsear_balanz(df_raw, ccl=ccl)
        elif fmt == "bullmarket":
            df_parsed = parsear_bullmarket(df_raw, ccl=ccl)
        else:
            df_parsed = parsear_iol(df_raw, ccl=ccl)
            if df_parsed.empty:
                df_parsed = parsear_balanz(df_raw, ccl=ccl)
            if df_parsed.empty:
                df_parsed = parsear_bullmarket(df_raw, ccl=ccl)
        if not df_parsed.empty:
            df_parsed["Propietario"] = propietario
            df_parsed["Cartera"] = cartera
            dfs.append(df_parsed)
    return _dataframe_comprobante_final(dfs, propietario, cartera)


def importar_comprobante(
    archivo,           # path string, Path, o BytesIO
    propietario: str,
    cartera: str,
    ccl: float = 1450.0,
) -> pd.DataFrame:
    """
    Función principal. Lee un Excel con una o dos hojas de comprobantes,
    detecta el formato de cada hoja, y devuelve un DataFrame unificado.

    Columnas de salida:
        Propietario | Cartera | Ticker | Tipo_Activo | Tipo_Op |
        Cantidad | Precio_ARS | Neto_ARS | PPC_USD | Fecha | Broker
    """
    xl = pd.ExcelFile(archivo)
    dfs = []

    for hoja in xl.sheet_names:
        df_raw = pd.read_excel(xl, sheet_name=hoja, header=0)
        if df_raw.empty:
            continue

        fmt = detectar_formato(df_raw)

        if fmt == "iol":
            df_parsed = parsear_iol(df_raw, ccl=ccl)
        elif fmt == "balanz":
            df_parsed = parsear_balanz(df_raw, ccl=ccl)
        elif fmt == "bullmarket":
            df_parsed = parsear_bullmarket(df_raw, ccl=ccl)
        else:
            df_parsed = parsear_iol(df_raw, ccl=ccl)
            if df_parsed.empty:
                df_parsed = parsear_balanz(df_raw, ccl=ccl)
            if df_parsed.empty:
                df_parsed = parsear_bullmarket(df_raw, ccl=ccl)

        if not df_parsed.empty:
            df_parsed['Propietario'] = propietario
            df_parsed['Cartera']     = cartera
            dfs.append(df_parsed)

    return _dataframe_comprobante_final(dfs, propietario, cartera)


def aplicar_operaciones_a_maestra(
    df_ops: pd.DataFrame,
    ruta_maestra: Path,
) -> pd.DataFrame:
    """
    Agrega las operaciones importadas al Maestra_Inversiones.xlsx.
    Las ventas se guardan con cantidad NEGATIVA para que el libro mayor las reste.
    """
    # Cargar maestra existente
    if ruta_maestra.exists():
        df_maestra = pd.read_excel(ruta_maestra)
    else:
        df_maestra = pd.DataFrame(columns=['Propietario','Cartera','Ticker','Cantidad','PPC_USD','FECHA_INICIAL','Tipo'])

    # Construir filas nuevas
    filas_nuevas = []
    for _, op in df_ops.iterrows():
        cant = int(op['Cantidad']) if op['Tipo_Op'] == 'COMPRA' else -int(op['Cantidad'])
        filas_nuevas.append({
            'Propietario':  op['Propietario'],
            'Cartera':      op['Cartera'],
            'Ticker':       op['Ticker'],
            'Cantidad':     cant,
            'PPC_USD':      round(float(op['PPC_USD']), 4),
            'FECHA_INICIAL':op['Fecha'],
            'Tipo':         op.get('Tipo_Activo', 'Cedears'),
        })

    df_nuevas = pd.DataFrame(filas_nuevas)
    df_resultado = pd.concat([df_maestra, df_nuevas], ignore_index=True)
    df_resultado.to_excel(ruta_maestra, index=False)
    return df_resultado
