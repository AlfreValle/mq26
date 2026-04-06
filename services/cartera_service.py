"""
services/cartera_service.py — Servicio de dominio para gestión de cartera
MQ26-DSS | Sin dependencias de Streamlit.

Encapsula la lógica de:
  - Obtener posiciones de cartera desde el transaccional.
  - Calcular métricas: valor, P&L, peso, PPC, precio actual.
  - Construir precios con fallback automático (live → Balanz → 0).

Consumido por app_main.py (tabs 2, 3) y libro_mayor.py.

Política ARS / USD / CCL (alineada con docs/product):
  - Cada operación guarda costo en ARS y USD coherentes con el CCL del día
    de la operación (o tipo de cambio explícito del importador).
  - Valoración "hoy": precio de mercado en ARS usando CCL vigente en sesión.
  - Mensajes de rendimiento comparativo: preferir marco en USD de costo
    (p. ej. pnl_pct en USD vía métricas), evitando mezclar nominal ARS
    histórico sin etiqueta clara.

Texto en criollo para pantallas: ver services/copy_inversor.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time as _time_mod

from config import RATIOS_CEDEAR
from core.logging_config import get_logger
from core.pricing_utils import obtener_ratio, subyacente_usd_desde_cedear

logger = get_logger(__name__)

# ─── CACHE DE DIVIDEND YIELD (TTL 24h, módulo-level) ─────────────────────────
_DIV_YIELD_CACHE: dict[str, tuple[float, float]] = {}
_DIV_CACHE_TTL = 86_400  # 24 horas en segundos


def _get_div_yield_cached(ticker: str) -> float:
    """
    Retorna el dividend yield de un ticker con cache de 24h.
    Nunca lanza excepción — retorna 0.0 si falla.
    Invariante: llamadas sucesivas dentro del TTL NO llaman a yfinance.
    """
    now = _time_mod.time()
    if ticker in _DIV_YIELD_CACHE:
        val, ts = _DIV_YIELD_CACHE[ticker]
        if now - ts < _DIV_CACHE_TTL:
            return val
    try:
        import yfinance as _yf
        dy = _yf.Ticker(ticker).fast_info.dividend_yield or 0.0
    except Exception:
        dy = 0.0
    _DIV_YIELD_CACHE[ticker] = (dy, now)
    return dy

# ─── PRECIOS FALLBACK (última conciliación Balanz 11/03/2026) ─────────────────
# Actualizar mensualmente con el resumen Balanz.
# Formato: {TICKER: precio_ARS_por_CEDEAR}
PRECIOS_FALLBACK_ARS: dict[str, float] = {
    # Cartera Alfredo y Andrea – Retiro (Balanz 11/03/2026)
    "ABBV": 33140, "CAT": 51525, "COST": 30020, "CVX": 17420,
    "KO":   22540, "LMT": 47180, "VALE": 11140, "VIST": 28740,
    # Bull Market / Reto 2026
    "AAPL": 18500, "AMZN":  2100, "BRKB": 31000, "GLD": 12800,
    "MELI": 22000, "META":  37000, "MSFT": 18500, "SPY": 48000,
    "UNH":  12000,
    # Santi
    "PAMP":  4800,
}


_fallback_cargado: bool = False  # MQ-D5: lazy load flag


def asegurar_precios_fallback_cargados() -> None:
    """Idempotente: carga PRECIOS_FALLBACK_ARS desde BD antes de instanciar PriceEngine."""
    _cargar_fallback_desde_bd()


def _cargar_fallback_desde_bd() -> None:
    """MQ-D5: Carga precios fallback desde BD de forma lazy (solo cuando se necesitan).
    No se ejecuta en el import — se llama la primera vez que se usa resolver_precios().
    """
    global _fallback_cargado
    if _fallback_cargado:
        return
    try:
        import core.db_manager as _dbm
        from_bd = _dbm.obtener_precios_fallback()
        if from_bd:
            PRECIOS_FALLBACK_ARS.update(from_bd)
            logger.info("Precios fallback cargados desde BD (lazy): %d tickers", len(from_bd))
    except Exception as _e:
        logger.debug("_cargar_fallback_desde_bd lazy: %s", _e)
    finally:
        _fallback_cargado = True  # No reintentar aunque falle


def actualizar_fallback(nuevos_precios: dict[str, float]) -> None:
    """
    Actualiza en memoria los precios de fallback con valores nuevos Y los persiste en BD.
    A5: los precios sobreviven reinicios de la app.
    """
    PRECIOS_FALLBACK_ARS.update(nuevos_precios)
    logger.info("Precios fallback actualizados: %d tickers", len(nuevos_precios))
    try:
        import core.db_manager as _dbm
        _dbm.guardar_precios_fallback_bulk(nuevos_precios, fuente="manual")
    except Exception as _e:
        logger.warning("No se pudo persistir fallback en BD: %s", _e)


def resolver_precios(
    tickers: list[str],
    precios_live: dict[str, float],
    ccl: float,
    universo_df: pd.DataFrame | None = None,
) -> dict[str, float]:
    """
    Construye el dict definitivo de precios ARS con jerarquía:
      1. Precio en vivo (yfinance / BYMA)
      2. Precio fallback de última conciliación Balanz
      3. 0.0 si no hay dato

    Devuelve {ticker: precio_ars}.
    """
    _cargar_fallback_desde_bd()  # MQ-D5: lazy — solo la primera vez
    resultado: dict[str, float] = {}

    byma_px: dict[str, float] = {}
    try:
        from core.data_providers import BYMA_FIRST
        from services.byma_provider import fetch_precios_ars_batch

        if BYMA_FIRST and tickers:
            byma_px = fetch_precios_ars_batch([str(x) for x in tickers if x])
    except Exception:
        byma_px = {}

    for t in tickers:
        tu = str(t).upper().strip() if t else ""
        key_orig = t
        live = float(precios_live.get(t, 0.0) or precios_live.get(tu, 0.0) or 0.0)
        if live <= 0 and tu:
            live = float(byma_px.get(tu, 0.0) or 0.0)
        if live > 0:
            resultado[key_orig] = live
        else:
            fallback = float(PRECIOS_FALLBACK_ARS.get(tu, 0.0) or PRECIOS_FALLBACK_ARS.get(t, 0.0) or 0.0)
            if fallback > 0:
                logger.debug("Usando fallback Balanz para %s: $%s ARS", t, fallback)
            resultado[key_orig] = fallback

    # ONs/bonos: último recurso desde paridad_ref en renta_fija_ar (no pisa live/fallback)
    try:
        from core.renta_fija_ar import get_meta

        ccl_f = float(ccl or 0.0)
        for t in tickers:
            tu = str(t).upper().strip() if t else ""
            if not tu:
                continue
            if float(resultado.get(t, 0) or resultado.get(tu, 0) or 0) > 0:
                continue
            meta = get_meta(tu)
            if meta is None:
                continue
            paridad = float(meta.get("paridad_ref", 100.0))
            moneda = str(meta.get("moneda", "USD")).upper()
            if moneda == "USD":
                precio_ars = (paridad / 100.0) * ccl_f if ccl_f > 0 else 0.0
            else:
                precio_ars = paridad
            if precio_ars > 0:
                resultado[t] = precio_ars
                if t != tu:
                    resultado[tu] = precio_ars
                logger.debug(
                    "ON/bono %s: precio estimado paridad_ref → $%.2f ARS", tu, precio_ars
                )
    except Exception as _e_rf:
        logger.debug("resolver_precios ON fallback: %s", _e_rf)

    return resultado


def rellenar_precios_desde_ultimo_ppc(
    trans: pd.DataFrame,
    cartera_activa: str,
    tickers: list[str],
    precios_dict: dict[str, float],
    ccl: float,
) -> dict[str, float]:
    """
    Si Yahoo/BYMA no devuelve cotización, usa el último PPC_ARS de Maestra_Transaccional
    (misma cartera y ticker); si PPC_ARS es 0, aproxima con PPC_USD × CCL.
    Evita valoración en cero en bonos/FCI/ON que yfinance no lista.
    """
    if trans is None or trans.empty or "CARTERA" not in trans.columns:
        return precios_dict
    out = {str(k).upper(): float(v or 0) for k, v in precios_dict.items()}
    sub_c = trans[trans["CARTERA"].astype(str).str.strip() == str(cartera_activa).strip()]
    if sub_c.empty:
        return precios_dict
    fecha_col = (
        "FECHA_COMPRA"
        if "FECHA_COMPRA" in sub_c.columns
        else ("FECHA" if "FECHA" in sub_c.columns else None)
    )
    ccl_f = float(ccl) if ccl else 0.0
    for t in tickers:
        tu = str(t).upper().strip()
        if float(out.get(tu, 0) or 0) > 0:
            continue
        sub = sub_c[sub_c["TICKER"].astype(str).str.upper().str.strip() == tu]
        if sub.empty:
            continue
        if fecha_col:
            try:
                sub = sub.sort_values(fecha_col, ascending=True)
            except Exception:
                pass
        last = sub.iloc[-1]
        pa = float(pd.to_numeric(last.get("PPC_ARS"), errors="coerce") or 0.0)
        pu = float(pd.to_numeric(last.get("PPC_USD"), errors="coerce") or 0.0)
        if pa > 0:
            out[tu] = round(pa, 2)
        elif pu > 0 and ccl_f > 0:
            out[tu] = round(pu * ccl_f, 2)
    return out


def calcular_posicion_neta(
    df_ag: pd.DataFrame,
    precios_ars: dict[str, float],
    ccl: float,
    universo_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Calcula métricas de posición neta a partir del DataFrame agregado por ticker.

    Columnas esperadas en df_ag: TICKER, CANTIDAD_TOTAL, PPC_USD_PROM, INV_USD_TOTAL,
                                 INV_ARS_HISTORICO (opcional)
    Devuelve df_ag enriquecido con: PRECIO_ARS, PRECIO_USD (USD/CEDEAR o equiv.),
                                    PRECIO_USD_SUBYACENTE (solo referencia CEDEAR),
                                    VALOR_ARS, PPC_ARS, INV_ARS, PNL_ARS, PNL_PCT,
                                    PNL_ARS_USD, PNL_PCT_USD, PESO_PCT

    INV_ARS usa el costo histórico real (CCL del mes de compra), no el CCL actual.
    PNL_PCT    = retorno total en pesos (incluye apreciación del CCL).
    PNL_PCT_USD = retorno puro en USD (para comparar con benchmarks globales).
    """
    if df_ag is None or df_ag.empty:
        return df_ag if df_ag is not None else pd.DataFrame()

    # MQ-D9: Validar columnas requeridas antes de procesar
    from core.validators import validar_df_columnas
    cols_req = ["TICKER"]
    ok, faltantes = validar_df_columnas(df_ag, cols_req, "df_ag (posicion_neta)")
    if not ok:
        logger.warning("calcular_posicion_neta: columnas faltantes %s — devuelve df original", faltantes)
        return df_ag

    from core.pricing_utils import (
        es_instrumento_local_ars,
        mensaje_validacion_lamina,
    )

    df = df_ag.copy()

    # Coerción defensiva: columnas numéricas pueden tener strings
    # si el usuario editó el data_editor (strings + floats mezclados)
    _num_cols = ["CANTIDAD_TOTAL", "PPC_USD_PROM", "PPC_ARS",
                 "INV_USD_TOTAL", "INV_ARS_HISTORICO"]
    for _col in _num_cols:
        if _col in df.columns:
            df[_col] = pd.to_numeric(df[_col], errors="coerce").fillna(0.0)

    if "LAMINA_VN" in df.columns:
        df["LAMINA_VN"] = pd.to_numeric(df["LAMINA_VN"], errors="coerce")
    else:
        df["LAMINA_VN"] = np.nan

    for _, r in df.iterrows():
        _msg = mensaje_validacion_lamina(
            str(r.get("TICKER", "")),
            str(r.get("TIPO", "")),
            r.get("LAMINA_VN"),
        )
        if _msg:
            logger.warning("%s", _msg)

    # Detectar si cada ticker es un instrumento local ARS (sin CCL/ratio)
    def _es_local(row):
        tipo = str(row.get("TIPO", "")) if "TIPO" in df.columns else ""
        es_l = bool(row.get("ES_LOCAL", False))
        return es_l or es_instrumento_local_ars(str(row["TICKER"]), tipo)

    df["ES_LOCAL"] = df.apply(_es_local, axis=1)

    # Ratio: mismo criterio que precios live (universo + corrección vs config)
    df["RATIO"] = df.apply(
        lambda r: (
            1.0
            if r["ES_LOCAL"]
            else obtener_ratio(str(r["TICKER"]), universo_df)
        ),
        axis=1,
    )

    df["PRECIO_ARS"] = df["TICKER"].map(precios_ars).fillna(0.0)

    # PRECIO_USD: equivalente USD del último precio en BYMA (misma escala que PPC_USD_PROM en CEDEAR).
    # CEDEAR: USD por certificado = PRECIO_ARS / CCL (no subyacente × ratio).
    # Subyacente en USD (referencia): PRECIO_ARS × RATIO / CCL.
    if ccl > 0:
        df["PRECIO_USD"] = df["PRECIO_ARS"] / ccl
        df["PRECIO_USD_SUBYACENTE"] = np.where(
            df["ES_LOCAL"],
            df["PRECIO_USD"],
            df["PRECIO_ARS"] * df["RATIO"] / ccl,
        )
    else:
        df["PRECIO_USD"] = 0.0
        df["PRECIO_USD_SUBYACENTE"] = 0.0

    df["VALOR_ARS"] = df["CANTIDAD_TOTAL"] * df["PRECIO_ARS"]

    # INV_ARS histórico (máxima precisión si viene de agregar_cartera):
    if "INV_ARS_HISTORICO" in df.columns and (df["INV_ARS_HISTORICO"] > 0).any():
        df["INV_ARS"] = df["INV_ARS_HISTORICO"]
        df["PPC_ARS"] = (df["INV_ARS"] / df["CANTIDAD_TOTAL"].replace(0, np.nan)).fillna(0.0)
    else:
        # Fallback: locales usan PPC_USD como precio ARS; CEDEARs aplican CCL×ratio
        df["PPC_ARS"] = np.where(
            df["ES_LOCAL"],
            df["PPC_USD_PROM"],                              # PPC_USD = precio en ARS para locales
            df["PPC_USD_PROM"] * ccl * df["RATIO"],          # fórmula CEDEAR
        )
        df["INV_ARS"] = df["CANTIDAD_TOTAL"] * df["PPC_ARS"]

    # PPC_USD_SUB: precio del subyacente en USD al momento de compra.
    # PPC_USD_PROM almacena el precio por CEDEAR en USD (sub_USD / ratio).
    # Una sola multiplicación por RATIO recupera el precio del subyacente (sub_USD).
    df["PPC_USD_SUB"] = np.where(
        df["ES_LOCAL"],
        df["PPC_ARS"] / ccl if ccl > 0 else 0.0,
        df["PPC_USD_PROM"] * df["RATIO"],   # sub_USD = ppc_usd_por_cedear × ratio
    )

    df["PNL_ARS"] = df["VALOR_ARS"] - df["INV_ARS"]
    df["PNL_PCT"] = np.where(df["INV_ARS"] > 0, df["PNL_ARS"] / df["INV_ARS"], 0.0)

    # P&L en USD: locales usan equivalente ARS/CCL; CEDEARs cancelan efecto CCL.
    # Para CEDEARs: PPC_USD_PROM es precio por CEDEAR en USD → × ccl da ARS al CCL actual.
    # No se aplica RATIO porque PPC_USD_PROM ya está expresado por unidad de CEDEAR.
    inv_usd_base = np.where(
        df["ES_LOCAL"],
        df["INV_ARS"] / ccl if ccl > 0 else df["INV_ARS"],
        df["CANTIDAD_TOTAL"] * df["PPC_USD_PROM"] * ccl,
    )
    df["PNL_ARS_USD"] = df["VALOR_ARS"] - inv_usd_base
    df["PNL_PCT_USD"] = np.where(inv_usd_base > 0, df["PNL_ARS_USD"] / inv_usd_base, 0.0)

    total_v = df["VALOR_ARS"].sum()
    df["PESO_PCT"] = df["VALOR_ARS"] / total_v if total_v > 0 else 0.0

    # MQ2-D8: VALOR_USD individual por posición (VALOR_ARS / CCL)
    df["VALOR_USD"] = df["VALOR_ARS"] / ccl if ccl > 0 else 0.0

    return df


