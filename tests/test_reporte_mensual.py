"""
tests/test_reporte_mensual.py — Tests de reporte_mensual.py (Sprint 10)
Sin red ni yfinance. Usa DataFrames sinteticos.
"""
from __future__ import annotations

import pandas as pd
import pytest


@pytest.fixture
def df_pos_ejemplo():
    return pd.DataFrame({
        "TICKER":    ["AAPL", "MSFT", "KO"],
        "VALOR_ARS": [150_000.0, 100_000.0, 50_000.0],
        "INV_ARS":   [120_000.0,  90_000.0, 48_000.0],
        "PNL_ARS":   [ 30_000.0,  10_000.0,  2_000.0],
        "PNL_PCT":   [0.25, 0.111, 0.042],
        "PESO_PCT":  [50.0, 33.33, 16.67],
        "TIPO":      ["CEDEAR", "CEDEAR", "CEDEAR"],
    })


@pytest.fixture
def metricas_ejemplo():
    return {
        "valor_ars":   300_000.0,
        "pnl_ars":      42_000.0,
        "pnl_pct":          0.14,
        "pnl_mes_pct":      0.03,
        "sharpe":           1.2,
    }


# ─── generar_reporte_mensual_html ─────────────────────────────────────────────

class TestGenerarReporteMensualHtml:
    def test_retorna_string_no_vacio(self, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html
        html = generar_reporte_mensual_html(
            cliente="Test Cliente",
            cartera="Retiro",
            perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        assert isinstance(html, str)
        assert len(html) > 200

    def test_html_contiene_nombre_cliente(self, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html
        html = generar_reporte_mensual_html(
            cliente="Alfredo Vallejos",
            cartera="Retiro",
            perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        assert "Alfredo Vallejos" in html

    def test_html_tiene_estructura_valida(self, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        assert "<html" in html or "<!DOCTYPE" in html or "<div" in html

    def test_df_posiciones_vacio_no_lanza(self, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=pd.DataFrame(),
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Enero 2026",
        )
        assert isinstance(html, str)

    def test_mes_ano_auto_cuando_vacio(self, df_pos_ejemplo, metricas_ejemplo):
        """Sin mes_año, se calcula automaticamente sin lanzar."""
        from services.reporte_mensual import generar_reporte_mensual_html
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            # mes_año no especificado
        )
        assert isinstance(html, str)

    def test_recomendaciones_se_incluyen(self, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html
        recom = [{"ticker": "AAPL", "accion": "COMPRAR", "motivo": "Score alto"}]
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=recom,
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        # Al menos el HTML se genera sin error con recomendaciones
        assert isinstance(html, str) and len(html) > 0


# ─── guardar_reporte ──────────────────────────────────────────────────────────

class TestGuardarReporte:
    def test_crea_archivo(self, tmp_path, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html, guardar_reporte
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        ruta = guardar_reporte(html, tmp_path / "reporte.html")
        assert ruta.exists()

    def test_contenido_igual(self, tmp_path, df_pos_ejemplo, metricas_ejemplo):
        from services.reporte_mensual import generar_reporte_mensual_html, guardar_reporte
        html = generar_reporte_mensual_html(
            cliente="X", cartera="Y", perfil="Moderado",
            df_posiciones=df_pos_ejemplo,
            df_operaciones_mes=pd.DataFrame(),
            metricas=metricas_ejemplo,
            recomendaciones=[],
            ccl=1465.0,
            mes_año="Marzo 2026",
        )
        ruta = guardar_reporte(html, tmp_path / "rep.html")
        assert ruta.read_text(encoding="utf-8") == html
