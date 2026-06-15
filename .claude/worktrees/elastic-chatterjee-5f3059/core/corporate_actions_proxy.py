"""
C08 — Detección proxy de saltos de precio (splits/dividendos no confirmados).

Solo **advertencias**; no sustituye feed oficial de corporate actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class JumpReport:
    flagged_dates: list[pd.Timestamp] = field(default_factory=list)
    max_abs_move: float = 0.0
    threshold: float = 0.25


def detect_price_jumps(
    close: pd.Series,
    *,
    threshold: float = 0.25,
) -> JumpReport:
    """
    Marca días con |r_t| > threshold en retornos simples.

    ``threshold`` en decimal (0.25 = 25%).
    """
    s = close.astype(float).dropna()
    if len(s) < 2:
        return JumpReport(threshold=threshold)
    r = s.pct_change().dropna()
    flagged = r.index[np.abs(r.values) > threshold].tolist()
    mx = float(np.max(np.abs(r.values))) if len(r) else 0.0
    return JumpReport(
        flagged_dates=list(flagged),
        max_abs_move=mx,
        threshold=threshold,
    )
