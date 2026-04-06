"""
tests/test_market_connector.py — Tests de market_connector.py (Sprint 13 + 24)
Sin internet — monkeypatch de yfinance.Ticker y yfinance.download.
Sprint 24: reset de estado mutable, _fetch_con_reintento, caché/circuit de fundamentales.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture(autouse=True)
def reset_market_state():
    """Limpia circuit breaker y caché de fundamentales entre tests."""
    import services.market_connector as mc
    mc._circuit_breaker.clear()
    mc._fundamentales_cache.clear()
    yield
    mc._circuit_breaker.clear()
    mc._fundamentales_cache.clear()


def _fake_close_series(prices: list[float]):
    """Helper que retorna un objeto fake con .history() → Series."""
    import pandas as pd

    class FakeHistory:
        def history(self, period=None, **kw):
            s = pd.Series(prices)
            return pd.DataFrame({"Close": s})

    return FakeHistory()


# ─── _fetch_con_reintento (Sprint 24) ────────────────────────────

class TestFetchConReintento:
    def test_retorna_resultado_en_primer_intento(self):
        import services.market_connector as mc

        def fn_ok():
            return 42

        assert mc._fetch_con_reintento(fn_ok, etiqueta="TEST/AAPL") == 42

    def test_circuit_breaker_bloquea_ticker_fallido(self):
        import services.market_connector as mc
        mc._circuit_breaker.add("AAPL")
        llamadas = []

        def fn():
            llamadas.append(1)
            return 100

        assert mc._fetch_con_reintento(fn, etiqueta="TEST/AAPL") is None
        assert len(llamadas) == 0

    def test_excepcion_retorna_none_sin_propagar(self):
        import services.market_connector as mc

        def fn_falla():
            raise ConnectionError("timeout")

        with patch("services.market_connector.time.sleep"):
            result = mc._fetch_con_reintento(fn_falla, etiqueta="TEST/MSFT")
        assert result is None

    def test_etiqueta_vacia_no_bloquea(self):
        import services.market_connector as mc

        def fn():
            return "resultado"

        assert mc._fetch_con_reintento(fn, etiqueta="") == "resultado"


# ─── obtener_ccl_mep ─────────────────────────────────────────────

class TestObtenerCclMep:
    def test_retorna_float(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            if ticker == "GGAL.BA":
                return _fake_close_series([1500.0])
            if ticker == "GGAL":
                return _fake_close_series([10.0])
            return _fake_close_series([])

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        resultado = mc.obtener_ccl_mep()
        assert isinstance(resultado, float)

    def test_ccl_positivo(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            if ticker == "GGAL.BA":
                return _fake_close_series([1500.0])
            if ticker == "GGAL":
                return _fake_close_series([10.0])
            return _fake_close_series([])

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        assert mc.obtener_ccl_mep() > 0

    def test_fallback_ante_excepcion(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker_falla(ticker):
            raise ConnectionError("sin red")

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker_falla)
        # Debe retornar el fallback sin lanzar
        resultado = mc.obtener_ccl_mep()
        assert isinstance(resultado, float)
        assert resultado == mc._CCL_FALLBACK


# ─── descargar_precios ────────────────────────────────────────────

class TestDescargarPrecios:
    def test_lista_vacia_retorna_df(self):
        from services.market_connector import descargar_precios
        df = descargar_precios([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_con_mock_retorna_df(self, monkeypatch):
        import services.market_connector as mc
        fake_df = pd.DataFrame({"AAPL": [150.0, 151.0, 152.0]})

        def fake_download(*args, **kwargs):
            return pd.DataFrame({"Close": fake_df})

        monkeypatch.setattr(mc.yf, "download", fake_download)
        df = mc.descargar_precios(["AAPL"])
        assert isinstance(df, pd.DataFrame)


# ─── precios_en_ars ───────────────────────────────────────────────

class TestPreciosEnArs:
    def test_conversion_exacta(self):
        from services.market_connector import precios_en_ars
        df_usd = pd.DataFrame({"AAPL": [10.0, 20.0], "KO": [5.0, 8.0]})
        ccl = 1500.0
        df_ars = precios_en_ars(df_usd, ccl=ccl)
        assert df_ars["AAPL"].iloc[0] == pytest.approx(15_000.0)
        assert df_ars["KO"].iloc[1] == pytest.approx(12_000.0)

    def test_df_vacio_retorna_vacio(self):
        from services.market_connector import precios_en_ars
        df_vacio = pd.DataFrame()
        resultado = precios_en_ars(df_vacio, ccl=1500.0)
        assert resultado.empty

    def test_mismas_dimensiones(self):
        import services.market_connector as mc
        df = pd.DataFrame({"A": [1.0, 2.0, 3.0], "B": [4.0, 5.0, 6.0]})
        result = mc.precios_en_ars(df, ccl=1000.0)
        assert result.shape == df.shape

    def test_mismas_columnas(self):
        import services.market_connector as mc
        df = pd.DataFrame({"AAPL": [10.0], "KO": [5.0]})
        result = mc.precios_en_ars(df, ccl=1500.0)
        assert list(result.columns) == list(df.columns)

    def test_ccl_none_llama_obtener_ccl(self):
        import services.market_connector as mc
        df = pd.DataFrame({"AAPL": [10.0]})
        with patch.object(mc, "obtener_ccl_mep", return_value=1465.0) as mock_ccl:
            result = mc.precios_en_ars(df, ccl=None)
        mock_ccl.assert_called_once()
        assert result["AAPL"].iloc[0] == pytest.approx(14_650.0)


# ─── obtener_ratios_fundamentales ────────────────────────────────

class TestObtenerRatiosFundamentales:
    def test_no_lanza_sin_internet(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            class FakeTicker:
                @property
                def info(self):
                    raise ConnectionError("sin red")
            return FakeTicker()

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        try:
            df = mc.obtener_ratios_fundamentales(["AAPL"])
            assert isinstance(df, pd.DataFrame)
        except Exception as e:
            pytest.fail(f"obtener_ratios_fundamentales lanzó: {e}")

    def test_retorna_dataframe(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            class FakeTicker:
                @property
                def info(self):
                    return {
                        "sector": "Tech",
                        "trailingPE": 28.0,
                        "dividendYield": 0.005,
                        "marketCap": 1_000_000_000,
                    }
            return FakeTicker()

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        df = mc.obtener_ratios_fundamentales(["AAPL"])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1


class TestCircuitBreakerFundamentales:
    def test_cache_hit_evita_segunda_llamada(self, monkeypatch):
        import services.market_connector as mc
        hoy = str(dt.date.today())
        mc._fundamentales_cache["AAPL"] = {
            "fecha": hoy,
            "data": {
                "Ticker": "AAPL",
                "Sector": "Tecnología",
                "P/E Trailing": 28.5,
                "P/E Forward": None,
                "Price/Book": None,
                "ROE": None,
                "Margen Operativo": None,
                "Dividend Yield %": 0.0,
                "Market Cap B": 0.0,
            },
        }
        llamadas = []

        def fake_ticker(symbol):
            llamadas.append(symbol)
            return _fake_close_series([100.0])

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        result = mc.obtener_ratios_fundamentales(["AAPL"])
        assert len(llamadas) == 0
        assert not result.empty
        assert result.iloc[0]["Sector"] == "Tecnología"

    def test_ticker_en_circuit_breaker_retorna_marca(self):
        import services.market_connector as mc
        mc._circuit_breaker.add("TICKER_ROTO")
        result = mc.obtener_ratios_fundamentales(["TICKER_ROTO"])
        assert not result.empty
        fila = result[result["Ticker"] == "TICKER_ROTO"].iloc[0]
        assert fila["Sector"] == "Circuit breaker"


# ─── precios_actuales_cartera ─────────────────────────────────────

class TestPreciosActualesCartera:
    def test_retorna_dict(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            return _fake_close_series([150.0])

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        resultado = mc.precios_actuales_cartera(["AAPL"], ratios={"AAPL": 10.0},
                                                ccl=1500.0)
        assert isinstance(resultado, dict)

    def test_ccl_cero_no_lanza(self, monkeypatch):
        import services.market_connector as mc

        def fake_ticker(ticker):
            return _fake_close_series([100.0])

        monkeypatch.setattr(mc.yf, "Ticker", fake_ticker)
        try:
            mc.precios_actuales_cartera(["KO"], ratios={"KO": 1.0}, ccl=0.0)
        except Exception as e:
            pytest.fail(f"precios_actuales_cartera con ccl=0 lanzó: {e}")
