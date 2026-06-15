"""
A16 — Hierarchical Risk Parity (pesos a partir de covarianza).

Núcleo puro: ``hrp_weights`` con ``scipy.cluster.hierarchy`` y bisección recursiva.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    cov = np.asarray(cov, dtype=float)
    std = np.sqrt(np.diag(cov))
    outer = np.outer(std, std)
    return cov / np.maximum(outer, 1e-12)


def _ivp_cluster_variance(cov: np.ndarray, ix: list[int]) -> float:
    sub = cov[np.ix_(ix, ix)]
    d = np.diag(sub)
    d = np.maximum(d, 1e-12)
    iv = 1.0 / d
    iv = iv / iv.sum()
    return float(iv @ sub @ iv)


def _recursive_bisection(cov: np.ndarray, items: list[int], w: np.ndarray) -> None:
    if len(items) == 1:
        return
    split = len(items) // 2
    c1, c2 = items[:split], items[split:]
    v1 = _ivp_cluster_variance(cov, c1)
    v2 = _ivp_cluster_variance(cov, c2)
    alpha = v2 / (v1 + v2) if (v1 + v2) > 1e-18 else 0.5
    w[c1] *= alpha
    w[c2] *= 1.0 - alpha
    _recursive_bisection(cov, c1, w)
    _recursive_bisection(cov, c2, w)


def hrp_weights(covariance: np.ndarray) -> np.ndarray:
    """
    Pesos long-only que suman 1; a partir de matriz de covarianza (anual o por paso).
    """
    cov = np.asarray(covariance, dtype=float)
    n = cov.shape[0]
    if cov.shape != (n, n) or n < 1:
        raise ValueError("covariance debe ser (n,n) con n>=1")

    if n == 1:
        return np.array([1.0])

    corr = _cov_to_corr(cov)
    dist = np.sqrt(np.clip(0.5 * (1.0 - corr), 0.0, None))
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="single")
    order = list(leaves_list(Z))
    w = np.ones(n, dtype=float)
    _recursive_bisection(cov, order, w)
    s = w.sum()
    if s <= 0:
        return np.ones(n) / n
    return w / s


def solve_erc(covariance: np.ndarray, tol: float = 1e-8) -> np.ndarray:
    """Equal Risk Contribution: iguala contribuciones de riesgo por activo."""
    cov = np.asarray(covariance, dtype=float)
    n = cov.shape[0]
    w0 = np.ones(n, dtype=float) / n

    def _obj(w: np.ndarray) -> float:
        sigma = float(np.sqrt(max(w @ cov @ w, 1e-12)))
        mrc = cov @ w / sigma
        rc = w * mrc
        return float(np.sum((rc - rc.mean()) ** 2))

    res = minimize(
        _obj,
        w0,
        method="SLSQP",
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}],
        bounds=[(0.0, 1.0)] * n,
        tol=tol,
    )
    w = np.asarray(res.x, dtype=float)
    s = float(w.sum())
    return (w / s) if s > 0 else w0
