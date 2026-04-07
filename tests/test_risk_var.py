"""
tests/test_risk_var.py — Tests de calcular_var_cvar (Sprint 24)
Sin red: mock streamlit/plotly; se parchea services.risk_var.cache_yfinance_close_matrix.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture(autouse=True)
def clear_streamlit_cache_risk_var():
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def mock_streamlit_plotly_risk_var():
    prev_st = sys.modules.get("streamlit")
    prev_plotly = sys.modules.get("plotly")
    prev_pgo = sys.modules.get("plotly.graph_objects")

    sys.modules["streamlit"] = MagicMock()
    mock_pgo = MagicMock()
    mock_plotly = MagicMock()
    mock_plotly.graph_objects = mock_pgo
    sys.modules["plotly"] = mock_plotly
    sys.modules["plotly.graph_objects"] = mock_pgo

    sys.modules.pop("services.risk_var", None)
    yield
    sys.modules.pop("services.risk_var", None)
    if prev_st is not None:
        sys.modules["streamlit"] = prev_st
    else:
        sys.modules.pop("streamlit", None)
    if prev_plotly is not None:
        sys.modules["plotly"] = prev_plotly
    else:
        sys.modules.pop("plotly", None)
    if prev_pgo is not None:
        sys.modules["plotly.graph_objects"] = prev_pgo
    else:
        sys.modules.pop("plotly.graph_objects", None)


@pytest.fixture
def precios_historicos_mock():
    """Close multi-ticker, índice B, ≥40 filas para pct_change ≥30 (columnas planas como cache_yfinance)."""
    idx = pd.date_range("2023-01-03", periods=45, freq="B")
    rng = np.random.default_rng(42)
    rets_a = rng.normal(0, 0.02, len(idx))
    rets_b = rng.normal(0, 0.015, len(idx))
    px_a = 100 * np.cumprod(1 + rets_a)
    px_b = 200 * np.cumprod(1 + rets_b)
    return pd.DataFrame(
        np.column_stack([px_a, px_b]), index=idx, columns=["AAPL", "MSFT"]
    )


def _import_risk_var():
    import services.risk_var as rv
    return rv


class TestCalcularVarCvar:
    def test_valor_total_cero_retorna_vacio(self, precios_historicos_mock):
        rv = _import_risk_var()
        with patch(
            "services.risk_var.cache_yfinance_close_matrix",
            return_value=precios_historicos_mock,
        ):
            out = rv.calcular_var_cvar(
                tickers=["AAPL"],
                cantidades={"AAPL": 0.0},
                precios_ars={"AAPL": 150.0},
                ccl=1200.0,
            )
        assert out == {}

    def test_download_falla_retorna_vacio(self):
        rv = _import_risk_var()
        with patch(
            "services.risk_var.cache_yfinance_close_matrix",
            return_value=pd.DataFrame(),
        ):
            out = rv.calcular_var_cvar(
                tickers=["AAPL"],
                cantidades={"AAPL": 10.0},
                precios_ars={"AAPL": 150.0},
                ccl=1200.0,
            )
        assert out == {}

    def test_mock_ok_claves_y_convencion_signos(self, precios_historicos_mock):
        rv = _import_risk_var()
        with patch(
            "services.risk_var.cache_yfinance_close_matrix",
            return_value=precios_historicos_mock,
        ):
            out = rv.calcular_var_cvar(
                tickers=["AAPL", "MSFT"],
                cantidades={"AAPL": 5.0, "MSFT": 2.0},
                precios_ars={"AAPL": 150.0, "MSFT": 300.0},
                ccl=1200.0,
                horizonte_dias=5,
                nivel_confianza=0.95,
            )
        assert out
        for k in (
            "var_pct",
            "cvar_pct",
            "var_usd",
            "cvar_usd",
            "mensaje",
            "distribucion_rets",
        ):
            assert k in out
        assert out["var_pct"] <= 0
        assert out["cvar_pct"] <= out["var_pct"]
        assert out["var_usd"] >= 0
        assert out["cvar_usd"] >= 0
        assert isinstance(out["mensaje"], str)
        assert len(out["mensaje"]) > 0
        assert isinstance(out["distribucion_rets"], list)

    def test_confianza_99_mayor_magnitud_absoluta_que_95(self, precios_historicos_mock):
        rv = _import_risk_var()
        tickers = ["AAPL", "MSFT"]
        cant = {"AAPL": 5.0, "MSFT": 2.0}
        px = {"AAPL": 150.0, "MSFT": 300.0}
        ccl = 1200.0
        with patch(
            "services.risk_var.cache_yfinance_close_matrix",
            return_value=precios_historicos_mock,
        ):
            v95 = rv.calcular_var_cvar(
                tickers=tickers,
                cantidades=cant,
                precios_ars=px,
                ccl=ccl,
                nivel_confianza=0.95,
            )
            v99 = rv.calcular_var_cvar(
                tickers=tickers,
                cantidades=cant,
                precios_ars=px,
                ccl=ccl,
                nivel_confianza=0.99,
            )
        assert v95 and v99
        assert abs(v99["var_pct"]) >= abs(v95["var_pct"])
