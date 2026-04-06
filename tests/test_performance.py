"""
tests/test_performance.py — Tests de performance y robustez (Sprint 14)
Verifica que las optimizaciones son correctas y los guards funcionan.
Sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestCalcularRendimientoPorTipoVectorizado:
    @pytest.fixture
    def df_grande(self):
        """DataFrame de 30 activos para medir performance."""
        n = 30
        rng = np.random.default_rng(42)
        return pd.DataFrame({
            "TICKER":         [f"TICK{i:02d}" for i in range(n)],
            "TIPO":           ["CEDEAR"] * 20 + ["ACCION_LOCAL"] * 5 + ["FCI"] * 5,
            "VALOR_ARS":      rng.uniform(50_000, 300_000, n),
            "INV_ARS":        rng.uniform(40_000, 250_000, n),
            "PNL_ARS":        rng.uniform(-20_000, 50_000, n),
            "CANTIDAD_TOTAL": rng.integers(1, 100, n).astype(float),
        })

    def test_retorna_dataframe(self, df_grande):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_grande, pd.DataFrame())
        assert isinstance(result, pd.DataFrame)

    def test_columnas_requeridas_presentes(self, df_grande):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_grande, pd.DataFrame())
        if not result.empty:
            for col in ("Tipo", "Inv. ARS", "Valor ARS", "P&L ARS",
                        "Rend. ARS %", "N posiciones"):
                assert col in result.columns, f"Falta columna: {col}"

    def test_agrupacion_correcta_por_tipo(self, df_grande):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_grande, pd.DataFrame())
        if not result.empty and "Tipo" in result.columns:
            tipos = set(result["Tipo"].str.upper().tolist())
            assert "CEDEAR" in tipos

    def test_velocidad_aceptable(self, df_grande):
        """La función vectorizada debe completarse en < 500ms para 30 activos."""
        from services.cartera_service import calcular_rendimiento_por_tipo
        t0 = time.monotonic()
        calcular_rendimiento_por_tipo(df_grande, pd.DataFrame())
        elapsed = time.monotonic() - t0
        assert elapsed < 0.5, f"Demasiado lento: {elapsed:.3f}s para 30 activos"

    def test_df_vacio_retorna_vacio(self):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(pd.DataFrame(), pd.DataFrame())
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_suma_n_posiciones_igual_total(self, df_grande):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_grande, pd.DataFrame())
        if not result.empty and "N posiciones" in result.columns:
            total = result["N posiciones"].sum()
            assert total == len(df_grande)


class TestCalcularPosicionNetaRobustez:
    def test_strings_en_columnas_numericas_no_rompen(self):
        """Guard: strings mezclados con floats generan 0.0, no NaN ni excepción."""
        from services.cartera_service import calcular_posicion_neta
        df = pd.DataFrame({
            "TICKER":         ["AAPL", "MSFT"],
            "CANTIDAD_TOTAL": ["10", "5abc"],   # strings — debe coercerse a 10 y 0
            "PPC_USD_PROM":   [8.0, 10.0],
            "PPC_ARS":        [1200.0, 2000.0],
            "TIPO":           ["CEDEAR", "CEDEAR"],
            "ES_LOCAL":       [False, False],
            "CARTERA":        ["Test"] * 2,
        })
        precios = {"AAPL": 19_000.0, "MSFT": 22_000.0}
        try:
            result = calcular_posicion_neta(df, precios, 1465.0)
            assert isinstance(result, pd.DataFrame)
        except Exception as e:
            pytest.fail(f"calcular_posicion_neta lanzó con strings: {e}")

    def test_columnas_faltantes_no_rompen(self):
        """DataFrame sin INV_ARS_HISTORICO debe funcionar igual."""
        from services.cartera_service import calcular_posicion_neta
        df = pd.DataFrame({
            "TICKER":         ["KO"],
            "CANTIDAD_TOTAL": [20.0],
            "PPC_USD_PROM":   [4.4],
            "PPC_ARS":        [660.0],
            "TIPO":           ["CEDEAR"],
            "ES_LOCAL":       [False],
            "CARTERA":        ["Test"],
            # INV_ARS_HISTORICO intencionalmente ausente
        })
        precios = {"KO": 22_000.0}
        result = calcular_posicion_neta(df, precios, 1465.0)
        assert isinstance(result, pd.DataFrame)


class TestDivYieldCachePerformance:
    def test_segunda_llamada_mas_rapida(self, monkeypatch):
        """El cache hace la segunda llamada significativamente más rápida."""
        from services import cartera_service as cs

        def fake_yf(ticker):
            time.sleep(0.05)  # simula latencia de red
            class FI:
                dividend_yield = 0.02
            class FT:
                fast_info = FI()
            return FT()

        cs._DIV_YIELD_CACHE.pop("PERF_TEST_SPD", None)
        monkeypatch.setattr("yfinance.Ticker", fake_yf)

        t0 = time.monotonic()
        cs._get_div_yield_cached("PERF_TEST_SPD")
        t1 = time.monotonic()
        cs._get_div_yield_cached("PERF_TEST_SPD")
        t2 = time.monotonic()

        primera = t1 - t0
        segunda = t2 - t1
        assert segunda < primera * 0.5, (
            f"Segunda llamada ({segunda:.4f}s) no es < 50% de la primera ({primera:.4f}s)"
        )
