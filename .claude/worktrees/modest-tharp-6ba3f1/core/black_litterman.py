"""
core/black_litterman.py — Black–Litterman completo (A6): P, Q, Ω, τ y π de equilibrio.

Fórmula estándar (retornos esperados posteriores):
μ_BL = M^{-1} rhs,
M = (τΣ)^{-1} + P' Ω^{-1} P,
rhs = (τΣ)^{-1} π + P' Ω^{-1} Q.

Unidades: π, Q y la salida en la misma escala que μ (p. ej. anual decimal);
Σ y τΣ coherentes con esa escala.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


def implied_equilibrium_returns(
    Sigma: np.ndarray,
    w_mkt: np.ndarray,
    risk_aversion: float,
) -> np.ndarray:
    """Prior π = δ Σ w_mkt (CAPM con coeficiente de aversión δ)."""
    S = np.asarray(Sigma, dtype=float)
    w = np.asarray(w_mkt, dtype=float).ravel()
    w = w / max(w.sum(), 1e-12)
    return float(risk_aversion) * (S @ w)


def risk_aversion_implied_from_mu_w(
    mu: np.ndarray,
    Sigma: np.ndarray,
    w_mkt: np.ndarray,
    *,
    ridge: float = 1e-10,
) -> float:
    """δ ≈ (w'μ) / (w'Σw) si el denominador > 0; si no, fallback 2.5."""
    w = np.asarray(w_mkt, dtype=float).ravel()
    w = w / max(w.sum(), 1e-12)
    S = np.asarray(Sigma, dtype=float) + ridge * np.eye(len(mu))
    denom = float(w @ S @ w)
    if denom <= 1e-18:
        return 2.5
    num = float(np.asarray(mu, dtype=float).ravel() @ w)
    if num <= 0:
        return 2.5
    return max(num / denom, 0.1)


def omega_proportional_psigma_pt(
    tau: float,
    P: np.ndarray,
    Sigma: np.ndarray,
    *,
    scale: float = 1.0,
    ridge: float = 1e-10,
) -> np.ndarray:
    """
    Ω diagonal proporcional a diag(P Σ P') — incertidumbre de la view acorde a Σ.
    τ y scale calibran confianza global (A7).
    """
    P = np.asarray(P, dtype=float)
    S = np.asarray(Sigma, dtype=float) + ridge * np.eye(P.shape[1])
    d = np.diag(P @ S @ P.T)
    d = np.maximum(d, 1e-12)
    return np.diag(float(tau) * float(scale) * d)


def omega_diagonal_from_confidence(
    P: np.ndarray,
    Sigma: np.ndarray,
    tau: float,
    confidence_per_view: np.ndarray,
    *,
    ridge: float = 1e-10,
) -> np.ndarray:
    """
    Ω_ii = (τ / c_i) * (P Σ P')_ii con c_i ∈ (0,1] confianza por view
    (mayor c_i → menor varianza de la view).
    """
    P = np.asarray(P, dtype=float)
    c = np.asarray(confidence_per_view, dtype=float).ravel()
    c = np.clip(c, 0.05, 1.0)
    S = np.asarray(Sigma, dtype=float) + ridge * np.eye(P.shape[1])
    base = np.diag(P @ S @ P.T)
    base = np.maximum(base, 1e-12)
    return np.diag(float(tau) * base / c)


def pick_matrix_absolute_views(tickers_ordered: list[str], view_tickers: list[str]) -> np.ndarray:
    """P (k × n): view i = retorno absoluto del activo view_tickers[i]."""
    n = len(tickers_ordered)
    idx_map = {t: j for j, t in enumerate(tickers_ordered)}
    rows: list[list[float]] = []
    for t in view_tickers:
        if t not in idx_map:
            raise ValueError(f"Ticker de view no está en universo: {t}")
        row = [0.0] * n
        row[idx_map[t]] = 1.0
        rows.append(row)
    return np.asarray(rows, dtype=float)


def black_litterman_posterior_mu(
    pi: np.ndarray,
    Sigma: np.ndarray,
    tau: float,
    P: np.ndarray,
    Q: np.ndarray,
    Omega: np.ndarray,
    *,
    ridge: float = 1e-10,
) -> np.ndarray:
    """
    Retorna μ_BL (vector n). Requiere Ω SPD (se regulariza con ridge en diagonal).
    """
    pi = np.asarray(pi, dtype=float).ravel()
    n = pi.shape[0]
    S = np.asarray(Sigma, dtype=float) + ridge * np.eye(n)
    TS = float(tau) * S
    P = np.asarray(P, dtype=float)
    Q = np.asarray(Q, dtype=float).ravel()
    k = P.shape[0]
    if Q.shape[0] != k:
        raise ValueError("Q debe tener longitud k = filas de P")
    Omega = np.asarray(Omega, dtype=float)
    if Omega.shape != (k, k):
        raise ValueError("Omega debe ser (k,k)")
    Omega_r = Omega + ridge * np.eye(k)

    inv_ts_pi = np.linalg.solve(TS, pi)
    o_inv_q = np.linalg.solve(Omega_r, Q)
    rhs = inv_ts_pi + P.T @ o_inv_q
    o_inv_p = np.linalg.solve(Omega_r, P)
    M = np.linalg.inv(TS) + P.T @ o_inv_p
    return np.linalg.solve(M, rhs)


@dataclass
class BlackLittermanResult:
    mu_prior: np.ndarray
    mu_posterior: np.ndarray
    P: np.ndarray
    Q: np.ndarray
    Omega: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


def black_litterman_with_absolute_views(
    mu_sample: np.ndarray,
    Sigma: np.ndarray,
    w_mkt: np.ndarray,
    tau: float,
    views: dict[str, float],
    tickers_ordered: list[str],
    *,
    omega_mode: str = "proportional",
    confidence: dict[str, float] | None = None,
    risk_aversion: float | None = None,
    ridge: float = 1e-10,
) -> BlackLittermanResult:
    """
    Flujo opinable: π desde δ implícita o explícita; views absolutas por ticker;
    Ω proporcional o con confianza por view.

    views: {ticker: retorno_esperado_anual_decimal}
    confidence: opcional {ticker: c_i en (0,1]}
    """
    if not views:
        tickers_ordered = list(tickers_ordered)
        w = np.asarray(w_mkt, dtype=float).ravel()
        w = w / max(w.sum(), 1e-12)
        delta = (
            float(risk_aversion)
            if risk_aversion is not None
            else risk_aversion_implied_from_mu_w(mu_sample, Sigma, w, ridge=ridge)
        )
        pi = implied_equilibrium_returns(Sigma, w, delta)
        return BlackLittermanResult(
            mu_prior=pi.copy(),
            mu_posterior=pi.copy(),
            P=np.zeros((0, len(tickers_ordered))),
            Q=np.zeros(0),
            Omega=np.zeros((0, 0)),
            metadata={"risk_aversion": delta, "no_views": True},
        )

    tickers_ordered = list(tickers_ordered)
    view_keys = [t for t in views if t in tickers_ordered]
    if not view_keys:
        raise ValueError("Ningún ticker de views está en tickers_ordered")
    P = pick_matrix_absolute_views(tickers_ordered, view_keys)
    Q = np.array([float(views[t]) for t in view_keys], dtype=float)
    w = np.asarray(w_mkt, dtype=float).ravel()
    w = w / max(w.sum(), 1e-12)
    delta = (
        float(risk_aversion)
        if risk_aversion is not None
        else risk_aversion_implied_from_mu_w(mu_sample, Sigma, w, ridge=ridge)
    )
    pi = implied_equilibrium_returns(Sigma, w, delta)

    if omega_mode == "proportional":
        Omega = omega_proportional_psigma_pt(tau, P, Sigma, scale=1.0, ridge=ridge)
    elif omega_mode == "confidence":
        conf = confidence or {}
        c_list = [float(conf.get(t, 0.5)) for t in view_keys]
        Omega = omega_diagonal_from_confidence(
            P, Sigma, tau, np.array(c_list), ridge=ridge
        )
    else:
        raise ValueError("omega_mode debe ser 'proportional' o 'confidence'")

    mu_bl = black_litterman_posterior_mu(pi, Sigma, tau, P, Q, Omega, ridge=ridge)
    return BlackLittermanResult(
        mu_prior=pi,
        mu_posterior=mu_bl,
        P=P,
        Q=Q,
        Omega=Omega,
        metadata={
            "risk_aversion": delta,
            "omega_mode": omega_mode,
            "view_tickers": view_keys,
        },
    )
