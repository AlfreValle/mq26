"""
A17 (v0) — Esqueleto dos etapas: pesos largo plazo + rebalanceo acotado.

Etapa 2: proyección al simplex con límite de turnover L1 respecto a ``w_long``.
"""
from __future__ import annotations

import numpy as np


def two_stage_rebalance(
    w_long: np.ndarray,
    w_unconstrained: np.ndarray,
    *,
    turnover_cap: float = 0.15,
) -> np.ndarray:
    """
    Mezcla hacia ``w_unconstrained`` sin exceder ``turnover_cap`` (mitad L1 / TV).

    TV = 0.5 * sum |w - w_long| ≤ turnover_cap.
    """
    w0 = np.asarray(w_long, dtype=float).ravel()
    w1 = np.asarray(w_unconstrained, dtype=float).ravel()
    if w0.shape != w1.shape:
        raise ValueError("w_long y w_unconstrained deben tener la misma dimensión")
    w1 = w1 / max(w1.sum(), 1e-12)
    w0 = w0 / max(w0.sum(), 1e-12)
    delta = w1 - w0
    tv = 0.5 * float(np.sum(np.abs(delta)))
    if tv <= 1e-12 or turnover_cap >= tv:
        w = w1
    else:
        lam = turnover_cap / tv
        w = w0 + lam * delta
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.ones_like(w) / len(w)
