"""tests/test_analizador_ticker.py — Analizador Elite por Ticker & Gem Detector."""
from __future__ import annotations

import pytest

from services.analizador_ticker import (
    AnalizadorResult,
    GemRating,
    _calcular_gem_score,
    _determinar_gem_rating,
    analizar_ticker,
    buscar_perlas_rapido,
)

# ─── Tests unitarios del Gem Score (sin red de) ───────────────────────────────

def _gem_base(**overrides):
    """Parámetros base para _calcular_gem_score con todos los campos."""
    defaults = dict(
        score_mq26=65.0,
        precio_actual=100.0,
        precio_52w_high=140.0,      # 28% descuento
        fcf_yield_pct=4.5,
        moat=2,
        ciclo_sector="expansion",
        upside_pct=25.0,
        consensus_rating="buy",
        rsi=45.0,
        macd=0.5,
        macd_signal=0.3,
        revenue_growth_pct=15.0,
        roe_pct=18.0,
        pe_ratio=18.0,
        hv20=22.0,
        max_dd_1y=18.0,
        revenue_ttm_m=5000.0,
        fcf_ttm_m=800.0,
        debt_to_equity=40.0,
        market_cap_m=50_000.0,
    )
    defaults.update(overrides)
    return defaults


def test_gem_score_perla_tipica():
    """Activo de calidad con todos los indicadores positivos debe superar 70."""
    gem, reasons, flags = _calcular_gem_score(**_gem_base())
    assert gem >= 70, f"Perla típica debería superar 70, got {gem}"
    assert len(reasons) >= 3, "Debe haber al menos 3 razones positivas"
    assert not any("FCF negativo" in f for f in flags)


def test_gem_score_baja_con_fcf_negativo():
    """FCF negativo penaliza el gem score."""
    gem_pos, _, _    = _calcular_gem_score(**_gem_base())
    gem_neg, _, flags = _calcular_gem_score(**_gem_base(fcf_ttm_m=-200.0, fcf_yield_pct=-1.5))
    assert gem_neg < gem_pos, "FCF negativo debe bajar el score"
    assert any("FCF negativo" in f for f in flags)


def test_gem_score_cero_con_todo_malo():
    """Activo deteriorado: revenue cayendo, FCF negativo, RSI alto, sin moat."""
    gem, _, flags = _calcular_gem_score(**_gem_base(
        score_mq26=28.0,
        fcf_yield_pct=-3.0,
        fcf_ttm_m=-500.0,
        moat=0,
        ciclo_sector="contraction",
        upside_pct=-15.0,
        consensus_rating="sell",
        rsi=80.0,
        macd=-0.5,
        macd_signal=0.2,
        revenue_growth_pct=-12.0,
        roe_pct=-8.0,
        hv20=70.0,
        max_dd_1y=55.0,
        debt_to_equity=280.0,
    ))
    assert gem <= 20, f"Activo deteriorado no debería superar 20, got {gem}"
    assert len(flags) >= 3


def test_gem_score_nunca_supera_100():
    """El gem score nunca puede superar 100."""
    gem, _, _ = _calcular_gem_score(**_gem_base(
        score_mq26=95.0,
        fcf_yield_pct=15.0,
        moat=3,
        upside_pct=60.0,
        consensus_rating="strong_buy",
        rsi=38.0,
        macd=1.0,
        macd_signal=0.5,
        revenue_growth_pct=35.0,
        roe_pct=45.0,
        pe_ratio=8.0,
        precio_52w_high=200.0,
        precio_actual=120.0,
    ))
    assert gem <= 100.0


def test_gem_rating_perla():
    rating = _determinar_gem_rating(
        gem_score=75.0, red_flags=[], score_mq26=70.0,
        fcf_ttm_m=500.0, debt_to_equity=30.0, hv20=18.0,
    )
    assert rating == GemRating.PERLA


