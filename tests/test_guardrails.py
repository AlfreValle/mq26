"""Tests de la capa de guardrails del recomendador (H1)."""
from __future__ import annotations

from types import SimpleNamespace

from services.guardrails import (
    SEV_ADVERTENCIA,
    SEV_ERROR,
    hay_errores,
    validar_recomendacion,
)


def _item(ticker, monto, precio=100.0):
    return SimpleNamespace(ticker=ticker, monto_ars=monto, precio_ars_estimado=precio)


def _rr(items):
    return SimpleNamespace(compras_recomendadas=items)


def test_plan_sano_sin_violaciones():
    # Arriesgado: rf_min 0.10. Mix con ~15% RF (PN43O) y RV repartida.
    rr = _rr([
        _item("PN43O", 150_000),   # RF
        _item("AAPL", 300_000),
        _item("MSFT", 300_000),
        _item("AMZN", 250_000),
    ])
    v = validar_recomendacion(rr, perfil="Arriesgado", capital_ars=1_000_000)
    assert v == [] and not hay_errores(v)


def test_excede_capital_es_error():
    rr = _rr([_item("AAPL", 1_200_000)])
    v = validar_recomendacion(rr, perfil="Moderado", capital_ars=1_000_000)
    assert hay_errores(v)
    assert any(x.regla == "capital" and x.severidad == SEV_ERROR for x in v)


def test_precio_cero_es_error():
    rr = _rr([_item("AAPL", 500_000, precio=0.0)])
    v = validar_recomendacion(rr, perfil="Moderado", capital_ars=1_000_000)
    assert any(x.regla == "precio" and x.severidad == SEV_ERROR for x in v)


def test_concentracion_rv_advierte():
    rr = _rr([_item("NVDA", 800_000), _item("PN43O", 200_000)])
    v = validar_recomendacion(rr, perfil="Arriesgado", capital_ars=1_000_000)
    assert any(x.regla == "concentracion" and x.severidad == SEV_ADVERTENCIA for x in v)
    assert not hay_errores(v)  # concentración no bloquea


def test_mix_perfil_conservador_sin_rf_advierte():
    # Conservador rf_min 0.40 — un plan 100% RV viola el piso.
    rr = _rr([_item("AAPL", 500_000), _item("MSFT", 500_000)])
    v = validar_recomendacion(rr, perfil="Conservador", capital_ars=1_000_000)
    assert any(x.regla == "mix_perfil" for x in v)


def test_monto_chico_advierte():
    rr = _rr([_item("AAPL", 980_000), _item("KO", 5_000)])
    v = validar_recomendacion(rr, perfil="Arriesgado", capital_ars=1_000_000)
    assert any(x.regla == "monto_chico" for x in v)


def test_plan_vacio_no_explota():
    assert validar_recomendacion(_rr([]), perfil="Moderado", capital_ars=1_000_000) == []
