"""Tests A15 — core/stale_policy.py: política de datos viejos por tipo de activo."""
from __future__ import annotations

from datetime import datetime, timedelta

from core.stale_policy import (
    Frescura,
    clasificar_frescura,
    es_stale,
    umbrales_minutos,
)

AHORA = datetime(2026, 6, 11, 15, 0, 0)


def _ts(minutos_atras: float) -> datetime:
    return AHORA - timedelta(minutes=minutos_atras)


class TestUmbrales:
    def test_rv_liquida_minutos(self):
        fresco, stale = umbrales_minutos("CEDEAR")
        assert fresco <= 30
        assert stale <= 120

    def test_rf_tolera_horas(self):
        fresco, stale = umbrales_minutos("ON_USD")
        assert fresco >= 60
        assert stale >= 60 * 12

    def test_fci_tolera_dias(self):
        _, stale = umbrales_minutos("FCI")
        assert stale >= 60 * 24

    def test_tipo_desconocido_usa_defecto(self):
        fresco, stale = umbrales_minutos("WHATEVER")
        assert fresco > 0
        assert stale > fresco


class TestClasificacion:
    def test_cedear_reciente_fresco(self):
        ev = clasificar_frescura("CEDEAR", _ts(5), AHORA)
        assert ev.frescura is Frescura.FRESCO
        assert ev.frescura.usable_para_recomendacion

    def test_cedear_2h_stale(self):
        ev = clasificar_frescura("CEDEAR", _ts(120), AHORA)
        assert ev.frescura is Frescura.STALE
        assert not ev.frescura.usable_para_recomendacion

    def test_on_2h_usable(self):
        # El mismo timestamp que mata a un CEDEAR sigue usable en una ON
        ev = clasificar_frescura("ON_USD", _ts(120), AHORA)
        assert ev.frescura.usable_para_recomendacion

    def test_on_6h_aceptable(self):
        ev = clasificar_frescura("ON_USD", _ts(360), AHORA)
        assert ev.frescura is Frescura.ACEPTABLE
        assert ev.frescura.usable_para_recomendacion

    def test_on_3dias_stale(self):
        ev = clasificar_frescura("ON_USD", _ts(60 * 72), AHORA)
        assert ev.frescura is Frescura.STALE

    def test_sin_timestamp_sin_dato(self):
        ev = clasificar_frescura("CEDEAR", None, AHORA)
        assert ev.frescura is Frescura.SIN_DATO
        assert ev.antiguedad_min is None

    def test_reloj_adelantado_no_explota(self):
        ev = clasificar_frescura("CEDEAR", AHORA + timedelta(minutes=3), AHORA)
        assert ev.frescura is Frescura.FRESCO
        assert ev.antiguedad_min == 0.0

    def test_antiguedad_reportada(self):
        ev = clasificar_frescura("CEDEAR", _ts(45), AHORA)
        assert ev.antiguedad_min is not None
        assert abs(ev.antiguedad_min - 45.0) < 0.01


class TestEsStale:
    def test_fresco_no_stale(self):
        assert not es_stale("CEDEAR", _ts(5), AHORA)

    def test_aceptable_no_stale(self):
        assert not es_stale("ON_USD", _ts(120), AHORA)

    def test_vencido_stale(self):
        assert es_stale("CEDEAR", _ts(600), AHORA)

    def test_sin_dato_stale(self):
        assert es_stale("CEDEAR", None, AHORA)


class TestLabelFuenteConFrescura:
    def test_none_guion(self):
        from core.price_engine import label_fuente_con_frescura

        assert label_fuente_con_frescura(None) == "—"

    def test_live_limpio(self):
        from core.price_engine import PriceRecord, PriceSource, label_fuente_con_frescura

        rec = PriceRecord(
            ticker="AAPL", precio_cedear_ars=30000, precio_subyacente_usd=200,
            ccl=1450, ratio=20, source=PriceSource.LIVE_BYMA, timestamp=datetime.now(),
        )
        assert label_fuente_con_frescura(rec) == "LIVE"

    def test_fallback_stale_marcado(self):
        from core.price_engine import PriceRecord, PriceSource, label_fuente_con_frescura

        rec = PriceRecord(
            ticker="AAPL", precio_cedear_ars=30000, precio_subyacente_usd=200,
            ccl=1450, ratio=20, source=PriceSource.FALLBACK_BD,
            timestamp=datetime.now(), stale=True,
        )
        assert label_fuente_con_frescura(rec) == "FALLBACK_BD ⚠STALE"

    def test_fallback_fresco_limpio(self):
        from core.price_engine import PriceRecord, PriceSource, label_fuente_con_frescura

        rec = PriceRecord(
            ticker="PN43O", precio_cedear_ars=1473, precio_subyacente_usd=0,
            ccl=1450, ratio=1, source=PriceSource.FALLBACK_CATALOGO_RF,
            timestamp=datetime.now(), stale=False,
        )
        assert label_fuente_con_frescura(rec) == "CATALOGO_RF"


class TestIntegracionPriceEngine:
    def test_aplicar_politica_marca_solo_no_live(self):
        from core.price_engine import PriceRecord, PriceSource, aplicar_politica_stale

        viejo = datetime.now() - timedelta(hours=5)
        records = {
            "AAPL": PriceRecord(
                ticker="AAPL", precio_cedear_ars=30000, precio_subyacente_usd=200,
                ccl=1450, ratio=20, source=PriceSource.FALLBACK_BD, timestamp=viejo,
            ),
            "MSFT": PriceRecord(
                ticker="MSFT", precio_cedear_ars=25000, precio_subyacente_usd=420,
                ccl=1450, ratio=25, source=PriceSource.LIVE_YFINANCE, timestamp=viejo,
            ),
        }
        out = aplicar_politica_stale(records)
        assert out["AAPL"].stale is True       # fallback viejo de RV líquida → STALE
        assert out["MSFT"].stale is False      # live nunca se marca
        assert out["AAPL"].calidad == "STALE"
