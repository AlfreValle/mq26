"""Tests Pilar 2 — services/ficha_ticker.py: ficha unificada con degradación."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

import services.ficha_ticker as ft

# ─── Dobles de prueba ─────────────────────────────────────────────────────────

@dataclass
class SnapFake:
    calidad: str = "live"
    precio_actual_usd: float = 200.0
    pe_forward: float = 22.0
    pb_ratio: float = 8.0
    roe: float = 0.45
    profit_margin: float = 0.25
    debt_to_equity: float = 1.2
    revenue_growth: float = 0.08
    dividend_yield: float = 0.005
    market_cap: float = 3_000_000_000_000
    sector: str = "Technology"
    industry: str = "Consumer Electronics"


@dataclass
class ActionFake:
    ticker: str = "AAPL"
    timestamp: str = "2026-06-11T00:00:00Z"
    score_total: float = 72.0
    score_valor: float = 55.0
    score_calidad: float = 88.0
    score_momentum: float = 70.0
    score_sectorial: float = 65.0
    pesos: dict = field(default_factory=lambda: {"valor": 0.35, "calidad": 0.30, "momentum": 0.20, "sectorial": 0.15})
    recomendacion: str = "COMPRAR"
    flags_alerta: list = field(default_factory=list)
    detalle_valor: dict = field(default_factory=dict)
    detalle_calidad: dict = field(default_factory=dict)
    detalle_momentum: dict = field(default_factory=dict)
    detalle_sectorial: dict = field(default_factory=dict)
    sector: str = "Technology"

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class DCFFake:
    ticker: str = "AAPL"
    precio_actual_usd: float = 200.0
    valor_intrinseco_usd: float = 240.0
    margen_seguridad_pct: float = 20.0
    recomendacion_dcf: str = "INFRAVALORADA"
    fcff_anual_usd_m: float = 100_000.0
    growth_explicito_pct: float = 8.0
    wacc_pct: float = 9.5
    terminal_growth_pct: float = 2.5
    beta_usado: float = 1.1
    shares_outstanding_m: float = 15_000.0
    sensibilidad: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


COMP_OK = {
    "fuente": "industria",
    "industria": "Consumer Electronics",
    "metricas": {"P/E TTM": {"empresa": 22.0, "industria": 25.0}},
    "summary": {"n_mejor": 5, "n_peor": 2, "n_neutral": 1, "total": 8},
}


@pytest.fixture()
def todo_ok(monkeypatch):
    monkeypatch.setattr(ft, "obtener_fundamentales", lambda t, force_refresh=False: SnapFake())
    monkeypatch.setattr(ft, "calcular_action_score", lambda t, force_refresh=False: ActionFake(ticker=t))
    monkeypatch.setattr(ft, "calcular_dcf", lambda t, snap=None: DCFFake(ticker=t))
    monkeypatch.setattr(ft, "comparar_vs_industria", lambda s, i, sec=None: dict(COMP_OK))


# ─── Camino feliz ─────────────────────────────────────────────────────────────

class TestFichaCompleta:
    def test_cinco_secciones_ok(self, todo_ok):
        f = ft.generar_ficha_ticker("AAPL")
        assert f.cobertura == "5/5"
        assert f.score_global == 72.0
        assert f.recomendacion == "COMPRAR"

    def test_resumen_combina_dcf_y_comparables(self, todo_ok):
        f = ft.generar_ficha_ticker("AAPL")
        assert "72/100" in f.resumen
        assert "descuento" in f.resumen          # DCF INFRAVALORADA refuerza
        assert "5 de 8" in f.resumen             # comparables

    def test_explicacion_multifactor_descompone_dimensiones(self, todo_ok):
        f = ft.generar_ficha_ticker("AAPL")
        e = f.multifactor.explicacion
        assert "Valor 55" in e and "35%" in e
        assert "Calidad 88" in e and "30%" in e

    def test_to_dict_serializable(self, todo_ok):
        import json

        f = ft.generar_ficha_ticker("AAPL")
        assert json.dumps(f.to_dict())  # no lanza


# ─── Degradación por sección ──────────────────────────────────────────────────

class TestDegradacion:
    def test_sin_fundamentales_ficha_sale_igual(self, monkeypatch):
        monkeypatch.setattr(
            ft, "obtener_fundamentales",
            lambda t, force_refresh=False: (_ for _ in ()).throw(RuntimeError("red caída")),
        )
        f = ft.generar_ficha_ticker("AAPL")
        assert f.identidad.ok                    # el maestro no necesita red
        assert not f.fundamentals.ok
        assert not f.multifactor.ok
        assert f.recomendacion == "SIN DATOS"
        assert "AAPL" in f.resumen

    def test_dcf_none_degrada_solo_esa_seccion(self, todo_ok, monkeypatch):
        monkeypatch.setattr(ft, "calcular_dcf", lambda t, snap=None: None)
        f = ft.generar_ficha_ticker("AAPL")
        assert not f.valuacion_dcf.ok
        assert f.multifactor.ok                  # el resto sigue vivo
        assert f.cobertura == "4/5"
        assert "flujo de caja" in f.valuacion_dcf.explicacion

    def test_comparables_sin_benchmark(self, todo_ok, monkeypatch):
        monkeypatch.setattr(
            ft, "comparar_vs_industria",
            lambda s, i, sec=None: {"fuente": "—", "metricas": {}},
        )
        f = ft.generar_ficha_ticker("AAPL")
        assert not f.comparables.ok
        assert f.cobertura == "4/5"

    def test_tension_dcf_sobrevaluada_vs_comprar(self, todo_ok, monkeypatch):
        monkeypatch.setattr(
            ft, "calcular_dcf",
            lambda t, snap=None: DCFFake(
                ticker=t, valor_intrinseco_usd=150.0,
                margen_seguridad_pct=-25.0, recomendacion_dcf="SOBREVALUADA",
            ),
        )
        f = ft.generar_ficha_ticker("AAPL")
        assert "sobrevaluada" in f.resumen.lower()
        assert "escalonado" in f.resumen


# ─── Renta fija y desconocidos ────────────────────────────────────────────────

class TestCasosEspeciales:
    def test_rf_no_aplica_y_deriva_a_ficha_rf(self):
        from core.renta_fija_ar import INSTRUMENTOS_RF

        rf = next(iter(INSTRUMENTOS_RF))
        f = ft.generar_ficha_ticker(rf)
        assert f.identidad.ok
        assert f.identidad.datos["es_renta_fija"]
        assert f.recomendacion == "VER FICHA RF"
        assert not f.multifactor.ok

    def test_ticker_desconocido(self, todo_ok):
        f = ft.generar_ficha_ticker("ZZZNOEXISTE")
        assert not f.identidad.ok
        assert "no está en el universo" in f.resumen

    def test_ticker_vacio(self, todo_ok):
        f = ft.generar_ficha_ticker("")
        assert not f.identidad.ok


# ─── Export HTML ──────────────────────────────────────────────────────────────

class TestFichaHtml:
    def test_html_completo_standalone(self, todo_ok):
        f = ft.generar_ficha_ticker("AAPL")
        html = ft.ficha_ticker_html(f)
        assert html.startswith("<!DOCTYPE html>")
        assert "AAPL" in html
        assert "COMPRAR" in html
        assert "72/100" in html
        assert "no constituye recomendación" in html

    def test_html_escapa_contenido(self, todo_ok, monkeypatch):
        # Un nombre con HTML malicioso no debe inyectarse crudo
        f = ft.generar_ficha_ticker("AAPL")
        f.identidad.datos["nombre"] = "<script>alert(1)</script>"
        html = ft.ficha_ticker_html(f)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_ficha_degradada_sale_igual(self, monkeypatch):
        monkeypatch.setattr(
            ft, "obtener_fundamentales",
            lambda t, force_refresh=False: (_ for _ in ()).throw(RuntimeError("x")),
        )
        f = ft.generar_ficha_ticker("AAPL")
        html = ft.ficha_ticker_html(f)
        assert "SIN DATOS" in html
        assert "1/5" in html
