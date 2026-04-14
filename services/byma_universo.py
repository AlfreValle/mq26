"""
services/byma_universo.py — Universo BYMA completo como fuente única de verdad.

Regla crítica del producto: todo activo comercializado en Argentina en ARS
debe estar en este universo. El precio siempre viene de BYMA Open Data.
Sin yfinance para precios de mercado AR. Sin hardcoding de precios.

Sin Streamlit. Testeable.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from services.byma_market_data import (
    _cached_byma,
    fetch_on_byma_live,
    enriquecer_on_desde_byma,
    cached_on_byma,
)


# ── TIPOS DE ACTIVO (vocabulario único del producto) ──────────────────────────
TIPO_CEDEAR       = "CEDEAR"
TIPO_ACCION       = "ACCION_LOCAL"
TIPO_BONO         = "BONO_USD"
TIPO_LETRA        = "LETRA"
TIPO_ON           = "ON_USD"
TIPO_FCI          = "FCI"

# Mapping endpoint BYMA → tipo interno
_ENDPOINT_TIPO: dict[str, str] = {
    "CEDEARs":       TIPO_CEDEAR,
    "Acciones Arg.": TIPO_ACCION,
    "Bonos":         TIPO_BONO,
    "Letras":        TIPO_LETRA,
}


def fetch_rv_completo() -> pd.DataFrame:
    """
    Renta Variable completa desde BYMA: CEDEARs + Acciones argentinas.
    Columnas garantizadas: Ticker, Tipo, Descripción, Último, Var. %, Vol. Nominal.
    Precio siempre de BYMA — nunca hardcodeado.
    Sin Streamlit.
    """
    frames: list[pd.DataFrame] = []
    for label, tipo in [("CEDEARs", TIPO_CEDEAR), ("Acciones Arg.", TIPO_ACCION)]:
        from services.byma_market_data import _ENDPOINTS
        df = _cached_byma(label, _ENDPOINTS[label])
        if not df.empty:
            df = df.copy()
            df["Tipo"] = tipo
            frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["Ticker", "Tipo", "Descripción", "Último", "Var. %"])

    out = pd.concat(frames, ignore_index=True)
    # Garantizar columnas mínimas
    for col in ["Ticker", "Tipo", "Descripción", "Último", "Var. %", "Vol. Nominal"]:
        if col not in out.columns:
            out[col] = None
    return out.sort_values(["Tipo", "Ticker"]).reset_index(drop=True)


def fetch_rf_completo(ccl: float) -> dict[str, pd.DataFrame]:
    """
    Renta Fija completa desde BYMA: ONs, Bonos, Letras.
    Retorna dict con claves "on", "bonos", "letras".
    Para ONs: incluye TIR calculada desde el catálogo.
    Para Letras: incluye tasa mensual efectiva.
    Precio siempre de BYMA — nunca hardcodeado.
    Sin Streamlit.
    """
    from services.byma_market_data import _ENDPOINTS
    from core.renta_fija_ar import (
        get_meta, tir_ponderada_cartera, INSTRUMENTOS_RF
    )

    # ONs: fetch live con normalización ×100
    on_dict = cached_on_byma(ccl)
    on_rows: list[dict] = []
    for ticker, datos in on_dict.items():
        meta = get_meta(ticker) or {}
        tir_ref = meta.get("tir_ref")
        paridad = datos.get("paridad_pct")
        on_rows.append({
            "Ticker":    ticker,
            "Descripción": datos.get("description") or meta.get("descripcion") or ticker,
            "Último ARS": datos.get("lastPrice_ars"),
            "Var. %":    datos.get("variationRate"),
            "TIR ref. %": round(float(tir_ref) * 100, 2) if tir_ref is not None else None,
            "Paridad %":  round(float(paridad), 1) if paridad is not None else None,
            "Vencimiento": meta.get("vencimiento"),
            "Emisor":    meta.get("emisor"),
            "Tipo":      "ON",
        })
    df_on = pd.DataFrame(on_rows).sort_values("Ticker").reset_index(drop=True)

    # Bonos soberanos
    df_bonos_raw = _cached_byma("Bonos", _ENDPOINTS["Bonos"])
    if not df_bonos_raw.empty:
        df_bonos = df_bonos_raw.copy()
        df_bonos["Tipo"] = "BONO"
        # Agregar TIR desde catálogo si existe
        def _tir_bono(ticker):
            m = get_meta(str(ticker)) or {}
            tir = m.get("tir_ref")
            return round(float(tir) * 100, 2) if tir is not None else None
        df_bonos["TIR ref. %"] = df_bonos["Ticker"].apply(_tir_bono)
    else:
        df_bonos = pd.DataFrame()

    # Letras
    df_letras_raw = _cached_byma("Letras", _ENDPOINTS["Letras"])
    if not df_letras_raw.empty:
        df_letras = df_letras_raw.copy()
        df_letras["Tipo"] = "LETRA"
        # Calcular tasa mensual efectiva desde precio de descuento
        # Precio Letra LECAP ≈ valor presente; TEM = (100/precio)^(1/n_meses) - 1
        def _tem_desde_precio(row):
            try:
                px = float(row.get("Último", 0) or 0)
                if px <= 0 or px >= 100:
                    return None
                # Estimación: LECAP a ~30 días típico
                # La TEM real requiere días exactos al vencimiento
                # Aquí usamos: TEM = (100/px - 1) como rendimiento del período
                return round((100.0 / px - 1) * 100, 2)
            except Exception:
                return None
        df_letras["Tasa mensual %"] = df_letras.apply(_tem_desde_precio, axis=1)
    else:
        df_letras = pd.DataFrame()

    return {
        "on":     df_on,
        "bonos":  df_bonos,
        "letras": df_letras,
    }


def universo_rv_con_señales(
    ccl: float,
    perfil: str = "Moderado",
    n_max: int = 100,
) -> pd.DataFrame:
    """
    Renta Variable BYMA enriquecida con señal MOD-23 y precio target.

    Combina:
      - Precio actual de BYMA (nunca hardcodeado)
      - Score MOD-23 del scoring_engine
      - Señal: COMPRAR / ACUMULAR / MANTENER / REDUCIR / SALIR
      - Precio target según perfil (motor_salida)
      - Precio stop según perfil

    Sin Streamlit. Puede tardar si hay muchos tickers (usa cache del scoring_engine).
    """
    from services.scoring_engine import calcular_score_total
    from services.motor_salida import OBJETIVOS_PERFIL

    df_rv = fetch_rv_completo()
    if df_rv.empty:
        return pd.DataFrame()

    obj = OBJETIVOS_PERFIL.get(perfil, OBJETIVOS_PERFIL["Moderado"])
    target_pct = obj["target_pct"]
    stop_pct   = obj["stop_pct"]

    rows: list[dict] = []
    for _, row in df_rv.head(n_max).iterrows():
        ticker = str(row.get("Ticker", "")).strip()
        tipo   = str(row.get("Tipo", "CEDEAR"))
        px_ars = float(row.get("Último") or 0)
        if not ticker or px_ars <= 0:
            continue

        try:
            resultado = calcular_score_total(ticker, tipo)
        except Exception:
            continue

        score   = float(resultado.get("Score_Total", 0))
        senal   = str(resultado.get("Senal", "MANTENER"))
        px_usd  = px_ars / ccl if ccl > 0 else 0
        target  = round(px_usd * (1 + target_pct / 100), 4) if px_usd > 0 else None
        stop    = round(px_usd * (1 + stop_pct   / 100), 4) if px_usd > 0 else None

        rows.append({
            "Ticker":        ticker,
            "Tipo":          tipo,
            "Descripción":   row.get("Descripción", ""),
            "Precio ARS":    round(px_ars, 2),
            "Precio USD":    round(px_usd, 4) if px_usd else None,
            "Var. %":        row.get("Var. %"),
            "Score":         round(score, 1),
            "Señal":         senal,
            "Target USD":    target,
            "Stop USD":      stop,
            "Target ARS":    round(target * ccl, 2) if target else None,
            "Stop ARS":      round(stop   * ccl, 2) if stop   else None,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Orden: Comprar → Acumular → Mantener → Reducir → Salir
    _orden = {"COMPRAR": 0, "ACUMULAR": 1, "MANTENER": 2, "REDUCIR": 3, "SALIR": 4}
    df["_ord"] = df["Señal"].apply(
        lambda s: next((v for k, v in _orden.items() if k in s.upper()), 5)
    )
    return df.sort_values(["_ord", "Score"], ascending=[True, False]) \
             .drop(columns=["_ord"]).reset_index(drop=True)
