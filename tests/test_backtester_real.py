"""
tests/test_backtester_real.py — Tests de calcular_metricas y calcular_equity_curve_real (Sprint 24)
Sin red: mock de streamlit/plotly antes del import; yfinance.download parcheado.
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
def mock_streamlit_plotly_backtester():
    prev_st = sys.modules.get("streamlit")
    prev_plotly = sys.modules.get("plotly")
    prev_pgo = sys.modules.get("plotly.graph_objects")

    sys.modules["streamlit"] = MagicMock()
    mock_pgo = MagicMock()
    mock_plotly = MagicMock()
    mock_plotly.graph_objects = mock_pgo
    sys.modules["plotly"] = mock_plotly
    sys.modules["plotly.graph_objects"] = mock_pgo

    sys.modules.pop("services.backtester_real", None)
    yield
    sys.modules.pop("services.backtester_real", None)
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


def _import_backtester():
    import services.backtester_real as bt
    return bt


def _equity_df_n(n: int, with_spy: bool = False) -> pd.DataFrame:
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    valor = np.linspace(10_000.0, 10_000.0 + n * 12.0, n)
    df = pd.DataFrame({"fecha": idx.date, "valor_usd": valor})
    df["retorno_diario"] = df["valor_usd"].pct_change()
    if with_spy:
        spy = np.linspace(400.0, 400.0 + n * 0.15, n)
        df["spy_usd"] = spy * (10_000.0 / spy[0])
    return df


class TestCalcularMetricas:
    def test_vacio_retorna_vacio(self):
        bt = _import_backtester()
        assert bt.calcular_metricas(pd.DataFrame()) == {}

    def test_menos_de_10_filas_retorna_vacio(self):
        bt = _import_backtester()
        df = _equity_df_n(9)
        assert bt.calcular_metricas(df) == {}

    def test_filas_suficientes_incluye_claves_requeridas(self):
        bt = _import_backtester()
        df = _equity_df_n(252)
        m = bt.calcular_metricas(df, capital_inicial=10_000.0)
        assert m
        for k in (
            "valor_inicial_usd",
            "valor_final_usd",
            "retorno_total_pct",
            "retorno_anual_pct",
            "volatilidad_anual",
            "sharpe_ratio",
            "max_drawdown_pct",
            "calmar_ratio",
            "retorno_spy_pct",
            "alfa_vs_spy_pct",
            "dias_activo",
            "años_activo",
        ):
            assert k in m

    def test_max_drawdown_no_positivo_serie_creciente(self):
        bt = _import_backtester()
        df = _equity_df_n(120)
        m = bt.calcular_metricas(df)
        assert m["max_drawdown_pct"] <= 0

    def test_dias_activo_igual_longitud(self):
        bt = _import_backtester()
        df = _equity_df_n(100)
        m = bt.calcular_metricas(df)
        assert m["dias_activo"] == len(df)

    def test_volatilidad_no_negativa(self):
        bt = _import_backtester()
        df = _equity_df_n(100)
        m = bt.calcular_metricas(df)
        assert m["volatilidad_anual"] >= 0

    def test_con_spy_usd_calcula_alfa(self):
        bt = _import_backtester()
        df = _equity_df_n(100, with_spy=True)
        m = bt.calcular_metricas(df)
        assert "alfa_vs_spy_pct" in m
        assert "retorno_spy_pct" in m

    def test_serie_constante_drawdown_cero(self):
        bt = _import_backtester()
        n = 50
        df = pd.DataFrame(
            {
                "fecha": pd.date_range("2022-01-03", periods=n, freq="B").date,
                "valor_usd": [10_000.0] * n,
            }
        )
        df["retorno_diario"] = df["valor_usd"].pct_change()
        m = bt.calcular_metricas(df)
        assert m["max_drawdown_pct"] == pytest.approx(0.0, abs=0.01)

    def test_serie_fuertemente_creciente_retorno_total_positivo(self):
        bt = _import_backtester()
        n = 60
        base = np.linspace(10_000.0, 15_000.0, n)
        df = pd.DataFrame(
            {
                "fecha": pd.date_range("2022-01-03", periods=n, freq="B").date,
                "valor_usd": base,
            }
        )
        df["retorno_diario"] = df["valor_usd"].pct_change()
        m = bt.calcular_metricas(df)
        assert m["retorno_total_pct"] > 0


class TestCalcularEquityCurveReal:
    def test_df_operaciones_vacio_dataframe_vacio(self):
        bt = _import_backtester()
        out = bt.calcular_equity_curve_real(
            pd.DataFrame(), ccl_historico={"2023-01": 1200.0}
        )
        assert isinstance(out, pd.DataFrame)
        assert out.empty

    def test_download_falla_columnas_vacias(self):
        bt = _import_backtester()
        df_ops = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "Tipo_Op": ["COMPRA"],
                "Cantidad": [1.0],
                "FECHA_INICIAL": [pd.Timestamp("2023-06-01")],
            }
        )
        with patch("yfinance.download", side_effect=RuntimeError("sin red")):
            out = bt.calcular_equity_curve_real(
                df_ops, ccl_historico={"2023-06": 1300.0}
            )
        assert isinstance(out, pd.DataFrame)
        assert list(out.columns) == ["fecha", "valor_usd", "spy_usd"]
        assert out.empty

    def test_download_ok_columnas_esperadas(self):
        bt = _import_backtester()
        fecha_op = pd.Timestamp("2023-06-01")
        df_ops = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "Tipo_Op": ["COMPRA"],
                "Cantidad": [10.0],
                "FECHA_INICIAL": [fecha_op],
            }
        )
        idx = pd.date_range("2023-05-25", "2023-08-31", freq="B")
        aapl = np.linspace(170.0, 175.0, len(idx))
        spy = np.linspace(410.0, 415.0, len(idx))
        cols = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "SPY")])
        full = pd.DataFrame(
            np.column_stack([aapl, spy]), index=idx, columns=cols
        )

        def fake_download(*_a, **_k):
            return full

        with patch("yfinance.download", fake_download):
            out = bt.calcular_equity_curve_real(
                df_ops,
                ccl_historico={"2023-05": 1250.0, "2023-06": 1300.0, "2023-07": 1280.0},
                capital_inicial=10_000.0,
            )
        assert isinstance(out, pd.DataFrame)
        assert not out.empty
        assert "fecha" in out.columns
        assert "valor_usd" in out.columns
        assert "spy_usd" in out.columns
        if len(out) >= 2:
            assert "retorno_diario" in out.columns