def metricas_resumen(df_pos: pd.DataFrame) -> dict:
    """
    Calcula totales de cartera desde un df ya enriquecido con calcular_posicion_neta.
    Devuelve dict con: total_valor, total_inversion, total_pnl, pnl_pct_total,
                       total_pnl_usd, pnl_pct_total_usd.

    pnl_pct_total     = retorno total en pesos (incluye apreciación CCL).
    pnl_pct_total_usd = retorno puro en USD (CCL cancela — para comparar con benchmarks).
    """
    total_valor     = df_pos["VALOR_ARS"].sum()   if not df_pos.empty else 0.0
    total_inversion = df_pos["INV_ARS"].sum()      if not df_pos.empty else 0.0
    total_pnl       = df_pos["PNL_ARS"].sum()      if not df_pos.empty else 0.0
    pnl_pct_total   = total_pnl / total_inversion  if total_inversion > 0 else 0.0

    # P&L solo en USD (base INV al CCL actual — cancela el efecto devaluación)
    total_pnl_usd     = df_pos["PNL_ARS_USD"].sum() if ("PNL_ARS_USD" in df_pos.columns and not df_pos.empty) else total_pnl
    inv_usd_base      = (df_pos["CANTIDAD_TOTAL"] * df_pos["PPC_ARS"]).sum() if not df_pos.empty else 0.0
    pnl_pct_total_usd = total_pnl_usd / inv_usd_base if inv_usd_base > 0 else 0.0

    return {
        "total_valor":         total_valor,
        "total_inversion":     total_inversion,
        "total_pnl":           total_pnl,
        "pnl_pct_total":       pnl_pct_total,
        "total_pnl_usd":       total_pnl_usd,
        "pnl_pct_total_usd":   pnl_pct_total_usd,
        "n_posiciones":        len(df_pos),
    }


