"""ui/inversor/_helpers.py — helpers compartidos entre secciones del tier IN.

Extraídos de ui/tab_inversor.py (Fase 2.1). Acá vive todo lo que usan dos o más
secciones (primera cartera, plata nueva, posiciones, orquestador): resolución de
precios, diagnóstico cacheado, mix RF, identificación de tickers y constantes de
edición. Sin lógica de render.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date

import pandas as pd
import streamlit as st

from core.diagnostico_types import (
    CARTERA_IDEAL,
    UNIVERSO_RENTA_FIJA_AR,
    perfil_motor_salida,
)
from core.logging_config import get_logger
from core.renta_fija_ar import es_fila_renta_fija_ar
from services.cartera_service import PRECIOS_FALLBACK_ARS

_log = get_logger(__name__)

_TIPOS_EDICION_PRIMERA_CARTERA = [
    "CEDEAR",
    "ACCION_LOCAL",
    "BONO",
    "LETRA",
    "FCI",
    "ETF",
    "ON",
    "ON_USD",
    "BONO_USD",
    "OTRO",
]


def _log_degradacion(ctx: dict, evento: str, exc: Exception | None = None, **extra) -> None:
    payload = {"evento": evento, **extra}
    if exc is not None:
        _log.warning("degradacion_tab_inversor: %s | error=%s", payload, exc, exc_info=True)
    else:
        _log.warning("degradacion_tab_inversor: %s", payload)
    st.session_state["inv_degradado_ui"] = True


def _precios_para_recomendar(ctx: dict) -> dict:
    """
    Precios **ARS por cuotaparte** (BYMA / teórico NY×CCL÷ratio / fallback).
    Sin esto, cartera vacía solo usa fallbacks viejos o valores que parecen USD.
    """
    from services.cartera_service import (
        asegurar_precios_fallback_cargados,
        resolver_precios,
    )

    ccl = float(ctx.get("ccl") or 1150.0)
    universo_df = ctx.get("universo_df")
    asegurar_precios_fallback_cargados()

    need: set[str] = set()
    for _pesos in CARTERA_IDEAL.values():
        for k in _pesos or {}:
            ks = str(k).strip()
            if ks and not ks.startswith("_"):
                need.add(ks.upper())
    df_an = ctx.get("df_analisis")
    if df_an is not None and not df_an.empty and "TICKER" in df_an.columns:
        for t in df_an["TICKER"].astype(str).str.upper().unique():
            tt = str(t).strip()
            if tt:
                need.add(tt)

    tickers_list = sorted(need)
    live: dict[str, float] = {}
    eng = ctx.get("engine_data")
    if eng is not None and tickers_list:
        try:
            live = eng.obtener_precios_cartera(tickers_list, ccl) or {}
        except Exception:
            live = {}

    resolved = resolver_precios(tickers_list, live, ccl, universo_df)
    out: dict[str, float] = {}
    for k, v in resolved.items():
        fv = float(v or 0.0)
        if fv > 0:
            out[str(k).upper()] = fv
    for k, v in (ctx.get("precios_dict") or {}).items():
        fv = float(v or 0.0)
        if fv > 0:
            out[str(k).upper()] = fv
    for k, v in PRECIOS_FALLBACK_ARS.items():
        out.setdefault(str(k).upper(), float(v))
    return out


def _ctx_hash_inversor(ctx: dict) -> str:
    df_ag = ctx.get("df_ag")
    ccl = round(float(ctx.get("ccl") or 0), 4)
    cartera = str(ctx.get("cartera_activa", ""))
    _plan = st.session_state.get("inv_mix_plan")
    _mix_part = ""
    if isinstance(_plan, dict) and _plan.get("rf") is not None:
        _mix_part = f"|mix={round(float(_plan['rf']), 4)}"
    if df_ag is None or df_ag.empty:
        return hashlib.md5(f"empty|{ccl}|{cartera}{_mix_part}".encode()).hexdigest()
    try:
        h = str(pd.util.hash_pandas_object(df_ag, index=False).sum())
    except Exception:
        h = str(len(df_ag)) + str(df_ag["TICKER"].tolist())
    return hashlib.md5(f"{h}|{ccl}|{cartera}{_mix_part}".encode()).hexdigest()


def _senales_precalculadas(ctx: dict) -> list[dict] | None:
    df_ag = ctx.get("df_ag")
    if df_ag is None or df_ag.empty:
        return None
    df_analisis = ctx.get("df_analisis")
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    score_map: dict = {}
    rsi_map: dict = {}
    if df_analisis is not None and not df_analisis.empty:
        if "TICKER" in df_analisis.columns and "PUNTAJE_TECNICO" in df_analisis.columns:
            score_map = df_analisis.set_index("TICKER")["PUNTAJE_TECNICO"].to_dict()
        if "RSI" in df_analisis.columns:
            rsi_map = df_analisis.set_index("TICKER")["RSI"].to_dict()
    from services.motor_salida import evaluar_salida

    out: list[dict] = []
    for _, row in df_ag.iterrows():
        ticker = str(row.get("TICKER", ""))
        ppc_ars = float(pd.to_numeric(row.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
        px_ars = float(pd.to_numeric(row.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
        rsi_val = float(rsi_map.get(ticker, 50.0) or 50.0)
        score_v = float(score_map.get(ticker, 5.0) or 5.0)
        fecha_c = row.get("FECHA_COMPRA", date(2020, 1, 1))
        if not isinstance(fecha_c, date):
            try:
                fecha_c = pd.to_datetime(str(fecha_c)).date()
            except Exception:
                fecha_c = date(2020, 1, 1)
        if ppc_ars <= 0 or px_ars <= 0:
            continue
        out.append(
            evaluar_salida(
                ticker=ticker,
                ppc_usd=ppc_ars,
                px_usd_actual=px_ars,
                rsi=rsi_val,
                score_actual=score_v,
                score_semana_anterior=score_v,
                fecha_compra=fecha_c,
                perfil=perfil_ms,
            )
        )
    return out if out else None


def _mix_rf_desde_filas_primera(filas: list[dict]) -> float:
    total = 0.0
    rf = 0.0
    for f in filas:
        v = float(f.get("PPC_ARS") or 0) * float(f.get("CANTIDAD") or 0)
        if v <= 0:
            continue
        total += v
        row = pd.Series({"TICKER": f.get("TICKER", ""), "TIPO": f.get("TIPO", "")})
        if es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
            rf += v
    return float(rf / total) if total > 1e-9 else 0.0


def _mix_objetivo_desde_sesion(df_ag: pd.DataFrame | None, universo_df) -> float | None:
    """Objetivo RF del armado reciente, si sigue alineado con la cartera actual."""
    from services.diagnostico_cartera import pct_renta_fija_cartera

    plan = st.session_state.get("inv_mix_plan")
    if not isinstance(plan, dict):
        return None
    try:
        ts = float(plan.get("ts") or 0)
        cand = float(plan["rf"])
    except (KeyError, TypeError, ValueError):
        return None
    if time.time() - ts > 90.0 * 86400.0:
        return None
    if df_ag is None or df_ag.empty:
        return cand
    try:
        pr = float(pct_renta_fija_cartera(df_ag, universo_df))
    except Exception:
        return cand
    if abs(cand - pr) > 0.22:
        return None
    return cand


def _get_diagnostico_cached(ctx: dict) -> object:
    h = _ctx_hash_inversor(ctx)
    now = time.monotonic()
    cache = st.session_state.get("inv_diagnostico") or {}
    ttl = 300.0
    if (
        cache.get("hash") == h
        and cache.get("result") is not None
        and (now - float(cache.get("ts", 0))) < ttl
    ):
        return cache["result"]
    from services.diagnostico_cartera import diagnosticar

    df_ag = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
    metricas = ctx.get("metricas") or {}
    senales = _senales_precalculadas(ctx)
    mix_o = _mix_objetivo_desde_sesion(df_ag, ctx.get("universo_df"))
    res = diagnosticar(
        df_ag=df_ag,
        perfil=str(ctx.get("cliente_perfil", "Moderado")),
        horizonte_label=_horizonte_ui(ctx),
        metricas=metricas,
        ccl=float(ctx.get("ccl") or 0.0),
        universo_df=ctx.get("universo_df"),
        senales_salida=senales,
        cliente_nombre=str(ctx.get("cliente_nombre", "")),
        mix_objetivo_rf=mix_o,
    )
    st.session_state["inv_diagnostico"] = {"hash": h, "ts": now, "result": res}
    st.session_state.pop("diagnostico_cache", None)
    return res


def _market_stress_optional() -> dict | None:
    try:
        import yfinance as yf

        vix_h = yf.Ticker("^VIX").history(period="5d")
        vix = float(vix_h["Close"].iloc[-1]) if len(vix_h) > 0 else None
        spy = yf.Ticker("SPY").history(period="30d")["Close"].dropna()
        dd = None
        if len(spy) >= 2:
            dd = float(spy.iloc[-1] / spy.iloc[0] - 1.0)
        return {"vix": vix, "spy_drawdown_30d": dd}
    except Exception:
        return None


def _horizonte_ui(ctx: dict) -> str:
    return str(
        ctx.get("cliente_horizonte_label")
        or ctx.get("horizonte_label")
        or "1 año",
    )


def _ticker_desde_fila_pos(row: pd.Series) -> str:
    """Ticker robusto (evita columnas alternativas y valores corruptos)."""
    for key in ("TICKER", "Ticker", "ticker", "ACTIVO", "Activo"):
        if key not in row.index:
            continue
        v = row.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "nat", "<na>"):
            continue
        if s in ("0", "0.0", "0.00"):
            continue
        return s.upper().strip()
    return ""


def _nombre_universo_para_ticker(ticker: str, udf: pd.DataFrame | None) -> str:
    if not ticker or udf is None or udf.empty or "TICKER" not in udf.columns:
        return ""
    tu = str(ticker).strip().upper()
    m = udf[udf["TICKER"].astype(str).str.strip().str.upper() == tu]
    if m.empty:
        return ""
    for col in ("NOMBRE", "DENOMINACION", "Nombre", "nombre", "DESCRIPCION", "descripcion"):
        if col not in m.columns:
            continue
        val = m.iloc[0].get(col)
        if val is not None and str(val).strip():
            return str(val).strip()[:72]
    return ""


def _cartera_resuelta_primera_cartera(ctx: dict) -> str:
    """
    Libro donde persistir compras sugeridas: **el mismo** que la cartera activa en contexto.

    Antes se reemplazaba «(sin datos)» por «Cartera principal», y las compras quedaban en
    otro `CARTERA` que el filtro del inversor no mostraba (no se veía la acumulación).
    Si no hay nombre activo, se usa «Cliente | Cartera principal» como fallback.
    """
    raw = str(ctx.get("cartera_activa") or "").strip()
    nombre = str(ctx.get("cliente_nombre", "")).split("|")[0].strip() or "Cliente"
    if not raw:
        return f"{nombre} | Cartera principal"
    return raw


def _tipo_universo_ticker(ticker: str, udf: pd.DataFrame | None) -> str:
    if udf is None or udf.empty or "TICKER" not in udf.columns:
        return "CEDEAR"
    tu = str(ticker or "").strip().upper()
    m = udf[udf["TICKER"].astype(str).str.strip().str.upper() == tu]
    if m.empty:
        return "CEDEAR"
    t = str(m.iloc[0].get("TIPO", "") or "CEDEAR").strip().upper()
    if t in ("ACCION", "ACCIÓN"):
        return "ACCION_LOCAL"
    return t or "CEDEAR"
