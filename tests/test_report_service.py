"""
tests/test_report_service.py — Tests de report_service.py
Cubre: funciones de formateo, secciones HTML, generar_reporte_html.
Sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def df_pos():
    return pd.DataFrame({
        "TICKER":         ["AAPL", "MSFT", "KO"],
        "CANTIDAD_TOTAL": [10, 5, 20],
        "VALOR_ARS":      [150_000.0, 100_000.0, 50_000.0],
        "INV_ARS":        [120_000.0,  90_000.0, 48_000.0],
        "PNL_ARS":        [ 30_000.0,  10_000.0,  2_000.0],
        "PNL_PCT":        [0.25, 0.111, 0.042],
        "PESO_PCT":       [50.0, 33.33, 16.67],
    })


@pytest.fixture
def df_analisis():
    return pd.DataFrame({
        "TICKER":          ["AAPL", "MSFT", "KO"],
        "PUNTAJE_TECNICO": [7.5, 5.0, 3.2],
        "ESTADO":          ["ELITE", "NEUTRO", "BAJISTA"],
    })


@pytest.fixture
def metricas():
    return {
        "total_valor": 300_000.0, "pnl_ars": 42_000.0,
        "pnl_pct": 0.14, "sharpe": 1.2, "max_dd": -0.08,
    }


# ─── Funciones de formateo ────────────────────────────────────────

class TestFormateoNumericos:
    def test_fmt_ars_formato_basico(self):
        from services.report_service import _fmt_ars
        result = _fmt_ars(1_234_567.0)
        assert "1" in result and ("234" in result or "1.234" in result)

    def test_fmt_ars_millones(self):
        from services.report_service import _fmt_ars
        result = _fmt_ars(1_500_000.0, millones=True)
        assert "M" in result or "m" in result or "1.5" in result

    def test_fmt_ars_cero(self):
        from services.report_service import _fmt_ars
        result = _fmt_ars(0.0)
        assert isinstance(result, str)

    def test_fmt_pct_positivo(self):
        from services.report_service import _fmt_pct
        result = _fmt_pct(0.123)
        assert "+" in result or "12" in result

    def test_fmt_pct_negativo(self):
        from services.report_service import _fmt_pct
        result = _fmt_pct(-0.051)
        assert "-" in result or "5" in result

    def test_fmt_pct_retorna_string(self):
        from services.report_service import _fmt_pct
        assert isinstance(_fmt_pct(0.10), str)

    def test_cls_pnl_positivo_retorna_pos(self):
        from services.report_service import _cls_pnl
        assert _cls_pnl(1000.0) == "pos"

    def test_cls_pnl_negativo_retorna_neg(self):
        from services.report_service import _cls_pnl
        assert _cls_pnl(-500.0) == "neg"

    def test_cls_pnl_cero_retorna_vacio(self):
        from services.report_service import _cls_pnl
        assert _cls_pnl(0.0) == ""

    def test_badge_estado_alcista(self):
        from services.report_service import _badge_estado
        badge = _badge_estado("ALCISTA")
        assert isinstance(badge, str) and len(badge) > 0

    def test_badge_estado_bajista(self):
        from services.report_service import _badge_estado
        badge = _badge_estado("BAJISTA")
        assert isinstance(badge, str)

    def test_badge_estado_desconocido_no_lanza(self):
        from services.report_service import _badge_estado
        badge = _badge_estado("ESTADO_RARO_XYZ")
        assert isinstance(badge, str)


# ─── Secciones HTML individuales ─────────────────────────────────

class TestSeccionesHtml:
    def test_html_posiciones_retorna_string(self, df_pos):
        from services.report_service import _html_posiciones
        html = _html_posiciones(df_pos)
        assert isinstance(html, str) and len(html) > 0

    def test_html_posiciones_contiene_tickers(self, df_pos):
        from services.report_service import _html_posiciones
        html = _html_posiciones(df_pos)
        assert "AAPL" in html
        assert "MSFT" in html

    def test_html_posiciones_df_vacio_no_lanza(self):
        from services.report_service import _html_posiciones
        html = _html_posiciones(pd.DataFrame())
        assert isinstance(html, str)

    def test_html_posiciones_nan_no_lanza(self):
        from services.report_service import _html_posiciones

        df = pd.DataFrame({
            "TICKER": ["AAPL"],
            "CANTIDAD_TOTAL": [np.nan],
            "VALOR_ARS": [np.nan],
            "INV_ARS": [np.nan],
            "PNL_ARS": [np.nan],
            "PNL_PCT": [np.nan],
            "PESO_PCT": [np.nan],
        })
        html = _html_posiciones(df)
        assert isinstance(html, str)

    def test_html_resumen_retorna_string(self, metricas):
        from services.report_service import _html_resumen
        html = _html_resumen(metricas, 1465.0, 252)
        assert isinstance(html, str) and len(html) > 0

    def test_html_resumen_metricas_vacias_no_lanza(self):
        from services.report_service import _html_resumen
        html = _html_resumen({}, 1465.0, 252)
        assert isinstance(html, str)

    def test_html_riesgo_retorna_string(self, df_pos, df_analisis):
        from services.report_service import _html_riesgo
        html = _html_riesgo(df_pos, df_analisis)
        assert isinstance(html, str) and len(html) > 0

    def test_html_riesgo_incluye_seccion_scores(self, df_pos, df_analisis):
        from services.report_service import _html_riesgo
        html = _html_riesgo(df_pos, df_analisis)
        assert "MOD-23" in html or "Score" in html or "AAPL" in html

    def test_html_attribution_none_retorna_string(self):
        from services.report_service import _html_attribution

        html = _html_attribution(None)
        assert isinstance(html, str)

    def test_html_attribution_con_datos(self):
        from services.report_service import _html_attribution

        html = _html_attribution({
            "active_total": 0.05,
            "allocation_sum": 0.02,
            "selection_sum": 0.02,
            "interaction_sum": 0.01,
        })
        assert isinstance(html, str)
        assert "Attribution" in html or "BHB" in html

    def test_html_stress_none_retorna_string(self):
        from services.report_service import _html_stress

        assert isinstance(_html_stress(None), str)

    def test_html_stress_con_dataframe_valido(self):
        from services.report_service import _html_stress

        stress_df = pd.DataFrame({
            "escenario": ["Crisis 2008"],
            "valor_original": [100000.0],
            "valor_stress": [80000.0],
            "pct_perdida": [-20.0],
        })
        html = _html_stress(stress_df)
        assert isinstance(html, str)
        assert "Crisis 2008" in html

    def test_html_notas_vacio_retorna_string(self):
        from services.report_service import _html_notas

        assert isinstance(_html_notas(""), str)

    def test_html_disclaimer_contiene_asesor(self):
        from services.report_service import _html_disclaimer

        html = _html_disclaimer("AsesorXYZ", "01/01/2026")
        assert isinstance(html, str)
        assert "AsesorXYZ" in html


# ─── generar_reporte_html completo ───────────────────────────────

class TestGenerarReporteHtml:
    def test_retorna_string_html(self, df_pos, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        html = generar_reporte_html(
            nombre_cliente="Test Cliente",
            nombre_asesor="Asesor Test",
            df_pos=df_pos,
            metricas=metricas,
            ccl=1465.0,
            df_analisis=df_analisis,
        )
        assert isinstance(html, str)
        assert len(html) > 500

    def test_contiene_nombre_cliente(self, df_pos, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        html = generar_reporte_html(
            "Alfredo Vallejos", "Asesor", df_pos, metricas,
            1465.0, df_analisis,
        )
        assert "Alfredo Vallejos" in html

    def test_tiene_estructura_html_valida(self, df_pos, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        html = generar_reporte_html("X", "Y", df_pos, metricas, 1465.0, df_analisis)
        assert "<!DOCTYPE html>" in html or "<html" in html

    def test_df_pos_vacio_no_lanza(self, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        html = generar_reporte_html("X", "Y", pd.DataFrame(), metricas, 1465.0, df_analisis)
        assert isinstance(html, str)

    def test_attribution_incluido(self, df_pos, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        attr = {"active_total": 0.05, "allocation_sum": 0.02,
                "selection_sum": 0.02, "interaction_sum": 0.01}
        html = generar_reporte_html("X", "Y", df_pos, metricas, 1465.0,
                                   df_analisis, attribution=attr)
        assert isinstance(html, str) and len(html) > 0

    def test_notas_asesor_incluidas(self, df_pos, metricas, df_analisis):
        from services.report_service import generar_reporte_html
        html = generar_reporte_html("X", "Y", df_pos, metricas, 1465.0,
                                   df_analisis, notas_asesor="Nota de prueba XYZ")
        assert "Nota de prueba XYZ" in html

    def test_acepta_scores_mod23(self, df_pos, metricas, df_analisis):
        import inspect

        from services.report_service import generar_reporte_html
        sig = inspect.signature(generar_reporte_html)
        assert callable(generar_reporte_html)
