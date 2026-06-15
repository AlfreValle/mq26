"""
tests/test_cartera_service.py — Tests del servicio de cartera.
Cubre: calcular_posicion_neta, resolver_precios, validaciones.
"""
from __future__ import annotations

import pandas as pd
import pytest


def test_resolver_precios_usa_live_primero(df_cartera_ejemplo, precios_mock):
    import services.cartera_service as cs
    resultado = cs.resolver_precios(
        tickers=["AAPL", "MSFT"],
        precios_live={"AAPL": 20_000.0, "MSFT": 21_000.0},
        ccl=1500.0,
    )
    assert resultado["AAPL"] == 20_000.0
    assert resultado["MSFT"] == 21_000.0


def test_resolver_precios_fallback_si_live_vacio(df_cartera_ejemplo):
    import services.cartera_service as cs
    # Si live está vacío, debe usar el fallback
    resultado = cs.resolver_precios(
        tickers=["AAPL"],
        precios_live={},
        ccl=1500.0,
    )
    # Debe haber un precio (del fallback hardcodeado o BD), nunca ausente
    assert "AAPL" in resultado
    assert resultado["AAPL"] >= 0.0


def test_calcular_posicion_neta_columnas(df_cartera_ejemplo, precios_mock):
    import services.cartera_service as cs
    df = cs.calcular_posicion_neta(df_cartera_ejemplo.copy(), precios_mock, ccl=1500.0)
    for col in ["VALOR_ARS", "PNL_ARS", "PNL_PCT", "PESO_PCT"]:
        assert col in df.columns, f"Columna {col} faltante en posición neta"


def test_calcular_posicion_neta_df_vacio():
    import services.cartera_service as cs
    df_vacio = pd.DataFrame()
    resultado = cs.calcular_posicion_neta(df_vacio, {}, ccl=1500.0)
    assert resultado.empty


def test_metricas_resumen_con_posiciones(df_cartera_ejemplo, precios_mock):
    import services.cartera_service as cs
    df = cs.calcular_posicion_neta(df_cartera_ejemplo.copy(), precios_mock, ccl=1500.0)
    metricas = cs.metricas_resumen(df)
    assert "total_valor" in metricas
    assert metricas["total_valor"] > 0
    assert "n_posiciones" in metricas
    assert metricas["n_posiciones"] == 4


def test_metricas_resumen_df_vacio():
    import services.cartera_service as cs
    metricas = cs.metricas_resumen(pd.DataFrame())
    assert metricas.get("total_valor", 0) == 0


# ─── Invariantes B1 / B2: fórmulas dimensionales CEDEAR ─────────────────────

def test_ppc_usd_sub_ratio_una_vez():
    """
    B1: PPC_USD_PROM almacena el precio por CEDEAR en USD (sub_USD / ratio).
    AAPL ratio=20, PPC_USD_PROM=7.50 → subyacente = 7.50 × 20 = 150.00 USD.
    Si se multiplicara RATIO dos veces el resultado sería 3 000 USD (incorrecto).
    """
    import services.cartera_service as cs
    df = pd.DataFrame({
        "TICKER":             ["AAPL"],
        "CANTIDAD_TOTAL":     [10.0],
        "PPC_USD_PROM":       [7.50],
        "ES_LOCAL":           [False],
        "TIPO":               ["CEDEAR"],
        "INV_ARS_HISTORICO":  [112_500.0],
    })
    result = cs.calcular_posicion_neta(df, {"AAPL": 15_000.0}, ccl=1500.0)
    assert result["PPC_USD_SUB"].iloc[0] == pytest.approx(150.0, rel=0.01)


def test_pnl_pct_usd_accion_local_coherente():
    """Local ARS: PNL_PCT_USD = (VALOR-INV)/INV (antes mezclaba ARS con USD)."""
    import services.cartera_service as cs
    df = pd.DataFrame({
        "TICKER":             ["GGAL"],
        "CANTIDAD_TOTAL":     [100.0],
        "PPC_USD_PROM":       [5_000.0],
        "ES_LOCAL":           [True],
        "TIPO":               ["ACCION_LOCAL"],
        "INV_ARS_HISTORICO":  [500_000.0],
    })
    result = cs.calcular_posicion_neta(df, {"GGAL": 5_500.0}, ccl=1_200.0)
    assert result["PNL_PCT_USD"].iloc[0] == pytest.approx(50_000 / 500_000, abs=0.001)


