"""Tests del parser IOL en broker_importer."""
from __future__ import annotations

import pandas as pd


def _df_iol_muestra() -> pd.DataFrame:
    """Simula el formato de exportación de IOL."""
    return pd.DataFrame({
        "Especie": ["AAPL", "GLD", "AL30"],
        "Cantidad": [10, 2, 5000],
        "Precio promedio": [850.0, 2100.0, 63.5],
        "Precio actual": [870.0, 2150.0, 65.0],
        "Variación": ["+2.3%", "+2.4%", "+2.4%"],
    })


def test_detectar_formato_iol():
    from broker_importer import detectar_formato

    df = _df_iol_muestra()
    assert detectar_formato(df) == "iol"


def test_parsear_iol_retorna_filas():
    from broker_importer import parsear_iol

    df = _df_iol_muestra()
    result = parsear_iol(df, ccl=1150.0)
    assert len(result) == 3
    assert "TICKER" in result.columns
    assert "CANTIDAD" in result.columns


def test_parsear_iol_ticker_correcto():
    from broker_importer import parsear_iol

    df = _df_iol_muestra()
    result = parsear_iol(df, ccl=1150.0)
    assert "AAPL" in result["TICKER"].values
    assert "GLD" in result["TICKER"].values


def test_parsear_iol_df_vacio_no_rompe():
    from broker_importer import parsear_iol

    result = parsear_iol(pd.DataFrame(), ccl=1150.0)
    assert result.empty or len(result) == 0


def test_parsear_iol_cantidad_correcta():
    from broker_importer import parsear_iol

    df = _df_iol_muestra()
    result = parsear_iol(df, ccl=1150.0)
    aapl = result[result["TICKER"] == "AAPL"].iloc[0]
    assert float(aapl["CANTIDAD"]) == 10.0
