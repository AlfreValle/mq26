"""
core/rebalanceo.py — Comparación de holdings actuales vs cartera óptima y generación
de órdenes de rebalanceo (buy/sell/hold) con banda de tolerancia y costos de transacción.

Contrato:
  - Entrada: pesos actuales (dict ticker→pct), pesos objetivo (dict ticker→pct),
    capital total en ARS, tipo de cambio CCL.
  - Salida: lista ordenada de OrdenRebalanceo con delta, monto, tipo y prioridad.
  - Banda de tolerancia: si |delta_peso| < banda_min, la orden es HOLD.
  - Costos de transacción: se restan al monto neto de cada orden.

Unidades:
  - pesos_* : valores en [0, 1] (fracción), o [0, 100] en pct — se normalizan internamente.
  - capital_total_ars : escalar positivo.
  - ccl : tipo de cambio ARS/USD.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


# ─── Tipos ────────────────────────────────────────────────────────────────────

class TipoOrden(str, Enum):
    COMPRA = "COMPRA"
    VENTA  = "VENTA"
    HOLD   = "HOLD"


@dataclass
class OrdenRebalanceo:
    """Una orden de rebalanceo para un activo individual."""
    ticker:          str
    tipo:            TipoOrden
    peso_actual:     float          # fracción [0,1]
    peso_objetivo:   float          # fracción [0,1]
    delta_peso:      float          # objetivo − actual (positivo = comprar más)
    monto_ars:       float          # valor absoluto del monto a operar en ARS
    monto_usd:       float          # ídem en USD (monto_ars / ccl)
    costo_estimado:  float          # comisión estimada en ARS
    monto_neto_ars:  float          # monto_ars − costo_estimado (neto)
    prioridad:       int            # 1=alta, 2=media, 3=baja (por magnitud)
    metadata:        dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultadoRebalanceo:
    """Resultado completo del análisis de rebalanceo."""
    ordenes:              list[OrdenRebalanceo]
    capital_total_ars:    float
    ccl:                  float
    banda_tolerancia:     float
    costo_transaccion_bps: float
    n_compras:            int
    n_ventas:             int
    n_holds:              int
    turnover_bruto:       float    # Σ|delta_peso| / 2
    costo_total_ars:      float
    tickers_nuevos:       list[str]   # en objetivo pero no en actuales
    tickers_eliminados:   list[str]   # en actuales pero no en objetivo
    params:               dict[str, Any] = field(default_factory=dict)


# ─── Normalización ────────────────────────────────────────────────────────────

def _normalizar_pesos(pesos: dict[str, float]) -> dict[str, float]:
    """
    Acepta pesos en [0,1] o en [0,100].  Normaliza a suma=1.
    """
    if not pesos:
        return {}
    vals = np.array(list(pesos.values()), dtype=float)
    # Si la suma > 1.5 asumimos que vienen en porcentaje (0–100)
    if vals.sum() > 1.5:
        vals = vals / 100.0
    s = vals.sum()
    if s > 0:
        vals = vals / s
    return dict(zip(pesos.keys(), vals.tolist()))


# ─── Función principal ────────────────────────────────────────────────────────

def calcular_ordenes_rebalanceo(
    pesos_actuales: dict[str, float],
    pesos_objetivo: dict[str, float],
    *,
    capital_total_ars: float,
    ccl: float = 1.0,
    banda_tolerancia: float = 0.03,
    costo_transaccion_bps: float = 30.0,
    umbral_prioridad_alta: float = 0.08,
    umbral_prioridad_media: float = 0.03,
) -> ResultadoRebalanceo:
    """
    Genera órdenes de rebalanceo comparando holdings actuales con la cartera óptima.

    Parámetros
    ----------
    pesos_actuales          : fracción o pct por ticker — holdings reales ahora.
    pesos_objetivo          : fracción o pct por ticker — salida del optimizador.
    capital_total_ars       : AUM total en ARS.
    ccl                     : tipo de cambio ARS/USD (para convertir montos).
    banda_tolerancia        : si |delta_peso| < banda, la orden es HOLD (default 3 %).
    costo_transaccion_bps   : comisión bilateral en bps sobre el monto (default 30 bps).
    umbral_prioridad_alta   : |delta| ≥ umbral → prioridad 1 (default 8 %).
    umbral_prioridad_media  : |delta| ≥ umbral → prioridad 2 (default 3 %).

    Retorna
    -------
    ResultadoRebalanceo con lista de OrdenRebalanceo ordenadas por |delta_peso| desc.
    """
    act = _normalizar_pesos(pesos_actuales)
    obj = _normalizar_pesos(pesos_objetivo)

    tickers_all      = sorted(set(act) | set(obj))
    tickers_nuevos   = [t for t in obj if t not in act]
    tickers_eliminados = [t for t in act if t not in obj]

    costo_frac = costo_transaccion_bps / 10_000.0
    ordenes: list[OrdenRebalanceo] = []

    for ticker in tickers_all:
        w_act = act.get(ticker, 0.0)
        w_obj = obj.get(ticker, 0.0)
        delta = w_obj - w_act

        if delta == 0.0 or abs(delta) < banda_tolerancia:
            tipo = TipoOrden.HOLD
        elif delta > 0:
            tipo = TipoOrden.COMPRA
        else:
            tipo = TipoOrden.VENTA

        monto_ars     = abs(delta) * capital_total_ars
        monto_usd     = monto_ars / max(ccl, 1.0)
        costo_est     = monto_ars * costo_frac
        monto_neto    = monto_ars - costo_est

        if abs(delta) >= umbral_prioridad_alta:
            prioridad = 1
        elif abs(delta) >= umbral_prioridad_media:
            prioridad = 2
        else:
            prioridad = 3

        ordenes.append(OrdenRebalanceo(
            ticker          = ticker,
            tipo            = tipo,
            peso_actual     = w_act,
            peso_objetivo   = w_obj,
            delta_peso      = delta,
            monto_ars       = monto_ars,
            monto_usd       = monto_usd,
            costo_estimado  = costo_est,
            monto_neto_ars  = monto_neto,
            prioridad       = prioridad,
            metadata        = {
                "es_nuevo":     ticker in tickers_nuevos,
                "es_eliminado": ticker in tickers_eliminados,
            },
        ))

    # Ordenar: tipo VENTA primero (libera caja), luego COMPRA; dentro de cada grupo por |delta| desc
    def _sort_key(o: OrdenRebalanceo) -> tuple:
        tipo_rank = {TipoOrden.VENTA: 0, TipoOrden.COMPRA: 1, TipoOrden.HOLD: 2}
        return (tipo_rank[o.tipo], -abs(o.delta_peso))

    ordenes.sort(key=_sort_key)

    n_compras = sum(1 for o in ordenes if o.tipo == TipoOrden.COMPRA)
    n_ventas  = sum(1 for o in ordenes if o.tipo == TipoOrden.VENTA)
    n_holds   = sum(1 for o in ordenes if o.tipo == TipoOrden.HOLD)

    # Turnover = Σ|delta| / 2 (doble conteo compra+venta)
    turnover = sum(abs(o.delta_peso) for o in ordenes) / 2.0
    costo_total = sum(o.costo_estimado for o in ordenes if o.tipo != TipoOrden.HOLD)

    return ResultadoRebalanceo(
        ordenes              = ordenes,
        capital_total_ars    = capital_total_ars,
        ccl                  = ccl,
        banda_tolerancia     = banda_tolerancia,
        costo_transaccion_bps = costo_transaccion_bps,
        n_compras            = n_compras,
        n_ventas             = n_ventas,
        n_holds              = n_holds,
        turnover_bruto       = turnover,
        costo_total_ars      = costo_total,
        tickers_nuevos       = tickers_nuevos,
        tickers_eliminados   = tickers_eliminados,
        params               = {
            "banda_tolerancia":       banda_tolerancia,
            "costo_transaccion_bps":  costo_transaccion_bps,
            "capital_total_ars":      capital_total_ars,
            "ccl":                    ccl,
            "n_tickers_actuales":     len(act),
            "n_tickers_objetivo":     len(obj),
        },
    )


# ─── Helpers para UI ──────────────────────────────────────────────────────────

def resumen_rebalanceo(resultado: ResultadoRebalanceo) -> dict[str, Any]:
    """
    Dict plano listo para mostrar en tabla o log.
    """
    return {
        "capital_total_ars":    resultado.capital_total_ars,
        "ccl":                  resultado.ccl,
        "n_compras":            resultado.n_compras,
        "n_ventas":             resultado.n_ventas,
        "n_holds":              resultado.n_holds,
        "turnover_bruto_pct":   round(resultado.turnover_bruto * 100, 2),
        "costo_total_ars":      round(resultado.costo_total_ars, 2),
        "costo_total_bps":      resultado.costo_transaccion_bps,
        "tickers_nuevos":       resultado.tickers_nuevos,
        "tickers_eliminados":   resultado.tickers_eliminados,
    }


def ordenes_a_dataframe(resultado: ResultadoRebalanceo):
    """Convierte la lista de órdenes en un DataFrame de pandas (sin importar en el módulo)."""
    import pandas as pd  # noqa: PLC0415
    rows = []
    for o in resultado.ordenes:
        rows.append({
            "ticker":         o.ticker,
            "tipo":           o.tipo.value,
            "peso_actual_%":  round(o.peso_actual * 100, 2),
            "peso_objetivo_%": round(o.peso_objetivo * 100, 2),
            "delta_%":        round(o.delta_peso * 100, 2),
            "monto_ARS":      round(o.monto_ars, 0),
            "monto_USD":      round(o.monto_usd, 0),
            "costo_ARS":      round(o.costo_estimado, 0),
            "neto_ARS":       round(o.monto_neto_ars, 0),
            "prioridad":      o.prioridad,
        })
    return pd.DataFrame(rows)
