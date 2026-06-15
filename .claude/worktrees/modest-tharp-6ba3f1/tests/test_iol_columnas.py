"""
Verifica que parsear_iol() retorna columnas estándar (TICKER, CANTIDAD, TIPO).
Evita regresión a alias mixtos (Ticker / Cantidad).
"""
from __future__ import annotations

import pandas as pd


def _df_iol() -> pd.DataFrame:
    return pd.DataFrame({
        "Especie": ["AAPL", "TLCTO"],
        "Cantidad": [10, 5000],
        "Precio promedio": [850.0, 102.5],
    })


def test_parsear_iol_columna_TICKER_mayuscula():
    """IOL debe retornar 'TICKER' no 'Ticker'."""
    from broker_importer import parsear_iol

    r = parsear_iol(_df_iol(), ccl=1150.0)
    assert "TICKER" in r.columns, f"Columna TICKER faltante. Columnas: {list(r.columns)}"
    assert "Ticker" not in r.columns, "Columna 'Ticker' (mixed case) no debe existir"


def test_parsear_iol_columna_CANTIDAD_mayuscula():
    from broker_importer import parsear_iol

    r = parsear_iol(_df_iol(), ccl=1150.0)
    assert "CANTIDAD" in r.columns


def test_parsear_iol_columna_TIPO_mayuscula():
    from broker_importer import parsear_iol

    r = parsear_iol(_df_iol(), ccl=1150.0)
    assert "TIPO" in r.columns


def test_parsear_iol_schema_completo():
    from broker_importer import parsear_iol

    cols_req = {
        "CARTERA",
        "FECHA_COMPRA",
        "TICKER",
        "CANTIDAD",
        "PPC_USD",
        "PPC_ARS",
        "TIPO",
        "Broker",
    }
    r = parsear_iol(_df_iol(), ccl=1150.0)
    faltantes = cols_req - set(r.columns)
    assert not faltantes, f"Columnas faltantes: {faltantes}"


def test_parsear_iol_normaliza_a_comprobante_con_ticker():
    """El pipeline interno expone Ticker/Cantidad para import y maestra."""
    import broker_importer as bi
    from broker_importer import parsear_iol

    df = parsear_iol(_df_iol(), ccl=1150.0).copy()
    df["Propietario"] = "Test"
    df["Cartera"] = "C | IOL"
    out = bi._dataframe_comprobante_final([df], "Test", "C | IOL")
    assert "Ticker" in out.columns
    assert len(out) == 2
