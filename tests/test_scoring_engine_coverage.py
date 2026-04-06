"""
tests/test_scoring_engine_coverage.py — Cobertura scoring_engine (Sprint 28)
Solo funciones puras que no llaman a yfinance.
SECTORES vive en config.py; scoring_engine lo importa internamente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestConstantesScoringEngine:
    def test_pesos_suman_1(self):
        from services.scoring_engine import PESO_FUNDAMENTAL, PESO_SECTOR_CTX, PESO_TECNICO

        total = PESO_FUNDAMENTAL + PESO_TECNICO + PESO_SECTOR_CTX
        assert abs(total - 1.0) < 1e-6

    def test_sectores_tiene_tickers_clave(self):
        from config import SECTORES

        for t in ("AAPL", "MSFT", "KO", "NVDA"):
            assert t in SECTORES, f"{t} no está en SECTORES"

    def test_contexto_macro_tiene_claves_esperadas(self):
        from services.scoring_engine import CONTEXTO_MACRO

        for k in ("recesion_riesgo", "fed_ciclo", "ccl_tendencia", "riesgo_pais"):
            assert k in CONTEXTO_MACRO, f"Clave faltante en CONTEXTO_MACRO: {k}"


class TestTickerYahoo:
    def test_conversiones_conocidas(self):
        from services.scoring_engine import _ticker_yahoo

        casos = {
            "BRKB": "BRK-B",
            "YPFD": "YPFD.BA",
            "CEPU": "CEPU.BA",
            "TGNO4": "TGNO4.BA",
            "PAMP": "PAMP.BA",
            "GGAL": "GGAL.BA",
        }
        for local, esperado in casos.items():
            assert _ticker_yahoo(local) == esperado, f"{local} → esperado {esperado}"

    def test_ticker_desconocido_uppercase(self):
        from services.scoring_engine import _ticker_yahoo

        assert _ticker_yahoo("aapl") == "AAPL"
        assert _ticker_yahoo("msft") == "MSFT"

    def test_case_insensitive(self):
        from services.scoring_engine import _ticker_yahoo

        assert _ticker_yahoo("brkb") == _ticker_yahoo("BRKB")


class TestContextoMacro:
    def test_obtener_retorna_dict_no_vacio(self):
        from services.scoring_engine import obtener_contexto_macro

        ctx = obtener_contexto_macro()
        assert isinstance(ctx, dict)
        assert len(ctx) > 0

    def test_obtener_retorna_copia_no_referencia(self):
        from services.scoring_engine import obtener_contexto_macro

        c1 = obtener_contexto_macro()
        c1["__test_key_sentinel__"] = True
        c2 = obtener_contexto_macro()
        assert "__test_key_sentinel__" not in c2

    def test_actualizar_persiste_en_memoria(self):
        from services.scoring_engine import (
            CONTEXTO_MACRO,
            actualizar_contexto_macro,
            obtener_contexto_macro,
        )

        prev = CONTEXTO_MACRO.get("recesion_riesgo")
        try:
            with patch("core.db_manager.guardar_config"):
                actualizar_contexto_macro({"recesion_riesgo": "ALTO"})
            assert obtener_contexto_macro()["recesion_riesgo"] == "ALTO"
        finally:
            with patch("core.db_manager.guardar_config"):
                actualizar_contexto_macro({"recesion_riesgo": prev})

    def test_actualizar_no_lanza_sin_bd(self):
        from services.scoring_engine import CONTEXTO_MACRO, actualizar_contexto_macro

        prev = CONTEXTO_MACRO.get("fed_ciclo")
        try:
            with patch(
                "core.db_manager.guardar_config",
                side_effect=Exception("BD no disponible"),
            ):
                try:
                    actualizar_contexto_macro({"fed_ciclo": "BAJA"})
                except Exception as e:
                    pytest.fail(f"actualizar_contexto_macro lanzó: {e}")
        finally:
            with patch("core.db_manager.guardar_config"):
                actualizar_contexto_macro({"fed_ciclo": prev})


class TestScoreSectorContexto:
    def test_retorna_tuple_float_dict(self):
        from services.scoring_engine import score_sector_contexto

        score, det = score_sector_contexto("AAPL", "CEDEAR")
        assert isinstance(score, float)
        assert isinstance(det, dict)

    def test_score_en_rango_0_100(self):
        from services.scoring_engine import score_sector_contexto

        tickers = ["AAPL", "MSFT", "KO", "YPFD", "GGAL", "TICKER_XYZ"]
        tipos = ["CEDEAR", "CEDEAR", "CEDEAR", "Acción Local", "Acción Local", "CEDEAR"]
        for t, tipo in zip(tickers, tipos):
            s, _ = score_sector_contexto(t, tipo)
            assert 0.0 <= s <= 100.0, f"{t}: score={s} fuera de [0,100]"

    def test_detalle_tiene_claves_esperadas(self):
        from services.scoring_engine import score_sector_contexto

        _, det = score_sector_contexto("AAPL", "CEDEAR")
        for k in ("sector", "score_base", "ajuste_macro_eeuu", "ajuste_arg"):
            assert k in det, f"Clave faltante en detalle: {k}"

    def test_ticker_desconocido_retorna_score_valido(self):
        from services.scoring_engine import score_sector_contexto

        s, det = score_sector_contexto("TICKER_RARO_XYZ_999", "CEDEAR")
        assert 0.0 <= s <= 100.0
        assert det["sector"] == "Otros"

    def test_bono_usd_ajuste_arg_positivo_con_riesgo_bajo(self):
        from services.scoring_engine import (
            CONTEXTO_MACRO,
            actualizar_contexto_macro,
            score_sector_contexto,
        )

        prev = CONTEXTO_MACRO.get("riesgo_pais")
        try:
            with patch("core.db_manager.guardar_config"):
                actualizar_contexto_macro({"riesgo_pais": "BAJO"})
            _, det = score_sector_contexto("AL30", "Bono USD")
            assert det["ajuste_arg"] > 0
        finally:
            with patch("core.db_manager.guardar_config"):
                actualizar_contexto_macro({"riesgo_pais": prev})