def calcular_twrr(
    transacciones: pd.DataFrame,
    precios_historicos: pd.DataFrame,
    ccl_actual: float = 1500.0,
) -> dict:
    """
    B5: TWRR (Time-Weighted Rate of Return) — estándar CFA para evaluar gestores.
    Elimina el efecto de flujos de capital (depósitos/retiros).

    Parámetros:
        transacciones: DataFrame con FECHA_COMPRA, TICKER, CANTIDAD, PPC_USD, TIPO
        precios_historicos: DataFrame de precios ajustados (columnas = tickers)
        ccl_actual: CCL para convertir USD → ARS

    Retorna dict con: twrr_anual, twrr_total, n_subperiodos, fechas_flujo
    """
    if transacciones.empty or precios_historicos.empty:
        return {"twrr_anual": 0.0, "twrr_total": 0.0, "n_subperiodos": 0, "fechas_flujo": []}

    try:

        from config import RATIOS_CEDEAR as _RATIOS

        # Identificar fechas de flujos (compras y ventas)
        trans = transacciones.copy()
        trans["FECHA_COMPRA"] = pd.to_datetime(trans["FECHA_COMPRA"]).dt.date
        trans = trans.sort_values("FECHA_COMPRA")
        fechas_flujo = sorted(trans["FECHA_COMPRA"].dropna().unique().tolist())

        if len(fechas_flujo) < 2:
            return {"twrr_anual": 0.0, "twrr_total": 0.0, "n_subperiodos": 0, "fechas_flujo": []}

        # Calcular retornos por sub-período entre cada flujo
        retornos_subperiodo = []
        tickers = trans["TICKER"].str.upper().unique().tolist()
        tickers_disp = [t for t in tickers if t in precios_historicos.columns]

        if not tickers_disp:
            return {"twrr_anual": 0.0, "twrr_total": 0.0, "n_subperiodos": 0, "fechas_flujo": []}

        precios_idx = pd.DatetimeIndex(
            [pd.Timestamp(d) for d in precios_historicos.index]
            if not isinstance(precios_historicos.index, pd.DatetimeIndex)
            else precios_historicos.index
        )

        for i in range(len(fechas_flujo) - 1):
            fecha_ini = pd.Timestamp(fechas_flujo[i])
            fecha_fin = pd.Timestamp(fechas_flujo[i + 1])

            # Pesos de la cartera al inicio del sub-período (basados en transacciones previas)
            trans_previas = trans[pd.to_datetime(trans["FECHA_COMPRA"]) <= fecha_ini]
            if trans_previas.empty:
                continue

            posiciones = {}
            for t in tickers_disp:
                t_trans = trans_previas[trans_previas["TICKER"].str.upper() == t]
                if not t_trans.empty:
                    cant = t_trans["CANTIDAD"].sum()
                    ppc  = (t_trans["CANTIDAD"] * t_trans["PPC_USD"]).sum() / max(cant, 1)
                    if cant > 0:
                        ratio = float(_RATIOS.get(t, 1.0))
                        posiciones[t] = {"cant": cant, "ppc": ppc, "ratio": ratio}

            if not posiciones:
                continue

            # Encontrar precios al inicio y fin del sub-período
            mask_ini = precios_idx <= fecha_ini
            mask_fin = precios_idx <= fecha_fin
            if not mask_ini.any() or not mask_fin.any():
                continue

            idx_ini = int(np.where(mask_ini)[0][-1])  # último índice ≤ fecha_ini
            idx_fin = int(np.where(mask_fin)[0][-1])

            valor_ini, valor_fin = 0.0, 0.0
            for t, pos in posiciones.items():
                if t not in precios_historicos.columns:
                    continue
                col = precios_historicos[t]
                p_ini = float(col.iloc[idx_ini])
                p_fin = float(col.iloc[idx_fin])
                if p_ini > 0:
                    valor_ini += pos["cant"] * p_ini * ccl_actual / max(pos["ratio"], 1)
                if p_fin > 0:
                    valor_fin += pos["cant"] * p_fin * ccl_actual / max(pos["ratio"], 1)

            if valor_ini > 0:
                retornos_subperiodo.append(valor_fin / valor_ini)

        if not retornos_subperiodo:
            return {"twrr_anual": 0.0, "twrr_total": 0.0, "n_subperiodos": 0, "fechas_flujo": []}

        twrr_total = float(np.prod(retornos_subperiodo) - 1.0)
        # Anualizar: n años = días totales / 365
        dias_total = (pd.Timestamp(fechas_flujo[-1]) - pd.Timestamp(fechas_flujo[0])).days
        if dias_total > 0:
            twrr_anual = float((1 + twrr_total) ** (365 / dias_total) - 1)
        else:
            twrr_anual = 0.0

        return {
            "twrr_anual":    round(twrr_anual, 4),
            "twrr_total":    round(twrr_total, 4),
            "n_subperiodos": len(retornos_subperiodo),
            "fechas_flujo":  [str(f) for f in fechas_flujo],
        }
    except Exception as _e:
        logger.warning("calcular_twrr: fallo en cálculo — %s", _e)
        return {"twrr_anual": 0.0, "twrr_total": 0.0, "n_subperiodos": 0, "fechas_flujo": []}


