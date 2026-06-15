"""
tests/test_resiliencia.py — Tests de resiliencia ante errores de red
y datos corruptos (Sprint 15).
Sin yfinance real — todo mockeado.
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


# ─── PriceEngine retry ────────────────────────────────────────────────────────

class TestPriceEngineRetry:
    def test_retry_exitoso_en_segundo_intento(self):
        """Si el primer intento retorna px=0 y el segundo tiene precio → retorna PriceRecord."""
        from core.price_engine import PriceEngine
        pe = PriceEngine()

        call_count = [0]

        def fake_ticker(symbol):
            call_count[0] += 1
            mock = MagicMock()
            if call_count[0] == 1:
                mock.fast_info.last_price = 0.0
            else:
                mock.fast_info.last_price = 15_000.0
            return mock

        with patch("yfinance.Ticker", fake_ticker):
            with patch("time.sleep"):
                result = pe._try_live("AAPL", 1465.0, 1.0)

        assert result is not None
        assert result.precio_subyacente_usd > 0

    def test_retorna_none_cuando_ambos_intentos_fallan(self):
        """Dos intentos fallidos → retorna None sin lanzar."""
        from core.price_engine import PriceEngine
        pe = PriceEngine()

        with patch("yfinance.Ticker", side_effect=ConnectionError("timeout simulado")):
            with patch("time.sleep"):
                result = pe._try_live("AAPL", 1465.0, 1.0)

        assert result is None

    def test_no_lanza_excepcion_con_red_caida(self):
        """_try_live nunca propaga excepciones al caller."""
        from core.price_engine import PriceEngine
        pe = PriceEngine()

        with patch("yfinance.Ticker", side_effect=Exception("no internet")):
            with patch("time.sleep"):
                try:
                    result = pe._try_live("MSFT", 1465.0, 1.0)
                    assert result is None
                except Exception as e:
                    pytest.fail(f"_try_live propagó excepción: {e}")

    def test_precio_cero_no_retorna_record(self):
        """Un precio de 0 en ambos intentos no es válido — debe retornar None."""
        from core.price_engine import PriceEngine
        pe = PriceEngine()

        def fake_ticker_precio_cero(symbol):
            mock = MagicMock()
            mock.fast_info.last_price = 0.0
            return mock

        with patch("yfinance.Ticker", fake_ticker_precio_cero):
            with patch("time.sleep"):
                result = pe._try_live("KO", 1465.0, 1.0)

        assert result is None


# ─── report_service NaN guard ─────────────────────────────────────────────────

class TestReportServiceNanGuard:
    def test_posiciones_con_nan_no_lanza(self):
        """_html_posiciones con NaN en columnas numéricas no lanza ValueError."""
        from services.report_service import _html_posiciones
        df = pd.DataFrame({
            "TICKER":         ["AAPL", "NAN_TICKER"],
            "CANTIDAD_TOTAL": [10.0, np.nan],
            "VALOR_ARS":      [150_000.0, np.nan],
            "INV_ARS":        [120_000.0, np.nan],
            "PNL_ARS":        [30_000.0, np.nan],
            "PNL_PCT":        [0.25, np.nan],
            "PESO_PCT":       [50.0, np.nan],
        })
        try:
            html = _html_posiciones(df)
            assert isinstance(html, str)
        except (ValueError, TypeError) as e:
            pytest.fail(f"_html_posiciones lanzó con NaN: {e}")

    def test_reporte_completo_con_posiciones_nan(self):
        """generar_reporte_html no lanza cuando df_pos contiene NaN."""
        from services.report_service import generar_reporte_html
        df = pd.DataFrame({
            "TICKER":         ["AAPL"],
            "CANTIDAD_TOTAL": [np.nan],
            "VALOR_ARS":      [np.nan],
            "INV_ARS":        [np.nan],
            "PNL_ARS":        [np.nan],
            "PNL_PCT":        [np.nan],
            "PESO_PCT":       [np.nan],
        })
        try:
            html = generar_reporte_html("Test", "Asesor", df, {}, 1465.0, pd.DataFrame())
            assert isinstance(html, str)
        except Exception as e:
            pytest.fail(f"generar_reporte_html lanzó con NaN: {e}")


# ─── cartera_service guards ───────────────────────────────────────────────────

class TestCarteraServiceGuards:
    def test_dividendos_con_ccl_cero_no_lanza(self):
        """ccl=0 no causa ZeroDivisionError — guard lo reemplaza por 1500."""
        from services.cartera_service import calcular_dividendos_proyectados
        df = pd.DataFrame({
            "TICKER":         ["AAPL"],
            "CANTIDAD_TOTAL": [10.0],
            "PRECIO_ARS":     [15_000.0],
            "VALOR_ARS":      [150_000.0],
            "TIPO":           ["CEDEAR"],
        })
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.fast_info.dividend_yield = 0.02
            try:
                result = calcular_dividendos_proyectados(df, ccl=0.0)
                assert isinstance(result, dict)
            except ZeroDivisionError:
                pytest.fail("ZeroDivisionError con ccl=0 — guard faltante")

    def test_dividendos_con_ccl_none_no_lanza(self):
        """ccl=None no causa TypeError — guard lo reemplaza por 1500."""
        from services.cartera_service import calcular_dividendos_proyectados
        df = pd.DataFrame({
            "TICKER": ["KO"], "CANTIDAD_TOTAL": [20.0],
            "PRECIO_ARS": [5_000.0], "VALOR_ARS": [100_000.0],
            "TIPO": ["CEDEAR"],
        })
        with patch("yfinance.Ticker") as mock_yf:
            mock_yf.return_value.fast_info.dividend_yield = 0.01
            try:
                result = calcular_dividendos_proyectados(df, ccl=None)
                assert isinstance(result, dict)
            except (ZeroDivisionError, TypeError):
                pytest.fail("Lanzó con ccl=None — guard faltante")

    def test_twrr_con_fechas_invalidas_retorna_neutro(self):
        """Fechas corruptas en df_trans retornan twrr=0 sin lanzar excepción."""
        from services.cartera_service import calcular_twrr
        df_trans = pd.DataFrame({
            "TICKER":       ["AAPL", "MSFT"],
            "CANTIDAD":     [10, 5],
            "FECHA_COMPRA": ["fecha_invalida", None],
            "PPC_USD":      [8.0, 10.0],
            "TIPO":         ["CEDEAR", "CEDEAR"],
        })
        try:
            result = calcular_twrr(df_trans, pd.DataFrame(), 1465.0)
            assert isinstance(result, dict)
            assert "twrr_anual" in result
        except Exception as e:
            pytest.fail(f"calcular_twrr lanzó con fechas inválidas: {e}")


# ─── ejecucion_service estructura de retorno ─────────────────────────────────

class TestEjecucionServiceLogging:
    def test_error_se_loguea_y_no_lanza(self):
        """generar_plan_rebalanceo con hist_precios vacío retorna dict con 'error'."""
        from services.ejecucion_service import generar_plan_rebalanceo
        df_ag = pd.DataFrame({
            "TICKER": ["AAPL"], "CANTIDAD_TOTAL": [10.0],
            "VALOR_ARS": [150_000.0], "PESO_PCT": [100.0],
        })
        result = generar_plan_rebalanceo(
            tickers_cartera=["AAPL"],
            df_ag=df_ag,
            hist_precios=pd.DataFrame(),
            precios_ars={"AAPL": 15_000.0},
        )
        assert isinstance(result, dict)
        assert "error" in result

    def test_retorna_estructura_correcta_siempre(self):
        """El dict retornado siempre contiene las claves esperadas."""
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo(
            tickers_cartera=[],
            df_ag=pd.DataFrame(),
            hist_precios=pd.DataFrame(),
            precios_ars={},
        )
        for k in ("pesos_optimos", "ejecutables", "bloqueadas", "reporte", "error"):
            assert k in result, f"Falta clave: {k}"
