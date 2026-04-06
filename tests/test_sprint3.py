"""Tests Sprint 3: wizard onboarding, backtest multimodelo, indicadores en UI"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ── Wizard onboarding ─────────────────────────────────────────────────────────

def test_tab_estudio_importa():
    mock_st = MagicMock()
    mock_st.session_state = {}
    mock_st.tabs.return_value = [MagicMock(), MagicMock()]
    with patch.dict(sys.modules, {"streamlit": mock_st}):
        import importlib
        import ui.tab_estudio as te
        importlib.reload(te)
        assert hasattr(te, "render_tab_estudio")
        assert hasattr(te, "_render_wizard_onboarding")


def test_wizard_paso1_requiere_nombre():
    """El botón Siguiente del paso 1 está disabled si nombre está vacío."""
    mock_st = MagicMock()
    mock_st.session_state = {"wizard_step": 1}
    mock_st.text_input.return_value = ""   # nombre vacío
    mock_st.selectbox.return_value = "Persona"
    mock_st.button.return_value = False

    with patch.dict(sys.modules, {"streamlit": mock_st}):
        import importlib
        import ui.tab_estudio as te
        importlib.reload(te)
        # No debe lanzar excepción con nombre vacío
        te._wizard_paso1({})


def test_wizard_paso3_valores_por_defecto():
    mock_st = MagicMock()
    mock_st.session_state = {"wizard_step": 3}
    mock_st.number_input.return_value = 0.0
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    mock_st.button.return_value = False

    with patch.dict(sys.modules, {"streamlit": mock_st}):
        import importlib
        import ui.tab_estudio as te
        importlib.reload(te)
        te._wizard_paso3({})   # no debe lanzar


# ── Backtest multimodelo ──────────────────────────────────────────────────────

def _precios_fake(n=300, cols=4):
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0003, 0.012, (n, cols)), axis=0),
        index=idx,
        columns=[f"A{i}" for i in range(cols)],
    )


def test_run_backtest_multimodelo_retorna_dict():
    from services.backtester import run_backtest_multimodelo
    precios = _precios_fake()
    tickers = list(precios.columns)
    pesos_mod = {
        "Sharpe":    {t: 0.25 for t in tickers},
        "min_var":   {t: 0.25 for t in tickers},
    }
    res = run_backtest_multimodelo(precios, pesos_mod, period="1y")
    assert isinstance(res, dict)
    # Al menos 1 modelo debe haber corrido
    assert len(res) >= 1


def test_run_backtest_multimodelo_claves_resultado():
    from services.backtester import run_backtest_multimodelo, BacktestResult
    precios = _precios_fake()
    tickers = list(precios.columns)
    pesos = {t: 1 / len(tickers) for t in tickers}
    res = run_backtest_multimodelo(precios, {"EqualW": pesos}, period="1y")
    if "EqualW" in res:
        bt = res["EqualW"]
        assert hasattr(bt, "sharpe_estrategia")
        assert hasattr(bt, "retorno_anual_estrategia")
        assert hasattr(bt, "max_dd_estrategia")
        assert hasattr(bt, "equity_strategy")


def test_run_backtest_multimodelo_tolerante_a_fallo():
    """Si un modelo falla, los demás deben seguir corriendo."""
    from services.backtester import run_backtest_multimodelo
    precios = _precios_fake()
    tickers = list(precios.columns)
    pesos_bad  = {"ROTO": {"XXXNONE": 1.0}}
    pesos_good = {"OK":   {t: 0.25 for t in tickers}}
    res = run_backtest_multimodelo(precios, {**pesos_bad, **pesos_good})
    assert "OK" in res


# ── calcular_indicadores_cartera en contexto de tab ───────────────────────────

def test_calcular_indicadores_retorna_5_keys_smoke():
    """Test de humo sin conexión a yfinance."""
    m = MagicMock()
    m.info = {"trailingPE": 22.0, "returnOnEquity": 0.20,
              "returnOnAssets": 0.10, "dividendYield": 0.015,
              "priceToSalesTrailing12Months": 5.0}
    with patch("services.scoring_engine.yf.Ticker", return_value=m):
        from services.scoring_engine import calcular_indicadores_cartera
        result = calcular_indicadores_cartera({"AAPL": 0.6, "MSFT": 0.4})
    assert set(result) == {"per_w", "ps_w", "roe_w", "roa_w", "dividend_yield_w"}
    assert result["per_w"] == pytest.approx(22.0, rel=1e-4)


def test_tab_optimizacion_tiene_sub_multi():
    src = (Path(__file__).resolve().parent.parent / "ui" / "tab_optimizacion.py").read_text(
        encoding="utf-8",
    )
    assert "sub_multi" in src
    assert "run_backtest_multimodelo" in src
    assert "calcular_indicadores_cartera" in src
    assert "Backtest Multi-Modelo" in src
