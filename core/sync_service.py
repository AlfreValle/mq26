"""
core/sync_service.py — Sincronización bidireccional Excel ↔ Base de datos
MQ26-DSS | Fuente de verdad: Excel (Maestra_Inversiones.xlsx) → BD como espejo.

Estrategia definida:
  - Excel es el ORIGEN PRINCIPAL de posiciones (editado por el usuario en Streamlit).
  - La BD replica la información de Excel para consultas rápidas y auditoría.
  - Flujo: operación nueva → se escribe en Excel → se sincroniza a BD.
  - La BD nunca es modificada directamente desde la UI; solo a través de este servicio.

Funciones principales:
  sincronizar_excel_a_bd(ruta_excel) → lee Maestra y popula la BD.
  exportar_bd_a_excel(ruta_salida, tenant_id=...)   → Excel desde la BD (solo ese tenant).
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logging_config import get_logger
from core.pricing_utils import parsear_ppc_usd

logger = get_logger(__name__)


def sincronizar_excel_a_bd(ruta_excel: Path) -> dict:
    """
    Lee Maestra_Inversiones.xlsx y replica el contenido en la BD.
    Devuelve un dict con métricas: {'insertadas': n, 'actualizadas': n, 'errores': n}
    """
    from core import db_manager as dbm

    resultado = {"insertadas": 0, "actualizadas": 0, "errores": 0, "total": 0}

    if not ruta_excel.exists():
        logger.warning("sync_excel_a_bd: Excel no encontrado → %s", ruta_excel)
        return resultado

    try:
        df = pd.read_excel(ruta_excel, sheet_name=0)
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as exc:
        logger.error("sync_excel_a_bd: no se pudo leer el Excel: %s", exc)
        resultado["errores"] += 1
        return resultado

    if df.empty:
        logger.info("sync_excel_a_bd: Excel vacío, nada que sincronizar.")
        return resultado

    col_ticker   = _buscar_col(df, ["Ticker", "TICKER"])
    col_cantidad = _buscar_col(df, ["Cantidad", "CANTIDAD"])
    col_ppc      = _buscar_col(df, ["PPC_USD", "PPC"])
    col_prop     = _buscar_col(df, ["Propietario", "PROPIETARIO"])
    col_cartera  = _buscar_col(df, ["Cartera", "CARTERA"])
    col_fecha    = _buscar_col(df, ["FECHA_INICIAL", "Fecha", "FECHA"])
    col_tipo     = _buscar_col(df, ["Tipo", "TIPO"])

    if not col_ticker or not col_cantidad:
        logger.error("sync_excel_a_bd: columnas Ticker/Cantidad no encontradas.")
        resultado["errores"] += 1
        return resultado

    for _, row in df.iterrows():
        try:
            ticker   = str(row.get(col_ticker, "")).strip().upper()
            if not ticker:
                continue
            cantidad = int(pd.to_numeric(row.get(col_cantidad, 0), errors="coerce") or 0)
            if cantidad <= 0:
                continue
            ppc_usd  = parsear_ppc_usd(row.get(col_ppc, 0.0))
            prop     = str(row.get(col_prop, "")) if col_prop else ""
            cartera  = str(row.get(col_cartera, "")) if col_cartera else ""
            tipo     = str(row.get(col_tipo, "Cedears")) if col_tipo else "Cedears"
            fecha_val = row.get(col_fecha) if col_fecha else None
            try:
                fecha = pd.to_datetime(fecha_val, errors="coerce").date() if fecha_val else date.today()
            except Exception:
                fecha = date.today()

            cartera_id = f"{prop} | {cartera}".strip(" |")

            # Buscar cliente por nombre/cartera o crear
            clientes_df = dbm.obtener_clientes_df()
            cliente_match = clientes_df[clientes_df["Nombre"].str.contains(prop, case=False, na=False)] \
                if not clientes_df.empty and prop else pd.DataFrame()

            if not cliente_match.empty:
                cliente_id = int(cliente_match.iloc[0]["ID"])
            else:
                if prop:
                    cliente_id = dbm.registrar_cliente(prop, "Moderado", 0.0, "Persona")
                else:
                    continue

            # Registrar como transacción COMPRA en la BD
            dbm.registrar_transaccion(
                cliente_id=cliente_id,
                ticker=ticker,
                tipo_op="COMPRA",
                cantidad=cantidad,
                precio=ppc_usd,
                fecha=str(fecha),
            )
            resultado["insertadas"] += 1
            resultado["total"] += 1

        except Exception as exc:
            logger.warning("sync_excel_a_bd: error en fila %s → %s", row.get(col_ticker, "?"), exc)
            resultado["errores"] += 1

    logger.info(
        "sync_excel_a_bd: insertadas=%d actualizadas=%d errores=%d",
        resultado["insertadas"], resultado["actualizadas"], resultado["errores"],
    )
    return resultado


def exportar_bd_a_excel(ruta_salida: Path, tenant_id: str = "default") -> bool:
    """
    Genera un Excel con las transacciones de la BD para un tenant.
    Útil como backup o para reconstruir la Maestra desde cero.
    Devuelve True si tuvo éxito.
    """
    from core import db_manager as dbm

    try:
        df = dbm.obtener_todos_los_trades(tenant_id=tenant_id)
        if df.empty:
            logger.warning("exportar_bd_a_excel: BD sin transacciones.")
            return False
        ruta_salida.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(ruta_salida, index=False)
        logger.info("exportar_bd_a_excel: %d filas exportadas a %s", len(df), ruta_salida)
        return True
    except Exception as exc:
        logger.error("exportar_bd_a_excel: %s", exc)
        return False


def reconciliar_fuentes(ruta_csv: Path, tenant_id: str = "default") -> dict:
    """
    D6: Reconciliación CSV vs SQLite.
    Compara las operaciones del CSV transaccional con las de la tabla transacciones en BD.
    Devuelve dict con: en_csv_no_bd, en_bd_no_csv, coincidencias, discrepancias.
    """
    from core import db_manager as dbm

    resultado = {
        "en_csv_no_bd":  [],
        "en_bd_no_csv":  [],
        "coincidencias": 0,
        "discrepancias": 0,
        "error": None,
    }

    if not ruta_csv.exists():
        resultado["error"] = f"CSV no encontrado: {ruta_csv}"
        return resultado

    try:
        df_csv = pd.read_csv(ruta_csv)
        df_csv["FECHA_COMPRA"] = pd.to_datetime(df_csv.get("FECHA_COMPRA", ""), errors="coerce").dt.date
        df_csv["TICKER"]       = df_csv.get("TICKER", pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        df_csv["CANTIDAD"]     = pd.to_numeric(df_csv.get("CANTIDAD", 0), errors="coerce").fillna(0)
    except Exception as exc:
        resultado["error"] = f"Error leyendo CSV: {exc}"
        return resultado

    try:
        df_bd = dbm.obtener_todos_los_trades(tenant_id=tenant_id)
        df_bd["TICKER"]   = df_bd.get("ticker",    pd.Series(dtype=str)).astype(str).str.upper().str.strip()
        df_bd["CANTIDAD"] = pd.to_numeric(df_bd.get("nominales", 0), errors="coerce").fillna(0)
        df_bd["FECHA"]    = pd.to_datetime(df_bd.get("fecha", ""), errors="coerce").dt.date
    except Exception as exc:
        resultado["error"] = f"Error leyendo BD: {exc}"
        return resultado

    # Crear clave única: TICKER + FECHA + CANTIDAD
    def _clave(row, col_fecha="FECHA_COMPRA"):
        return f"{row.get('TICKER','')}-{row.get(col_fecha,'')}-{int(abs(row.get('CANTIDAD',0)))}"

    claves_csv = set(df_csv.apply(_clave, axis=1).tolist()) if not df_csv.empty else set()
    claves_bd  = set(df_bd.apply(lambda r: _clave(r, "FECHA"), axis=1).tolist()) if not df_bd.empty else set()

    solo_csv = claves_csv - claves_bd
    solo_bd  = claves_bd  - claves_csv
    comunes  = claves_csv & claves_bd

    resultado["en_csv_no_bd"]  = sorted(list(solo_csv))[:50]
    resultado["en_bd_no_csv"]  = sorted(list(solo_bd))[:50]
    resultado["coincidencias"] = len(comunes)
    resultado["discrepancias"] = len(solo_csv) + len(solo_bd)

    logger.info(
        "reconciliar_fuentes: coincidencias=%d discrepancias=%d (csv_no_bd=%d, bd_no_csv=%d)",
        resultado["coincidencias"], resultado["discrepancias"],
        len(solo_csv), len(solo_bd),
    )
    return resultado


# ─── UTILIDAD INTERNA ─────────────────────────────────────────────────────────

def _buscar_col(df: pd.DataFrame, candidatos: list) -> str | None:
    """Retorna el primer nombre de columna que coincida con alguno de los candidatos."""
    for c in candidatos:
        if c in df.columns:
            return c
    return None
