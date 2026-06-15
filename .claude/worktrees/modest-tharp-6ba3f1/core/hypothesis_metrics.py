"""
H03 — Contraste simple de exceso de retorno vs benchmark (t-stat naïve).
"""
from __future__ import annotations

import numpy as np


def excess_return_tstat(
    strat_returns: np.ndarray,
    bench_returns: np.ndarray,
) -> float:
    """
    t-statistic de la media de (strat - bench) / stderr, asumiendo i.i.d.
    """
    a = np.asarray(strat_returns, dtype=float).ravel()
    b = np.asarray(bench_returns, dtype=float).ravel()
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    d = a[:n] - b[:n]
    mu = float(d.mean())
    se = float(d.std(ddof=1)) / np.sqrt(n)
    return mu / se if se > 1e-18 else 0.0
