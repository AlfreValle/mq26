"""
services/ejecucion_service.py — Servicio de dominio para la Mesa de Ejecución
MQ26-DSS | Sin dependencias de Streamlit.

Orquesta:
  - RiskEngine: optimización de pesos.
  - execution_engine: generación de órdenes brutas.
  - decision_engine: filtrado por alpha neto vs costos.
  - alert_bot: envío de alertas de rebalanceo.

Consumido por app_main.py (Tab 9 — Mesa de Ejecución).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logging_config import get_logger

logger = get_logger(__name__)


def generar_plan_rebalanceo(
    tickers_cartera: list[str],
    df_ag: pd.DataFrame,
    hist_precios: pd.DataFrame,
    precios_ars: dict[str, float],
    modelo: str = "Sharpe",
    capital_nuevo_ars: float = 0.0,
    umbral_churning: float = 0.05,
    comision_pct: float = 0.006,
    horizonte_dias: int = 252,
    risk_free_rate: float = 0.043,
) -> dict:
    """
    Genera el plan de rebalanceo completo:
      1. Optimiza pesos con RiskEngine.
      2. Genera órdenes brutas con execution_engine.
      3. Filtra por alpha neto con decision_engine.
      4. Retorna resultado estructurado.

    Devuelve dict con:
      'pesos_optimos'   : dict {ticker: peso}
      'ejecutables'     : DataFrame órdenes aprobadas
      'bloqueadas'      : DataFrame órdenes bloqueadas
      'reporte'         : str resumen textual
      'metricas'        : dict {sharpe, vol, retorno, max_dd}
      'error'           : str | None
    """
    vacio = {
        "pesos_optimos": {}, "ejecutables": pd.DataFrame(),
        "bloqueadas": pd.DataFrame(), "reporte": "", "metricas": {}, "error": None,
    }

    if not tickers_cartera or df_ag.empty:
        vacio["error"] = "Sin posiciones en la cartera activa."
        return vacio

    tickers_ok = [t for t in tickers_cartera if t in hist_precios.columns]
    if len(tickers_ok) < 2:
        vacio["error"] = "Insuficientes datos históricos (se necesitan al menos 2 activos)."
        return vacio

    try:
        from risk_engine import RiskEngine
        risk_eng  = RiskEngine(hist_precios[tickers_ok])
        pesos_opt = risk_eng.optimizar(modelo)
        ret_anual, vol_anual, sharpe = risk_eng.calcular_metricas(pesos_opt)

        # Retornos diarios esperados para el filtro de alpha
        ret_diarios = hist_precios[tickers_ok].pct_change().dropna().mean().to_dict()

        # Capital actual por ticker (en ARS)
        cap_actual = {
            str(row["TICKER"]): float(row.get("VALOR_ARS", 0.0))
            for _, row in df_ag.iterrows()
        }
        # Si no viene VALOR_ARS en df_ag, calcularlo desde precios
        if all(v == 0.0 for v in cap_actual.values()):
            cap_actual = {
                str(row["TICKER"]): float(row["CANTIDAD_TOTAL"]) * float(precios_ars.get(str(row["TICKER"]), 0.0))
                for _, row in df_ag.iterrows()
            }

        from execution_engine import generar_ordenes
        ordenes_brutas = generar_ordenes(
            pesos_objetivo=pesos_opt,
            capital_actual=cap_actual,
            capital_nuevo=capital_nuevo_ars,
            precios_ars=precios_ars,
            umbral_pct=umbral_churning,
        )

        if not ordenes_brutas:
            return {
                "pesos_optimos": pesos_opt,
                "ejecutables":   pd.DataFrame(),
                "bloqueadas":    pd.DataFrame(),
                "reporte":       "Cartera ya optimizada. Sin órdenes necesarias.",
                "metricas":      {"sharpe": sharpe, "vol": vol_anual, "retorno": ret_anual, "max_dd": None},
                "error":         None,
            }

        ordenes_para_filtro = [
            {
                "ticker":    o.get("TICKER", ""),
                "tipo_op":   "COMPRA" if o.get("ACCION", "COMPRAR") == "COMPRAR" else "VENTA",
                "nominales": int(abs(o.get("NOMINALES", 0))),
                "precio_ars": float(o.get("PRECIO_ARS", precios_ars.get(o.get("TICKER", ""), 0.0))),
            }
            for o in ordenes_brutas
        ]

        from decision_engine import filtrar_por_alpha_neto, generar_reporte_decision
        ejecutables, bloqueadas = filtrar_por_alpha_neto(
            ordenes_para_filtro,
            ret_diarios,
            horizonte_dias=horizonte_dias,
            comision_pct=comision_pct,
        )

        reporte = generar_reporte_decision(ejecutables, bloqueadas)

        # Max drawdown de la cartera optimizada
        w_arr = np.array([pesos_opt.get(t, 0.0) for t in tickers_ok])
        w_arr /= w_arr.sum() if w_arr.sum() > 0 else 1.0
        ret_d = hist_precios[tickers_ok].pct_change().dropna()
        ret_port = ret_d @ w_arr
        eq = np.cumprod(1 + ret_port.values)
        max_dd = float((eq / np.maximum.accumulate(eq) - 1).min()) if len(eq) > 0 else 0.0

        logger.info(
            "Plan de rebalanceo: modelo=%s, aprobadas=%d, bloqueadas=%d",
            modelo, len(ejecutables), len(bloqueadas),
        )

        return {
            "pesos_optimos": pesos_opt,
            "ejecutables":   ejecutables,
            "bloqueadas":    bloqueadas,
            "reporte":       reporte,
            "metricas": {
                "sharpe":  round(sharpe, 3),
                "vol":     round(vol_anual, 4),
                "retorno": round(ret_anual, 4),
                "max_dd":  round(max_dd, 4),
            },
            "error": None,
        }

    except Exception as exc:
        logger.exception("ejecucion_service.generar_plan_rebalanceo: %s", exc)
        vacio["error"] = str(exc)
        return vacio


def enviar_alerta_rebalanceo(
    ejecutables: pd.DataFrame,
    nombre_cartera: str,
) -> None:
    """
    Envía alerta Telegram con las órdenes aprobadas si hay alguna.
    Invariante: no propaga excepciones; entradas None o vacías no llaman al bot.
    """
    if ejecutables is None or ejecutables.empty:
        return
    try:
        from alert_bot import alerta_rebalanceo
        compras = ejecutables[ejecutables["tipo_op"] == "COMPRA"]["ticker"].tolist()
        ventas  = ejecutables[ejecutables["tipo_op"] == "VENTA"]["ticker"].tolist()
        alerta_rebalanceo(compras, ventas, nombre_cartera)
    except Exception as exc:
        logger.warning("No se pudo enviar alerta de rebalanceo: %s", exc)
