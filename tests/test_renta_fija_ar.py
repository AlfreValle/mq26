"""Tests core/renta_fija_ar.py"""
from datetime import date

import pandas as pd
import pytest

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
from core.renta_fija_ar import (
    DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF,
    GUION_FICHA_RF,
    INSTRUMENTOS_RF,
    ON_USD_PARIDAD_BASE_VN,
    RF_SCHEMA_KEYS,
    analisis_obligaciones_negociables_usd_df,
    cashflow_ilustrativo_por_100_vn,
    descripcion_legible,
    es_fila_renta_fija_ar,
    es_renta_fija,
    fecha_vencimiento_desde_meta,
    ficha_rf_denominacion_min,
    ficha_rf_forma_amortizacion,
    ficha_rf_isin,
    ficha_rf_minima_bundle,
    get_meta,
    ladder_vencimientos,
    lamina_min_on,
    meta_on_usd_unidades_resumen,
    meta_rf_con_precio,
    monto_minimo_compra_on,
    ons_comprables_para_capital,
    precio_ars_on_usd_por_base_vn,
    tickers_por_tipo,
    tickers_rf_activos,
    tir_al_precio,
    tir_estimada_con_ccl,
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
        # TIR de TLCTO actualizada a 7.5% (era 8.0% en datos de mar-26)
        df = pd.DataFrame([{"TICKER": "TLCTO", "PESO_PCT": 1.0, "TIPO": "ON"}])
        assert abs(float(tir_ponderada_cartera(df)) - 7.5) < 1e-6

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


def test_precio_ars_on_usd_por_base_vn_coincide_con_ejemplo_100_vn():
    # Paridad 104,7 % y CCL 1465 → 104,7 × 1465 ARS por cada 100 VN USD
    p = precio_ars_on_usd_por_base_vn(104.7, 1465.0, vn_usd=ON_USD_PARIDAD_BASE_VN)
    assert p == pytest.approx(104.7 * 1465.0)


def test_analisis_obligaciones_negociables_cubre_todas_on_usd():
    df = analisis_obligaciones_negociables_usd_df(1465.0)
    n_on = len(tickers_por_tipo("ON_USD"))
    assert len(df) == n_on
    assert "TLCTO" in set(df["Ticker"])
    col_px = f"ARS / {int(ON_USD_PARIDAD_BASE_VN)} VN USD (×CCL)"
    assert col_px in df.columns
    assert df.loc[df["Ticker"] == "TLCTO", col_px].iloc[0] > 0


def test_meta_on_usd_unidades_tlcto():
    m = meta_on_usd_unidades_resumen("TLCTO")
    assert m is not None
    assert m["paridad_es_pct_sobre_nominal_usd"] is True
    assert m["base_vn_paridad_pct"] == ON_USD_PARIDAD_BASE_VN


def test_descripcion_legible_no_vacia():
    assert len(descripcion_legible("PN43O")) > 5


def test_tickers_rf_activos_no_vacio():
    t = tickers_rf_activos()
    assert len(t) >= 5


class TestP2Rf05FichaCatalogo:
    def test_isin_guion_si_ausente(self):
        assert ficha_rf_isin(None) == GUION_FICHA_RF
        assert ficha_rf_isin({}) == GUION_FICHA_RF
        assert ficha_rf_isin({"isin": ""}) == GUION_FICHA_RF

    def test_al30_tiene_isin_en_catálogo(self):
        m = get_meta("AL30")
        assert m is not None
        assert ficha_rf_isin(m) == "ARARGE3209S6"
        assert "Step-up" in ficha_rf_forma_amortizacion(m)

    def test_denominacion_desde_lamina_min(self):
        m = get_meta("TLCTO")
        assert m is not None
        assert "USD VN" in ficha_rf_denominacion_min(m)

    def test_denominacion_texto_libre(self):
        assert ficha_rf_denominacion_min({"denominacion_min": "Lote mín. 500 u$s"}) == "Lote mín. 500 u$s"


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


class TestP2Rf01FichaMinima:
    def test_sin_catalogo_ok_false(self):
        b = ficha_rf_minima_bundle("NOTATICKER")
        assert b["ok"] is False
        assert b["motivo"] == "sin_meta_catalogo"

    def test_tlcto_con_paridad_tir_a_precio(self):
        m = get_meta("TLCTO")
        assert m is not None
        b = ficha_rf_minima_bundle(
            "TLCTO",
            m,
            paridad_pct=float(m["paridad_ref"]),
            fuente_precio="Catálogo ref.",
        )
        assert b["ok"] is True
        assert b["tir_ref_pct"] == pytest.approx(float(m["tir_ref"]), rel=0.01)
        assert b["tir_a_precio_pct"] == pytest.approx(float(m["tir_ref"]), rel=0.01)
        assert b["tir_a_precio_motivo"] is None
        assert b["isin"] == GUION_FICHA_RF
        assert "ARS por 100" in b["unidad_precio"]
        assert b["cashflow_ilustrativo_disponible"] is True

    def test_tlcto_sin_paridad_motivo(self):
        m = get_meta("TLCTO")
        assert m is not None
        b = ficha_rf_minima_bundle("TLCTO", m)
        assert b["ok"] is True
        assert b["tir_a_precio_pct"] is None
        assert b["tir_a_precio_motivo"] == "sin_paridad_mercado"

    def test_al30_isin_y_escala_flag(self):
        m = get_meta("AL30")
        assert m is not None
        b = ficha_rf_minima_bundle(
            "AL30",
            m,
            paridad_pct=63.5,
            escala_div100_aplicada=True,
            nota_escala="Ajuste ×100 BYMA aplicado al último.",
        )
        assert b["ok"] is True
        assert b["isin"] == "ARARGE3209S6"
        assert b["escala_div100_aplicada"] is True
        assert "×100" in (b["nota_escala"] or "")

    def test_meta_sin_tir_ref(self):
        b = ficha_rf_minima_bundle(
            "X",
            {"emisor": "X", "descripcion": "Y", "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2030-01-01"},
        )
        assert b["ok"] is True
        assert b["tir_ref_pct"] is None
        assert b["tir_a_precio_motivo"] == "sin_tir_ref"


class TestCashflowIlustrativoP2Rf02:
    def test_disclaimer_menciona_prospecto(self):
        assert "prospecto" in DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF.lower()

    def test_fecha_vencimiento_desde_meta_tlcto(self):
        m = get_meta("TLCTO")
        assert m is not None
        d = fecha_vencimiento_desde_meta(m)
        assert d == date(2036, 1, 20)

    def test_bono_cupon_cero_un_flujo_amortizacion(self):
        m = get_meta("GD30")
        assert m is not None
        cf = cashflow_ilustrativo_por_100_vn(m, hoy=date(2020, 1, 1), solo_futuros=True)
        assert cf["ok"] is True
        assert len(cf["filas"]) == 1
        row = cf["filas"][0]
        assert set(row.keys()) == {"fecha", "concepto", "monto_100vn", "moneda"}
        assert row["monto_100vn"] == 100.0
        assert row["moneda"] == "USD"

    def test_cupon_fijo_semestral_columnas_y_ultimo_mayor(self):
        m = get_meta("TLCTO")
        cf = cashflow_ilustrativo_por_100_vn(m, hoy=date(2030, 6, 1), solo_futuros=True)
        assert cf["ok"] is True
        assert len(cf["filas"]) >= 2
        df = pd.DataFrame(cf["filas"])
        assert list(df.columns) == ["fecha", "concepto", "monto_100vn", "moneda"]
        ultimo = cf["filas"][-1]
        assert "amortización" in ultimo["concepto"].lower() or "vn" in ultimo["concepto"].lower()
        penultimos = [r["monto_100vn"] for r in cf["filas"][:-1]]
        assert ultimo["monto_100vn"] > max(penultimos)


# ─── Lámina mínima y utilidades de compra ────────────────────────────────────

class TestLaminaMinima:
    """Lámina mínima en VN USD: unidad negociable mínima por ON."""

    def test_tlcto_lamina_uno(self):
        assert lamina_min_on("TLCTO") == 1

    def test_ym34o_lamina_uno(self):
        assert lamina_min_on("YM34O") == 1

    def test_pn43o_lamina_1000(self):
        assert lamina_min_on("PN43O") == 1_000

    def test_ymcxo_lamina_1000(self):
        assert lamina_min_on("YMCXO") == 1_000

    def test_dnc7o_lamina_100(self):
        assert lamina_min_on("DNC7O") == 100

    def test_tsc4o_lamina_10000(self):
        assert lamina_min_on("TSC4O") == 10_000

    def test_cedear_devuelve_1(self):
        """Para un ticker CEDEAR la lámina es 1 (unidad única)."""
        assert lamina_min_on("AAPL") == 1

    def test_ticker_inexistente_devuelve_1(self):
        assert lamina_min_on("ZZZZZ") == 1


class TestMontoMinimoCompraOn:
    """monto_minimo_compra_on: monto en USD/ARS para 1 lámina completa."""

    def test_tlcto_monto_min_usd_aprox_paridad(self):
        """TLCTO lám=1 → monto_min_usd ≈ paridad/100 ≈ 1.025 USD."""
        m = monto_minimo_compra_on("TLCTO", ccl=1429.0)
        assert m["lamina_vn_usd"] == 1
        assert m["monto_min_usd"] == pytest.approx(1.025, rel=0.05)
        assert m["monto_min_ars"] == pytest.approx(1025 * 1429 / 1000, rel=0.05)

    def test_pn43o_monto_min_usd_aprox_1030(self):
        """PN43O lám=1000 → monto_min_usd ≈ 1000 × 103% ≈ 1030 USD."""
        m = monto_minimo_compra_on("PN43O", ccl=1429.0)
        assert m["lamina_vn_usd"] == 1_000
        assert m["monto_min_usd"] == pytest.approx(1030.0, rel=0.05)

    def test_tsc4o_monto_min_usd_aprox_9780(self):
        """TSC4O lám=10000 → monto_min_usd ≈ 10000 × 97.8% ≈ 9780 USD."""
        m = monto_minimo_compra_on("TSC4O", ccl=1429.0)
        assert m["lamina_vn_usd"] == 10_000
        assert m["monto_min_usd"] == pytest.approx(9_780.0, rel=0.05)

    def test_campos_obligatorios_presentes(self):
        m = monto_minimo_compra_on("TLCTO", ccl=1429.0)
        for k in ("lamina_vn_usd", "monto_min_usd", "monto_min_ars", "paridad_ref", "fecha_ref"):
            assert k in m

    def test_escala_con_ccl(self):
        """monto_min_ars debe escalar proporcionalmente al CCL."""
        m1 = monto_minimo_compra_on("TLCTO", ccl=1000.0)
        m2 = monto_minimo_compra_on("TLCTO", ccl=1500.0)
        assert m2["monto_min_ars"] == pytest.approx(m1["monto_min_ars"] * 1.5, rel=0.001)


class TestOnsComprablesParaCapital:
    """ons_comprables_para_capital filtra por lámina y horizonte."""

    def test_tsc4o_excluida_con_1000_usd(self):
        """TSC4O requiere ~9.780 USD; no aparece con USD 1.000."""
        result = ons_comprables_para_capital(1_000.0, horizonte_meses=12)
        tickers = [o["ticker"] for o in result]
        assert "TSC4O" not in tickers

    def test_tsc4o_incluida_con_10000_usd(self):
        """Con USD 10.000 se puede comprar 1 lámina de TSC4O."""
        result = ons_comprables_para_capital(10_000.0, horizonte_meses=12)
        tickers = [o["ticker"] for o in result]
        assert "TSC4O" in tickers

    def test_tlcto_incluida_con_500_usd(self):
        """TLCTO (lámina=1) siempre comprable con cualquier capital > 0."""
        result = ons_comprables_para_capital(500.0, horizonte_meses=12)
        assert any(o["ticker"] == "TLCTO" for o in result)

    def test_mrcao_excluida_por_vencimiento_12m(self):
        """MRCAO vence en ~30 días — excluida con horizonte_meses=12."""
        result = ons_comprables_para_capital(10_000.0, horizonte_meses=12)
        tickers = [o["ticker"] for o in result]
        assert "MRCAO" not in tickers
        assert "YCA6O" not in tickers

    def test_cso2o_excluida_por_inactiva(self):
        """CSO2O tiene activo=False — excluida siempre."""
        result = ons_comprables_para_capital(100_000.0, horizonte_meses=1)
        tickers = [o["ticker"] for o in result]
        assert "CSO2O" not in tickers

    def test_ordenada_por_tir_desc(self):
        """Resultado ordenado de mayor a menor TIR."""
        result = ons_comprables_para_capital(10_000.0, horizonte_meses=12)
        tirs = [o["tir_ref"] for o in result]
        assert tirs == sorted(tirs, reverse=True)

    def test_campos_requeridos(self):
        result = ons_comprables_para_capital(5_000.0, horizonte_meses=12)
        for o in result:
            for k in ("ticker", "emisor", "paridad_ref", "tir_ref", "lamina_min",
                      "monto_min_usd", "vencimiento", "dias_al_vto", "calificacion", "fecha_ref"):
                assert k in o, f"Falta campo '{k}' en {o['ticker']}"

    def test_capital_cero_devuelve_vacio(self):
        """Con capital=0, ninguna ON es comprable."""
        result = ons_comprables_para_capital(0.0, horizonte_meses=12)
        assert result == []


class TestTirEstimadaConCcl:
    """tir_estimada_con_ccl recomputa TIR desde paridad_ref × CCL live."""

    def test_tlcto_devuelve_tir_ref(self):
        """TLCTO paridad_ref=102.5 → tir ≈ tir_ref=7.5."""
        tir = tir_estimada_con_ccl("TLCTO", ccl=1429.0)
        assert tir == pytest.approx(7.5, abs=0.5)

    def test_ticker_cedear_devuelve_none(self):
        assert tir_estimada_con_ccl("AAPL", ccl=1429.0) is None

    def test_ticker_inexistente_devuelve_none(self):
        assert tir_estimada_con_ccl("ZZZZZ", ccl=1429.0) is None

    def test_ccl_cero_devuelve_none(self):
        assert tir_estimada_con_ccl("TLCTO", ccl=0.0) is None


class TestPrecioReferenciaArsDesdeCatalogo:
    """A04: normalizador único paridad→ARS/VN (antes repetido en 3 sitios)."""

    def test_on_usd_paridad_por_ccl(self):
        from core.renta_fija_ar import get_meta, precio_referencia_ars_desde_catalogo

        meta = get_meta("PN43O")
        esperado = (float(meta["paridad_ref"]) / 100.0) * 1429.0
        assert precio_referencia_ars_desde_catalogo("PN43O", 1429.0) == pytest.approx(esperado)

    def test_vn_multiplica(self):
        from core.renta_fija_ar import precio_referencia_ars_desde_catalogo

        p1 = precio_referencia_ars_desde_catalogo("PN43O", 1429.0, vn=1.0)
        p100 = precio_referencia_ars_desde_catalogo("PN43O", 1429.0, vn=100.0)
        assert p100 == pytest.approx(p1 * 100.0)

    def test_usd_sin_ccl_cero(self):
        from core.renta_fija_ar import precio_referencia_ars_desde_catalogo

        assert precio_referencia_ars_desde_catalogo("PN43O", 0.0) == 0.0

    def test_ticker_fuera_catalogo_cero(self):
        from core.renta_fija_ar import precio_referencia_ars_desde_catalogo

        assert precio_referencia_ars_desde_catalogo("AAPL", 1429.0) == 0.0
        assert precio_referencia_ars_desde_catalogo("", 1429.0) == 0.0

    def test_moneda_ars_no_usa_ccl(self):
        from core.renta_fija_ar import INSTRUMENTOS_RF, precio_referencia_ars_desde_catalogo

        t_ars = next(
            (t for t, m in INSTRUMENTOS_RF.items()
             if str(m.get("moneda", "")).upper() == "ARS" and float(m.get("paridad_ref", 0) or 0) > 0),
            None,
        )
        if t_ars is None:
            pytest.skip("catálogo sin instrumentos ARS con paridad")
        con_ccl = precio_referencia_ars_desde_catalogo(t_ars, 1429.0)
        sin_ccl = precio_referencia_ars_desde_catalogo(t_ars, 0.0)
        assert con_ccl == sin_ccl > 0
