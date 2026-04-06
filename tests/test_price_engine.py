"""
tests/test_price_engine.py — Tests del PriceEngine (Sprint 1)
Cubre: PriceRecord, PriceSource, PriceEngine sin llamadas reales a yfinance.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from core.price_engine import PriceEngine, PriceRecord, PriceSource, records_tras_rellenar_ppc

# ─── PriceRecord ──────────────────────────────────────────────────────────────

class TestPriceRecord:
    def _make(self, source=PriceSource.LIVE_YFINANCE, precio=15_000.0) -> PriceRecord:
        return PriceRecord(
            ticker="AAPL", precio_cedear_ars=precio,
            precio_subyacente_usd=200.0, ccl=1500.0, ratio=20.0,
            source=source, timestamp=datetime.now(),
        )

    def test_es_valido_live(self):
        assert self._make(PriceSource.LIVE_YFINANCE).es_valido

    def test_es_valido_fallback_hard(self):
        assert self._make(PriceSource.FALLBACK_HARD).es_valido

    def test_no_valido_missing(self):
        assert not self._make(PriceSource.MISSING, precio=0.0).es_valido

    def test_no_valido_precio_cero(self):
        r = self._make(PriceSource.LIVE_YFINANCE, precio=0.0)
        assert not r.es_valido

    def test_calidad_live(self):
        assert self._make(PriceSource.LIVE_YFINANCE).calidad == "LIVE"

    def test_calidad_fallback(self):
        assert self._make(PriceSource.FALLBACK_HARD).calidad == "FALLBACK"

    def test_calidad_missing(self):
        r = self._make(PriceSource.MISSING, precio=0.0)
        assert r.calidad == "SIN PRECIO"

    def test_to_dict_tiene_campos_clave(self):
        d = self._make().to_dict()
        for key in ("ticker", "precio_cedear_ars", "source", "calidad", "timestamp"):
            assert key in d


# ─── Conversiones estáticas ───────────────────────────────────────────────────

class TestConversionesEstaticas:
    def test_cedear_ars_formula_canonica(self):
        """subyacente=200 USD, ccl=1500, ratio=20 → 200*1500/20 = 15 000 ARS"""
        resultado = PriceEngine.cedear_ars(200.0, 20.0, 1500.0)
        assert resultado == pytest.approx(15_000.0, rel=0.001)

    def test_subyacente_usd_formula_canonica(self):
        """precio_cedear=15 000 ARS, ratio=20, ccl=1500 → 15000*20/1500 = 200 USD"""
        resultado = PriceEngine.subyacente_usd(15_000.0, 20.0, 1500.0)
        assert resultado == pytest.approx(200.0, rel=0.001)

    def test_inversa_exacta(self):
        """cedear_ars y subyacente_usd son inversas exactas."""
        sub = 175.50
        ccl, ratio = 1465.0, 20.0
        px_ars = PriceEngine.cedear_ars(sub, ratio, ccl)
        sub_back = PriceEngine.subyacente_usd(px_ars, ratio, ccl)
        assert sub_back == pytest.approx(sub, rel=0.0001)

    def test_ccl_cero_devuelve_cero(self):
        assert PriceEngine.cedear_ars(200.0, 20.0, 0.0) == 0.0
        assert PriceEngine.subyacente_usd(15_000.0, 20.0, 0.0) == 0.0

    def test_ratio_cero_devuelve_cero(self):
        assert PriceEngine.cedear_ars(200.0, 0.0, 1500.0) == 0.0


# ─── PriceEngine.get_portfolio ────────────────────────────────────────────────

class TestPriceEnginePortfolio:
    """Tests del motor de precios — sin llamadas reales a yfinance."""

    def _engine(self) -> PriceEngine:
        return PriceEngine()

    def test_override_live_tiene_prioridad(self):
        """Si el caller pasa precios_live_override, tienen prioridad absoluta."""
        engine = self._engine()
        records = engine.get_portfolio(
            ["AAPL"], ccl=1500.0,
            precios_live_override={"AAPL": 18_000.0},
        )
        assert records["AAPL"].precio_cedear_ars == pytest.approx(18_000.0)
        assert records["AAPL"].source == PriceSource.LIVE_YFINANCE

    def test_missing_cuando_sin_precio(self):
        """Ticker desconocido sin fallback → MISSING, nunca None ni excepción."""
        engine = self._engine()
        engine._fallback_hard = {}  # vaciar fallback para forzar MISSING
        with patch.object(engine, "_try_live", return_value=None):
            rec = engine.get("XYZNOTEXIST123", ccl=1500.0)
        assert rec.source == PriceSource.MISSING
        assert rec.precio_cedear_ars == 0.0
        assert not rec.es_valido

    def test_fallback_hard_cuando_live_falla(self):
        """Si live falla, usa fallback hardcodeado."""
        engine = self._engine()
        engine._fallback_hard["TESTTKR"] = 9_999.0
        engine._ratios["TESTTKR"] = 10.0
        with patch.object(engine, "_try_live", return_value=None):
            rec = engine.get("TESTTKR", ccl=1500.0)
        assert rec.source == PriceSource.FALLBACK_HARD
        assert rec.precio_cedear_ars == pytest.approx(9_999.0)

    def test_cobertura_cien_pct_cuando_todos_validos(self):
        engine = self._engine()
        records = engine.get_portfolio(
            ["AAPL", "KO"],
            ccl=1500.0,
            precios_live_override={"AAPL": 15_000.0, "KO": 22_000.0},
        )
        assert engine.cobertura_pct(records) == pytest.approx(100.0)

    def test_cobertura_cero_cuando_todos_missing(self):
        engine = self._engine()
        engine._fallback_hard = {}
        with patch.object(engine, "_try_live", return_value=None):
            records = engine.get_portfolio(["ZZZZ1", "ZZZZ2"], ccl=1500.0)
        assert engine.cobertura_pct(records) == pytest.approx(0.0)

    def test_tickers_sin_precio_lista_correcta(self):
        engine = self._engine()
        engine._fallback_hard = {}
        with patch.object(engine, "_try_live", return_value=None):
            records = engine.get_portfolio(
                ["AAPL", "ZZZZ1"],
                ccl=1500.0,
                precios_live_override={"AAPL": 15_000.0},
            )
        sin_precio = engine.tickers_sin_precio(records)
        assert "ZZZZ1" in sin_precio
        assert "AAPL" not in sin_precio

    def test_to_precios_ars_compatibilidad(self):
        """to_precios_ars() devuelve dict[str, float] compatible con calcular_posicion_neta."""
        engine = self._engine()
        records = engine.get_portfolio(
            ["AAPL"], ccl=1500.0,
            precios_live_override={"AAPL": 15_000.0},
        )
        precios = engine.to_precios_ars(records)
        assert isinstance(precios, dict)
        assert isinstance(precios["AAPL"], float)
        assert precios["AAPL"] == pytest.approx(15_000.0)

    def test_refresh_fallback_actualiza_precio(self):
        engine = self._engine()
        engine.refresh_fallback({"NEWTKR": 5_000.0})
        assert engine._fallback_hard.get("NEWTKR") == pytest.approx(5_000.0)


class TestRecordsTrasPPC:
    def test_marca_fallback_ppc(self):
        r = PriceRecord(
            ticker="BONO", precio_cedear_ars=0.0, precio_subyacente_usd=0.0,
            ccl=1000.0, ratio=1.0, source=PriceSource.MISSING, timestamp=datetime.now(),
        )
        out = records_tras_rellenar_ppc(
            {"BONO": r},
            {"BONO": 0.0},
            {"BONO": 123.45},
            1000.0,
        )
        assert out["BONO"].source == PriceSource.FALLBACK_PPC
        assert out["BONO"].precio_cedear_ars == pytest.approx(123.45)
