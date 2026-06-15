"""
tests/test_backtester.py — Tests de backtester.py (Sprint 10)
Sin red: yfinance.download mockeado con serie alineada al índice de precios.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _run_bt(monkeypatch, precios: pd.DataFrame, pesos: dict, **kw) -> object:
    """Ejecuta run_backtest con benchmark sintético en el mismo calendario que precios."""

    def fake_download(*_a, **_k):
        rng = np.random.default_rng(5)
        idx = precios.index
        n = len(idx)
        close = 180.0 * np.cumprod(1 + rng.normal(0.00025, 0.01, n))
        return pd.DataFrame({"Close": close}, index=idx)

    monkeypatch.setattr("services.backtester.yf.download", fake_download)
    from services.backtester import run_backtest

    return run_backtest(precios, pesos, **kw)


@pytest.fixture
def df_precios_sintetico():
    """Precios historicos sinteticos para 2 activos — 2 años de trading."""
    rng = np.random.default_rng(42)
    n = 504
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "AAPL": 150.0 * np.cumprod(1 + rng.normal(0.001, 0.02, n)),
            "MSFT": 250.0 * np.cumprod(1 + rng.normal(0.001, 0.018, n)),
        },
        index=idx,
    )


@pytest.fixture
def pesos_validos():
    return {"AAPL": 0.6, "MSFT": 0.4}


# ─── run_backtest ──────────────────────────────────────────────────────────────


class TestRunBacktest:
    def test_importa_sin_error(self):
        from services.backtester import run_backtest

        assert callable(run_backtest)

    def test_retorna_resultado_no_none_con_datos_validos(
        self, monkeypatch, df_precios_sintetico, pesos_validos
    ):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None

    def test_retorna_none_con_df_vacio(self, monkeypatch, pesos_validos):
        from services.backtester import run_backtest

        monkeypatch.setattr("services.backtester.yf.download", lambda *a, **k: pd.DataFrame())
        result = run_backtest(pd.DataFrame(), pesos_validos)
        assert result is None

    def test_retorna_none_con_pesos_vacios(self, monkeypatch, df_precios_sintetico):
        from services.backtester import run_backtest

        def fake_download(*_a, **_k):
            rng = np.random.default_rng(1)
            idx = df_precios_sintetico.index
            n = len(idx)
            c = 100.0 * np.cumprod(1 + rng.normal(0.0001, 0.01, n))
            return pd.DataFrame({"Close": c}, index=idx)

        monkeypatch.setattr("services.backtester.yf.download", fake_download)
        result = run_backtest(df_precios_sintetico, {})
        assert result is None

    def test_retorna_none_con_tickers_no_en_df(self, monkeypatch, df_precios_sintetico):
        from services.backtester import run_backtest

        def fake_download(*_a, **_k):
            rng = np.random.default_rng(2)
            idx = df_precios_sintetico.index
            n = len(idx)
            c = 100.0 * np.cumprod(1 + rng.normal(0.0001, 0.01, n))
            return pd.DataFrame({"Close": c}, index=idx)

        monkeypatch.setattr("services.backtester.yf.download", fake_download)
        result = run_backtest(df_precios_sintetico, {"ZZZ": 1.0})
        assert result is None

    def test_resultado_tiene_retorno_anual(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert hasattr(result, "retorno_anual_estrategia")
        assert isinstance(result.retorno_anual_estrategia, float)

    def test_resultado_tiene_sharpe(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert hasattr(result, "sharpe_estrategia")

    def test_resultado_max_drawdown_no_positivo(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert result.max_dd_estrategia <= 0.0

    def test_equity_curve_positiva(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert (result.equity_strategy > 0).all()

    def test_sin_rebalanceo_funciona(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos_validos,
            rebalanceo_mensual=False,
        )
        assert result is None or hasattr(result, "retorno_anual_estrategia")

    def test_tickers_usados_en_resultado(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert len(result.tickers_usados) > 0
        for t in result.tickers_usados:
            assert t in pesos_validos


# ─── D03 / D04 reporte OOS y benchmarks ────────────────────────────────────────


class TestReporteOOSyBenchmarks:
    def test_reporte_oos_tiene_todas_las_metricas(
        self, monkeypatch, df_precios_sintetico, pesos_validos
    ):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        rep = result.oos_report()
        esperadas = {
            "cagr_estrategia",
            "vol_anual_estrategia",
            "sharpe_estrategia",
            "sortino_estrategia",
            "max_dd_estrategia",
            "skew_retornos_estrategia",
            "kurtosis_retornos_estrategia",
            "sharpe_spy",
            "sharpe_1n",
            "alpha_vs_spy",
            "retorno_anual_benchmark",
        }
        assert esperadas <= set(rep.keys())
        for k in esperadas:
            assert isinstance(rep[k], (int, float)), k

    def test_benchmark_spy_incluido(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos_validos,
            benchmark_ticker="SPY",
        )
        assert result is not None
        assert result.sharpe_spy == pytest.approx(result.sharpe_benchmark)
        assert "sharpe_spy" in result.oos_report()

    def test_naive_1_n_incluido(self, monkeypatch, df_precios_sintetico, pesos_validos):
        result = _run_bt(monkeypatch, df_precios_sintetico, pesos_validos)
        assert result is not None
        assert hasattr(result, "sharpe_1n")
        assert hasattr(result, "retorno_anual_1n")
        assert isinstance(result.sharpe_1n, float)


# ─── D06 costos de rebalanceo ──────────────────────────────────────────────────


class TestCostosRebalanceo:
    def test_costos_reducen_retorno_neto(self, monkeypatch, df_precios_sintetico):
        """Con rebalanceo mensual, mayor costo por turnover reduce el retorno anual."""
        pesos = {"AAPL": 0.85, "MSFT": 0.15}
        r_libre = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos,
            rebalanceo_mensual=True,
            costo_rebalanceo_pct=0.0,
        )
        r_costoso = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos,
            rebalanceo_mensual=True,
            costo_rebalanceo_pct=0.02,
        )
        assert r_libre is not None and r_costoso is not None
        assert r_costoso.retorno_anual_estrategia < r_libre.retorno_anual_estrategia

    def test_sin_rebalanceo_cero_costos(self, monkeypatch, df_precios_sintetico, pesos_validos):
        """Sin rebalanceo mensual no se aplican costos; el retorno no depende del parámetro."""
        r0 = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos_validos,
            rebalanceo_mensual=False,
            costo_rebalanceo_pct=0.0,
        )
        r1 = _run_bt(
            monkeypatch,
            df_precios_sintetico,
            pesos_validos,
            rebalanceo_mensual=False,
            costo_rebalanceo_pct=0.05,
        )
        assert r0 is not None and r1 is not None
        assert r0.retorno_anual_estrategia == pytest.approx(r1.retorno_anual_estrategia, rel=1e-9, abs=1e-9)


# ─── D05 walk-forward ──────────────────────────────────────────────────────────


class TestWalkForward:
    def test_wfv_n_ventanas_correcto(self):
        from services.temporal_split import walk_forward_splits

        n = 600
        idx = pd.date_range("2018-01-01", periods=n, freq="B")
        df = pd.DataFrame({"X": np.linspace(100, 200, n)}, index=idx)
        ventanas = walk_forward_splits(df, train_rows=252, test_rows=21, step_rows=21)
        assert len(ventanas) == 16

    def test_wfv_no_fuga_datos(self):
        from services.temporal_split import walk_forward_splits

        rng = np.random.default_rng(3)
        n = 400
        idx = pd.date_range("2019-01-01", periods=n, freq="B")
        df = pd.DataFrame({"A": rng.random(n), "B": rng.random(n)}, index=idx)
        for _train, test, meta in walk_forward_splits(
            df, train_rows=120, test_rows=20, step_rows=20
        ):
            assert meta.train_end < meta.test_start


# ─── BacktestResult ───────────────────────────────────────────────────────────


class TestBacktestResult:
    def test_importa_sin_error(self):
        from services.backtester import BacktestResult

        assert BacktestResult is not None

    def test_campos_requeridos_existen(self):
        import dataclasses

        from services.backtester import BacktestResult

        campos = {f.name for f in dataclasses.fields(BacktestResult)}
        for campo in (
            "retorno_anual_estrategia",
            "sharpe_estrategia",
            "max_dd_estrategia",
            "equity_strategy",
            "tickers_usados",
        ):
            assert campo in campos, f"Campo {campo} no encontrado en BacktestResult"


# ─── funciones auxiliares ─────────────────────────────────────────────────────


class TestFuncionesAuxiliares:
    def test_max_drawdown_serie_creciente(self):
        """Serie siempre creciente tiene drawdown = 0."""
        from services.backtester import _max_drawdown

        equity = np.array([1.0, 1.1, 1.2, 1.3, 1.4])
        dd = _max_drawdown(equity)
        assert dd == pytest.approx(0.0, abs=1e-6)

    def test_max_drawdown_negativo(self):
        """Serie con caida tiene drawdown negativo."""
        from services.backtester import _max_drawdown

        equity = np.array([1.0, 1.2, 0.9, 1.1])
        dd = _max_drawdown(equity)
        assert dd < 0.0

    def test_sharpe_con_retornos_positivos(self):
        """Serie de retornos positivos tiene Sharpe > 0."""
        from services.backtester import _sharpe

        retornos = pd.Series([0.001] * 252)
        s = _sharpe(retornos)
        assert s > 0.0

    def test_sharpe_con_retornos_cero(self):
        """Serie de retornos cero tiene Sharpe = 0."""
        from services.backtester import _sharpe

        retornos = pd.Series([0.0] * 252)
        s = _sharpe(retornos)
        assert s == pytest.approx(0.0, abs=1e-6)


class TestTrainTestOOS:
    """Contrato OOS: backtest sobre tramo test no incluye fechas del train."""

    def test_run_backtest_limitado_al_slice_test(self, monkeypatch):
        from services.backtester import run_backtest
        from services.temporal_split import split_precios_train_test

        rng = np.random.default_rng(0)
        n = 300
        idx = pd.date_range("2020-01-01", periods=n, freq="B")
        df = pd.DataFrame(
            {
                "AAPL": 100 * np.cumprod(1 + rng.normal(0.0003, 0.015, n)),
                "MSFT": 200 * np.cumprod(1 + rng.normal(0.0003, 0.014, n)),
            },
            index=idx,
        )
        train, test, meta = split_precios_train_test(
            df, train_frac=0.7, min_train_rows=50, min_test_rows=30
        )
        assert meta.n_test > 0
        pesos = {"AAPL": 0.5, "MSFT": 0.5}

        def fake_download(*_a, **_k):
            rng_b = np.random.default_rng(8)
            tidx = test.index
            m = len(tidx)
            c = 150.0 * np.cumprod(1 + rng_b.normal(0.0002, 0.012, m))
            return pd.DataFrame({"Close": c}, index=tidx)

        monkeypatch.setattr("services.backtester.yf.download", fake_download)
        res = run_backtest(test, pesos, rebalanceo_mensual=False)
        assert res is not None
        assert pd.Timestamp(res.fechas[0]) >= test.index[0]
        assert pd.Timestamp(res.fechas[-1]) <= test.index[-1]
