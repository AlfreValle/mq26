"""Regresión del prefill de retiro: P&L total no es retorno anual."""
from __future__ import annotations

import pandas as pd
import pytest

from services.retiro_proyeccion import inputs_desde_cartera, proyeccion_clasica


def test_pnl_total_se_anualiza_no_se_usa_crudo():
    """+45% en 2,5 años → CAGR ~16%, no 45% compuesto 20 años (~89×)."""
    out = inputs_desde_cartera(
        {"pnl_pct_total_usd": 0.45, "valor_usd": 100_000},
        anios_tenencia=2.5,
    )
    esperado = 1.45 ** (1.0 / 2.5) - 1.0
    assert out["retorno_anual"] == pytest.approx(esperado, rel=1e-6)
    assert out["retorno_anual"] == pytest.approx(0.160, abs=0.005)
    assert out["retorno_fuente"] == "cagr"


def test_pnl_sin_tenencia_usa_default_8_no_el_acumulado():
    out = inputs_desde_cartera({"pnl_pct_total_usd": 0.45, "valor_usd": 100_000})
    assert out["retorno_anual"] == pytest.approx(0.08)
    assert out["retorno_fuente"] == "default_sin_tenencia"


def test_proyeccion_20a_no_explota_89x():
    inp = inputs_desde_cartera(
        {"pnl_pct_total_usd": 0.45, "valor_usd": 100_000},
        anios_tenencia=2.5,
    )
    r = proyeccion_clasica(100_000.0, 0.0, 20, inp["retorno_anual"])
    # CAGR ~16% → ~1.9M; el bug (1.45^20) daba ~168M
    assert 1_000_000 < r.capital_final < 5_000_000


def test_cagr_explicito_tiene_prioridad_sobre_pnl_total():
    out = inputs_desde_cartera(
        {"cagr": 0.10, "pnl_pct_total_usd": 0.45, "valor_usd": 50_000},
        anios_tenencia=2.5,
    )
    assert out["retorno_anual"] == pytest.approx(0.10)
    assert out["retorno_fuente"] == "cagr"


def test_hero_retiro_no_promete_certeza():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "ui" / "tab_retiro.py").read_text(
        encoding="utf-8"
    )
    assert "va a valer" not in src
    assert "podría valer" in src
    assert "proyección, no garantía" in src
    assert 'color:{_VERDE}">reales</b>' in src


def test_anios_tenencia_desde_df_ag():
    hace = pd.Timestamp.today().normalize() - pd.Timedelta(days=int(2.5 * 365.25))
    df = pd.DataFrame({"FECHA_PRIMERA_COMPRA": [hace, hace + pd.Timedelta(days=30)]})
    out = inputs_desde_cartera(
        {"pnl_pct_total_usd": 0.45, "valor_usd": 100_000},
        df_ag=df,
    )
    assert out["retorno_fuente"] == "cagr"
    assert out["retorno_anual"] == pytest.approx(1.45 ** (1.0 / 2.5) - 1.0, rel=0.02)


def test_pnl_total_mayor_a_100pct_no_se_divide_por_100():
    """+120% (fracción 1.2) en 2.5 años no es 1.2% anual."""
    out = inputs_desde_cartera(
        {"pnl_pct_total_usd": 1.2, "valor_usd": 100_000},
        anios_tenencia=2.5,
    )
    esperado = 2.2 ** (1.0 / 2.5) - 1.0
    assert out["retorno_anual"] == pytest.approx(esperado, rel=1e-6)
    assert out["retorno_anual"] > 0.05
    assert out["retorno_fuente"] == "cagr"
