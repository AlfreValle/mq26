"""Sin red: yfinance mockeado."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from services.sp500_sector_panel import (
    BENCHMARK_TICKER,
    SP500_SECTOR_COLS,
    build_sp500_sector_panel,
)


def _mock_download(ticker: str, period: str = "", **kwargs):
    end = pd.Timestamp.utcnow().normalize()
    rng = pd.bdate_range(end=end, periods=280, tz="UTC")
    base = 100.0 + np.arange(len(rng)) * 0.05
    if ticker == "XLK":
        base = base * 1.02
    if ticker == BENCHMARK_TICKER:
        base = base * 0.99
    df = pd.DataFrame({"Close": base}, index=rng)
    return df


@pytest.fixture
def mock_ticker_info():
    def _Ticker(sym: str):
        m = MagicMock()
        info = {"forwardPE": 20.0, "dividendYield": 0.015}
        if sym == BENCHMARK_TICKER:
            info = {"forwardPE": 19.7, "dividendYield": 0.016}
        m.info = info
        return m

    return _Ticker


def test_build_panel_shape_and_spy_beta(mock_ticker_info):
    res = build_sp500_sector_panel(
        download_fn=_mock_download,
        ticker_fn=mock_ticker_info,
    )
    assert res.table.shape[0] == 6
    assert res.table.shape[1] == len(SP500_SECTOR_COLS) + 1
    assert "S&P 500" in res.table.columns
    assert res.table.loc["Beta vs SPY", "S&P 500"] == pytest.approx(1.0)
    assert res.table.loc["Peso en S&P 500 (%)", "S&P 500"] == pytest.approx(100.0)
    w = res.table.loc["Peso en S&P 500 (%)"]
    assert w.drop(labels="S&P 500").sum() == pytest.approx(100.0, rel=0, abs=0.2)


def test_returns_numeric(mock_ticker_info):
    res = build_sp500_sector_panel(
        download_fn=_mock_download,
        ticker_fn=mock_ticker_info,
    )
    q = res.table.loc["Retorno QTD (%)", "Tecnología"]
    y = res.table.loc["Retorno YTD (%)", "Tecnología"]
    assert q is not None and isinstance(q, (int, float))
    assert y is not None and isinstance(y, (int, float))
