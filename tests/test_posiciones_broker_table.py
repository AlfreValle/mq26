"""Tabla broker: columnas de tenencia condicionadas a fechas de compra."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ui.posiciones_broker_table import build_posiciones_broker_html


def _fila_base(**kwargs):
    row = {
        "TICKER": "TEST",
        "CANTIDAD_TOTAL": 10.0,
        "PRECIO_ARS": 100.0,
        "PESO_PCT": 0.1,
        "PPC_ARS": 90.0,
        "VALOR_ARS": 1000.0,
        "INV_ARS": 900.0,
        "PNL_ARS": 100.0,
        "PNL_PCT": 100.0 / 900.0,
        "PNL_PCT_USD": 0.05,
    }
    row.update(kwargs)
    return row


def test_sin_fechas_oculta_columnas_tenencia():
    df = pd.DataFrame([_fila_base()])
    html = build_posiciones_broker_html(df, group_rf_rv=False)
    assert html is not None
    assert "<th>1ª compra</th>" not in html
    assert "<th>Tasa anual posición*</th>" not in html
    assert "FECHA_COMPRA" in html  # nota: cómo habilitar la métrica


def test_con_fecha_muestra_columnas_tenencia():
    hace = date.today() - timedelta(days=400)
    df = pd.DataFrame([_fila_base(FECHA_COMPRA=hace)])
    html = build_posiciones_broker_html(df, group_rf_rv=False)
    assert html is not None
    assert "<th>1ª compra</th>" in html
    assert "<th>Tasa anual posición*</th>" in html


def test_tasa_anual_corto_plazo_no_muestra_explosivos():
    hace = date.today() - timedelta(days=3)
    # +30% en 3 días genera anualizado astronómico; debe mostrarse como "—".
    df = pd.DataFrame([_fila_base(FECHA_COMPRA=hace, PNL_PCT=0.30)])
    html = build_posiciones_broker_html(df, group_rf_rv=False)
    assert html is not None
    assert ">—<" in html

