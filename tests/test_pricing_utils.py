"""
tests/test_pricing_utils.py — Tests unitarios para core/pricing_utils.py
Ejecutar: pytest tests/test_pricing_utils.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.pricing_utils import (
    ccl_historico_por_fecha,
    es_accion_local,
    parsear_ppc_usd,
    parsear_precio_ars,
    parsear_ratio,
    ppc_usd_desde_precio_ars,
    precio_cedear_ars,
    subyacente_usd_desde_cedear,
)


# ─── parsear_ppc_usd ──────────────────────────────────────────────────────────
class TestParsearPPCUsd:
    def test_float_directo(self):
        assert parsear_ppc_usd(1.60) == 1.60

    def test_int_directo(self):
        assert parsear_ppc_usd(34) == 34.0

    def test_cadena_usd(self):
        assert parsear_ppc_usd("usd 1,60") == pytest.approx(1.60)

    def test_cadena_dolar(self):
        assert parsear_ppc_usd("$34,58") == pytest.approx(34.58)

    def test_cadena_punto_decimal(self):
        assert parsear_ppc_usd("1.60") == pytest.approx(1.60)

    def test_cadena_miles_coma(self):
        assert parsear_ppc_usd("1.234,56") == pytest.approx(1234.56)

    def test_none(self):
        assert parsear_ppc_usd(None) == 0.0

    def test_nan(self):
        assert parsear_ppc_usd(float("nan")) == 0.0

    def test_cadena_invalida(self):
        assert parsear_ppc_usd("abc") == 0.0


# ─── parsear_precio_ars ───────────────────────────────────────────────────────
class TestParsearPrecioARS:
    def test_formato_argentino(self):
        assert parsear_precio_ars("$49.180,00") == pytest.approx(49180.0)

    def test_float_directo(self):
        assert parsear_precio_ars(49180.0) == pytest.approx(49180.0)

    def test_int_directo(self):
        assert parsear_precio_ars(49180) == pytest.approx(49180.0)

    def test_none(self):
        assert parsear_precio_ars(None) == 0.0

    def test_cadena_simple(self):
        assert parsear_precio_ars("49180.00") == pytest.approx(49180.0)


# ─── parsear_ratio ────────────────────────────────────────────────────────────
class TestParsearRatio:
    def test_entero(self):
        assert parsear_ratio(20) == 20.0

    def test_cadena_con_sufijo(self):
        assert parsear_ratio("20:1") == 20.0

    def test_cadena_simple(self):
        assert parsear_ratio("20") == 20.0

    def test_invalido(self):
        assert parsear_ratio("x") == 1.0

    def test_none(self):
        assert parsear_ratio(None) == 1.0


# ─── precio_cedear_ars / subyacente_usd_desde_cedear (inversa) ──────────────
class TestConversionCedear:
    # AAPL ratio=20, CCL=1465
    # subyacente_usd=222.50 → cedear_ars = 222.50/20 * 1465 = 16278.125
    SUBYACENTE = 222.50
    RATIO = 20.0
    CCL = 1465.0

    def test_precio_cedear_ars(self):
        esperado = (self.SUBYACENTE / self.RATIO) * self.CCL
        resultado = precio_cedear_ars(self.SUBYACENTE, self.RATIO, self.CCL)
        assert resultado == pytest.approx(esperado, rel=1e-4)

    def test_inversa_exacta(self):
        """subyacente_usd_desde_cedear debe ser la inversa de precio_cedear_ars."""
        px_ars = precio_cedear_ars(self.SUBYACENTE, self.RATIO, self.CCL)
        recuperado = subyacente_usd_desde_cedear(px_ars, self.RATIO, self.CCL)
        assert recuperado == pytest.approx(self.SUBYACENTE, rel=1e-4)

    def test_ratio_cero_devuelve_cero(self):
        assert precio_cedear_ars(100.0, 0.0, 1465.0) == 0.0

    def test_ccl_cero_devuelve_cero(self):
        assert precio_cedear_ars(100.0, 20.0, 0.0) == 0.0

    def test_subyacente_cero_devuelve_cero(self):
        assert precio_cedear_ars(0.0, 20.0, 1465.0) == 0.0


# ─── ppc_usd_desde_precio_ars ────────────────────────────────────────────────
class TestPPCUsdDesdePrecioARS:
    def test_aapl(self):
        # precio_ars=18000, ratio=20, ccl=1465
        # PPC_USD = 18000 / (1465 * 20) = 0.6143...
        resultado = ppc_usd_desde_precio_ars(18000.0, "AAPL", 1465.0)
        esperado = 18000.0 / (1465.0 * 20)
        assert resultado == pytest.approx(esperado, rel=1e-3)

    def test_ticker_desconocido_ratio_1(self):
        resultado = ppc_usd_desde_precio_ars(1465.0, "XYZUNKNOWN", 1465.0)
        assert resultado == pytest.approx(1.0, rel=1e-3)

    def test_ccl_cero(self):
        assert ppc_usd_desde_precio_ars(18000.0, "AAPL", 0.0) == 0.0

    def test_precio_cero(self):
        assert ppc_usd_desde_precio_ars(0.0, "AAPL", 1465.0) == 0.0


# ─── ccl_historico_por_fecha ─────────────────────────────────────────────────
class TestCCLHistorico:
    def test_fecha_conocida(self):
        assert ccl_historico_por_fecha("2026-03-15") == pytest.approx(1465.0)

    def test_fecha_formato_mes(self):
        assert ccl_historico_por_fecha("2024-06") == pytest.approx(1130.0)

    def test_fecha_desconocida_fallback(self):
        resultado = ccl_historico_por_fecha("2099-01", fallback=9999.0)
        assert resultado == pytest.approx(9999.0)

    def test_fecha_futura_sin_fallback_usa_ultimo_conocido(self):
        """B3: fecha desconocida sin fallback explícito → max del dict, nunca 1350."""
        resultado = ccl_historico_por_fecha("2099-06")
        assert resultado >= 1465.0


# ─── es_accion_local ──────────────────────────────────────────────────────────
class TestEsAccionLocal:
    def test_conocidas(self):
        for ticker in ("CEPU", "TGNO4", "YPFD", "PAMP", "GGAL"):
            assert es_accion_local(ticker)

    def test_cedear_no_es_local(self):
        for ticker in ("AAPL", "MSFT", "COST", "SPY"):
            assert not es_accion_local(ticker)

    def test_case_insensitive(self):
        assert es_accion_local("cepu")
        assert not es_accion_local("aapl")
