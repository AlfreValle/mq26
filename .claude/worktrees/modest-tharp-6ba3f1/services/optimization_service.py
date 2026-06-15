"""
F01 — Servicio puro de optimización (sin Streamlit).

Expone ``run_optimize`` serializable para FastAPI, jobs y tests.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from core.export_lineage import digest_inputs, stable_json_dumps
from core.portfolio_optimization import OptimizationProblem, solve_minimum_variance


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
    Ejecuta mínima varianza con μ y Σ en el payload, o demo 3×3.

    Retorna dict JSON-friendly: pesos, métricas mínimas, meta (firma de input).
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

    rf = float(payload.get("rf", 0.0))
    long_only = bool(payload.get("long_only", True))
    prob = OptimizationProblem(mu=mu, Sigma=Sigma, rf=rf, long_only=long_only)
    res = solve_minimum_variance(prob)
    w = res.weights
    vol = float(np.sqrt(w @ prob.Sigma @ w))
    ret = float(w @ mu)

    return {
        "success": bool(res.success),
        "weights": {t: float(x) for t, x in zip(tickers, w, strict=True)},
        "metrics": {
            "expected_return": ret,
            "portfolio_vol": vol,
        },
        "message": res.message,
        "meta": meta,
        "raw": {"method": res.method},
    }


def run_optimize_json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Igual que ``run_optimize`` pero garantiza tipos serializables (debug)."""
    out = run_optimize(payload)
    stable_json_dumps(out)
    return out
