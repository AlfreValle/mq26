from __future__ import annotations

from ui.tab_admin import _collect_degradaciones


def test_collect_degradaciones_ok():
    eventos = _collect_degradaciones(
        {"price_coverage_pct": 100.0, "tickers_sin_precio": []}
    )
    assert any(e.get("evento") == "sin_degradaciones_activas" for e in eventos)


def test_collect_degradaciones_cobertura_baja():
    eventos = _collect_degradaciones(
        {"price_coverage_pct": 80.0, "tickers_sin_precio": ["AAPL", "MSFT"]}
    )
    assert any(e.get("evento") == "cobertura_precios_baja" for e in eventos)
