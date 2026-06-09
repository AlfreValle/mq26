"""tests/test_diagnostico_cartera.py — Motor diagnóstico S5 (datos sintéticos)."""
from datetime import date, timedelta

import pandas as pd
import pytest

from core.diagnostico_types import Semaforo
from core.perfil_allocation import RULESET_VERSION
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
    # Conservador ~60% RF / ~40% RV; cada línea ≤20% (límite concentración)
    df = pd.DataFrame(
        [
            _row("PN43O", 200_000, 0.20, tipo="ON_USD"),
            _row("TLCTO", 200_000, 0.20, tipo="ON_USD"),
            _row("AL30", 200_000, 0.20, tipo="BONO_USD"),
            _row("SPY", 200_000, 0.20, tipo="CEDEAR"),
            _row("BRKB", 200_000, 0.20, tipo="CEDEAR"),
        ]
    )
    m = {"total_valor": 1_000_000.0, "pnl_pct_total_usd": 0.04}
    r = diagnosticar(
        df_ag=df,
        perfil="Conservador",
        horizonte_label="3 años",
        metricas=m,
        ccl=1000.0,
    )
    assert r.semaforo == Semaforo.VERDE
    assert r.score_cobertura_defensiva >= 95.0
    assert r.score_concentracion >= 99.0
    assert r.pct_defensivo_actual == pytest.approx(0.60, abs=0.02)


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
    assert abs(r.pct_defensivo_requerido - 0.60) < 1e-6


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
    assert r.score_concentracion <= 75.0
    assert r.score_concentracion < 100.0
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
    df = pd.DataFrame(
        [
            _row("PN43O", 50_000, 0.25, tipo="ON_USD"),
            _row("TLCTO", 50_000, 0.25, tipo="ON_USD"),
            _row("SPY", 50_000, 0.25, tipo="CEDEAR"),
            _row("MSFT", 50_000, 0.25, tipo="CEDEAR"),
        ]
    )
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


def test_letra_cuenta_como_renta_fija():
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
    assert r.pct_defensivo_actual == pytest.approx(0.5, abs=0.02)


def test_activo_bono_cuenta_como_rf():
    df = pd.DataFrame(
        [{"TICKER": "GD30", "VALOR_ARS": 100_000.0, "TIPO": "BONO_USD", "PESO_PCT": 1.0}]
    )
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
    assert r.ruleset_version == RULESET_VERSION


def test_diagnostico_cartera_casi_toda_rv():
    df = pd.DataFrame(
        [
            _row("NVDA", 95_000, 0.95),
            _row("PN43O", 5_000, 0.05, tipo="ON_USD"),
        ]
    )
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
    )
    assert r.pct_defensivo_actual < 0.15
    assert r.pct_rv_actual > 0.80


def test_diagnostico_cartera_casi_toda_rf():
    df = pd.DataFrame(
        [
            _row("PN43O", 400_000, 0.40, tipo="ON_USD"),
            _row("TLCTO", 400_000, 0.40, tipo="ON_USD"),
            _row("AL30", 200_000, 0.20, tipo="BONO_USD"),
        ]
    )
    m = {"total_valor": 1_000_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(
        df_ag=df,
        perfil="Arriesgado",
        horizonte_label="1 año",
        metricas=m,
        ccl=1000.0,
    )
    assert r.pct_defensivo_actual >= 0.99
    assert r.pct_rv_actual <= 0.05


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


def test_mix_objetivo_rf_no_penaliza_armado_coherente():
    """Perfil con RF teórica 30% pero cartera armada al ~47%: con mix_objetivo sube alineación."""
    df = pd.DataFrame(
        [
            _row("PN43O", 470_000, 0.47, tipo="ON_USD"),
            _row("SPY", 530_000, 0.53, tipo="CEDEAR"),
        ]
    )
    m = {"total_valor": 1_000_000.0, "pnl_pct_total_usd": 0.0}
    sin_plan = diagnosticar(df, "Muy arriesgado", "1 año", m, 1000.0)
    con_plan = diagnosticar(
        df, "Muy arriesgado", "1 año", m, 1000.0, mix_objetivo_rf=0.47
    )
    assert con_plan.score_cobertura_defensiva > sin_plan.score_cobertura_defensiva
    assert con_plan.pct_defensivo_requerido == pytest.approx(0.47)


def test_tres_lineas_peso_similar_no_dispara_concentracion():
    df = pd.DataFrame(
        [
            _row("A", 333_333, 1.0 / 3),
            _row("B", 333_333, 1.0 / 3),
            _row("C", 333_334, 1.0 / 3),
        ]
    )
    m = {"total_valor": 1_000_000.0, "pnl_pct_total_usd": 0.0}
    r = diagnosticar(df, "Moderado", "1 año", m, 1000.0)
    assert r.score_concentracion == pytest.approx(100.0)
    assert not any(o.dimension == "concentracion" for o in r.observaciones)


def test_cartera_comprada_hoy_ignora_senales_salida():
    df = pd.DataFrame([_row("NVDA", 100_000, 1.0, fecha=date.today())])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    senales = [{"prioridad": 3}]
    r = diagnosticar(
        df, "Moderado", "1 año", m, 1000.0, senales_salida=senales
    )
    assert r.score_senales_salida == pytest.approx(100.0)
    assert r.n_senales_salida_altas == 0


def test_senales_salida_none_equivale_vacio():
    df = pd.DataFrame([_row("SPY", 100_000, 1.0)])
    m = {"total_valor": 100_000.0, "pnl_pct_total_usd": 0.0}
    r_none = diagnosticar(df, "Moderado", "1 año", m, 1000.0, senales_salida=None)
    r_empty = diagnosticar(df, "Moderado", "1 año", m, 1000.0, senales_salida=[])
    assert r_none.score_total == pytest.approx(r_empty.score_total)
    assert r_none.score_senales_salida == pytest.approx(r_empty.score_senales_salida)
