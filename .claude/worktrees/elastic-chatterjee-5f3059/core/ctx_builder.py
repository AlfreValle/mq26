"""
core/ctx_builder.py — Constructor del contexto AppContext (MQ-A5)
Centraliza las ~50 líneas de construcción del ctx dispersas en mq26_main.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.app_context import AppContext


def build_ctx(
    *,
    tenant_id: str = "default",  # Sprint 5: multi-tenant
    # Cartera
    df_ag: pd.DataFrame,
    tickers_cartera: list[str],
    precios_dict: dict[str, float],
    ccl: float,
    cartera_activa: str,
    prop_nombre: str,
    df_clientes: pd.DataFrame,
    df_analisis: pd.DataFrame,
    metricas: dict[str, Any],
    df_trans: pd.DataFrame,
    # Cliente
    cliente_id: int | None,
    cliente_nombre: str,
    cliente_perfil: str,
    horizonte_label: str,
    # Config
    RISK_FREE_RATE: float,
    PESO_MAX_CARTERA: float,
    N_SIM_DEFAULT: int,
    RUTA_ANALISIS: str,
    horizonte_dias: int,
    capital_nuevo: float,
    BASE_DIR: Path,
    # Motores
    engine_data: Any,
    RiskEngine: Any,
    cached_historico: Any,
    # Servicios
    dbm: Any,
    cs: Any,
    m23svc: Any,
    ejsvc: Any,
    rpt: Any,
    bt: Any,
    ab: Any,
    lm: Any,
    bi: Any,
    gr: Any,
    mc: Any,
    # Helpers
    _boton_exportar: Any,
    asignar_sector: Any,
) -> AppContext:
    """
    Construye y devuelve un AppContext completamente poblado.
    Retorna el contexto tanto como dataclass (ctx.key) como dict-compatible (ctx['key']).
    """
    return AppContext(
        tenant_id=tenant_id,
        df_ag=df_ag,
        tickers_cartera=tickers_cartera,
        precios_dict=precios_dict,
        ccl=ccl,
        cartera_activa=cartera_activa,
        prop_nombre=prop_nombre,
        df_clientes=df_clientes,
        df_analisis=df_analisis,
        metricas=metricas,
        df_trans=df_trans,
        cliente_id=cliente_id,
        cliente_nombre=cliente_nombre,
        cliente_perfil=cliente_perfil,
        horizonte_label=horizonte_label,
        RISK_FREE_RATE=RISK_FREE_RATE,
        PESO_MAX_CARTERA=PESO_MAX_CARTERA,
        N_SIM_DEFAULT=N_SIM_DEFAULT,
        RUTA_ANALISIS=RUTA_ANALISIS,
        horizonte_dias=horizonte_dias,
        capital_nuevo=capital_nuevo,
        BASE_DIR=BASE_DIR,
        engine_data=engine_data,
        RiskEngine=RiskEngine,
        cached_historico=cached_historico,
        dbm=dbm,
        cs=cs,
        m23svc=m23svc,
        ejsvc=ejsvc,
        rpt=rpt,
        bt=bt,
        ab=ab,
        lm=lm,
        bi=bi,
        gr=gr,
        mc=mc,
        _boton_exportar=_boton_exportar,
        asignar_sector=asignar_sector,
    )
