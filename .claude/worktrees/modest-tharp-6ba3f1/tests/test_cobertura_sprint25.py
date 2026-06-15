"""
tests/test_cobertura_sprint25.py — Tests de cobertura rápida (Sprint 25)
Cubre líneas de alto impacto en scoring_engine, report_service y motor_salida.
Sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestScoringEnginePuro:
    def test_ticker_yahoo_conversiones_conocidas(self):
        from services.scoring_engine import _ticker_yahoo

        assert _ticker_yahoo("BRKB") == "BRK-B"
        assert _ticker_yahoo("YPFD") == "YPFD.BA"
        assert _ticker_yahoo("CEPU") == "CEPU.BA"

    def test_ticker_yahoo_desconocido_uppercase(self):
        from services.scoring_engine import _ticker_yahoo

        assert _ticker_yahoo("aapl") == "AAPL"

    def test_obtener_contexto_macro_retorna_dict(self):
        from services.scoring_engine import obtener_contexto_macro

        ctx = obtener_contexto_macro()
        assert isinstance(ctx, dict) and len(ctx) > 0

    def test_obtener_contexto_macro_es_copia(self):
        from services.scoring_engine import obtener_contexto_macro

        c1 = obtener_contexto_macro()
        c1["_test_key_s25"] = "modificado"
        c2 = obtener_contexto_macro()
        assert "_test_key_s25" not in c2

    def test_score_sector_rango_valido(self):
        from services.scoring_engine import score_sector_contexto

        for ticker in ["AAPL", "KO", "YPFD", "XYZ_RARO"]:
            s, d = score_sector_contexto(ticker, "CEDEAR")
            assert 0.0 <= s <= 100.0
            assert isinstance(d, dict)

    def test_score_sector_detalle_tiene_claves(self):
        from services.scoring_engine import score_sector_contexto

        _, d = score_sector_contexto("AAPL", "CEDEAR")
        for k in ("sector", "score_base", "ajuste_macro_eeuu", "ajuste_arg"):
            assert k in d

    def test_actualizar_contexto_macro_no_lanza_sin_bd(self):
        from services.scoring_engine import actualizar_contexto_macro

        with patch("core.db_manager.guardar_config", side_effect=Exception("BD no disponible")):
            try:
                actualizar_contexto_macro({"recesion_riesgo": "BAJO"})
            except Exception as e:
                pytest.fail(f"lanzó: {e}")

    def test_actualizar_y_leer_contexto(self):
        import services.scoring_engine as se

        backup = dict(se.CONTEXTO_MACRO)
        try:
            with patch("core.db_manager.guardar_config"):
                se.actualizar_contexto_macro({"fed_ciclo": "BAJA"})
            ctx = se.obtener_contexto_macro()
            assert ctx["fed_ciclo"] == "BAJA"
        finally:
            se.CONTEXTO_MACRO.clear()
            se.CONTEXTO_MACRO.update(backup)


class TestReportServiceFormateo:
    def test_fmt_ars_retorna_string(self):
        from services.report_service import _fmt_ars

        assert isinstance(_fmt_ars(1_234_567.0), str)

    def test_fmt_ars_millones(self):
        from services.report_service import _fmt_ars

        result = _fmt_ars(1_500_000.0, millones=True)
        assert "M" in result or "m" in result or "1.5" in result

    def test_fmt_pct_positivo_tiene_signo(self):
        from services.report_service import _fmt_pct

        result = _fmt_pct(12.5)
        assert "+" in result and "12" in result

    def test_fmt_pct_negativo_tiene_menos(self):
        from services.report_service import _fmt_pct

        result = _fmt_pct(-5.0)
        assert "-" in result

    def test_cls_pnl_positivo(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(1000.0) == "pos"

    def test_cls_pnl_negativo(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(-500.0) == "neg"

    def test_cls_pnl_cero_vacio(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(0.0) == ""

    def test_badge_estado_retorna_string(self):
        from services.report_service import _badge_estado

        for estado in ("ALCISTA", "BAJISTA", "NEUTRO", "ELITE", "RARO"):
            assert isinstance(_badge_estado(estado), str)

    def test_html_posiciones_con_nan_no_lanza(self):
        from services.report_service import _html_posiciones

        df = pd.DataFrame(
            {
                "TICKER": ["AAPL"],
                "CANTIDAD_TOTAL": [np.nan],
                "VALOR_ARS": [np.nan],
                "PNL_ARS": [np.nan],
                "PNL_PCT": [np.nan],
                "PESO_PCT": [np.nan],
            }
        )
        html = _html_posiciones(df)
        assert isinstance(html, str)

    def test_generar_reporte_html_retorna_string(self):
        from services.report_service import generar_reporte_html

        df = pd.DataFrame(
            {
                "TICKER": ["AAPL", "MSFT"],
                "CANTIDAD_TOTAL": [10.0, 5.0],
                "VALOR_ARS": [190_000.0, 110_000.0],
                "PNL_ARS": [40_000.0, 20_000.0],
                "PNL_PCT": [0.267, 0.222],
                "PESO_PCT": [0.633, 0.367],
            }
        )
        df_mod = pd.DataFrame(
            {
                "TICKER": ["AAPL", "MSFT"],
                "PUNTAJE_TECNICO": [7.5, 3.0],
                "ESTADO": ["ALCISTA", "BAJISTA"],
            }
        )
        html = generar_reporte_html(
            "Alfredo Vallejos",
            "Asesor",
            df,
            {"total_valor": 300_000.0},
            1465.0,
            df_mod,
        )
        assert isinstance(html, str) and len(html) > 500

    def test_generar_reporte_html_con_notas(self):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "X",
            "Y",
            pd.DataFrame(),
            {},
            1465.0,
            pd.DataFrame(),
            notas_asesor="NOTA_ESPECIFICA_TEST_XYZ",
        )
        assert "NOTA_ESPECIFICA_TEST_XYZ" in html


class TestMotorSalidaPuro:
    def test_estimar_prob_exito_rango(self):
        from services.motor_salida import estimar_prob_exito

        for s in [0, 50, 100]:
            for rsi in [20, 45, 80]:
                p = estimar_prob_exito(s, rsi)
                assert 0.20 <= p <= 0.80

    def test_kelly_sizing_retorna_claves(self):
        from services.motor_salida import kelly_sizing

        r = kelly_sizing(0.6, 35.0, 15.0, 1_000_000.0)
        for k in ("kelly_aplicado_pct", "capital_sugerido_ars", "interpretacion"):
            assert k in r

    def test_kelly_no_negativo(self):
        from services.motor_salida import kelly_sizing

        r = kelly_sizing(0.1, 3.0, 50.0, 1_000_000.0)
        assert r["kelly_aplicado_pct"] >= 0.0

    def test_evaluar_salida_ppc_cero_guard(self):
        from services.motor_salida import evaluar_salida

        r = evaluar_salida(
            "AAPL", 0.0, 150.0, 50.0, 7.0, 7.0, date(2023, 1, 1)
        )
        assert r["progreso_pct"] == 0.0

    def test_evaluar_salida_claves_requeridas(self):
        from services.motor_salida import evaluar_salida

        r = evaluar_salida(
            "AAPL", 100.0, 120.0, 45.0, 7.0, 7.0, date(2023, 1, 1)
        )
        for k in ("senal", "progreso_pct", "precio_target", "precio_stop"):
            assert k in r
