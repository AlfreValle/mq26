from __future__ import annotations

import numpy as np
import pandas as pd

from services.iol_api.backtest_lab import (
    _positions_ma_cross,
    build_named_strategies,
    compare_strategies,
    fit_regime_router_walk_forward,
    simulate_positions,
    walk_forward_oos_grid,
)


def _trending_close(n: int = 200) -> pd.Series:
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(np.linspace(100.0, 200.0, n), index=idx)


def test_simulate_positions_long_flat_no_crash():
    c = _trending_close(120)
    pos = _positions_ma_cross(c, 5, 20)
    r = simulate_positions(c, pos, commission_pct=0.0, mode="long_flat")
    assert r.n_bars == 120
    assert -1.0 <= r.max_drawdown <= 0.0
    assert isinstance(r.equity.iloc[-1], float)


def test_compare_strategies_ordering():
    c = _trending_close(200)
    df = compare_strategies(c, commission_pct=0.0, mode="long_flat")
    assert "estrategia" in df.columns
    assert len(df) == len(build_named_strategies(c))
    assert df["sharpe"].notna().all()
    for col in (
        "profit_factor",
        "calmar",
        "skew_net",
        "kurtosis_net",
        "cvar95_daily",
    ):
        assert col in df.columns
        assert df[col].notna().all()


def test_walk_forward_oos_grid_rows():
    c = _trending_close(400)
    df = walk_forward_oos_grid(
        c, train_ratios=[0.55, 0.7], commission_pct=0.0, mode="long_flat"
    )
    assert len(df) == 2
    assert set(df["train_ratio"].tolist()) == {0.55, 0.7}
    assert "oos_sharpe_router" in df.columns


def test_router_returns_result_keys():
    c = _trending_close(300)
    out = fit_regime_router_walk_forward(c, train_ratio=0.6, commission_pct=0.0)
    assert hasattr(out, "regime_to_strategy")
    assert hasattr(out, "default_strategy")
    assert isinstance(out.default_strategy, str)
    assert hasattr(out, "oos_sharpe_router")
    assert isinstance(out.oos_sharpe_best_single, float)
