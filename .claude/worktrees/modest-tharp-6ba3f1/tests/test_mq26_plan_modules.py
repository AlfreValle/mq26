"""Tests agrupados — entregables plan F2/F3 (módulos nuevos, sin red)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_optimize_payload_typedict():
    from core.api_contracts import OptimizePayloadTD

    p: OptimizePayloadTD = {"tickers": ["A"], "rf": 0.03}
    assert p["tickers"] == ["A"]


def test_optimization_cache_fingerprint_stable():
    from services.optimization_service import optimization_cache_fingerprint

    a = optimization_cache_fingerprint({"tickers": ["Z", "A"], "mu": [1.0, 2.0]})
    b = optimization_cache_fingerprint({"tickers": ["Z", "A"], "mu": [1.0, 2.0]})
    assert a == b
    c = optimization_cache_fingerprint({"tickers": ["Z", "A"], "mu": [1.0, 2.0], "secret": "x"})
    assert c == a


def test_latency_measure_records():
    from services.latency_metrics import measure, reset_metrics, snapshot

    reset_metrics()
    with measure("op_ms"):
        pass
    snap = snapshot()
    assert "op_ms" in snap
    assert snap["op_ms"]["count"] >= 1.0


def test_hrp_weights_simplex():
    from core.hrp_weights import hrp_weights

    rng = np.random.default_rng(0)
    n = 3
    x = rng.standard_normal((n, 60))
    cov = np.cov(x)
    w = hrp_weights(cov)
    assert w.shape == (n,)
    assert np.all(w >= -1e-9)
    assert w.sum() == pytest.approx(1.0, abs=1e-5)


def test_corporate_jump_detects_spike():
    from core.corporate_actions_proxy import detect_price_jumps

    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    s = pd.Series([100.0, 101.0, 140.0, 141.0, 142.0], index=idx)
    rep = detect_price_jumps(s, threshold=0.25)
    assert len(rep.flagged_dates) >= 1


def test_after_tax_reduces_magnitude():
    from core.after_tax import adjust_returns_net_of_costs

    r = np.array([0.01, -0.02, 0.03])
    net = adjust_returns_net_of_costs(r, commission_bps=100.0)
    assert float(np.sum(net)) < float(np.sum(r))


def test_deflated_sharpe_penalizes_trials():
    from core.deflated_sharpe import deflated_sharpe_ratio

    raw = 2.0
    d = deflated_sharpe_ratio(raw, n_observations=120, n_trials=50)
    assert d < raw


def test_sox_light_bundle():
    from core.export_lineage import build_export_manifest
    from core.sox_export import build_sox_light_bundle

    m = build_export_manifest(
        optimization_method="mv",
        inputs_digest="abc",
        parameters={},
        tickers=["A"],
        user_id="u",
    )
    b = build_sox_light_bundle(m)
    assert b["checklist"]["lineage_manifest_present"] is True


def test_multiperiod_turnover_cap():
    from core.multiperiod_opt import two_stage_rebalance

    w0 = np.array([0.5, 0.5])
    w1 = np.array([1.0, 0.0])
    w = two_stage_rebalance(w0, w1, turnover_cap=0.1)
    assert w.sum() == pytest.approx(1.0)
    assert np.all(w >= 0)


def test_hypothesis_tstat():
    from core.hypothesis_metrics import excess_return_tstat

    a = np.linspace(0.001, 0.004, 30)
    b = np.zeros(30)
    t = excess_return_tstat(a, b)
    assert t > 0


def test_workflow_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("MQ26_WORKFLOW_DB", str(tmp_path / "wf.db"))
    from core.workflow_draft_publish import (
        create_entity,
        get_entity,
        init_workflow_schema,
        transition_state,
    )

    init_workflow_schema()
    eid = create_entity("portfolio", {"name": "p1"})
    transition_state(eid, "review")
    ent = get_entity(eid)
    assert ent["state"] == "review"
    transition_state(eid, "published")
    assert get_entity(eid)["state"] == "published"


def test_port_like_hhi():
    from services.port_like_report import build_port_style_summary

    df = pd.DataFrame(
        {
            "TICKER": ["A", "B"],
            "PRECIO_ARS": [100.0, 100.0],
            "CANTIDAD": [1.0, 1.0],
        }
    )
    s = build_port_style_summary(df)
    assert s["n_positions"] == 2
    assert s["hhi"] == pytest.approx(0.5, abs=0.01)


def test_risk_engine_hrp():
    import sys
    from pathlib import Path

    motor = Path(__file__).resolve().parent.parent / "1_Scripts_Motor"
    sys.path.insert(0, str(motor))
    from risk_engine import RiskEngine  # noqa: E402

    rng = np.random.default_rng(7)
    idx = pd.date_range("2023-01-01", periods=80, freq="B")
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0002, 0.012, (80, 3)), axis=0),
        index=idx,
        columns=["X", "Y", "Z"],
    )
    eng = RiskEngine(prices)
    w = eng.optimizar_hrp()
    assert isinstance(w, dict)
    assert sum(w.values()) == pytest.approx(1.0, abs=0.02)


def test_secrets_and_consent_and_byma_flag(monkeypatch):
    import importlib

    from core.consent_law_25326 import ConsentRecord25326
    from core.secrets_rotation import list_expected_secret_env_keys, secret_env_documented

    assert "MQ26_PASSWORD" in list_expected_secret_env_keys()
    assert secret_env_documented("MQ26_PASSWORD") is True
    rec = ConsentRecord25326.create("u1", "analytics", True)
    assert rec.accepted is True
    monkeypatch.setenv("MQ26_BYMA_FIRST", "1")
    import core.data_providers as dp

    importlib.reload(dp)
    assert dp.BYMA_FIRST is True


def test_optimization_smoke_timing_h09():
    """H09 — smoke: optimización pequeña termina en tiempo razonable."""
    import time

    from services.optimization_service import run_optimize

    mu = [0.07] * 5
    sigma = np.eye(5) * 0.04 + np.ones((5, 5)) * 0.005
    t0 = time.perf_counter()
    out = run_optimize(
        {
            "tickers": [f"T{i}" for i in range(5)],
            "mu": mu,
            "Sigma": sigma.tolist(),
        }
    )
    elapsed = time.perf_counter() - t0
    assert out["success"] is True
    assert elapsed < 5.0
