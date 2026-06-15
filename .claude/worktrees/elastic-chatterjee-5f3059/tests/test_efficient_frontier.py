"""
tests/test_efficient_frontier.py — Tests de efficient_frontier en RiskEngine (Sprint 1)
Verifica las invariantes matemáticas de la Frontera Eficiente de Markowitz.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def engine_frontier():
    """RiskEngine con datos sintéticos para tests de frontera eficiente."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "1_Scripts_Motor"))
    from risk_engine import RiskEngine
    np.random.seed(42)
    n_days, n_assets = 300, 5
    tickers = ["AAPL", "MSFT", "KO", "CVX", "VALE"]
    # Retornos con diferentes medias para generar frontera no trivial
    means = np.array([0.0008, 0.0007, 0.0003, 0.0005, 0.0006])
    cov = np.diag([0.0004, 0.0003, 0.0001, 0.0002, 0.0003])
    retornos = np.random.multivariate_normal(means, cov, n_days)
    precios = 100 * np.cumprod(1 + retornos, axis=0)
    df = pd.DataFrame(precios, columns=tickers)
    return RiskEngine(df)


class TestEfficientFrontierEstructura:
    def test_devuelve_dataframe(self, engine_frontier):
        df = engine_frontier.efficient_frontier(n_puntos=10)
        assert isinstance(df, pd.DataFrame)

    def test_columnas_requeridas(self, engine_frontier):
        df = engine_frontier.efficient_frontier(n_puntos=10)
        for col in ("retorno_anual_pct", "volatilidad_pct", "sharpe", "pesos"):
            assert col in df.columns, f"Columna faltante: {col}"

    def test_produce_puntos(self, engine_frontier):
        df = engine_frontier.efficient_frontier(n_puntos=20)
        assert len(df) > 0, "Frontera eficiente vacía"

    def test_pesos_son_dict(self, engine_frontier):
        df = engine_frontier.efficient_frontier(n_puntos=10)
        for pesos in df["pesos"]:
            assert isinstance(pesos, dict)

    def test_pesos_no_negativos(self, engine_frontier):
        """Invariante: ningún peso en la frontera puede ser negativo."""
        df = engine_frontier.efficient_frontier(n_puntos=20)
        for pesos in df["pesos"]:
            for ticker, w in pesos.items():
                assert w >= -1e-6, f"Peso negativo en frontera: {ticker}={w}"

    def test_pesos_suman_uno_aprox(self, engine_frontier):
        """Cada punto de la frontera es una cartera válida: suma ~ 1."""
        df = engine_frontier.efficient_frontier(n_puntos=10)
        for pesos in df["pesos"]:
            total = sum(pesos.values())
            assert total == pytest.approx(1.0, abs=0.02), \
                f"Pesos no suman 1: {total}"


class TestEfficientFrontierInvariantes:
    def test_retorno_creciente(self, engine_frontier):
        """Los puntos deben estar ordenados por retorno creciente."""
        df = engine_frontier.efficient_frontier(n_puntos=20)
        if len(df) < 2:
            pytest.skip("Insuficientes puntos")
        retornos = df["retorno_anual_pct"].tolist()
        assert retornos == sorted(retornos), "Retornos no están ordenados"

    def test_volatilidad_no_negativa(self, engine_frontier):
        """La volatilidad siempre es >= 0."""
        df = engine_frontier.efficient_frontier(n_puntos=20)
        assert (df["volatilidad_pct"] >= 0).all()

    def test_retornos_positivos_o_negativos_validos(self, engine_frontier):
        """Los retornos pueden ser positivos o negativos — no hay restricción."""
        df = engine_frontier.efficient_frontier(n_puntos=10)
        assert df["retorno_anual_pct"].dtype == float or df["retorno_anual_pct"].dtype == np.float64

    def test_sharpe_calculado(self, engine_frontier):
        """Sharpe = (retorno - rf) / vol — debe estar presente y ser float."""
        df = engine_frontier.efficient_frontier(n_puntos=10)
        assert df["sharpe"].dtype in (float, np.float64)

    def test_n_puntos_parametro(self, engine_frontier):
        """n_puntos controla la granularidad (puede haber menos por filtrado)."""
        df5  = engine_frontier.efficient_frontier(n_puntos=5)
        df30 = engine_frontier.efficient_frontier(n_puntos=30)
        assert len(df30) >= len(df5), \
            "Mayor n_puntos debe producir >= puntos que menor n_puntos"

    def test_activos_en_universo(self, engine_frontier):
        """Los tickers en los pesos deben pertenecer al universo del engine."""
        df = engine_frontier.efficient_frontier(n_puntos=10)
        for pesos in df["pesos"]:
            for t in pesos:
                assert t in engine_frontier.activos, \
                    f"Ticker {t} no está en el universo del engine"
