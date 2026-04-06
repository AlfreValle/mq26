"""H81–H82: tests reproducibles del núcleo Fase 0 (credibilidad mínima)."""
import numpy as np
import pandas as pd
import pytest

from core.data_lineage import (
    DATA_CATALOG,
    align_calendar_hint,
    validate_returns_na,
)
from core.evaluation_oos import (
    compare_to_naive_benchmark,
    metrics_from_returns,
    naive_one_over_n_weights,
    temporal_train_test_split,
)
from core.portfolio_optimization import (
    OptimizationProblem,
    estimate_mu_sigma_mle,
    solve_equal_risk_contribution,
    solve_max_sharpe,
    solve_minimum_variance,
)
from core.rbac_audit import audit_param_change, get_effective_role, require_can_edit_optimization_params
from core.risk_metrics import (
    factor_betas_ols,
    historical_var_cvar,
    max_drawdown_from_returns,
    portfolio_vol_annual,
)


def test_estimate_and_mv_sums_to_one_and_positive():
    rng = np.random.default_rng(42)
    T, n = 200, 5
    r = rng.normal(0.0005, 0.015, size=(T, n))
    mu, Sigma = estimate_mu_sigma_mle(r, annualization=252, ledoit_wolf=False)
    prob = OptimizationProblem(mu=mu, Sigma=Sigma, rf=0.0, long_only=True)
    res = solve_minimum_variance(prob)
    assert res.success
    w = res.weights
    assert np.isclose(w.sum(), 1.0)
    assert (w >= -1e-9).all()


def test_erc_and_max_sharpe_bounded():
    rng = np.random.default_rng(7)
    T, n = 300, 4
    r = rng.normal(0.0003, 0.012, size=(T, n))
    mu, Sigma = estimate_mu_sigma_mle(r, annualization=252, ledoit_wolf=False)
    prob = OptimizationProblem(mu=mu, Sigma=Sigma, rf=0.02, long_only=True)
    erc = solve_equal_risk_contribution(prob)
    assert erc.weights.sum() == pytest.approx(1.0)
    assert (erc.weights >= 0).all()
    ms = solve_max_sharpe(prob)
    assert ms.weights.sum() == pytest.approx(1.0)
    assert (ms.weights >= -1e-8).all()


def test_risk_metrics_and_betas():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.01, 500)
    var, cvar = historical_var_cvar(r, alpha=0.05)
    assert var >= 0 and cvar >= var - 1e-6
    mdd = max_drawdown_from_returns(r)
    assert mdd <= 0
    n = 3
    Sigma = np.eye(n) * 0.04 + 0.01
    w = np.ones(n) / n
    vol = portfolio_vol_annual(w, Sigma)
    assert vol > 0
    T = 400
    mkt = rng.normal(0.0004, 0.012, T)
    eps = rng.normal(0, 0.008, (T, n))
    y = 0.5 * mkt.reshape(-1, 1) + eps
    betas, r2m = factor_betas_ols(y, mkt)
    assert betas.shape == (n,)
    assert 0 <= r2m <= 1


def test_oos_split_and_benchmark():
    rng = np.random.default_rng(99)
    idx = pd.date_range("2020-01-01", periods=100, freq="B")
    tickers = ["A", "B", "C"]
    d = pd.DataFrame(rng.normal(0.0002, 0.01, (100, 3)), index=idx, columns=tickers)
    tr, te = temporal_train_test_split(d, train_fraction=0.7)
    assert len(tr) + len(te) == len(d)
    assert tr.index.max() < te.index.min()
    w = naive_one_over_n_weights(3)
    cmp = compare_to_naive_benchmark(d, w * 1.5, tickers)
    assert "optimized" in cmp and "naive_1n" in cmp
    m = metrics_from_returns(d @ w)
    assert "sharpe" in m


def test_lineage_validation():
    assert "yfinance_eod" in DATA_CATALOG
    df = pd.DataFrame({"a": [0.01, np.nan, 0.02], "b": [0.0, 0.0, 0.0]})
    ok, issues = validate_returns_na(df, max_na_fraction_per_column=0.5)
    assert ok or issues
    ny = pd.DataFrame({"x": [1]}, index=pd.to_datetime(["2024-01-02"]))
    loc = pd.DataFrame({"x": [1]}, index=pd.to_datetime(["2024-01-02"]))
    h = align_calendar_hint(ny, loc)
    assert h["intersection"] == 1


def test_rbac_viewer_blocks_and_audit_smoke():
    assert get_effective_role({}) == "analyst"
    assert get_effective_role({"mq_role": "viewer"}) == "viewer"
    with pytest.raises(PermissionError):
        require_can_edit_optimization_params({"mq_role": "viewer"})
    audit_param_change("test_key", "0", "1", usuario="pytest")


def test_reproducibility_same_seed():
    rng = np.random.default_rng(123)
    r = rng.normal(0.0004, 0.014, (250, 3))
    mu, Sigma = estimate_mu_sigma_mle(r, annualization=252, ledoit_wolf=False)
    w1 = solve_minimum_variance(OptimizationProblem(mu=mu, Sigma=Sigma)).weights
    rng = np.random.default_rng(123)
    r2 = rng.normal(0.0004, 0.014, (250, 3))
    mu2, Sigma2 = estimate_mu_sigma_mle(r2, annualization=252, ledoit_wolf=False)
    w2 = solve_minimum_variance(OptimizationProblem(mu=mu2, Sigma=Sigma2)).weights
    np.testing.assert_allclose(w1, w2)
