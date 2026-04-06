"""
tests/test_scoring_engine.py — Tests del motor de scoring 60/20/20 (Sprint 11)
Sin red real: monkeypatch de yfinance y sub-funciones donde haga falta.
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


@pytest.fixture(autouse=True)
def limpiar_cache_score_tecnico():
    import services.scoring_engine as se
    se._SCORE_TEC_CACHE.clear()
    yield
    se._SCORE_TEC_CACHE.clear()


@pytest.fixture(autouse=True)
def restaurar_contexto_macro():
    """Invariante: cada test deja CONTEXTO_MACRO en su estado original."""
    import services.scoring_engine as se

    original = se.CONTEXTO_MACRO.copy()
    yield
    se.CONTEXTO_MACRO.clear()
    se.CONTEXTO_MACRO.update(original)


# ─── calcular_score_total, score_tecnico, score_fundamental (mocks) ─

class TestCalcularScoreTotal:
    def _mock_scores(self, monkeypatch, sf=70.0, st=60.0, ss=50.0):
        import services.scoring_engine as se
        monkeypatch.setattr(se, "score_fundamental", lambda t, tipo: (sf, {}))
        monkeypatch.setattr(se, "score_tecnico", lambda t, tipo: (st, {}))
        monkeypatch.setattr(se, "score_sector_contexto", lambda t, tipo: (ss, {}))
        import yfinance as yf
        monkeypatch.setattr(yf.Ticker, "history", lambda self, **kw: pd.DataFrame())

    def test_retorna_claves_requeridas(self, monkeypatch):
        self._mock_scores(monkeypatch)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL", "CEDEAR")
        for k in ["Score_Total", "Score_Fund", "Score_Tec", "Score_Sector", "Senal", "Ticker", "Tipo"]:
            assert k in r, f"Falta clave: {k}"

    def test_pesos_60_20_20(self, monkeypatch):
        self._mock_scores(monkeypatch, sf=80.0, st=60.0, ss=40.0)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL", "CEDEAR")
        esperado = 0.60 * 80 + 0.20 * 60 + 0.20 * 40
        assert abs(r["Score_Total"] - esperado) < 1.0

    def test_score_en_rango_0_100(self, monkeypatch):
        self._mock_scores(monkeypatch)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL")
        assert 0.0 <= r["Score_Total"] <= 100.0

    def test_senal_comprar_score_alto(self, monkeypatch):
        self._mock_scores(monkeypatch, sf=90.0, st=90.0, ss=90.0)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL")
        assert "COMPRAR" in r["Senal"]

    def test_senal_acumular(self, monkeypatch):
        self._mock_scores(monkeypatch, sf=65.0, st=65.0, ss=65.0)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL")
        assert "ACUMULAR" in r["Senal"] or "COMPRAR" in r["Senal"]

    def test_senal_salir_score_bajo(self, monkeypatch):
        self._mock_scores(monkeypatch, sf=20.0, st=20.0, ss=20.0)
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL")
        assert "SALIR" in r["Senal"] or "REDUCIR" in r["Senal"]

    def test_fci_usa_score_tecnico_50_fijo(self, monkeypatch):
        import services.scoring_engine as se
        monkeypatch.setattr(se, "score_fci", lambda t: (55.0, {}))
        monkeypatch.setattr(se, "score_sector_contexto", lambda t, tipo: (60.0, {}))
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("MAF AHORRO ARS", "FCI")
        assert r["Score_Tec"] == 50.0

    def test_no_lanza_cuando_yfinance_falla(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(
            yf.Ticker,
            "history",
            lambda self, **kw: (_ for _ in ()).throw(Exception("sin red")),
        )
        monkeypatch.setattr(
            yf.Ticker,
            "info",
            property(lambda self: (_ for _ in ()).throw(Exception("sin red"))),
        )
        from services.scoring_engine import calcular_score_total
        r = calcular_score_total("AAPL", "CEDEAR")
        assert "Score_Total" in r


class TestScoreTecnico:
    def test_retorna_tupla_float_dict(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(yf.Ticker, "history", lambda self, **kw: pd.DataFrame())
        from services.scoring_engine import score_tecnico
        result = score_tecnico("AAPL")
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], dict)

    def test_rango_valido(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(yf.Ticker, "history", lambda self, **kw: pd.DataFrame())
        from services.scoring_engine import score_tecnico
        score, _ = score_tecnico("AAPL")
        assert 0.0 <= score <= 100.0

    def test_default_40_cuando_yfinance_falla(self, monkeypatch):
        import yfinance as yf

        def raise_exc(self, **kw):
            raise RuntimeError("sin red")

        monkeypatch.setattr(yf.Ticker, "history", raise_exc)
        from services.scoring_engine import score_tecnico
        score, _ = score_tecnico("AAPL")
        assert score == 40.0

    def test_detalle_tiene_rsi(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(yf.Ticker, "history", lambda self, **kw: pd.DataFrame())
        from services.scoring_engine import score_tecnico
        _, detalle = score_tecnico("AAPL")
        assert "rsi" in detalle


class TestScoreFundamental:
    def test_retorna_tupla_float_dict(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(yf.Ticker, "info", property(lambda self: {}))
        from services.scoring_engine import score_fundamental
        result = score_fundamental("AAPL", "CEDEAR")
        assert isinstance(result[0], float) and isinstance(result[1], dict)

    def test_default_40_cuando_yfinance_falla(self, monkeypatch):
        import yfinance as yf
        monkeypatch.setattr(
            yf.Ticker,
            "info",
            property(lambda self: (_ for _ in ()).throw(Exception("net"))),
        )
        from services.scoring_engine import score_fundamental
        score, _ = score_fundamental("AAPL", "CEDEAR")
        assert score == 40.0

    def test_rango_valido_con_info_completa(self, monkeypatch):
        import yfinance as yf
        fake_info = {
            "regularMarketPrice": 150.0,
            "trailingPE": 18.0,
            "returnOnEquity": 0.30,
            "debtToEquity": 40.0,
            "dividendYield": 0.01,
            "earningsGrowth": 0.15,
            "profitMargins": 0.25,
        }
        monkeypatch.setattr(yf.Ticker, "info", property(lambda self: fake_info))
        from services.scoring_engine import score_fundamental
        score, _ = score_fundamental("AAPL", "CEDEAR")
        assert 0.0 <= score <= 100.0

    def test_bono_no_llama_info_yfinance(self, monkeypatch):
        import yfinance as yf
        # La rama Bono USD usa _score_bono (.history), no el bloque CEDEAR que lee .info.
        monkeypatch.setattr(
            yf.Ticker,
            "history",
            lambda self, **kw: pd.DataFrame({"Close": [100.0, 102.0, 101.0]}),
        )
        from services.scoring_engine import score_fundamental
        score, _ = score_fundamental("GD30", "Bono USD")
        assert 0.0 <= score <= 100.0


# ─── score_sector_contexto (pura — usa CONTEXTO_MACRO en memoria) ─

class TestScoreSectorContexto:
    def test_importa_sin_error(self):
        from services.scoring_engine import score_sector_contexto
        assert callable(score_sector_contexto)

    def test_retorna_tuple_float_dict(self):
        from services.scoring_engine import score_sector_contexto
        score, detalle = score_sector_contexto("AAPL", "CEDEAR")
        assert isinstance(score, float)
        assert isinstance(detalle, dict)

    def test_score_en_rango_valido(self):
        from services.scoring_engine import score_sector_contexto
        tickers = ["AAPL", "MSFT", "KO", "XOM", "JPM", "YPFD", "GGAL"]
        for t in tickers:
            score, _ = score_sector_contexto(t, "CEDEAR")
            assert 0.0 <= score <= 100.0, f"{t}: score={score} fuera de [0, 100]"

    def test_detalle_tiene_claves_requeridas(self):
        from services.scoring_engine import score_sector_contexto
        _, detalle = score_sector_contexto("AAPL", "CEDEAR")
        for k in ("sector", "score_base", "ajuste_macro_eeuu", "ajuste_arg"):
            assert k in detalle

    def test_ticker_desconocido_no_lanza(self):
        from services.scoring_engine import score_sector_contexto
        score, detalle = score_sector_contexto("TICKER_INEXISTENTE_XYZ", "CEDEAR")
        assert 0.0 <= score <= 100.0

    def test_tipo_accion_local_usa_ajuste_arg(self):
        from services.scoring_engine import score_sector_contexto
        _, detalle = score_sector_contexto("YPFD", "Acción Local")
        # El ajuste_arg debe estar presente
        assert "ajuste_arg" in detalle


# ─── _ticker_yahoo (pura — mapeo de tickers) ──────────────────────

class TestTickerYahoo:
    def test_brkb_a_brk_b(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("BRKB") == "BRK-B"

    def test_ypfd_a_ba(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("YPFD") == "YPFD.BA"

    def test_ggal_a_ba(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("GGAL") == "GGAL.BA"

    def test_cepu_a_ba(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("CEPU") == "CEPU.BA"

    def test_ticker_desconocido_retorna_uppercase(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("aapl") == "AAPL"
        assert _ticker_yahoo("msft") == "MSFT"

    def test_case_insensitive(self):
        from services.scoring_engine import _ticker_yahoo
        assert _ticker_yahoo("brkb") == _ticker_yahoo("BRKB")


# ─── obtener_contexto_macro / actualizar_contexto_macro ───────────

class TestContextoMacro:
    def test_obtener_retorna_dict(self):
        from services.scoring_engine import obtener_contexto_macro
        ctx = obtener_contexto_macro()
        assert isinstance(ctx, dict)
        assert len(ctx) > 0

    def test_obtener_retorna_copia(self):
        from services.scoring_engine import obtener_contexto_macro
        ctx1 = obtener_contexto_macro()
        ctx1["test_key"] = "test_value"
        ctx3 = obtener_contexto_macro()
        assert "test_key" not in ctx3

    def test_actualizar_modifica_contexto(self):
        from services.scoring_engine import actualizar_contexto_macro, obtener_contexto_macro
        actualizar_contexto_macro({"recesion_riesgo": "BAJO"})
        ctx_despues = obtener_contexto_macro()
        assert ctx_despues["recesion_riesgo"] == "BAJO"

    def test_actualizar_no_lanza_sin_bd(self):
        from services.scoring_engine import actualizar_contexto_macro
        with patch("core.db_manager.guardar_config", side_effect=Exception("BD no disponible")):
            try:
                actualizar_contexto_macro({"fed_ciclo": "BAJA"})
            except Exception:
                pytest.fail("actualizar_contexto_macro lanzó excepción con BD fallida")

    def test_actualizar_y_obtener(self):
        from services.scoring_engine import actualizar_contexto_macro, obtener_contexto_macro
        actualizar_contexto_macro({"fed_ciclo": "BAJA", "_test_key_scoring": "ok"})
        ctx = obtener_contexto_macro()
        assert ctx["_test_key_scoring"] == "ok"

    def test_cache_tecnico_importa_sin_error(self):
        from services.scoring_engine import _SCORE_TEC_CACHE, _get_score_tecnico_cached
        assert callable(_get_score_tecnico_cached)
        assert isinstance(_SCORE_TEC_CACHE, dict)


class TestConstantesScoringEngine:
    def test_pesos_suman_exactamente_1(self):
        from services.scoring_engine import PESO_FUNDAMENTAL, PESO_SECTOR_CTX, PESO_TECNICO

        total = PESO_FUNDAMENTAL + PESO_TECNICO + PESO_SECTOR_CTX
        assert abs(total - 1.0) < 1e-9

    def test_peso_fundamental_es_mayor_que_componentes_20(self):
        from services.scoring_engine import PESO_FUNDAMENTAL, PESO_SECTOR_CTX, PESO_TECNICO

        assert PESO_FUNDAMENTAL > PESO_TECNICO
        assert PESO_FUNDAMENTAL > PESO_SECTOR_CTX

    def test_contexto_macro_tiene_claves_obligatorias(self):
        from services.scoring_engine import CONTEXTO_MACRO

        for key in ("recesion_riesgo", "fed_ciclo", "ccl_tendencia", "riesgo_pais"):
            assert key in CONTEXTO_MACRO


class TestScoreSectorContextoRamasMacro:
    def test_cedear_con_ccl_sube_tiene_ajuste_arg_positivo(self):
        from services.scoring_engine import actualizar_contexto_macro, score_sector_contexto

        with patch("core.db_manager.guardar_config"):
            actualizar_contexto_macro({"ccl_tendencia": "SUBE"})
        _, detalle = score_sector_contexto("AAPL", "CEDEAR")
        assert detalle["ajuste_arg"] >= 5

    def test_bono_usd_con_riesgo_bajo_tiene_ajuste_positivo(self):
        from services.scoring_engine import actualizar_contexto_macro, score_sector_contexto

        with patch("core.db_manager.guardar_config"):
            actualizar_contexto_macro({"riesgo_pais": "BAJO"})
        _, detalle = score_sector_contexto("AL30", "Bono USD")
        assert detalle["ajuste_arg"] > 0

    def test_accion_local_con_riesgo_alto_tiene_ajuste_no_positivo(self):
        from services.scoring_engine import actualizar_contexto_macro, score_sector_contexto

        with patch("core.db_manager.guardar_config"):
            actualizar_contexto_macro({"riesgo_pais": "ALTO"})
        _, detalle = score_sector_contexto("YPFD", "Acción Local")
        assert detalle["ajuste_arg"] <= 0
