"""Tests core/rebalanceo.py — comparar holdings vs cartera óptima → órdenes."""
from __future__ import annotations

from core.rebalanceo import (
    TipoOrden,
    calcular_ordenes_rebalanceo,
    ordenes_a_dataframe,
    resumen_rebalanceo,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

ACTUALES = {"AAPL": 30.0, "MSFT": 25.0, "GOOG": 20.0, "AMZN": 15.0, "META": 10.0}
OBJETIVO = {"AAPL": 20.0, "MSFT": 30.0, "GOOG": 20.0, "AMZN": 20.0, "META":  5.0, "NVDA": 5.0}
CAPITAL   = 1_000_000.0
CCL        = 1_200.0


# ─── Tests básicos ────────────────────────────────────────────────────────────

def test_resultado_tipo_correcto():
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
    )
    assert res.n_compras + res.n_ventas + res.n_holds == len(res.ordenes)
    assert res.capital_total_ars == CAPITAL
    assert res.ccl == CCL


def test_compra_venta_correctos():
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.0,
    )
    for orden in res.ordenes:
        if orden.tipo == TipoOrden.COMPRA:
            assert orden.delta_peso > 0
        elif orden.tipo == TipoOrden.VENTA:
            assert orden.delta_peso < 0
        elif orden.tipo == TipoOrden.HOLD:
            assert abs(orden.delta_peso) < 1e-9


def test_ticker_nuevo_y_eliminado():
    # NVDA no está en actuales → nuevo; META no está en objetivo con 0 peso en obj → eliminado
    objetivo_sin_meta = {k: v for k, v in OBJETIVO.items() if k != "META"}
    res = calcular_ordenes_rebalanceo(
        ACTUALES, objetivo_sin_meta,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.0,
    )
    assert "NVDA" in res.tickers_nuevos
    assert "META" in res.tickers_eliminados


def test_banda_tolerancia_genera_holds():
    # Con banda 5 %, los deltas pequeños deberían ser HOLD
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.05,
    )
    for orden in res.ordenes:
        if abs(orden.delta_peso) < 0.05:
            assert orden.tipo == TipoOrden.HOLD


def test_montos_positivos():
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
    )
    for orden in res.ordenes:
        assert orden.monto_ars >= 0
        assert orden.monto_usd >= 0


def test_costo_estimado():
    bps = 50.0
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
        costo_transaccion_bps=bps,
        banda_tolerancia=0.0,
    )
    for orden in res.ordenes:
        expected_costo = abs(orden.delta_peso) * CAPITAL * (bps / 10_000)
        assert abs(orden.costo_estimado - expected_costo) < 0.01


def test_monto_neto_menor_que_bruto():
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.0,
    )
    for orden in res.ordenes:
        assert orden.monto_neto_ars <= orden.monto_ars + 1e-9


def test_prioridad_valores_validos():
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
    )
    for orden in res.ordenes:
        assert orden.prioridad in (1, 2, 3)


def test_turnover_cero_cuando_identicos():
    pesos = {"A": 40.0, "B": 30.0, "C": 30.0}
    res = calcular_ordenes_rebalanceo(
        pesos, pesos,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.0,
    )
    assert res.turnover_bruto < 1e-9
    assert res.n_ventas == 0
    assert res.n_compras == 0


def test_pesos_en_fraccion_y_porcentaje_equivalentes():
    pesos_frac = {"A": 0.4, "B": 0.3, "C": 0.3}
    pesos_pct  = {"A": 40.0, "B": 30.0, "C": 30.0}
    res_f = calcular_ordenes_rebalanceo(pesos_frac, pesos_frac, capital_total_ars=CAPITAL, ccl=CCL, banda_tolerancia=0.0)
    res_p = calcular_ordenes_rebalanceo(pesos_pct,  pesos_pct,  capital_total_ars=CAPITAL, ccl=CCL, banda_tolerancia=0.0)
    assert abs(res_f.turnover_bruto - res_p.turnover_bruto) < 1e-9


def test_orden_ventas_primero():
    """Las ventas deben aparecer antes que las compras en la lista."""
    res = calcular_ordenes_rebalanceo(
        ACTUALES, OBJETIVO,
        capital_total_ars=CAPITAL, ccl=CCL,
        banda_tolerancia=0.0,
    )
    tipos = [o.tipo for o in res.ordenes if o.tipo != TipoOrden.HOLD]
    ventas = [t for t in tipos if t == TipoOrden.VENTA]
    compras = [t for t in tipos if t == TipoOrden.COMPRA]
    if ventas and compras:
        ultimo_venta  = max(i for i, t in enumerate(tipos) if t == TipoOrden.VENTA)
        primer_compra = min(i for i, t in enumerate(tipos) if t == TipoOrden.COMPRA)
        assert ultimo_venta < primer_compra


def test_resumen_dict_tiene_claves():
    res = calcular_ordenes_rebalanceo(ACTUALES, OBJETIVO, capital_total_ars=CAPITAL, ccl=CCL)
    s = resumen_rebalanceo(res)
    for k in ("n_compras", "n_ventas", "n_holds", "turnover_bruto_pct", "costo_total_ars"):
        assert k in s


def test_ordenes_a_dataframe():
    res = calcular_ordenes_rebalanceo(ACTUALES, OBJETIVO, capital_total_ars=CAPITAL, ccl=CCL)
    df = ordenes_a_dataframe(res)
    assert len(df) == len(res.ordenes)
    assert "ticker" in df.columns
    assert "tipo" in df.columns


def test_cartera_vacia_no_falla():
    res = calcular_ordenes_rebalanceo({}, {"A": 100.0}, capital_total_ars=CAPITAL, ccl=CCL)
    assert res.n_compras >= 0


def test_ccl_afecta_monto_usd():
    res1 = calcular_ordenes_rebalanceo(ACTUALES, OBJETIVO, capital_total_ars=CAPITAL, ccl=1000.0, banda_tolerancia=0.0)
    res2 = calcular_ordenes_rebalanceo(ACTUALES, OBJETIVO, capital_total_ars=CAPITAL, ccl=2000.0, banda_tolerancia=0.0)
    for o1, o2 in zip(res1.ordenes, res2.ordenes, strict=True):
        if o1.monto_ars > 0:
            assert abs(o2.monto_usd - o1.monto_usd / 2) < 0.01