def calcular_dividendos_proyectados(
    df_pos: pd.DataFrame,
    ccl: float,
    tickers_div_yields: dict[str, float] | None = None,
) -> dict:
    """
    Máquina de Dividendos: proyecta flujo de caja pasivo anual/mensual.

    Para CEDEARs: usa yfinance dividendYield del subyacente.
    Para bonos y letras: usa cupón estimado según tipo de instrumento.
    Para FCIs: rendimiento promedio estimado.

    Retorna:
        flujo_mensual_ars, flujo_anual_ars, flujo_anual_usd,
        por_ticker: {ticker: {yield_pct, div_anual_ars}},
        tickers_con_dividendo
    """
    if df_pos is None or df_pos.empty:
        return {"flujo_mensual_ars": 0.0, "flujo_anual_ars": 0.0,
                "flujo_anual_usd": 0.0, "por_ticker": {}, "tickers_con_dividendo": []}

    # Guard: ccl=None causa TypeError; ccl=0 causa ZeroDivisionError en conversiones USD
    if ccl is None or float(ccl) <= 0:
        logger.warning(
            "calcular_dividendos_proyectados: ccl=%s inválido, usando fallback 1500", ccl
        )
        ccl = 1500.0

    yields = dict(tickers_div_yields or {})

    # Descargar yields desde yfinance para los tickers sin dato
    cedears_sin_yield = [
        str(row["TICKER"]).upper()
        for _, row in df_pos.iterrows()
        if str(row.get("TIPO","")).upper() in ("CEDEAR","ETF","ACCION_LOCAL")
           and str(row["TICKER"]).upper() not in yields
    ]
    if cedears_sin_yield:
        for ticker in set(cedears_sin_yield):
            dy = _get_div_yield_cached(ticker)
            if dy > 0:
                yields[ticker] = float(dy)

    por_ticker: dict = {}
    flujo_anual_ars  = 0.0
    flujo_anual_usd  = 0.0

    # Yields por defecto según tipo de instrumento
    YIELD_DEFAULTS = {
        "BONO":     0.08,   # 8% cupón estimado ARS CER
        "LETRA":    0.06,   # 6% rendimiento capitalizable
        "BONO_USD": 0.07,   # 7% cupón global
        "ON_USD":   0.075,  # 7.5% cupón ON corporativa
        "ON":       0.08,
        "FCI":      0.065,  # 6.5% rendimiento promedio fondo
    }

    for _, row in df_pos.iterrows():
        ticker    = str(row.get("TICKER", "")).upper()
        valor_ars = float(row.get("VALOR_ARS", 0.0))
        tipo      = str(row.get("TIPO", "CEDEAR")).upper()

        dy = yields.get(ticker) or YIELD_DEFAULTS.get(tipo, 0.0)

        if dy > 0 and valor_ars > 0:
            div_anual_ars = valor_ars * dy
            div_anual_usd = div_anual_ars / ccl if ccl > 0 else 0.0
            por_ticker[ticker] = {
                "yield_anual_pct":    round(dy * 100, 2),
                "dividendo_anual_ars": round(div_anual_ars, 0),
                "dividendo_anual_usd": round(div_anual_usd, 2),
                "valor_posicion_ars": round(valor_ars, 0),
                "tipo": tipo,
            }
            flujo_anual_ars += div_anual_ars
            flujo_anual_usd += div_anual_usd

    return {
        "flujo_mensual_ars":     round(flujo_anual_ars / 12, 0),
        "flujo_anual_ars":       round(flujo_anual_ars, 0),
        "flujo_anual_usd":       round(flujo_anual_usd, 2),
        "por_ticker":            por_ticker,
        "tickers_con_dividendo": list(por_ticker.keys()),
    }


