"""
Utilidades puras para sanitizar paneles de retornos (C02 — outliers / winsorizado).
Sin I/O ni dependencia de Streamlit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def winsorize_returns_panel(
    retornos: pd.DataFrame,
    lower_q: float = 0.005,
    upper_q: float = 0.995,
) -> tuple[pd.DataFrame, dict]:
    """
    Winsorizado por columna sobre cuantiles empíricos.

    Retorna (df_ajustado, reporte) con claves:
      - n_recortes_por_columna: dict ticker -> int
      - n_recortes_total: int
    """
    if retornos.empty:
        return retornos, {"n_recortes_por_columna": {}, "n_recortes_total": 0}

    lo = float(np.clip(lower_q, 0.0, 1.0))
    hi = float(np.clip(upper_q, lo, 1.0))
    out = retornos.copy()
    por_col: dict[str, int] = {}
    total = 0

    for c in out.columns:
        s = out[c].astype(float)
        valid = s.dropna()
        if len(valid) < 5:
            por_col[str(c)] = 0
            continue
        q_lo, q_hi = valid.quantile(lo), valid.quantile(hi)
        mask_lo = s < q_lo
        mask_hi = s > q_hi
        n = int(mask_lo.sum() + mask_hi.sum())
        por_col[str(c)] = n
        total += n
        s = s.where(~mask_lo, q_lo)
        s = s.where(~mask_hi, q_hi)
        out[c] = s

    return out, {"n_recortes_por_columna": por_col, "n_recortes_total": total}
