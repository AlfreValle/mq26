"""Heurística de paridad ON desde BYMA Open Data."""
from __future__ import annotations

import pytest

from services.byma_market_data import (
    _normalizar_lastprice_on_byma,
    _normalizar_lastprice_on_byma_meta,
    _paridad_pct_desde_precio_on,
)


def test_paridad_directa_pct_cuando_precio_bajo():
    assert _paridad_pct_desde_precio_on(101.25, 1500.0) == pytest.approx(101.25)


def test_paridad_desde_ars_por_100_vn():
    # 153.380 ARS por 100 nominales, CCL 1465 → paridad ≈ 104,7 %
    assert _paridad_pct_desde_precio_on(153_380.0, 1465.0) == pytest.approx(104.7, rel=1e-3)


def test_paridad_desde_ars_por_1_vn():
    # Mismo resultado económico si BYMA manda ARS por 1 USD nominal
    assert _paridad_pct_desde_precio_on(1533.80, 1465.0) == pytest.approx(104.7, rel=1e-3)


def test_normaliza_byma_escala_x100_a_precio_unitario():
    # Feed BYMA a veces trae 148500; /100 → 1485 ARS por 1 nominal (ej. VSCXO vs Balanz)
    ccl = 1488.56
    assert _normalizar_lastprice_on_byma(148_500.0, ccl) == pytest.approx(1485.0, rel=1e-6)


def test_normaliza_meta_indica_div100():
    ccl = 1488.56
    px, div = _normalizar_lastprice_on_byma_meta(148_500.0, ccl)
    assert px == pytest.approx(1485.0, rel=1e-6)
    assert div is True
    _px2, div2 = _normalizar_lastprice_on_byma_meta(1485.0, ccl)
    assert div2 is False


def test_normaliza_no_rompe_precio_ya_unitario():
    ccl = 1488.56
    assert _normalizar_lastprice_on_byma(1485.0, ccl) == pytest.approx(1485.0, rel=1e-6)
