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
    def test_aapl_es_usd_por_certificado_sin_ratio(self):
        # Contrato: PPC_USD = ARS / CCL (no ÷ ratio). 18000/1465 ≈ 12.286.
        resultado = ppc_usd_desde_precio_ars(18000.0, "AAPL", 1465.0)
        esperado = 18000.0 / 1465.0
        assert resultado == pytest.approx(esperado, rel=1e-3)

    def test_on_usd_es_paridad_pct(self):
        # 1170 ARS / VN, CCL 1200 → paridad 97.5
        from core.pricing_utils import ppc_usd_desde_precio_ars

        assert ppc_usd_desde_precio_ars(1170.0, "PN43O", 1200.0, tipo="ON_USD") == pytest.approx(97.5)

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


# ─── Contrato único PPC_USD → ARS / guard de paridad RF ──────────────────────

class TestPrecioArsDesdePpcUsd:
    def test_on_usd_es_paridad_por_cien(self):
        from core.pricing_utils import precio_ars_desde_ppc_usd

        assert precio_ars_desde_ppc_usd("PN43O", "ON_USD", 97.5, 1200.0) == pytest.approx(1170.0)

    def test_cedear_no_divide_cien_ni_ratio(self):
        from core.pricing_utils import precio_ars_desde_ppc_usd

        assert precio_ars_desde_ppc_usd("GOOGL", "CEDEAR", 2.5, 1200.0) == pytest.approx(3000.0)

    def test_alias_es_instrumento_rf_usd_paridad(self):
        from core.pricing_utils import es_instrumento_rf_usd_paridad, es_ppc_usd_paridad_rf

        assert es_ppc_usd_paridad_rf("PN43O", "ON_USD") is True
        assert es_instrumento_rf_usd_paridad is es_ppc_usd_paridad_rf


class TestValidarPpcUsdParidadRf:
    def test_fraccion_bloquea(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, marca, msg = validar_ppc_usd_paridad_rf("PN43O", "ON_USD", 0.975)
        assert ok is False
        assert marca == "parece_fraccion"
        assert "No se guarda" in msg

    def test_menor_a_diez_bloquea(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, _, _ = validar_ppc_usd_paridad_rf("PN43O", "ON_USD", 8.0)
        assert ok is False

    def test_fuera_de_70_150_marca_pero_permite(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, marca, msg = validar_ppc_usd_paridad_rf("PN43O", "ON_USD", 45.0)
        assert ok is True
        assert marca == "fuera_rango_tipico"
        assert "45" in msg

    def test_paridad_tipica_ok(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, marca, msg = validar_ppc_usd_paridad_rf("PN43O", "ON_USD", 97.5)
        assert ok is True
        assert marca == ""
        assert msg == ""

    def test_cedear_no_aplica(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, marca, _ = validar_ppc_usd_paridad_rf("GOOGL", "CEDEAR", 1.60)
        assert ok is True
        assert marca == ""

    def test_absurda_bloquea(self):
        from core.pricing_utils import validar_ppc_usd_paridad_rf

        ok, marca, _ = validar_ppc_usd_paridad_rf("PN43O", "ON_USD", 500.0)
        assert ok is False
        assert marca == "paridad_absurda"
