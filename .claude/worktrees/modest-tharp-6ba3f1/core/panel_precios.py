"""
Validación de panel de precios antes de optimizar / exportar pesos (E02).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def validar_panel_precios(
    hist: pd.DataFrame,
    tickers: list[str],
    *,
    min_obs: int = 30,
) -> tuple[bool, str]:
    """
    Retorna (ok, mensaje). ok=False si falta algún ticker, hay columna vacía
    o demasiados NaN en precios de cierre.
    """
    if hist is None or hist.empty:
        return False, "Histórico vacío."
    if not tickers or len(tickers) < 2:
        return False, "Se requieren al menos 2 tickers."
    h = hist.sort_index()
    for t in tickers:
        if t not in h.columns:
            return False, f"Falta serie de precios para {t}."
        col = pd.to_numeric(h[t], errors="coerce")
        finite = int(np.isfinite(col.to_numpy(dtype=float, copy=False)).sum())
        if finite < min_obs:
            return False, f"Precios insuficientes para {t} (observaciones válidas={finite}, mínimo={min_obs})."
    return True, "Panel de precios válido."
