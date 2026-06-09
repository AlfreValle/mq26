from __future__ import annotations

import pandas as pd

from services.iol_api.backtest_lab import (
    build_named_strategies,
    long_flat_roundtrip_stats,
    report_capital_window,
)


def test_roundtrip_uptrend_one_trade():
    c = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
    pos = pd.Series([0.0, 1.0, 1.0, 1.0, 0.0], index=c.index)
    n_tr, n_win, d_exp, d_gan = long_flat_roundtrip_stats(c, pos, commission_pct=0.0)
    assert n_tr == 1
    assert n_win == 1
    assert d_exp >= 1


def test_report_capital_window():
    c = pd.Series([100.0 + i * 0.5 for i in range(80)])
    pos = build_named_strategies(c)["ma_cross_10_30"]
    r = report_capital_window(c, pos, ventana_dias=80, estrategia="ma_cross_10_30", capital_inicial_ars=100_000.0, commission_pct=0.0)
    assert r.capital_inicial_ars == 100_000.0
    assert r.capital_final_ars > 0