def test_gem_rating_trampa_valor():
    """Score MQ26 OK pero FCF negativo + deuda alta = trampa."""
    flags = ["FCF negativo: -$300M", "ROE negativo (-5%)", "revenue cayendo -8%"]
    rating = _determinar_gem_rating(
        gem_score=45.0, red_flags=flags, score_mq26=55.0,
        fcf_ttm_m=-300.0, debt_to_equity=180.0, hv20=30.0,
    )
    assert rating == GemRating.TRAMPA


def test_gem_rating_evitar():
    rating = _determinar_gem_rating(
        gem_score=20.0, red_flags=["x","y","z"], score_mq26=35.0,
        fcf_ttm_m=-100.0, debt_to_equity=50.0, hv20=40.0,
    )
    assert rating == GemRating.EVITAR


def test_gem_rating_interesante():
    rating = _determinar_gem_rating(
        gem_score=58.0, red_flags=[], score_mq26=60.0,
        fcf_ttm_m=200.0, debt_to_equity=50.0, hv20=20.0,
    )
    assert rating == GemRating.INTERESANTE


# ─── Test AnalizadorResult básico ────────────────────────────────────────────

def test_analizador_result_to_dict():
    """to_dict() debe convertir GemRating a string."""
    r = AnalizadorResult(ticker="TEST", gem_rating=GemRating.PERLA)
    d = r.to_dict()
    assert d["gem_rating"] == "💎 PERLA"
    assert isinstance(d["gem_reasons"], list)


def test_analizador_result_resumen_texto():
    """resumen_texto() no debe lanzar excepción."""
    r = AnalizadorResult(
        ticker="MSFT", tipo="CEDEAR", sector="Tecnología",
        precio_actual=400.0, precio_52w_high=500.0, precio_52w_low=300.0,
        score_total=78.0, score_fundamental=75.0, score_tecnico=72.0, score_sector=80.0,
        moat=3, moat_bonus=5.0, rsi=48.0, hv20=18.0, max_dd_1y=15.0,
        fcf_yield_pct=3.5, roe_pct=35.0, pe_ratio=30.0, revenue_growth_pct=12.0,
        gem_rating=GemRating.PERLA, gem_score=78.0,
        gem_reasons=["FCF Yield sólido", "Moat muy amplio"],
        red_flags=[],
        senal="🟢 COMPRAR",
    )
    texto = r.resumen_texto()
    assert "MSFT" in texto
    assert "PERLA" in texto
    assert "78" in texto


# ─── Test integración (usa yfinance — puede ser lento) ───────────────────────

@pytest.mark.integration
def test_analizar_ticker_brkb():
    """
    Prueba integración real con BRKB — activo de alta calidad.
    Debe tener score > 55 y moat ≥ 2.
    """
    r = analizar_ticker("BRKB", tipo="CEDEAR")
    assert r.ticker == "BRKB"
    assert r.score_total > 0.0
    assert r.moat >= 2, f"BRKB debería tener moat ≥ 2, got {r.moat}"
    assert r.gem_rating in (GemRating.PERLA, GemRating.INTERESANTE, GemRating.NEUTRAL)
    assert r.fecha_analisis != ""


@pytest.mark.integration
def test_analizar_ticker_devuelve_estructura_completa():
    """Verifica que todos los campos clave están presentes y tienen tipos correctos."""
    r = analizar_ticker("AAPL")
    assert isinstance(r.gem_score, float)
    assert isinstance(r.gem_reasons, list)
    assert isinstance(r.red_flags, list)
    assert isinstance(r.gem_rating, GemRating)
    assert 0.0 <= r.gem_score <= 100.0
    assert 0.0 <= r.score_total <= 100.0
    d = r.to_dict()
    assert "gem_rating" in d
    assert isinstance(d["gem_rating"], str)


@pytest.mark.integration
def test_buscar_perlas_rapido_retorna_dataframe():
    """Scanner rápido debe retornar DataFrame con columnas esperadas."""
    df = buscar_perlas_rapido(["MSFT", "KO"], min_gem_score=0.0)
    if not df.empty:
        assert "Ticker" in df.columns
        assert "Gem Score" in df.columns
        assert "Rating" in df.columns
        assert (df["Gem Score"] >= 0).all()
        assert (df["Gem Score"] <= 100).all()
