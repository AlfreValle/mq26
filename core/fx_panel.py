"""
C10 (MVP): conversión de columnas de precios en ARS a USD usando un CCL único (nivel).
Para series con distinta moneda por ticker, pasar el conjunto de tickers cotizados en ARS.
"""
from __future__ import annotations

import pandas as pd


def panel_precios_a_moneda_base(
    precios: pd.DataFrame,
    tickers_en_ars: set[str],
    *,
    moneda_base: str,
    ccl_ars_por_usd: float,
) -> pd.DataFrame:
    """
    Si moneda_base=='USD', divide las columnas en tickers_en_ars por ccl (>0).
    Otros tickers se dejan igual (asume ya en USD o en la misma unidad que la cartera).
    """
    if precios is None or precios.empty:
        return precios.copy() if precios is not None else pd.DataFrame()
    out = precios.copy()
    if str(moneda_base).upper() != "USD":
        return out
    if ccl_ars_por_usd <= 0:
        return out
    f = 1.0 / float(ccl_ars_por_usd)
    for t in tickers_en_ars:
        if t in out.columns:
            out[t] = pd.to_numeric(out[t], errors="coerce") * f
    return out
