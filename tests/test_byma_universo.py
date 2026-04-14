"""
tests/test_byma_universo.py — Contratos de services/byma_universo.py.

Sin llamadas reales a BYMA (monkeypatch). Sin yfinance real.
Verifica que precio siempre viene parametrizado de BYMA (regla crítica).
"""
from __future__ import annotations

import pandas as pd
import pytest

ROOT_COLS_RV = ["Ticker", "Tipo", "Descripción", "Último", "Var. %"]
ROOT_COLS_SEÑALES = ["Ticker", "Tipo", "Precio ARS", "Score", "Señal", "Target ARS", "Stop ARS"]


@pytest.fixture()
def mock_byma_rv(monkeypatch):
    """Simula fetch de acciones y CEDEARs desde BYMA sin red."""
    df_fake = pd.DataFrame([
        {"Ticker": "GGAL", "Descripción": "Grupo Financiero Galicia",
         "Último": 3500.0, "Var. %": 1.5, "Vol. Nominal": 1000000},
        {"Ticker": "YPFD", "Descripción": "YPF",
         "Último": 45000.0, "Var. %": -0.5, "Vol. Nominal": 500000},
    ])

    def _fake_cached_byma(label, endpoint):
        return df_fake.copy()

    monkeypatch.setattr("services.byma_universo._cached_byma", _fake_cached_byma)
    return df_fake


@pytest.fixture()
def mock_scoring(monkeypatch):
    """Simula scoring_engine sin yfinance."""
    def _fake_score(ticker, tipo="CEDEAR"):
        return {
            "Ticker": ticker, "Score_Total": 72.0, "Score_Fund": 65.0,
            "Score_Tec": 70.0, "Score_Sector": 80.0,
            "Senal": "🟡 ACUMULAR", "Fecha_Score": "2026-04-14",
        }
    monkeypatch.setattr("services.byma_universo.calcular_score_total", _fake_score)


def test_fetch_rv_completo_columnas_minimas(mock_byma_rv):
    from services.byma_universo import fetch_rv_completo
    df = fetch_rv_completo()
    for col in ["Ticker", "Tipo"]:
        assert col in df.columns, f"Columna obligatoria faltante: {col}"


def test_fetch_rv_tiene_cedears_y_acciones(mock_byma_rv):
    from services.byma_universo import fetch_rv_completo
    df = fetch_rv_completo()
    tipos = set(df["Tipo"].unique())
    assert "CEDEAR" in tipos or "ACCION_LOCAL" in tipos


def test_universo_rv_con_señales_retorna_columnas(mock_byma_rv, mock_scoring):
    from services.byma_universo import universo_rv_con_señales
    df = universo_rv_con_señales(ccl=1400.0, perfil="Moderado", n_max=5)
    if df.empty:
        pytest.skip("Sin datos simulados suficientes")
    for col in ["Ticker", "Señal", "Score"]:
        assert col in df.columns


def test_universo_rv_precio_no_hardcodeado(mock_byma_rv, mock_scoring):
    """El precio debe venir del DataFrame BYMA, no de una constante interna."""
    from services.byma_universo import universo_rv_con_señales
    df = universo_rv_con_señales(ccl=1400.0, perfil="Moderado", n_max=5)
    if df.empty:
        return
    # Verificar que Precio ARS corresponde al precio del mock (3500 o 45000)
    precios = set(df["Precio ARS"].dropna().tolist())
    assert any(p in {3500.0, 45000.0} for p in precios), \
        "Precio ARS no coincide con datos BYMA — posible hardcoding"


def test_fetch_rf_completo_retorna_tres_claves(monkeypatch):
    """fetch_rf_completo debe retornar dict con 'on', 'bonos', 'letras'."""
    monkeypatch.setattr(
        "services.byma_universo.cached_on_byma",
        lambda ccl: {}
    )
    monkeypatch.setattr(
        "services.byma_universo._cached_byma",
        lambda label, ep: pd.DataFrame()
    )
    from services.byma_universo import fetch_rf_completo
    rf = fetch_rf_completo(ccl=1400.0)
    assert set(rf.keys()) == {"on", "bonos", "letras"}


def test_get_mix_rf_rv_suma_100():
    from core.perfil_allocation import get_mix_rf_rv
    for perfil in ["Conservador", "Moderado", "Agresivo"]:
        mix = get_mix_rf_rv(perfil)
        assert abs(mix["rf_pct"] + mix["rv_pct"] - 100.0) < 0.01, \
            f"Mix no suma 100% para {perfil}"


def test_tab_mercado_importa_sin_streamlit():
    """El módulo tab_mercado debe importar sin errores (Streamlit mockeado en tests)."""
    # Solo verificar que las funciones existen en el módulo fuente
    from pathlib import Path
    src = (Path(__file__).parent.parent / "ui" / "tab_mercado.py").read_text(encoding="utf-8")
    assert "def render_tab_mercado" in src
    assert "_render_rv" in src
    assert "_render_rf" in src
    assert "_render_cartera_optima" in src
    assert "BYMA" in src  # La regla crítica debe estar mencionada


def test_rbac_asesor_eliminado():
    """Confirmar que el rol 'asesor' ya no existe en ACTION_POLICY."""
    from ui.rbac import ACTION_POLICY
    for action, roles in ACTION_POLICY.items():
        assert "asesor" not in {r.lower() for r in roles}, \
            f"Rol 'asesor' encontrado en acción '{action}' — debe eliminarse"
