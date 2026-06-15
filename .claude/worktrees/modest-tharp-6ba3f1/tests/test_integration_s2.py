"""
tests/test_integration_s2.py — Tests de integración Sprint 2
Verifica que PriceEngine y FlowManager se integren correctamente al contexto.
Sin llamadas reales a yfinance (mocks sobre _try_live).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.flow_manager import FlowManager, StepState
from core.price_engine import PriceEngine, PriceSource

# ─── PriceEngine: cobertura y tickers_sin_precio ──────────────────────────────

class TestPriceEngineCobertura:
    def test_cobertura_100_con_todos_los_precios(self):
        pe = PriceEngine()
        records = pe.get_portfolio(
            ["AAPL", "KO"], ccl=1465.0,
            precios_live_override={"AAPL": 15_000.0, "KO": 22_000.0}
        )
        assert pe.cobertura_pct(records) == pytest.approx(100.0)

    def test_cobertura_parcial_cuando_falta_ticker(self):
        pe = PriceEngine()
        pe._fallback_hard = {}
        with patch.object(pe, "_try_live", return_value=None):
            records = pe.get_portfolio(
                ["AAPL", "ZZZINEXISTENTE999"],
                ccl=1465.0,
                precios_live_override={"AAPL": 15_000.0}
            )
        cob = pe.cobertura_pct(records)
        assert 0.0 < cob < 100.0

    def test_ticker_sin_precio_aparece_en_lista(self):
        pe = PriceEngine()
        pe._fallback_hard = {}
        with patch.object(pe, "_try_live", return_value=None):
            records = pe.get_portfolio(
                ["AAPL", "ZZZ_NO_EXISTE"],
                ccl=1465.0,
                precios_live_override={"AAPL": 15_000.0}
            )
        assert "ZZZ_NO_EXISTE" in pe.tickers_sin_precio(records)
        assert "AAPL" not in pe.tickers_sin_precio(records)

    def test_ticker_valido_no_aparece_en_sin_precio(self):
        pe = PriceEngine()
        records = pe.get_portfolio(
            ["AAPL"], ccl=1465.0,
            precios_live_override={"AAPL": 15_000.0}
        )
        assert pe.tickers_sin_precio(records) == []

    def test_to_precios_ars_compatible_formato(self):
        """to_precios_ars() devuelve dict[str, float] listo para calcular_posicion_neta."""
        pe = PriceEngine()
        records = pe.get_portfolio(
            ["AAPL"], ccl=1465.0,
            precios_live_override={"AAPL": 15_000.0}
        )
        precios = pe.to_precios_ars(records)
        assert isinstance(precios, dict)
        assert isinstance(precios["AAPL"], float)
        assert precios["AAPL"] == pytest.approx(15_000.0)

    def test_missing_cuando_sin_precio_ni_fallback(self):
        pe = PriceEngine()
        pe._fallback_hard = {}
        with patch.object(pe, "_try_live", return_value=None):
            rec = pe.get("TICKER_FANTASMA_XYZ123", ccl=1465.0)
        assert rec.source == PriceSource.MISSING
        assert not rec.es_valido
        assert rec.precio_cedear_ars == 0.0

    def test_cobertura_cero_cuando_todos_missing(self):
        pe = PriceEngine()
        pe._fallback_hard = {}
        with patch.object(pe, "_try_live", return_value=None):
            records = pe.get_portfolio(["ZZZ1", "ZZZ2"], ccl=1465.0)
        assert pe.cobertura_pct(records) == pytest.approx(0.0)


# ─── FlowManager: integración con coverage ────────────────────────────────────

class TestFlowManagerCoverage:
    def test_paso1_completo_con_coverage_alta(self):
        fm = FlowManager()
        assert fm.get_step_state(1, {"price_coverage_pct": 98.0}) == StepState.COMPLETO

    def test_paso1_completo_en_umbral_exacto(self):
        fm = FlowManager()
        assert fm.get_step_state(1, {"price_coverage_pct": 95.0}) == StepState.COMPLETO

    def test_paso1_alerta_con_coverage_baja(self):
        fm = FlowManager()
        assert fm.get_step_state(1, {"price_coverage_pct": 70.0}) == StepState.ALERTA

    def test_paso1_pendiente_sin_contexto(self):
        fm = FlowManager()
        assert fm.get_step_state(1, {}) == StepState.PENDIENTE

    def test_siguiente_accion_roja_con_coverage_baja(self):
        fm = FlowManager()
        _, color = fm.siguiente_accion({"price_coverage_pct": 60.0})
        assert color == "red"

    def test_siguiente_accion_verde_con_todo_ok(self):
        fm = FlowManager()
        ctx = {
            "price_coverage_pct":     100.0,
            "n_concentration_alerts": 0,
            "optimizacion_aprobada":  True,
            "ordenes_aprobadas":      True,
            "ultimo_reporte_generado": True,
        }
        _, color = fm.siguiente_accion(ctx)
        assert color == "green"

    def test_resumen_paso1_completo_con_coverage_alta(self):
        fm = FlowManager()
        r = fm.resumen({"price_coverage_pct": 100.0})
        assert r[1]["state"] == "completo"

    def test_resumen_contiene_siguiente_accion(self):
        fm = FlowManager()
        r = fm.resumen({"price_coverage_pct": 100.0})
        assert "siguiente_accion" in r
        assert "mensaje" in r["siguiente_accion"]
        assert "color" in r["siguiente_accion"]
