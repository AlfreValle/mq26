"""
core/cache_manager.py — Gestión centralizada de caché (MQ-A3)
Todos los @st.cache_data y TTLs configurables desde .env.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

# TTLs configurables vía variables de entorno
_TTL_CCL       = int(os.environ.get("CACHE_TTL_CCL",       300))   # 5 min
_TTL_HISTORICO = int(os.environ.get("CACHE_TTL_HISTORICO", 3600))  # 1 hora
_TTL_PRECIOS   = int(os.environ.get("CACHE_TTL_PRECIOS",   300))   # 5 min
_TTL_RATIOS    = int(os.environ.get("CACHE_TTL_RATIOS",    3600))  # 1 hora
_TTL_METRICAS  = int(os.environ.get("CACHE_TTL_METRICAS",  60))    # 1 min
_TTL_DASHBOARD = int(os.environ.get("CACHE_TTL_DASHBOARD", 120))   # 2 min


@st.cache_data(ttl=_TTL_CCL)
def cache_ccl(engine_data) -> float:
    """CCL en tiempo real con TTL=5 min."""
    try:
        from data_engine import obtener_ccl
        return obtener_ccl()
    except Exception:
        return float(os.environ.get("CCL_FALLBACK_OVERRIDE", 1500.0))


@st.cache_data(ttl=_TTL_HISTORICO)
def cache_historico(engine_data, tickers: tuple, period: str = "1y") -> pd.DataFrame:
    """Histórico de precios ajustados, cacheado 1 hora."""
    return engine_data.descargar_historico(list(tickers), period)


@st.cache_data(ttl=_TTL_PRECIOS)
def cache_precios_actuales(engine_data, tickers: tuple, ccl: float) -> dict:
    """Precios actuales de la cartera, cacheados 5 min."""
    return engine_data.obtener_precios_cartera(list(tickers), ccl)


@st.cache_data(ttl=_TTL_RATIOS)
def cache_ratios_fundamentales(mc_module, tickers: tuple) -> pd.DataFrame:
    """Ratios fundamentales, cacheados 1 hora."""
    return mc_module.obtener_ratios_fundamentales(list(tickers))


@st.cache_data(ttl=_TTL_METRICAS)
def cache_metricas_resumen(df_serialized: str, ccl: float, cartera_key: str) -> dict:
    """Métricas de resumen de cartera, cacheadas 60s."""
    import io

    import services.cartera_service as cs
    try:
        df = pd.read_json(io.StringIO(df_serialized))
        return cs.metricas_resumen(df) if not df.empty else {}
    except Exception:
        return {}


@st.cache_data(ttl=_TTL_DASHBOARD, hash_funcs={"builtins.int": lambda x: x})
def cache_resumen_12_meses(cliente_id: int, anio_actual: int, mes_actual: int) -> list[dict]:
    """
    Carga los últimos 12 meses de resúmenes DSS en una sola llamada cacheada.
    Evita 12 queries separadas al BD en cada rerender del dashboard (DS-D2 / MQ-D2).
    """
    import datetime as dt

    import core.db_manager as dbm
    meses_data = []
    hoy = dt.date(anio_actual, mes_actual, 1)
    for delta in range(11, -1, -1):
        # Calcular mes correctamente sin saltar días (DS-D1 / MQ-D1)
        mes_n  = (mes_actual - delta - 1) % 12 + 1
        anio_n = anio_actual - ((delta + (12 - mes_actual)) // 12)
        # Ajuste de año más preciso
        d = hoy
        for _ in range(delta):
            primer_dia = d.replace(day=1)
            d = (primer_dia - dt.timedelta(days=1)).replace(day=1)
        mes_n  = d.month
        anio_n = d.year
        try:
            r = dbm.obtener_resumen_mes(cliente_id, mes_n, anio_n)
        except Exception:
            r = {}
        meses_data.append({
            "Mes":       d.strftime("%b %Y"),
            "mes_n":     mes_n,
            "anio_n":    anio_n,
            "Ingresos":  r.get("ingresos", 0.0),
            "Egresos":   r.get("total_egresos", 0.0),
            "Liquidez":  r.get("liquidez_libre", 0.0),
        })
    return meses_data


def limpiar_cache_cartera() -> None:
    """Limpia todas las cachés de datos de cartera."""
    st.cache_data.clear()


def limpiar_cache_sesion(cartera_activa: str) -> None:
    """Limpia solo la caché de session_state para la cartera activa."""
    for prefix in ["_df_ag_cache_", "_df_ag_hash_", "_df_ag_fifo_"]:
        st.session_state.pop(f"{prefix}{cartera_activa}", None)
