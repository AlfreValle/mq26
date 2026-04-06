"""
tests/test_cobertura_residual.py — Tests de cobertura rápida (Sprint 22)
Cubre: mod23_service, helpers puros de scoring_engine, cartera_service.
Sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestMod23ServiceDirecto:
    @pytest.fixture
    def df_analisis(self):
        return pd.DataFrame({
            "TICKER":           ["AAPL", "MSFT", "KO", "TSLA"],
            "PUNTAJE_TECNICO":  [7.5, 5.0, 3.2, 1.8],
            "ESTADO":           ["ALCISTA", "NEUTRO", "BAJISTA", "BAJISTA"],
        })

    def test_scores_cartera_retorna_df(self, df_analisis):
        from services.mod23_service import scores_cartera
        r = scores_cartera(df_analisis, ["AAPL", "KO"])
        assert isinstance(r, pd.DataFrame)
        assert "AAPL" in r["TICKER"].values
        assert "KO" in r["TICKER"].values

    def test_scores_cartera_df_vacio_retorna_vacio(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(pd.DataFrame(), ["AAPL"])
        assert r.empty

    def test_detectar_alertas_debajo_umbral(self, df_analisis):
        from services.mod23_service import detectar_alertas_venta
        alertas = detectar_alertas_venta(df_analisis, ["KO", "TSLA", "AAPL"])
        tickers = [a["ticker"] for a in alertas]
        assert "KO" in tickers
        assert "TSLA" in tickers
        assert "AAPL" not in tickers

    def test_resumen_universo_tiene_total(self, df_analisis):
        from services.mod23_service import resumen_universo
        r = resumen_universo(df_analisis)
        assert isinstance(r, dict)
        assert r.get("total", 0) == 4


class TestScoringEnginePuro:
    def test_ticker_yahoo_brkb(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("BRKB") == "BRK-B"

    def test_ticker_yahoo_desconocido_upper(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("aapl") == "AAPL"

    def test_obtener_contexto_macro(self):
        from services.scoring_engine import obtener_contexto_macro
        ctx = obtener_contexto_macro()
        assert isinstance(ctx, dict) and len(ctx) > 0

    def test_score_sector_en_rango(self):
        from services.scoring_engine import score_sector_contexto
        for ticker in ["AAPL", "MSFT", "KO", "YPFD"]:
            s, _ = score_sector_contexto(ticker, "CEDEAR")
            assert 0.0 <= s <= 100.0

    def test_actualizar_contexto_macro_no_lanza_si_bd_falla(self):
        from services.scoring_engine import actualizar_contexto_macro
        with patch("core.db_manager.guardar_config", side_effect=Exception("BD")):
            try:
                actualizar_contexto_macro({"recesion_riesgo": "BAJO"})
            except Exception as e:
                pytest.fail(f"actualizar_contexto_macro lanzó: {e}")


class TestCarteraServiceMinor:
    def test_calcular_progreso_objetivo_cero_si_ppc_invalido(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(0.0, 100.0, 35.0) == pytest.approx(0.0)

    def test_calcular_progreso_objetivo_100_en_target(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(100.0, 135.0, 35.0) == pytest.approx(100.0, abs=0.1)

    def test_calcular_progreso_objetivo_clipeado(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(100.0, 1000.0, 35.0) <= 200.0
        assert calcular_progreso_objetivo(100.0, 1.0, 35.0) >= -100.0

    def test_metricas_resumen_df_vacio(self):
        from services.cartera_service import metricas_resumen
        r = metricas_resumen(pd.DataFrame())
        assert r["total_valor"] == 0.0
        assert r["n_posiciones"] == 0

    def test_get_div_yield_cached_retorna_float(self):
        from services.cartera_service import _get_div_yield_cached
        result = _get_div_yield_cached("TICKER_XYZ_RARO_999")
        assert isinstance(result, float)
