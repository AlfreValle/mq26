from __future__ import annotations

import pandas as pd

from core.unit_contracts import (
    enriquecer_ordenes_con_unidad,
    es_instrumento_rf_usd_paridad,
    validar_dataframe_ordenes_ejecucion,
    validar_escala_precio_vs_ppc_rf_usd,
    validar_fila_orden_ejecucion,
)


def test_es_rf_usd_paridad_por_tipo():
    assert es_instrumento_rf_usd_paridad("FOO", "ON_USD") is True
    assert es_instrumento_rf_usd_paridad("FOO", "ACCION_LOCAL") is False


def test_validar_escala_ok_paridad_similar():
    ok, msg = validar_escala_precio_vs_ppc_rf_usd("TLCTO", "ON_USD", 1520.0, 1500.0)
    assert ok is True
    assert msg == ""


def test_validar_escala_falla_ratio_100x():
    # Precio "por 100 VN" tratado como por 1 nominal → ~100× PPC
    ok, msg = validar_escala_precio_vs_ppc_rf_usd("TLCTO", "ON_USD", 150_000.0, 1500.0)
    assert ok is False
    assert "Escala inconsistente" in msg


def test_validar_escala_falla_precio_demasiado_bajo():
    ok, msg = validar_escala_precio_vs_ppc_rf_usd("TLCTO", "ON_USD", 1.0, 15000.0)
    assert ok is False
    assert "demasiado bajo" in msg


def test_validar_fila_con_df_ag():
    df_ag = pd.DataFrame(
        [
            {
                "TICKER": "TLCTO",
                "TIPO": "ON_USD",
                "PPC_ARS": 1500.0,
            }
        ]
    )
    ok, msg, lab = validar_fila_orden_ejecucion("TLCTO", 1520.0, df_ag)
    assert ok is True
    assert lab == "Nominales USD (VN)"


def test_validar_dataframe_ordenes_detecta_inconsistencia():
    df_ag = pd.DataFrame([{"TICKER": "TLCTO", "TIPO": "ON_USD", "PPC_ARS": 1500.0}])
    ordenes = pd.DataFrame(
        [{"ticker": "TLCTO", "tipo_op": "COMPRA", "precio_ars": 150_000.0, "nominales": 1}]
    )
    all_ok, msgs = validar_dataframe_ordenes_ejecucion(ordenes, df_ag)
    assert all_ok is False
    assert len(msgs) == 1


def test_enriquecer_ordenes_anade_unidad():
    df_ag = pd.DataFrame([{"TICKER": "SPY", "TIPO": "CEDEAR", "PPC_ARS": 100_000.0}])
    ordenes = pd.DataFrame([{"ticker": "SPY", "precio_ars": 500_000.0}])
    out = enriquecer_ordenes_con_unidad(ordenes, df_ag)
    assert "unidad_operativa" in out.columns
    assert "Nominales" in out["unidad_operativa"].iloc[0] or "acciones" in out["unidad_operativa"].iloc[0]
