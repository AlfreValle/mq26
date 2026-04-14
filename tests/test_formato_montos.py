"""Tests formato_montos (Excelencia #25)."""
from __future__ import annotations

from core.formato_montos import formato_monto_ar, formato_monto_usd


def test_formato_monto_ar_miles():
    assert formato_monto_ar(1250300.5) == "$ 1.250.300,50"
    assert formato_monto_ar(0) == "$ 0,00"


def test_formato_monto_ar_negativo():
    assert formato_monto_ar(-1000) == "-$ 1.000,00"


def test_formato_monto_ar_none():
    assert formato_monto_ar(None) == "—"


def test_formato_monto_usd():
    assert formato_monto_usd(1_250_300) == "USD 1.250.300"


def test_formato_monto_usd_decimales():
    assert formato_monto_usd(1000.4, decimales=1) == "USD 1.000,4"
