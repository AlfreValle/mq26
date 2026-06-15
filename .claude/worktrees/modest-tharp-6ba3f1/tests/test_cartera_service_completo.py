"""
tests/test_cartera_service_completo.py — Cobertura Sprint 30 (cartera_service).
Prioriza precios_usd_subyacente y rutas no cubiertas en otros tests; sin yfinance real.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture
def df_pos_simple():
    """Invariante: columnas mínimas para calcular_posicion_neta con CEDEARs."""
    return pd.DataFrame({
        "TICKER":         ["AAPL", "MSFT"],
        "CANTIDAD_TOTAL": [10.0, 5.0],
        "PPC_USD_PROM":   [8.0, 10.0],
        "PPC_ARS":        [11_760.0, 14_650.0],
        "TIPO":           ["CEDEAR", "CEDEAR"],
        "ES_LOCAL":       [False, False],
        "CARTERA":        ["Retiro", "Retiro"],
    })


@pytest.fixture
def hist_precios_sinteticos():
    """Invariante: índice temporal alineado con TWRR (≥2 fechas de flujo únicas)."""
    rng = np.random.default_rng(42)
    n = 252
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "AAPL": 150.0 * np.cumprod(1 + rng.normal(0.001, 0.02, n)),
        "MSFT": 250.0 * np.cumprod(1 + rng.normal(0.001, 0.018, n)),
    }, index=idx)


@pytest.fixture
def df_trans_twrr():
    return pd.DataFrame({
        "TICKER":       ["AAPL", "MSFT", "AAPL"],
        "CANTIDAD":     [10, 5, 0],
        "PPC_USD":      [8.0, 10.0, 8.0],
        "FECHA_COMPRA": ["2023-01-15", "2023-03-01", "2023-06-01"],
        "TIPO":         ["CEDEAR", "CEDEAR", "CEDEAR"],
        "TIPO_OP":      ["COMPRA", "COMPRA", "VENTA"],
    })


# ─── precios_usd_subyacente ───────────────────────────────────────────────────


class TestPreciosUsdSubyacente:
    def test_lista_vacia_retorna_dos_dicts_vacios(self):
        from services.cartera_service import precios_usd_subyacente

        usd, ratios = precios_usd_subyacente([], {"AAPL": 1.0}, 1500.0)
        assert usd == {} and ratios == {}

    def test_ccl_cero_precio_usd_cero(self):
        from services.cartera_service import precios_usd_subyacente

        usd, ratios = precios_usd_subyacente(["AAPL"], {"AAPL": 20_000.0}, 0.0)
        assert usd.get("AAPL", -1) == 0.0
        assert "AAPL" in ratios

    def test_formula_cedear_AAPL_ratio_config(self):
        """Invariante: subyacente_USD = precio_ARS * ratio / CCL (config RATIOS_CEDEAR)."""
        from services.cartera_service import precios_usd_subyacente

        ccl = 1_000.0
        px_ars = 20_000.0
        usd, ratios = precios_usd_subyacente(["AAPL"], {"AAPL": px_ars}, ccl)
        ratio = ratios["AAPL"]
        esperado = round(px_ars * ratio / ccl, 4)
        assert usd["AAPL"] == pytest.approx(esperado, rel=1e-4)

    def test_universo_df_sobrescribe_ratio(self):
        from services.cartera_service import precios_usd_subyacente

        uni = pd.DataFrame({"Ticker": ["MSFT"], "Ratio": ["30:1"]})
        usd, ratios = precios_usd_subyacente(
            ["MSFT"], {"MSFT": 30_000.0}, 1_500.0, universo_df=uni,
        )
        assert ratios["MSFT"] == pytest.approx(30.0)
        assert usd["MSFT"] > 0


# ─── resolver_precios ─────────────────────────────────────────────────────────


class TestResolverPreciosS30:
    def test_tickers_vacios_retorna_dict_vacio(self):
        from services.cartera_service import resolver_precios

        result = resolver_precios([], {}, 1465.0)
        assert result == {}

    def test_fallback_modulo_cuando_live_vacio(self):
        from services.cartera_service import resolver_precios

        with patch("services.cartera_service.PRECIOS_FALLBACK_ARS", {"MSFT_S30": 22_000.0}):
            result = resolver_precios(["MSFT_S30"], {}, 1465.0)
        assert result.get("MSFT_S30", 0) == pytest.approx(22_000.0)


# ─── calcular_posicion_neta ───────────────────────────────────────────────────


class TestCalcularPosicionNetaS30:
    def test_columnas_valor_y_pnl(self, df_pos_simple):
        from services.cartera_service import calcular_posicion_neta

        precios = {"AAPL": 19_000.0, "MSFT": 22_000.0}
        result = calcular_posicion_neta(df_pos_simple, precios, 1465.0)
        assert "VALOR_ARS" in result.columns
        assert "PNL_ARS" in result.columns

    def test_cantidad_string_se_coerce(self, df_pos_simple):
        """Invariante: CANTIDAD_TOTAL como string no rompe el cálculo."""
        from services.cartera_service import calcular_posicion_neta

        df = df_pos_simple.copy()
        df["CANTIDAD_TOTAL"] = df["CANTIDAD_TOTAL"].astype(object)
        df.loc[0, "CANTIDAD_TOTAL"] = "10"
        result = calcular_posicion_neta(df, {"AAPL": 19_000.0, "MSFT": 22_000.0}, 1465.0)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty


# ─── calcular_twrr ────────────────────────────────────────────────────────────


class TestCalcularTwrrS30:
    def test_con_historial_retorna_claves_twrr(self, df_trans_twrr, hist_precios_sinteticos):
        from services.cartera_service import calcular_twrr

        result = calcular_twrr(df_trans_twrr, hist_precios_sinteticos, 1465.0)
        assert isinstance(result, dict)
        assert "twrr_anual" in result
        assert "twrr_total" in result


# ─── calcular_dividendos_proyectados ──────────────────────────────────────────


class TestDividendosProyectadosS30:
    def test_con_patch_yield_retorna_dict(self):
        from services.cartera_service import calcular_dividendos_proyectados

        df = pd.DataFrame({
            "TICKER": ["KO"], "CANTIDAD_TOTAL": [20.0],
            "VALOR_ARS": [100_000.0], "TIPO": ["CEDEAR"],
        })
        with patch(
            "services.cartera_service._get_div_yield_cached",
            return_value=0.025,
        ):
            result = calcular_dividendos_proyectados(df, 1465.0)
        assert isinstance(result, dict)
        assert "flujo_anual_ars" in result


# ─── calcular_rendimiento_por_tipo / global ───────────────────────────────────


class TestRendimientoTipoS30:
    def test_suma_n_posiciones_igual_filas_entrada(self):
        from services.cartera_service import calcular_rendimiento_por_tipo

        df_pos = pd.DataFrame({
            "TICKER":    ["AAPL", "MSFT", "YPFD"],
            "TIPO":      ["CEDEAR", "CEDEAR", "ACCION_LOCAL"],
            "VALOR_ARS": [190_000.0, 110_000.0, 50_000.0],
            "INV_ARS":   [150_000.0, 90_000.0, 48_000.0],
            "PNL_ARS":   [40_000.0, 20_000.0, 2_000.0],
            "CANTIDAD_TOTAL": [10, 5, 100],
        })
        result = calcular_rendimiento_por_tipo(df_pos)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert "N posiciones" in result.columns
        assert int(result["N posiciones"].sum()) == len(df_pos)
        for col in ("Tipo", "Inv. ARS", "Valor ARS", "P&L ARS"):
            assert col in result.columns


class TestRendimientoGlobalS30:
    def test_dict_con_cagr_cuando_hay_tipos(self):
        from services.cartera_service import calcular_rendimiento_global_anual

        df_rend = pd.DataFrame({
            "Tipo":             ["CEDEAR", "ACCION_LOCAL"],
            "Inv. ARS":         [240_000.0, 48_000.0],
            "Valor ARS":        [300_000.0, 50_000.0],
            "P&L ARS":          [60_000.0, 2_000.0],
            "P&L USD aprox":    [5_000.0, 200.0],
            "Rend. ARS %":      [25.0, 4.2],
            "CAGR ARS %":       [20.0, 3.5],
            "N posiciones":     [5, 1],
            "Días en cartera":  [400, 200],
        })
        result = calcular_rendimiento_global_anual(df_rend, pd.DataFrame())
        assert isinstance(result, dict)
        assert "cagr_global_ars" in result