def calcular_rendimiento_por_tipo(
    df_pos: pd.DataFrame,
    df_transacciones: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Calcula rendimientos desagregados por tipo de instrumento BYMA.
    Implementación vectorizada con groupby (sin iterrows) para performance.

    Tipos: CEDEAR | ACCION_LOCAL | BONO | BONO_USD | LETRA | FCI | ON | ON_USD

    Columnas del resultado:
        Tipo, Inv. ARS, Valor ARS, P&L ARS, Rend. ARS %,
        P&L USD aprox, Rend. USD %, CAGR ARS %, CAGR USD %,
        Contribución %, N posiciones, Primera compra, Días en cartera

    Invariante: retorna DataFrame vacío si df_pos está vacío o es None.
    """
    import datetime as _dt

    if df_pos is None or df_pos.empty:
        return pd.DataFrame()

    hoy = _dt.date.today()

    # ── Paso 1: preparar copia con columnas numéricas y tipo normalizado ──
    df = df_pos.copy()
    for _col in ("INV_ARS", "VALOR_ARS", "PNL_ARS"):
        if _col in df.columns:
            df[_col] = pd.to_numeric(df[_col], errors="coerce").fillna(0.0)

    df["_TIPO_NORM"] = (
        df.get("TIPO", pd.Series(["CEDEAR"] * len(df)))
        .fillna("CEDEAR")
        .str.upper()
        .str.strip()
    )
    df.loc[df["_TIPO_NORM"].isin(["ON", "ON_USD"]), "_TIPO_NORM"] = "ON_USD"

    pnl_usd_col = "PNL_ARS_USD" if "PNL_ARS_USD" in df.columns else "PNL_ARS"

    # ── Paso 2: primera fecha de compra por ticker (desde df_transacciones) ──
    primera_compra_por_ticker: dict[str, _dt.date] = {}
    if df_transacciones is not None and not df_transacciones.empty:
        fecha_col = "FECHA_COMPRA" if "FECHA_COMPRA" in df_transacciones.columns else "FECHA"
        if fecha_col in df_transacciones.columns:
            df_f = df_transacciones.copy()
            df_f[fecha_col] = pd.to_datetime(df_f[fecha_col], errors="coerce")
            for tkr, grp in df_f.dropna(subset=[fecha_col]).groupby("TICKER"):
                primera_compra_por_ticker[str(tkr).upper()] = grp[fecha_col].min().date()

    # Fallback: fecha inicial desde df_pos si existe
    if "FECHA_INICIAL" in df.columns and not df["FECHA_INICIAL"].isna().all():
        for _, row in df.iterrows():
            tkr = str(row.get("TICKER", "")).upper()
            if tkr not in primera_compra_por_ticker:
                try:
                    primera_compra_por_ticker[tkr] = pd.to_datetime(row["FECHA_INICIAL"]).date()
                except Exception:
                    pass

    # ── Paso 3: agrupar métricas por tipo (vectorizado) ──────────────────
    agg = df.groupby("_TIPO_NORM", as_index=False).agg(
        inv_ars   =("INV_ARS",   "sum"),
        val_ars   =("VALOR_ARS", "sum"),
        pnl_ars   =("PNL_ARS",   "sum"),
        pnl_usd   =(pnl_usd_col, "sum"),
        n         =("TICKER",    "count"),
    )

    total_pnl_ars = agg["pnl_ars"].sum() or 1.0

    # ── Paso 4: calcular métricas por tipo ───────────────────────────────
    filas = []
    for _, row in agg.iterrows():
        tipo  = row["_TIPO_NORM"]
        inv   = row["inv_ars"]
        val   = row["val_ars"]
        pnl   = row["pnl_ars"]
        pusd  = row["pnl_usd"]
        n     = int(row["n"])

        rend_pct     = pnl / inv * 100     if inv > 0 else 0.0
        rend_usd_pct = pusd / inv * 100    if inv > 0 else 0.0
        contribucion = pnl / total_pnl_ars * 100

        # Primera compra del tipo: mínimo entre todos los tickers del tipo
        tickers_tipo = df[df["_TIPO_NORM"] == tipo]["TICKER"].str.upper().tolist()
        fechas = [primera_compra_por_ticker[t] for t in tickers_tipo if t in primera_compra_por_ticker]
        primera = min(fechas) if fechas else hoy - _dt.timedelta(days=365)

        dias = max((hoy - primera).days, 1)
        cagr_ars = (((1 + rend_pct / 100) ** (365 / dias)) - 1) * 100 if rend_pct > -100 else -100.0
        cagr_usd = (((1 + rend_usd_pct / 100) ** (365 / dias)) - 1) * 100 if rend_usd_pct > -100 else -100.0

        filas.append({
            "Tipo":            tipo,
            "Inv. ARS":        round(inv, 0),
            "Valor ARS":       round(val, 0),
            "P&L ARS":         round(pnl, 0),
            "Rend. ARS %":     round(rend_pct, 2),
            "P&L USD aprox":   round(pusd, 0),
            "Rend. USD %":     round(rend_usd_pct, 2),
            "CAGR ARS %":      round(cagr_ars, 2),
            "CAGR USD %":      round(cagr_usd, 2),
            "Contribución %":  round(contribucion, 2),
            "N posiciones":    n,
            "Primera compra":  primera,
            "Días en cartera": dias,
        })

    if not filas:
        return pd.DataFrame()

    return pd.DataFrame(filas).sort_values("Inv. ARS", ascending=False).reset_index(drop=True)


def calcular_rendimiento_global_anual(
    df_rendimiento_tipo: pd.DataFrame,
    df_transacciones: pd.DataFrame | None = None,
) -> dict:
    """
    Consolida el rendimiento de todos los tipos en una cifra anualizada global.
    Usa retorno ponderado por capital invertido.

    Retorna:
        cagr_global_ars, cagr_global_usd,
        pnl_total_ars, rendimiento_total_pct,
        mejor_tipo, peor_tipo,
        dias_hold_promedio
    """

    if df_rendimiento_tipo is None or df_rendimiento_tipo.empty:
        return {
            "cagr_global_ars": 0.0, "cagr_global_usd": 0.0,
            "pnl_total_ars": 0.0, "rendimiento_total_pct": 0.0,
            "mejor_tipo": "—", "peor_tipo": "—", "dias_hold_promedio": 0,
        }

    df = df_rendimiento_tipo.copy()
    total_inv = df["Inv. ARS"].sum()
    pnl_total = df["P&L ARS"].sum()

    rend_global = pnl_total / total_inv * 100 if total_inv > 0 else 0.0
    rend_usd_global = df["P&L USD aprox"].sum() / total_inv * 100 if total_inv > 0 else 0.0

    # Promedio ponderado de días en cartera por capital invertido
    if total_inv > 0:
        dias_pond = (df["Días en cartera"] * df["Inv. ARS"]).sum() / total_inv
    else:
        dias_pond = 365
    dias_pond = max(int(dias_pond), 1)

    cagr_ars = (((1 + rend_global / 100) ** (365 / dias_pond)) - 1) * 100 if rend_global > -100 else -100.0
    cagr_usd = (((1 + rend_usd_global / 100) ** (365 / dias_pond)) - 1) * 100 if rend_usd_global > -100 else -100.0

    mejor_idx = df["Rend. ARS %"].idxmax() if not df.empty else None
    peor_idx  = df["Rend. ARS %"].idxmin() if not df.empty else None
    mejor_tipo = f"{df.loc[mejor_idx,'Tipo']} ({df.loc[mejor_idx,'Rend. ARS %']:+.1f}%)" if mejor_idx is not None else "—"
    peor_tipo  = f"{df.loc[peor_idx,'Tipo']} ({df.loc[peor_idx,'Rend. ARS %']:+.1f}%)"  if peor_idx  is not None else "—"

    return {
        "cagr_global_ars":     round(cagr_ars, 2),
        "cagr_global_usd":     round(cagr_usd, 2),
        "pnl_total_ars":       round(pnl_total, 0),
        "rendimiento_total_pct": round(rend_global, 2),
        "mejor_tipo":          mejor_tipo,
        "peor_tipo":           peor_tipo,
        "dias_hold_promedio":  dias_pond,
    }


def precios_usd_subyacente(
    tickers: list[str],
    precios_ars: dict[str, float],
    ccl: float,
    universo_df: pd.DataFrame | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Construye los dicts de precios en USD (subyacente) y ratios para el Libro Mayor.
    Devuelve (precios_usd_subs, ratios_cartera).

    Fórmula: subyacente_USD = precio_CEDEAR_ARS * ratio / CCL
    """
    precios_usd: dict[str, float] = {}
    ratios: dict[str, float] = {}

    for t in tickers:
        ratio = obtener_ratio(t, universo_df)
        ratios[t] = ratio
        px_ars = precios_ars.get(t, 0.0)
        if ccl > 0 and px_ars > 0:
            precios_usd[t] = subyacente_usd_desde_cedear(px_ars, ratio, ccl)
        else:
            precios_usd[t] = 0.0

    return precios_usd, ratios


def calcular_progreso_objetivo(
    ppc_usd: float,
    px_usd_actual: float,
    target_pct: float,
) -> float:
    """
    Calcula el porcentaje de progreso de una posición hacia su precio objetivo.

    Escala:
        0%   = precio actual igual al PPC de compra (sin ganancia).
       100%  = precio objetivo alcanzado.
      >100%  = objetivo superado.
      <0%    = posición en pérdida respecto al PPC.

    El resultado se clipea al rango [-100, 200].

    Parámetros:
        ppc_usd:       precio promedio de compra en USD (subyacente).
        px_usd_actual: precio actual en USD del subyacente.
        target_pct:    porcentaje objetivo de ganancia (ej: 35.0 para +35%).

    Retorna:
        float con el progreso en porcentaje, clipeado a [-100, 200].
        Devuelve 0.0 si algún parámetro es inválido (≤ 0).
    """
    if ppc_usd <= 0 or px_usd_actual <= 0 or target_pct <= 0:
        return 0.0
    pnl_pct = (px_usd_actual / ppc_usd - 1) * 100
    return min(200.0, max(-100.0, pnl_pct / target_pct * 100))
