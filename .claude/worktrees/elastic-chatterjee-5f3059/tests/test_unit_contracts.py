from __future__ import annotations

import pandas as pd

from core.unit_contracts import validar_contrato_unidades_posicion_neta


def test_contrato_unidades_ok_en_fraccion():
    df = pd.DataFrame(
        [
            {
                "PRECIO_ARS": 15000.0,
                "PPC_ARS": 12000.0,
                "VALOR_ARS": 150000.0,
                "INV_ARS": 120000.0,
                "PESO_PCT": 0.55,
                "MONEDA_PRECIO": "usd_mep",
            }
        ]
    )
    out, issues = validar_contrato_unidades_posicion_neta(df)
    assert issues == []
    assert bool(out["CONTRATO_UNIDADES_OK"].iloc[0]) is True
    assert out["MONEDA_PRECIO"].iloc[0] == "USD_MEP"


def test_contrato_unidades_detecta_peso_en_0_100():
    df = pd.DataFrame(
        [
            {
                "PRECIO_ARS": 100.0,
                "PPC_ARS": 90.0,
                "VALOR_ARS": 1000.0,
                "INV_ARS": 900.0,
                "PESO_PCT": 55.0,
            }
        ]
    )
    out, issues = validar_contrato_unidades_posicion_neta(df)
    assert any("PESO_PCT fuera de contrato" in x for x in issues)
    assert bool(out["CONTRATO_UNIDADES_OK"].iloc[0]) is False
