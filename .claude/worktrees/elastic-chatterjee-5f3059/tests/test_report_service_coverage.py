"""
tests/test_report_service_coverage.py — Cobertura report_service (Sprint 28)
Formateo, secciones HTML y generar_reporte_html. Sin yfinance ni red.
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


@pytest.fixture
def df_pos_completo():
    return pd.DataFrame({
        "TICKER":         ["AAPL", "MSFT", "KO"],
        "CANTIDAD_TOTAL": [10, 5, 20],
        "VALOR_ARS":      [190_000.0, 110_000.0, 45_000.0],
        "INV_ARS":        [150_000.0,  90_000.0, 44_000.0],
        "PNL_ARS":        [ 40_000.0,  20_000.0,  1_000.0],
        "PNL_PCT":        [0.267, 0.222, 0.023],
        "PESO_PCT":       [55.1, 31.9, 13.0],
    })


@pytest.fixture
def df_analisis_sample():
    return pd.DataFrame({
        "TICKER":          ["AAPL", "MSFT", "KO"],
        "PUNTAJE_TECNICO": [7.5, 5.0, 3.2],
        "ESTADO":          ["ELITE", "NEUTRO", "BAJISTA"],
    })


@pytest.fixture
def metricas_sample():
    return {
        "total_valor": 345_000.0,
        "pnl_ars":      61_000.0,
        "pnl_pct":          0.21,
        "sharpe":           1.4,
        "max_dd":          -0.07,
    }


class TestFmtArs:
    def test_retorna_string(self):
        from services.report_service import _fmt_ars

        assert isinstance(_fmt_ars(100_000.0), str)

    def test_cero_no_lanza(self):
        from services.report_service import _fmt_ars

        assert isinstance(_fmt_ars(0.0), str)

    def test_millones_contiene_M(self):
        from services.report_service import _fmt_ars

        result = _fmt_ars(2_500_000.0, millones=True)
        assert "M" in result or "2.5" in result

    def test_negativo_no_lanza(self):
        from services.report_service import _fmt_ars

        assert isinstance(_fmt_ars(-50_000.0), str)


class TestFmtPct:
    def test_positivo_tiene_mas(self):
        from services.report_service import _fmt_pct

        result = _fmt_pct(0.15)
        assert "+" in result or "15" in result

    def test_negativo_tiene_menos(self):
        from services.report_service import _fmt_pct

        result = _fmt_pct(-0.08)
        assert "-" in result

    def test_cero_no_lanza(self):
        from services.report_service import _fmt_pct

        assert isinstance(_fmt_pct(0.0), str)


class TestClsPnl:
    def test_positivo_pos(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(100.0) == "pos"

    def test_negativo_neg(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(-100.0) == "neg"

    def test_cero_vacio(self):
        from services.report_service import _cls_pnl

        assert _cls_pnl(0.0) == ""


class TestBadgeEstado:
    def test_retorna_string_para_todos_los_estados(self):
        from services.report_service import _badge_estado

        for estado in ("ALCISTA", "BAJISTA", "NEUTRO", "ELITE", "DESCONOCIDO"):
            result = _badge_estado(estado)
            assert isinstance(result, str) and len(result) > 0


class TestHtmlPosiciones:
    def test_retorna_string(self, df_pos_completo):
        from services.report_service import _html_posiciones

        assert isinstance(_html_posiciones(df_pos_completo), str)

    def test_contiene_tickers(self, df_pos_completo):
        from services.report_service import _html_posiciones

        html = _html_posiciones(df_pos_completo)
        assert "AAPL" in html

    def test_df_vacio_no_lanza(self):
        from services.report_service import _html_posiciones

        assert isinstance(_html_posiciones(pd.DataFrame()), str)

    def test_nan_no_lanza(self):
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
        assert isinstance(_html_posiciones(df), str)


class TestHtmlResumen:
    def test_retorna_string(self, metricas_sample):
        from services.report_service import _html_resumen

        assert isinstance(_html_resumen(metricas_sample, 1465.0, 252), str)

    def test_metricas_vacias_no_lanza(self):
        from services.report_service import _html_resumen

        assert isinstance(_html_resumen({}, 1465.0, 252), str)


class TestHtmlRiesgo:
    def test_retorna_string(self, df_pos_completo, df_analisis_sample):
        from services.report_service import _html_riesgo

        html = _html_riesgo(df_pos_completo, df_analisis_sample)
        assert isinstance(html, str) and len(html) > 0

    def test_dfs_vacios_no_lanzan(self):
        from services.report_service import _html_riesgo

        assert isinstance(_html_riesgo(pd.DataFrame(), pd.DataFrame()), str)


class TestGenerarReporteHtml:
    def test_retorna_string_con_estructura_html(
        self, df_pos_completo, metricas_sample, df_analisis_sample
    ):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "Alfredo Vallejos",
            "Asesor",
            df_pos_completo,
            metricas_sample,
            1465.0,
            df_analisis_sample,
        )
        assert isinstance(html, str)
        assert len(html) > 500
        assert ("<!DOCTYPE html>" in html or "<html" in html)

    def test_nombre_cliente_en_html(
        self, df_pos_completo, metricas_sample, df_analisis_sample
    ):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "NOMBRE_UNICO_TEST_XYZ",
            "Asesor",
            df_pos_completo,
            metricas_sample,
            1465.0,
            df_analisis_sample,
        )
        assert "NOMBRE_UNICO_TEST_XYZ" in html

    def test_notas_asesor_en_html(
        self, df_pos_completo, metricas_sample, df_analisis_sample
    ):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "X",
            "Y",
            df_pos_completo,
            metricas_sample,
            1465.0,
            df_analisis_sample,
            notas_asesor="NOTA_ESPECIAL_TEST_9999",
        )
        assert "NOTA_ESPECIAL_TEST_9999" in html

    def test_df_vacio_no_lanza(self, metricas_sample, df_analisis_sample):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "X",
            "Y",
            pd.DataFrame(),
            metricas_sample,
            1465.0,
            df_analisis_sample,
        )
        assert isinstance(html, str)

    def test_metricas_vacias_no_lanza(self, df_pos_completo, df_analisis_sample):
        from services.report_service import generar_reporte_html

        html = generar_reporte_html(
            "X",
            "Y",
            df_pos_completo,
            {},
            1465.0,
            df_analisis_sample,
        )
        assert isinstance(html, str)
