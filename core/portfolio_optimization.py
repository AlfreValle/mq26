"""
core/portfolio_optimization.py — Núcleo de optimización de cartera (Fase 0, ítems A1–A5).

Contrato:
- **Estimación** (μ, Σ) separada de **solvers** (pesos).
- Solvers puros NumPy/SciPy, sin Streamlit.

Invariantes:
- Pesos de salida en R^n, sum(w)=1, long-only opcional.
- Σ se regulariza con ridge numérico si hace falta para estabilidad.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import minimize

# ─── Contratos (A1) ───────────────────────────────────────────────────────────


@dataclass
class OptimizationProblem:
    """Problema listo para optimizar: μ anual o por el mismo paso que Σ."""
    mu: np.ndarray
    Sigma: np.ndarray
    rf: float = 0.0
    long_only: bool = True
    ridge: float = 1e-8

    def __post_init__(self) -> None:
        self.mu = np.asarray(self.mu, dtype=float).ravel()
        self.Sigma = np.asarray(self.Sigma, dtype=float)
        n = self.mu.shape[0]
        if self.Sigma.shape != (n, n):
            raise ValueError("Sigma debe ser (n,n) y mu (n,)")


@dataclass
class OptimizationResult:
    weights: np.ndarray
    method: str
    success: bool
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def regularize_sigma(Sigma: np.ndarray, ridge: float) -> np.ndarray:
    s = np.asarray(Sigma, dtype=float)
    n = s.shape[0]
    return s + ridge * np.eye(n)


def estimate_mu_sigma_mle(
    returns: np.ndarray,
    *,
    annualization: int = 252,
    ledoit_wolf: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Estimación clásica de μ y Σ a partir de retornos (T × n).
    μ anualizado; Σ como covarianza anual de retornos.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2 or r.shape[0] < 2:
        raise ValueError("returns debe ser (T,n) con T>=2")
    mu = r.mean(axis=0) * annualization
    if ledoit_wolf:
        try:
            from sklearn.covariance import LedoitWolf

            cov = LedoitWolf().fit(r).covariance_
            Sigma = cov * annualization
        except Exception:
            Sigma = np.cov(r.T, bias=False) * annualization
    else:
        Sigma = np.cov(r.T, bias=False) * annualization
    return mu, Sigma


def solve_minimum_variance(
    problem: OptimizationProblem,
) -> OptimizationResult:
    """Mínima varianza con sum(w)=1 y caja [0,1] (A3)."""
    n = problem.mu.shape[0]
    S = regularize_sigma(problem.Sigma, problem.ridge)

    def objective(w: np.ndarray) -> float:
        return float(w @ S @ w)

    w0 = np.ones(n) / n
    cons = {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}
    bounds = [(0.0, 1.0) for _ in range(n)] if problem.long_only else None

    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=cons,
        options={"maxiter": 500, "ftol": 1e-10},
    )
    w = np.asarray(res.x, dtype=float)
    if w.sum() > 0:
        w = w / w.sum()
    return OptimizationResult(
        weights=w,
        method="minimum_variance_slsqp",
        success=bool(res.success),
        message=str(res.message),
        metadata={"fun": float(res.fun)},
    )


def solve_max_sharpe(
    problem: OptimizationProblem,
    *,
    w_prev: np.ndarray | None = None,
    lambda_turnover_penalty: float = 0.0,
    max_turnover_l1: float | None = None,
) -> OptimizationResult:
    """
    Max Sharpe (tangency) long-only, rf en la misma unidad que μ (A4).

    Penalización opcional (A11/A12): λ·Σ|wᵢ−wᵢᵖʳᵉᵛ| sumada al objetivo
    (minimizar −Sharpe + penalización). Restricción dura: Σ|w−w_prev| ≤ max_turnover_l1.
    """
    n = problem.mu.shape[0]
    S = regularize_sigma(problem.Sigma, problem.ridge)
    mu_ex = problem.mu - problem.rf
    wp = None if w_prev is None else np.asarray(w_prev, dtype=float).ravel()
    if wp is not None and wp.shape[0] != n:
        wp = None
    lam = float(lambda_turnover_penalty)

    def neg_sharpe(w: np.ndarray) -> float:
        w = np.maximum(w, 0.0)
        s = w.sum()
        if s <= 0:
            return 1e9
        w = w / s
        vol = float(np.sqrt(max(w @ S @ w, 1e-18)))
        ret = float(mu_ex @ w)
        if vol < 1e-12:
            return 1e9
        pen = 0.0
        if wp is not None and lam > 0:
            pen = lam * float(np.sum(np.abs(w - wp)))
        return -(ret / vol) + pen

    w0 = np.ones(n) / n
    cons: list = [{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}]
    if wp is not None and max_turnover_l1 is not None:
        mt = float(max_turnover_l1)
        cons.append({"type": "ineq", "fun": lambda w, _wp=wp, _mt=mt: _mt - float(np.sum(np.abs(w - _wp)))})
    bounds = [(0.0, 1.0) for _ in range(n)] if problem.long_only else None

    res = minimize(
        neg_sharpe,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=tuple(cons),
        options={"maxiter": 500, "ftol": 1e-10},
    )
    w = np.maximum(np.asarray(res.x, dtype=float), 0.0)
    if w.sum() > 0:
        w = w / w.sum()
    vol = float(np.sqrt(max(w @ S @ w, 1e-18)))
    ret = float((problem.mu @ w) - problem.rf * np.sum(w))
    sharpe = (ret / vol * np.sqrt(252)) if vol > 0 else 0.0
    return OptimizationResult(
        weights=w,
        method="max_sharpe_slsqp",
        success=bool(res.success),
        message=str(res.message),
        metadata={"vol_annual_est": vol, "sharpe_ann_hint": sharpe},
    )


def solve_equal_risk_contribution(
    problem: OptimizationProblem,
    *,
    max_iter: int = 500,
    tol: float = 1e-10,
) -> OptimizationResult:
    """
    ERC (aproximación por punto fijo habitual, A5).
    Requiere Σ bien condicionada; usa ridge del problema.
    """
    n = problem.mu.shape[0]
    S = regularize_sigma(problem.Sigma, max(problem.ridge, 1e-8))
    w = np.ones(n) / n

    for k in range(max_iter):
        sw = S @ w
        sw = np.maximum(sw, 1e-12)
        w_new = (1.0 / sw) / float(np.sum(1.0 / sw))
        if float(np.linalg.norm(w_new - w, 1)) < tol:
            w = w_new
            return OptimizationResult(
                weights=w / w.sum(),
                method="erc_fixed_point",
                success=True,
                message="converged",
                metadata={"iterations": k + 1},
            )
        w = w_new

    w = np.maximum(w, 0)
    return OptimizationResult(
        weights=w / w.sum(),
        method="erc_fixed_point",
        success=False,
        message="max_iter",
        metadata={"iterations": max_iter},
    )


def solve_max_return_tracking_error(
    problem: OptimizationProblem,
    w_benchmark: np.ndarray,
    te_max_annual: float,
    *,
    w_prev: np.ndarray | None = None,
    lambda_turnover_penalty: float = 0.0,
    max_turnover_l1: float | None = None,
) -> OptimizationResult:
    """
    Maximiza μ'w sujeto a sum w = 1, w ≥ 0 y (w - b)'Σ(w - b) ≤ TE² (A8).

    te_max_annual: tracking error anual del exceso de rentabilidad frente al benchmark,
    en la misma unidad que √(w'Σw) (p. ej. 0.05 = 5 % anual).
    """
    n = problem.mu.shape[0]
    S = regularize_sigma(problem.Sigma, problem.ridge)
    b = np.asarray(w_benchmark, dtype=float).ravel()
    b = b / max(b.sum(), 1e-12)
    te2 = float(te_max_annual) ** 2
    wp = None if w_prev is None else np.asarray(w_prev, dtype=float).ravel()
    if wp is not None and wp.shape[0] != n:
        wp = None
    lam = float(lambda_turnover_penalty)

    def neg_mu(w: np.ndarray) -> float:
        base = -float(problem.mu @ w)
        if wp is not None and lam > 0:
            base += lam * float(np.sum(np.abs(w - wp)))
        return base

    def te_slack(w: np.ndarray) -> float:
        d = w - b
        return float(te2 - (d @ S @ d))

    w0 = np.maximum(b, 1e-6)
    w0 = w0 / w0.sum()
    cons = [
        {"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},
        {"type": "ineq", "fun": te_slack},
    ]
    if wp is not None and max_turnover_l1 is not None:
        mt = float(max_turnover_l1)
        cons.append({"type": "ineq", "fun": lambda w, _wp=wp, _mt=mt: _mt - float(np.sum(np.abs(w - _wp)))})
    bounds = [(0.0, 1.0) for _ in range(n)] if problem.long_only else None

    res = minimize(
        neg_mu,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=tuple(cons),
        options={"maxiter": 800, "ftol": 1e-10},
    )
    w = np.maximum(np.asarray(res.x, dtype=float), 0.0)
    if w.sum() > 0:
        w = w / w.sum()
    d = w - b
    te_achieved = float(np.sqrt(max(d @ S @ d, 0.0)))
    return OptimizationResult(
        weights=w,
        method="max_return_te_constrained",
        success=bool(res.success),
        message=str(res.message),
        metadata={
            "tracking_error_annual": te_achieved,
            "te_budget": float(te_max_annual),
        },
    )


def solve_black_litterman_max_sharpe(
    mu_bl: np.ndarray,
    Sigma: np.ndarray,
    *,
    rf: float = 0.0,
    long_only: bool = True,
    ridge: float = 1e-8,
    w_prev: np.ndarray | None = None,
    lambda_turnover_penalty: float = 0.0,
    max_turnover_l1: float | None = None,
) -> OptimizationResult:
    """Optimiza max Sharpe usando retornos posteriores μ_BL (post Black–Litterman)."""
    prob = OptimizationProblem(
        mu=np.asarray(mu_bl, dtype=float).ravel(),
        Sigma=np.asarray(Sigma, dtype=float),
        rf=rf,
        long_only=long_only,
        ridge=ridge,
    )
    return solve_max_sharpe(
        prob,
        w_prev=w_prev,
        lambda_turnover_penalty=lambda_turnover_penalty,
        max_turnover_l1=max_turnover_l1,
    )
