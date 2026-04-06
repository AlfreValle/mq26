"""tests/test_diagnostico_cartera.py — Motor diagnóstico S5 (datos sintéticos)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.diagnostico_types import Semaforo
from services.diagnostico_cartera import diagnosticar


def _row(ticker, valor, peso_frac=None, tipo="CEDEAR", fecha=None):
    r = {
        "TICKER": ticker,
        "VALOR_ARS": float(valor),
        "TIPO": tipo,
        "FECHA_COMPRA": fecha or date.today() - timedelta(days=200),
    }
    if peso_frac is not None:
        r["PESO_PCT"] = peso_frac
    return r


def test_diagnostico_cartera_conservadora_deficiente():
    df = pd.DataFrame(
        [
            _row("NVDA", 100_000, 1.0, fecha=date.today() - timedelta(days=400)),
        ]
    )
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.02}
    r = diagnosticar(
        df_ag=df,
        perfil="Conservador",
        horizonte_label="3 años",
        metricas=m,
        ccl=1000.0,
        universo_df=None,
        senales_salida=None,
    )
    assert r.semaforo == Semaforo.ROJO
    assert r.score_total < 60.0
    assert r.pct_defensivo_actual < 0.01


def test_diagnostico_cartera_bien_balanceada():
    # 60% defensivo (GLD+KO+BRKB), sin concentración >20% (Conservador)
    df = pd.DataFrame(
        [
            _row("GLD", 120_000, 0.20),
            _row("KO", 120_000, 0.20),
            _row("BRKB", 120_000, 0.20),
            _row("SPY", 120_000, 0.20),
            _row("MSFT", 120_000, 0.20),
        ]
    )
    m = {"total_valor": 600_000.0, "pnl_pct_total_usd": 0.04}
    r = diagnosticar(
        df_ag=df,
        perfil="Conservador",
        horizonte_label="3 años",
        metricas=m,
        ccl=1000.0,
    )
    assert r.semaforo == Semaforo.VERDE
    assert r.score_cobertura_defensiva >= 99.0
    assert r.score_concentracion >= 99.0


def test_ajuste_horizonte_corto():
    df = pd.DataFrame([_row("SPY", 100_000, 1.0)])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="3 meses",
        metricas=m,
        ccl=1000.0,
    )
    assert abs(r.pct_defensivo_requerido - 0.50) < 1e-6


def test_concentracion_detecta_activo_sobre_limite():
    df = pd.DataFrame(
        [
            _row("NVDA", 400_000, 0.40),
            _row("MSFT", 600_000, 0.60),
        ]
    )
    m = {"total_valor": 1_000_000.0, "pnl_pct_total_usd": 0.05}
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
    )
    assert r.score_concentracion < 75.0
    assert any(o.dimension == "concentracion" for o in r.observaciones)


def test_observaciones_tienen_cifras_concretas():
    df = pd.DataFrame([_row("MELI", 100_000, 1.0)])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": -0.05}
    r = diagnosticar(
        df_ag=df,
        perfil="Conservador",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
    )
    for o in r.observaciones:
        assert o.cifra_clave and str(o.cifra_clave).strip()


def test_score_total_es_promedio_ponderado():
    df = pd.DataFrame([_row("GLD", 50_000, 0.5), _row("KO", 50_000, 0.5)])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    senales = [{"prioridad": 3}, {"prioridad": 2}]
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
        senales_salida=senales,
    )
    d1 = r.score_cobertura_defensiva
    d2 = r.score_concentracion
    d3 = r.score_rendimiento
    d4 = r.score_senales_salida
    esperado = 0.35 * d1 + 0.25 * d2 + 0.20 * d3 + 0.20 * d4
    assert abs(r.score_total - esperado) < 0.05


def test_letra_no_cuenta_como_defensivo():
    df = pd.DataFrame(
        [
            {"TICKER": "S17A6", "VALOR_ARS": 50_000.0, "TIPO": "LETRA", "PESO_PCT": 0.5},
            {"TICKER": "SPY", "VALOR_ARS": 50_000.0, "TIPO": "CEDEAR", "PESO_PCT": 0.5},
        ]
    )
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
        universo_df=None,
    )
    assert r.pct_defensivo_actual == pytest.approx(0.0, abs=0.02)


def test_activo_on_cuenta_como_defensivo():
    df = pd.DataFrame([{"TICKER": "GD30", "VALOR_ARS": 100_000.0, "TIPO": "ON", "PESO_PCT": 1.0}])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
    )
    assert r.pct_defensivo_actual >= 0.99


def test_diagnostico_sin_posiciones():
    r = diagnosticar(
        df_ag=pd.DataFrame(),
        perfil="Moderado",
        horizonte_label="3 años",
        metricas={},
        ccl=1150.0,
        universo_df=None,
        senales_salida=None,
    )
    assert r.score_total < 60.0
    assert len(r.observaciones) >= 1


def test_diagnostico_metricas_vacias_fallback():
    df = pd.DataFrame([_row("GLD", 80_000, 0.8), _row("SPY", 20_000, 0.2)])
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas={},
        ccl=500.0,
    )
    assert r.modo_fallback is True
    assert r.n_posiciones == 2