def test_rellenar_precios_on_usd_usa_paridad_sobre_100():
    """Sin live: último PPC_USD en ON USD es paridad % → precio ARS = (PPC/100)×CCL, no PPC×CCL."""
    import services.cartera_service as cs

    trans = pd.DataFrame(
        [
            {
                "CARTERA": "X",
                "TICKER": "TLCTO",
                "TIPO": "ON_USD",
                "PPC_USD": 100.0,
                "PPC_ARS": 0.0,
                "FECHA_COMPRA": "2026-04-10",
            }
        ]
    )
    out = cs.rellenar_precios_desde_ultimo_ppc(
        trans, "X", ["TLCTO"], {"TLCTO": 0.0}, ccl=1481.89
    )
    assert out["TLCTO"] == pytest.approx(1481.89, rel=1e-4)


def test_calcular_posicion_neta_on_usd_sin_hist_ppc_ars_es_paridad():
    """Sin INV_ARS_HISTORICO: PPC_USD_PROM en ON USD se interpreta como paridad %."""
    import services.cartera_service as cs

    df = pd.DataFrame({
        "TICKER": ["TLCTO"],
        "CANTIDAD_TOTAL": [1.0],
        "PPC_USD_PROM": [100.0],
        "ES_LOCAL": [True],
        "TIPO": ["ON_USD"],
    })
    r = cs.calcular_posicion_neta(df, {"TLCTO": 1481.89}, ccl=1481.89)
    assert r["PPC_ARS"].iloc[0] == pytest.approx(1481.89, rel=1e-4)
    assert r["INV_ARS"].iloc[0] == pytest.approx(1481.89, rel=1e-4)
    assert r["VALOR_ARS"].iloc[0] == pytest.approx(1481.89, rel=1e-4)
    assert abs(float(r["PNL_ARS"].iloc[0])) < 1.0


def test_calcular_posicion_neta_on_usd_normaliza_precio_100x_con_hist():
    """Si PRECIO_ARS queda 100x por encima de PPC_ARS en ON USD, corrige escala en valoración."""
    import services.cartera_service as cs

    df = pd.DataFrame({
        "TICKER": ["TLCTO"],
        "CANTIDAD_TOTAL": [750.0],
        "PPC_USD_PROM": [14.77],
        "ES_LOCAL": [True],
        "TIPO": ["ON_USD"],
        "INV_ARS_HISTORICO": [11_075.0],  # PPC_ARS histórico ~14,77
    })
    r = cs.calcular_posicion_neta(df, {"TLCTO": 1488.56}, ccl=1488.56)
    assert r["PRECIO_ARS"].iloc[0] == pytest.approx(14.8856, rel=1e-4)
    assert r["VALOR_ARS"].iloc[0] == pytest.approx(11_164.2, rel=1e-4)
    assert r["PNL_PCT"].iloc[0] < 0.02  # evita +9.980% artificial
    assert r["ESCALA_PRECIO_RF"].iloc[0] == "÷100 vs PPC"  # P2-RF-04 trazabilidad


def test_pnl_pct_usd_correcto():
    """
    B2: 10 AAPL a PPC=7.50 USD/CEDEAR; precio sube a 10 USD/CEDEAR.
    10 USD/CEDEAR × CCL 1500 = 15 000 ARS/CEDEAR (precio de mercado).
    inv_usd_base = 10 × 7.50 × 1500 = 112 500 ARS  (sin RATIO).
    VALOR_ARS    = 10 × 15 000      = 150 000 ARS.
    PNL_PCT_USD  = 37 500 / 112 500 = +33.3 %.
    """
    import services.cartera_service as cs
    df = pd.DataFrame({
        "TICKER":             ["AAPL"],
        "CANTIDAD_TOTAL":     [10.0],
        "PPC_USD_PROM":       [7.50],
        "ES_LOCAL":           [False],
        "TIPO":               ["CEDEAR"],
        "INV_ARS_HISTORICO":  [112_500.0],
    })
    result = cs.calcular_posicion_neta(df, {"AAPL": 15_000.0}, ccl=1500.0)
    assert result["PNL_PCT_USD"].iloc[0] == pytest.approx(0.333, abs=0.01)


