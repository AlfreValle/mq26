"""
F01 — Servicio puro de optimización (sin Streamlit).

Expone ``run_optimize`` serializable para FastAPI, jobs y tests.

Parámetros de payload reconocidos:
  tickers        : list[str]
  mu             : list[float]           — retornos esperados anualizados
  Sigma          : list[list[float]]     — covarianza anualizada
  rf             : float                 — tasa libre de riesgo (default 0.0)
  long_only      : bool                  — solo posiciones largas (default True)
  method         : str                   — "minimum_variance" | "max_sharpe" (default min_var)
  cvar_max       : float | null          — CVaR diario máximo (ej. 0.03 = 3 %)
  cvar_alpha     : float                 — nivel de cola para CVaR (default 0.05)
  returns        : list[list[float]]     — retornos históricos (T×n) para CVaR constraint
"""
from __future__ import annotations

from typing import Any

import numpy as np

from core.export_lineage import digest_inputs, stable_json_dumps
from core.portfolio_optimization import (
    OptimizationProblem,
    calcular_cvar,
    solve_max_sharpe,
    solve_minimum_variance,
)


def optimization_cache_fingerprint(payload: dict[str, Any]) -> str:
    """
    F02 — Firma determinista del input de optimización (clave de caché lógica).

    Excluye claves efímeras: secret, user_id, tenant_id, job_id.
    """
    skip = frozenset({"secret", "user_id", "tenant_id", "job_id", "request_id"})
    lean = {k: v for k, v in sorted(payload.items()) if k not in skip}
    return digest_inputs(payload=lean)


def run_optimize(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Ejecuta optimización con μ y Σ en el payload, o demo 3×3.

    Soporta restricción CVaR si se proveen 'cvar_max' y 'returns' en el payload.
    Retorna dict JSON-friendly: pesos, métricas, cvar_achieved (si aplica), meta.
    """
    meta = {
        "cache_fingerprint": optimization_cache_fingerprint(payload),
        "method": str(payload.get("method", "minimum_variance")),
    }

    tickers = list(payload.get("tickers") or [])
    if "Sigma" in payload and "mu" in payload:
        Sigma = np.asarray(payload["Sigma"], dtype=float)
        mu = np.asarray(payload["mu"], dtype=float).ravel()
    else:
        Sigma = np.array([[0.04, 0.01, 0.0], [0.01, 0.06, 0.01], [0.0, 0.01, 0.05]])
        mu = np.array([0.08, 0.10, 0.07])
        if not tickers:
            tickers = [f"A{i}" for i in range(len(mu))]

    if Sigma.shape[0] != len(mu):
        return {
            "success": False,
            "error": "Sigma y mu incompatibles",
            "weights": {},
            "meta": meta,
        }

    n = len(mu)
    if len(tickers) != n:
        tickers = [f"T{i}" for i in range(n)]

    rf         = float(payload.get("rf", 0.0))
    long_only  = bool(payload.get("long_only", True))
    cvar_max   = payload.get("cvar_max")
    cvar_alpha = float(payload.get("cvar_alpha", 0.05))

    returns_history: np.ndarray | None = None
    if cvar_max is not None and "returns" in payload:
        try:
            rh = np.asarray(payload["returns"], dtype=float)
            if rh.ndim == 2 and rh.shape[1] == n:
                returns_history = rh
            else:
                meta["cvar_warning"] = f"returns shape {rh.shape} incompatible con n={n} — CVaR omitido"
                cvar_max = None
        except Exception as exc:
            meta["cvar_warning"] = f"returns inválidos: {exc} — CVaR omitido"
            cvar_max = None

    prob = OptimizationProblem(
        mu=mu,
        Sigma=Sigma,
        rf=rf,
        long_only=long_only,
        cvar_max=float(cvar_max) if cvar_max is not None else None,
        returns_history=returns_history,
        cvar_alpha=cvar_alpha,
    )

    method = str(payload.get("method", "minimum_variance")).lower()
    if method == "max_sharpe":
        res = solve_max_sharpe(prob)
    else:
        res = solve_minimum_variance(prob)

    w   = res.weights
    vol = float(np.sqrt(max(w @ prob.Sigma @ w, 0.0)))
    ret = float(w @ mu)

    metrics: dict[str, Any] = {
        "expected_return": ret,
        "portfolio_vol": vol,
    }
    if "cvar_achieved" in res.metadata:
        metrics["cvar_achieved"] = float(res.metadata["cvar_achieved"])
        metrics["cvar_max"]      = float(res.metadata["cvar_max"])
        metrics["cvar_alpha"]    = cvar_alpha
    elif returns_history is not None:
        metrics["cvar_achieved"] = calcular_cvar(returns_history @ w, cvar_alpha)

    return {
        "success": bool(res.success),
        "weights": {t: float(x) for t, x in zip(tickers, w, strict=True)},
        "metrics": metrics,
        "message": res.message,
        "meta": meta,
        "raw": {"method": res.method},
    }


def run_optimize_json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Igual que ``run_optimize`` pero garantiza tipos serializables (debug)."""
    out = run_optimize(payload)
    stable_json_dumps(out)
    return out
