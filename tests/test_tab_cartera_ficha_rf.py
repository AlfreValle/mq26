"""Helpers P2-RF-01 en tab_cartera (sin ejecutar Streamlit)."""
from __future__ import annotations

import pandas as pd
import pytest

from ui.tab_cartera import _paridad_implicita_pct_on_usd_desde_fila


def test_paridad_implicita_on_usd_sin_escala_usa_px_sobre_ccl():
    row = pd.Series({"TIPO": "ON_USD", "PRECIO_ARS": 150_000.0, "ESCALA_PRECIO_RF": ""})
    assert _paridad_implicita_pct_on_usd_desde_fila(row, 1500.0) == pytest.approx(100.0)


def test_paridad_implicita_on_usd_con_escala_multiplica_px_por_100():
    row = pd.Series(
        {"TIPO": "ON_USD", "PRECIO_ARS": 1000.0, "ESCALA_PRECIO_RF": "÷100 vs PPC"}
    )
    assert _paridad_implicita_pct_on_usd_desde_fila(row, 1500.0) == pytest.approx(66.67, abs=0.01)


def test_paridad_implicita_no_on_usd_devuelve_none():
    row = pd.Series({"TIPO": "LETRA", "PRECIO_ARS": 100.0, "ESCALA_PRECIO_RF": ""})
    assert _paridad_implicita_pct_on_usd_desde_fila(row, 1500.0) is None


def test_paridad_implicita_ccl_cero_none():
    row = pd.Series({"TIPO": "ON_USD", "PRECIO_ARS": 100.0, "ESCALA_PRECIO_RF": ""})
    assert _paridad_implicita_pct_on_usd_desde_fila(row, 0.0) is None
