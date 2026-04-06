"""
tests/test_mod23_service.py — Tests de mod23_service.py (Sprint 13)
Lógica pura de DataFrames — sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


def _df_analisis_sample() -> pd.DataFrame:
    return pd.DataFrame({
        "TICKER":          ["AAPL", "KO",      "MSFT",    "VALE",    "YPFD"],
        "PUNTAJE_TECNICO": [8.5,    3.2,        6.1,       4.5,       2.8],
        "ESTADO":          ["ALCISTA", "BAJISTA", "ALCISTA", "ALCISTA", "BAJISTA"],
    })


# ─── scores_cartera ───────────────────────────────────────────────

class TestScoresCartera:
    def test_df_vacio_retorna_vacio(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(pd.DataFrame(columns=["TICKER", "PUNTAJE_TECNICO"]), ["AAPL"])
        assert r.empty

    def test_tickers_vacia_retorna_vacio(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(_df_analisis_sample(), [])
        assert r.empty

    def test_filtra_solo_cartera(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(_df_analisis_sample(), ["AAPL", "KO"])
        assert set(r["TICKER"].tolist()) == {"AAPL", "KO"}

    def test_ordenado_descendente(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(_df_analisis_sample(), ["AAPL", "KO", "MSFT"])
        puntajes = r["PUNTAJE_TECNICO"].tolist()
        assert puntajes == sorted(puntajes, reverse=True)

    def test_case_insensitive(self):
        from services.mod23_service import scores_cartera
        r = scores_cartera(_df_analisis_sample(), ["aapl", "ko"])
        assert len(r) == 2


# ─── detectar_alertas_venta ───────────────────────────────────────

class TestDetectarAlertasVenta:
    def test_ninguna_alerta_score_alto(self):
        from services.mod23_service import detectar_alertas_venta
        df = pd.DataFrame({
            "TICKER":          ["AAPL"],
            "PUNTAJE_TECNICO": [8.0],
            "ESTADO":          ["ALCISTA"],
        })
        assert detectar_alertas_venta(df, ["AAPL"]) == []

    def test_detecta_score_bajo(self):
        from services.mod23_service import detectar_alertas_venta
        alertas = detectar_alertas_venta(_df_analisis_sample(), ["KO", "YPFD"])
        tickers_alertados = [a["ticker"] for a in alertas]
        assert "KO" in tickers_alertados and "YPFD" in tickers_alertados

    def test_umbral_configurable(self):
        from services.mod23_service import detectar_alertas_venta
        # VALE=4.5 < umbral=5.0 → debe alertar
        alertas = detectar_alertas_venta(_df_analisis_sample(), ["AAPL", "VALE"], umbral=5.0)
        tickers = [a["ticker"] for a in alertas]
        assert "VALE" in tickers


# ─── resumen_universo ─────────────────────────────────────────────

class TestResumenUniverso:
    def test_vacio_retorna_ceros(self):
        from services.mod23_service import resumen_universo
        r = resumen_universo(pd.DataFrame(columns=["PUNTAJE_TECNICO"]))
        assert r == {"n_elite": 0, "n_alcistas": 0, "n_alertas": 0, "total": 0}

    def test_cuenta_elite(self):
        from services.mod23_service import resumen_universo
        r = resumen_universo(_df_analisis_sample())
        assert r["n_elite"] == 1       # solo AAPL (8.5) >= 7

    def test_cuenta_alertas(self):
        from services.mod23_service import resumen_universo
        r = resumen_universo(_df_analisis_sample())
        assert r["n_alertas"] == 2     # KO (3.2) y YPFD (2.8) < 4

    def test_total_correcto(self):
        from services.mod23_service import resumen_universo
        r = resumen_universo(_df_analisis_sample())
        assert r["total"] == 5
