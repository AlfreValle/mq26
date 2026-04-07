"""Tests core/renta_fija_ar.py"""
import pandas as pd
import pytest

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    RF_SCHEMA_KEYS,
    descripcion_legible,
    es_fila_renta_fija_ar,
    es_renta_fija,
    get_meta,
    ladder_vencimientos,
    meta_rf_con_precio,
    tickers_por_tipo,
    tickers_rf_activos,
    tir_al_precio,
    tir_ponderada_cartera,
    top_instrumentos_rf,
    valor_nominal_a_ars,
)


def _univ_sample():
    return {
        "AA": {"tir_ref": 6.0, "tipo": "ON", "vencimiento": 2031, "calificacion": "AA"},
        "BB": {"tir_ref": 8.0, "tipo": "ON", "vencimiento": 2031, "calificacion": "AA"},
    }


class TestEsFilaRentaFijaAr:
    def test_tipo_on(self):
        row = pd.Series({"TICKER": "X", "TIPO": "ON"})
        assert es_fila_renta_fija_ar(row, _univ_sample()) is True

    def test_prefijo_gd(self):
        row = pd.Series({"TICKER": "GD30", "TIPO": "CEDEAR"})
        assert es_fila_renta_fija_ar(row, {}) is True

    def test_accion_comun_no_rf(self):
        row = pd.Series({"TICKER": "MSFT", "TIPO": "CEDEAR"})
        assert es_fila_renta_fija_ar(row, _univ_sample()) is False

    def test_tipo_boncer_cuenta_rf(self):
        row = pd.Series({"TICKER": "TX26", "TIPO": "BONCER"})
        assert es_fila_renta_fija_ar(row, {}) is True


class TestTirPonderadaCartera:
    def test_vacio_none(self):
        assert tir_ponderada_cartera(pd.DataFrame()) is None

    def test_un_solo_on_usa_tir(self):
        df = pd.DataFrame([{"TICKER": "TLCTO", "PESO_PCT": 1.0, "TIPO": "ON"}])
        assert abs(float(tir_ponderada_cartera(df)) - 8.0) < 1e-6

    def test_mix_ponderado(self):
        u = _univ_sample()
        df = pd.DataFrame(
            [
                {"TICKER": "AA", "PESO_PCT": 0.5, "TIPO": "ON"},
                {"TICKER": "BB", "PESO_PCT": 0.5, "TIPO": "ON"},
            ]
        )
        assert abs(float(tir_ponderada_cartera(df, u)) - 7.0) < 1e-6


class TestTopInstrumentosRf:
    def test_excluye_soberanos(self):
        top = top_instrumentos_rf(n=20)
        tickers = {x["ticker"] for x in top}
        assert "GD30" not in tickers
        assert "TLCTO" in tickers or len(top) == 0

    def test_orden_por_tir(self):
        top = top_instrumentos_rf(n=6)
        tirs = [x["tir_ref"] for x in top]
        assert tirs == sorted(tirs, reverse=True)


class TestLadderVencimientos:
    def test_vacio(self):
        assert ladder_vencimientos(pd.DataFrame()) == []

    def test_agrega_mismo_anio(self):
        u = _univ_sample()
        df = pd.DataFrame(
            [
                {"TICKER": "AA", "PESO_PCT": 0.3, "TIPO": "ON"},
                {"TICKER": "BB", "PESO_PCT": 0.2, "TIPO": "ON"},
            ]
        )
        lad = ladder_vencimientos(df, u)
        assert lad == [(2031, 0.5)]


def test_meta_rf_con_precio_incluye_schema():
    row = meta_rf_con_precio("AL30", precio_mercado_ars=72.5, universo_renta=UNIVERSO_RENTA_FIJA_AR)
    assert row["ticker"] == "AL30"
    assert row["tir_ref"] == UNIVERSO_RENTA_FIJA_AR["AL30"]["tir_ref"]
    assert row["cupon_pct"] == UNIVERSO_RENTA_FIJA_AR["AL30"]["cupon_pct"]
    assert row["precio_mercado_ars"] == pytest.approx(72.5)
    assert "spread_tir_pp" in RF_SCHEMA_KEYS


def test_es_renta_fija_conoce_PN43O():
    assert es_renta_fija("PN43O") is True


def test_get_meta_retorna_dict_con_tir():
    m = get_meta("YM34O")
    assert m is not None
    assert "tir_ref" in m


def test_tir_al_precio_igual_a_ref_cuando_paridad_igual():
    m = get_meta("TLCTO")
    assert m is not None
    tir = tir_al_precio("TLCTO", float(m["paridad_ref"]))
    assert tir == pytest.approx(float(m["tir_ref"]), rel=0.01)


def test_tir_al_precio_mayor_cuando_paridad_menor():
    assert tir_al_precio("TLCTO", 90.0) > tir_al_precio("TLCTO", 110.0)


def test_valor_nominal_a_ars_calculo_correcto():
    assert valor_nominal_a_ars(5000, 102.5, 1150) == 5000 * 1.025 * 1150


def test_descripcion_legible_no_vacia():
    assert len(descripcion_legible("PN43O")) > 5


def test_tickers_rf_activos_no_vacio():
    t = tickers_rf_activos()
    assert len(t) >= 5


def test_todos_instrumentos_tienen_campos_obligatorios():
    """Todos los entries de INSTRUMENTOS_RF tienen los 8 campos mínimos."""
    required = {
        "emisor",
        "tipo",
        "vencimiento",
        "tir_ref",
        "paridad_ref",
        "calificacion",
        "moneda",
        "activo",
    }
    for ticker, meta in INSTRUMENTOS_RF.items():
        missing = required - set(meta.keys())
        assert not missing, f"{ticker} le faltan: {missing}"


def test_total_instrumentos_minimo_20():
    assert len(tickers_rf_activos()) >= 20, "Deben haber al menos 20 instrumentos RF"


def test_on_usd_y_bonos_y_letras_presentes():
    assert len(tickers_por_tipo("ON_USD")) >= 8
    assert len(tickers_por_tipo("BONO_USD")) >= 6
    assert len(tickers_por_tipo("LETRA")) >= 2


def test_resolver_precios_usa_paridad_on():
    """resolver_precios enriquece ONs desde renta_fija_ar cuando no hay live ni fallback."""
    from unittest.mock import patch

    from services.cartera_service import resolver_precios

    precios_live: dict[str, float] = {}
    with patch("services.cartera_service.PRECIOS_FALLBACK_ARS", {}):
        resultado = resolver_precios(["TLCTO", "SPY"], precios_live, ccl=1150.0)
    assert resultado.get("TLCTO", 0) > 0, "TLCTO debe tener precio estimado"
