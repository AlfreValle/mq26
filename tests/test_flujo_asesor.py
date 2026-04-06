"""
Tests de integración del flujo del asesor: diagnosticar → recomendar → informe.
"""
from __future__ import annotations

import pandas as pd


def _df_ag_moderado() -> pd.DataFrame:
    return pd.DataFrame({
        "TICKER": ["SPY", "MSFT", "GLD"],
        "CANTIDAD_TOTAL": [5, 10, 2],
        "PPC_USD_PROM": [400.0, 280.0, 180.0],
        "PRECIO_USD": [450.0, 320.0, 195.0],
        "VALOR_ARS": [2587500, 1840000, 449250],
        "INV_ARS": [2300000, 1624000, 414000],
        "PNL_ARS": [287500, 216000, 35250],
        "PNL_PCT": [0.125, 0.133, 0.085],
        "PNL_ARS_USD": [250.0, 187.8, 30.7],
        "PNL_PCT_USD": [0.109, 0.116, 0.074],
        "PESO_PCT": [52.9, 37.6, 9.5],
        "TIPO": ["CEDEAR", "CEDEAR", "CEDEAR"],
    })


def test_diagnosticar_cartera_moderada():
    from services.diagnostico_cartera import diagnosticar

    diag = diagnosticar(
        df_ag=_df_ag_moderado(),
        perfil="Moderado",
        horizonte_label="3 años",
        metricas={"pnl_pct_total_usd": 0.11},
        ccl=1150.0,
        universo_df=None,
        senales_salida=None,
    )
    assert 0 <= diag.score_total <= 100
    assert diag.semaforo is not None
    assert isinstance(diag.cliente_nombre, str)


def test_recomendar_con_capital_cero():
    from services.diagnostico_cartera import diagnosticar
    from services.recomendacion_capital import recomendar

    df = _df_ag_moderado()
    diag = diagnosticar(df, "Moderado", "3 años", {}, 1150.0, None, None)
    rr = recomendar(
        df_ag=df,
        perfil="Moderado",
        horizonte_label="3 años",
        capital_ars=0.0,
        ccl=1150.0,
        precios_dict={"SPY": 517500.0, "MSFT": 184000.0, "GLD": 224850.0},
        diagnostico=diag,
        universo_df=None,
    )
    assert rr is not None
    assert rr.capital_remanente_ars == 0.0


def test_generar_reporte_inversor_completo():
    from services.diagnostico_cartera import diagnosticar
    from services.recomendacion_capital import recomendar
    from services.reporte_inversor import generar_reporte_inversor

    df = _df_ag_moderado()
    diag = diagnosticar(
        df, "Moderado", "3 años", {"pnl_pct_total_usd": 0.11}, 1150.0, None, None
    )
    rr = recomendar(
        df,
        "Moderado",
        "3 años",
        150_000.0,
        1150.0,
        {"GLD": 224850.0, "KO": 9430.0},
        diag,
        None,
    )
    html = generar_reporte_inversor(
        diag, rr, {"pnl_pct_total_usd": 0.11, "total_valor": 4_875_750.0}
    )
    assert len(html) > 2000
    assert "MQ26" in html


def test_iol_parser_smoke():
    from broker_importer import detectar_formato, parsear_iol

    df_iol = pd.DataFrame({
        "Especie": ["AAPL", "GLD"],
        "Cantidad": [10, 2],
        "Precio promedio": [850.0, 2100.0],
    })
    assert detectar_formato(df_iol) == "iol"
    result = parsear_iol(df_iol, ccl=1150.0)
    assert len(result) == 2
    assert "AAPL" in result["Ticker"].values


def test_precio_on_estimado_desde_paridad():
    from unittest.mock import patch

    from services.cartera_service import resolver_precios

    with patch("services.cartera_service.PRECIOS_FALLBACK_ARS", {}):
        res = resolver_precios(["TLCTO"], {}, ccl=1150.0)
    assert res.get("TLCTO", 0) > 0