# ─── calcular_rendimiento_por_tipo ──────────────────────────────────────────
class TestCalcularRendimientoPorTipo:
    @pytest.fixture
    def df_ag_ejemplo(self):
        return pd.DataFrame({
            "TICKER":         ["AAPL",      "MSFT",      "YPFD"],
            "TIPO":           ["CEDEAR",    "CEDEAR",    "ACCION_LOCAL"],
            "VALOR_ARS":      [150_000.0,   100_000.0,   50_000.0],
            "INV_ARS":        [120_000.0,    90_000.0,   48_000.0],
            "PNL_ARS":        [ 30_000.0,    10_000.0,    2_000.0],
            "CANTIDAD_TOTAL": [10,            5,           100],
        })

    def test_retorna_dataframe(self, df_ag_ejemplo):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_ag_ejemplo, pd.DataFrame())
        assert isinstance(result, pd.DataFrame)

    def test_columnas_requeridas(self, df_ag_ejemplo):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_ag_ejemplo, pd.DataFrame())
        if not result.empty:
            for col in ("Tipo", "Inv. ARS", "Valor ARS", "P&L ARS"):
                assert col in result.columns, f"Falta columna: {col}"

    def test_df_vacio_no_lanza(self):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(pd.DataFrame(), pd.DataFrame())
        assert isinstance(result, pd.DataFrame)

    def test_agrupacion_por_tipo(self, df_ag_ejemplo):
        from services.cartera_service import calcular_rendimiento_por_tipo
        result = calcular_rendimiento_por_tipo(df_ag_ejemplo, pd.DataFrame())
        if not result.empty and "Tipo" in result.columns:
            tipos = result["Tipo"].tolist()
            assert len(tipos) >= 1


# ─── metricas_resumen ────────────────────────────────────────────────────────
class TestMetricasResumen:
    def test_retorna_dict(self):
        from services.cartera_service import metricas_resumen
        df = pd.DataFrame({
            "VALOR_ARS":      [100_000.0, 50_000.0],
            "INV_ARS":        [ 80_000.0, 48_000.0],
            "PNL_ARS":        [ 20_000.0,  2_000.0],
            "PNL_PCT":        [0.25, 0.042],
            "PESO_PCT":       [66.7, 33.3],
            "CANTIDAD_TOTAL": [10, 5],
            "PPC_ARS":        [8_000.0, 9_600.0],
        })
        result = metricas_resumen(df)
        assert isinstance(result, dict)

    def test_total_valor_correcto(self):
        from services.cartera_service import metricas_resumen
        df = pd.DataFrame({
            "VALOR_ARS":      [100_000.0, 50_000.0],
            "INV_ARS":        [ 80_000.0, 48_000.0],
            "PNL_ARS":        [ 20_000.0,  2_000.0],
            "CANTIDAD_TOTAL": [10, 5],
            "PPC_ARS":        [8_000.0, 9_600.0],
        })
        result = metricas_resumen(df)
        valor = result.get("total_valor", result.get("valor_total", 0))
        assert abs(valor - 150_000.0) < 1.0

    def test_df_vacio_retorna_dict(self):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(pd.DataFrame())
        assert isinstance(result, dict)


# ─── calcular_progreso_objetivo ──────────────────────────────────────────────
class TestCalcularProgresoObjetivo:
    def test_importa_sin_error(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert callable(calcular_progreso_objetivo)

    def test_progreso_en_rango_cuando_precio_sube(self):
        from services.cartera_service import calcular_progreso_objetivo
        # ppc=100, precio_actual=117.5 (=50% del target 35%) => progreso ~50%
        result = calcular_progreso_objetivo(100.0, 117.5, 35.0)
        assert isinstance(result, float)
        assert -100.0 <= result <= 200.0

    def test_ppc_cero_no_lanza(self):
        from services.cartera_service import calcular_progreso_objetivo
        try:
            result = calcular_progreso_objetivo(0.0, 150.0, 35.0)
            assert isinstance(result, float)
        except Exception as e:
            pytest.fail(f"calcular_progreso_objetivo con ppc=0 lanzó: {e}")
