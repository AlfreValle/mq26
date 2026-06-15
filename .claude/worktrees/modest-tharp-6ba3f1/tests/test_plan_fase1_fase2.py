"""Tests Fase 1–2 del plan 100 mejoras (BL+TE, lineage, jobs, API, OTel noop)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.black_litterman import (
    black_litterman_posterior_mu,
    black_litterman_with_absolute_views,
    implied_equilibrium_returns,
)
from core.export_lineage import build_export_manifest, digest_inputs, wrap_payload_with_lineage
from core.otel_tracing import get_tracer, span
from core.portfolio_optimization import (
    OptimizationProblem,
    solve_black_litterman_max_sharpe,
    solve_max_return_tracking_error,
)
from core.rbac_audit import audit_optimization_run, get_effective_role, require_role


def test_implied_pi_and_bl_posterior():
    n = 3
    Sigma = np.eye(n) * 0.04 + 0.01 * (1 - np.eye(n))
    w = np.ones(n) / n
    pi = implied_equilibrium_returns(Sigma, w, risk_aversion=2.5)
    assert pi.shape == (n,)
    P = np.array([[1.0, 0.0, 0.0]])
    Q = np.array([0.25])
    Omega = np.eye(1) * 0.0001
    mu_bl = black_litterman_posterior_mu(pi, Sigma, 0.05, P, Q, Omega, ridge=1e-8)
    assert mu_bl.shape == (n,)


def test_bl_with_views_changes_first_asset():
    tickers = ["A0", "A1", "A2"]
    n = 3
    Sigma = np.eye(n) * 0.04 + 0.005
    mu = np.array([0.07, 0.07, 0.07])
    w = np.ones(n) / n
    out = black_litterman_with_absolute_views(
        mu,
        Sigma,
        w,
        tau=0.05,
        views={"A0": 0.30},
        tickers_ordered=tickers,
        omega_mode="proportional",
        risk_aversion=2.5,
    )
    assert out.mu_posterior[0] >= out.mu_prior[0] - 1e-4


def test_te_constraint_feasible():
    rng = np.random.default_rng(0)
    n = 4
    r = rng.normal(0.0004, 0.012, (400, n))
    Sigma = np.cov(r.T, bias=False) * 252
    mu = r.mean(axis=0) * 252
    b = np.ones(n) / n
    prob = OptimizationProblem(mu=mu, Sigma=Sigma, rf=0.0, long_only=True, ridge=1e-7)
    res = solve_max_return_tracking_error(prob, b, te_max_annual=0.12)
    assert res.success
    d = res.weights - b
    te = float(np.sqrt(max(d @ Sigma @ d, 0.0)))
    assert te <= 0.12 + 0.02


def test_bl_then_max_sharpe():
    n = 3
    Sigma = np.eye(n) * 0.05 + 0.01
    mu_bl = np.array([0.12, 0.08, 0.09])
    res = solve_black_litterman_max_sharpe(mu_bl, Sigma, rf=0.02, long_only=True)
    assert res.success
    assert res.weights.sum() == pytest.approx(1.0)


def test_export_lineage_wrap():
    man = build_export_manifest(
        optimization_method="mv",
        inputs_digest=digest_inputs(mu=[1, 2], n=2),
        parameters={"tau": 0.05},
        tickers=["A", "B"],
    )
    wrapped = wrap_payload_with_lineage({"w": [0.5, 0.5]}, man)
    assert "_lineage" in wrapped
    assert "manifest_sha256" in wrapped["_lineage"]


def test_rbac_require_role():
    require_role({"mq_role": "admin"}, "analyst")
    with pytest.raises(PermissionError):
        require_role({"mq_role": "viewer"}, "admin")
    assert get_effective_role({}) == "analyst"


def test_optimization_jobs_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MQ26_OPT_JOBS_DB", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("MQ26_ARTIFACTS_DIR", str(tmp_path / "art"))
    import services.optimization_jobs as oj

    oj.init_schema()
    jid = oj.submit_job(
        "test",
        {
            "method": "unit",
            "inputs_digest": "x",
            "tickers": ["A", "B"],
            "user_id": "pytest",
        },
    )
    oj.process_job_sync(jid)
    final = oj.get_job(jid)
    assert final["status"] == "completed"
    assert final["artifact_path"] is not None
    assert Path(final["artifact_path"]).exists()


def test_audit_optimization_run_smoke():
    audit_optimization_run(
        job_id="test-job",
        method="mv",
        manifest_sha256="0" * 64,
        usuario="pytest",
        tenant_id=None,
    )


def test_otel_noop():
    t = get_tracer("test")
    with span("op", x=1):
        pass
    with t.start_as_current_span("n", attributes={"a": 1}) as _s:
        pass


def test_risk_engine_bl_and_te():
    import sys

    motor = Path(__file__).resolve().parent.parent / "1_Scripts_Motor"
    sys.path.insert(0, str(motor))
    from risk_engine import RiskEngine  # noqa: E402

    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=120, freq="B")
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0003, 0.01, (120, 3)), axis=0),
        index=idx,
        columns=["AAA", "BBB", "CCC"],
    )
    eng = RiskEngine(prices)
    w = eng.optimizar_black_litterman(views=None, tau=0.05)
    assert isinstance(w, dict) and sum(w.values()) == pytest.approx(1.0, abs=0.02)
    w2 = eng.optimizar_black_litterman(views={"AAA": (0.20, 0.8)}, tau=0.05)
    assert isinstance(w2, dict)
    w3 = eng.optimizar_max_retorno_te(te_max=0.15)
    assert isinstance(w3, dict)


def test_fastapi_optimization_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MQ26_OPT_JOBS_DB", str(tmp_path / "jobs_api.db"))
    monkeypatch.setenv("MQ26_ARTIFACTS_DIR", str(tmp_path / "art_api"))
    import services.optimization_jobs as oj

    oj.init_schema()

    from api.optimization_app import app

    c = TestClient(app)
    r = c.post("/jobs/optimization", json={"job_type": "x", "payload": {"method": "api"}})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    r2 = c.post(f"/jobs/optimization/{jid}/run")
    assert r2.status_code == 200
    r3 = c.get(f"/jobs/optimization/{jid}")
    assert r3.status_code == 200
    assert r3.json()["status"] == "completed"
