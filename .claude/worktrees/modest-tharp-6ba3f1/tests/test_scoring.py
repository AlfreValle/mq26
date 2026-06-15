"""Tests para calcular_indicadores_cartera() — Sprint 2 T-2.2"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_ticker(pe=20.0, ps=3.0, roe=0.18, roa=0.09, dy=0.02):
    info = {
        "trailingPE": pe,
        "priceToSalesTrailing12Months": ps,
        "returnOnEquity": roe,
        "returnOnAssets": roa,
        "dividendYield": dy,
    }
    m = MagicMock()
    m.info = info
    return m


def test_calcular_indicadores_retorna_5_keys():
    with patch("services.scoring_engine.yf.Ticker", return_value=_mock_ticker()):
        from services.scoring_engine import calcular_indicadores_cartera
        result = calcular_indicadores_cartera({"AAPL": 0.5, "MSFT": 0.5})
    assert set(result.keys()) == {"per_w", "ps_w", "roe_w", "roa_w", "dividend_yield_w"}


def test_calcular_indicadores_valores_numericos():
    with patch("services.scoring_engine.yf.Ticker", return_value=_mock_ticker(pe=25.0, dy=0.03)):
        from services.scoring_engine import calcular_indicadores_cartera
        result = calcular_indicadores_cartera({"AAPL": 1.0})
    assert result["per_w"] == pytest.approx(25.0, rel=1e-4)
    assert result["dividend_yield_w"] == pytest.approx(0.03, rel=1e-4)


def test_calcular_indicadores_pesos_ponderados():
    tickers_info = {"AAA": _mock_ticker(pe=10.0), "BBB": _mock_ticker(pe=30.0)}

    def mock_factory(ticker):
        return tickers_info[ticker]

    with patch("services.scoring_engine.yf.Ticker", side_effect=mock_factory):
        from services.scoring_engine import calcular_indicadores_cartera
        result = calcular_indicadores_cartera({"AAA": 0.5, "BBB": 0.5})
    assert result["per_w"] == pytest.approx(20.0, rel=1e-4)


def test_calcular_indicadores_tolerante_a_none():
    m = MagicMock()
    m.info = {}
    with patch("services.scoring_engine.yf.Ticker", return_value=m):
        from services.scoring_engine import calcular_indicadores_cartera
        result = calcular_indicadores_cartera({"UNKNOWN": 1.0})
    assert all(v == 0.0 for v in result.values())


def test_calcular_indicadores_pesos_vacios():
    from services.scoring_engine import calcular_indicadores_cartera
    result = calcular_indicadores_cartera({})
    assert result["per_w"] == 0.0
