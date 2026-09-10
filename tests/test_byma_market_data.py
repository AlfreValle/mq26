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


def test_paridad_on_distress_bajo_34pct_ars_por_vn():
    """ON a 25% de paridad (375 ARS/VN a CCL 1500) no se lee como 375%."""
    assert _paridad_pct_desde_precio_on(375.0, 1500.0) == pytest.approx(25.0)


def test_paridad_on_distress_32pct_supera_umbral_fijo_500():
    """32% × 1500 = 480 ARS: el umbral fijo 500 la tiraba al catálogo."""
    assert _paridad_pct_desde_precio_on(480.0, 1500.0) == pytest.approx(32.0)


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


def test_normaliza_escala_x100_distress_25pct():
    """37.500 ARS = 25% × CCL 1500 × 100 VN → ÷100 a 375 ARS/VN."""
    px, div = _normalizar_lastprice_on_byma_meta(37_500.0, 1500.0)
    assert div is True
    assert px == pytest.approx(375.0)
    assert _paridad_pct_desde_precio_on(px, 1500.0) == pytest.approx(25.0)


def test_enriquecer_on_distress_25pct_no_cae_al_catalogo(monkeypatch):
    from services import byma_market_data as bmd

    monkeypatch.setattr(
        bmd,
        "fetch_on_byma_live",
        lambda: {"YMCHO": {"lastPrice": 375.0, "variationRate": -1.2, "description": "ON dist", "volumeAmount": 1}},
    )
    got = bmd.enriquecer_on_desde_byma(1500.0)
    assert "YMCHO" in got
    assert got["YMCHO"]["paridad_ref"] == pytest.approx(25.0)
    assert got["YMCHO"]["precio_ars"] == pytest.approx(375.0)


def test_enriquecer_on_distress_escala_x100(monkeypatch):
    from services import byma_market_data as bmd

    monkeypatch.setattr(
        bmd,
        "fetch_on_byma_live",
        lambda: {"YMCHO": {"lastPrice": 37_500.0, "description": "ON dist", "volumeAmount": 1}},
    )
    got = bmd.enriquecer_on_desde_byma(1500.0)
    assert "YMCHO" in got
    assert got["YMCHO"]["paridad_ref"] == pytest.approx(25.0)
    assert got["YMCHO"]["precio_ars"] == pytest.approx(375.0)
    assert got["YMCHO"]["escala_div100"] is True


def test_last_ars_rv_byma_mapea_symbol_y_ba(monkeypatch):
    from services import byma_market_data as bmd

    def _fake_fetch(endpoint, timeout=None):
        if endpoint == "cedears":
            return [
                {"symbol": "AAPL", "lastPrice": 22100.5},
                {"symbol": "SPY.BA", "lastPrice": 58000.0},
                {"symbol": "KO", "lastPrice": 0},
            ]
        return [{"symbol": "GGAL", "lastPrice": 3500.0}]

    monkeypatch.setattr(bmd, "_fetch_tipo", _fake_fetch)
    got = bmd.last_ars_rv_byma(["AAPL", "SPY", "GGAL", "KO"], timeout_s=4)
    assert got["AAPL"] == pytest.approx(22100.5)
    assert got["SPY"] == pytest.approx(58000.0)
    assert got["GGAL"] == pytest.approx(3500.0)
    assert "KO" not in got
