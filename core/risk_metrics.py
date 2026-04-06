"""
core/risk_metrics.py — Métricas de riesgo mínimas (Fase 0: B19–B21 parcial).

B19: documentar unidades — retornos como fracción por periodo (diario si inputs diarios).
B20: vol anualizada, VaR/CVaR histórico, max drawdown.
B21: betas OLS frente a un factor (ej. mercado).
"""
from __future__ import annotations

import numpy as np


def portfolio_vol_annual(weights: np.ndarray, Sigma: np.ndarray) -> float:
    """Vol anual del portfolio √(w'Σw) si Σ ya está anualizada."""
    w = np.asarray(weights, dtype=float).ravel()
    S = np.asarray(Sigma, dtype=float)
    v = float(w @ S @ w)
    return float(np.sqrt(max(v, 0.0)))


def historical_var_cvar(
    returns: np.ndarray,
    *,
    alpha: float = 0.05,
    as_portfolio_loss_positive: bool = True,
) -> tuple[float, float]:
    """
    VaR y CVaR históricos al nivel alpha (cola inferior de retornos).
    Devuelve (VaR, CVaR) como magnitud positiva si as_portfolio_loss_positive.
    """
    r = np.asarray(returns, dtype=float).ravel()
    r = np.sort(r)
    k = max(int(np.floor(alpha * len(r))), 1)
    tail = r[:k]
    var = float(-np.percentile(r, alpha * 100)) if len(r) else 0.0
    cvar = float(-tail.mean()) if len(tail) else 0.0
    if not as_portfolio_loss_positive:
        return -var, -cvar
    return var, cvar


def max_drawdown_from_returns(returns: np.ndarray) -> float:
    """Max drawdown sobre equity curve (1+r).t.cumprod()."""
    r = np.asarray(returns, dtype=float).ravel()
    if len(r) == 0:
        return 0.0
    eq = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.maximum(peak, 1e-12)
    return float(dd.min())


def factor_betas_ols(
    asset_returns: np.ndarray,
    factor_returns: np.ndarray,
) -> tuple[np.ndarray, float]:
    """
    Betas por columna: cada columna de asset_returns (T×n) regredida sobre factor (T,).
    Retorna (betas, r2_medio).
    """
    y = np.asarray(asset_returns, dtype=float)
    f = np.asarray(factor_returns, dtype=float).ravel()
    if y.ndim == 1:
        y = y.reshape(-1, 1)
    t, n = y.shape
    if f.shape[0] != t:
        raise ValueError("factor y activos deben tener mismo T")
    X = np.column_stack([np.ones(t), f])
    betas = []
    r2s = []
    for j in range(n):
        b, _, _, _ = np.linalg.lstsq(X, y[:, j], rcond=None)
        betas.append(float(b[1]))
        resid = y[:, j] - X @ b
        sse = float((resid ** 2).sum())
        sst = float(((y[:, j] - y[:, j].mean()) ** 2).sum())
        r2s.append(1.0 - sse / sst if sst > 0 else 0.0)
    return np.asarray(betas, dtype=float), float(np.mean(r2s))
