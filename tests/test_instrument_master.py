"""Tests A01 — core/instrument_master.py: maestro único de instrumentos."""
from __future__ import annotations

import pandas as pd
import pytest

from core.instrument_master import (
    TIPOS_CANONICOS,
    InstrumentMaster,
    get_master,
    normalizar_tipo,
    validar_ticker,
)
from core.renta_fija_ar import INSTRUMENTOS_RF


@pytest.fixture()
def master() -> InstrumentMaster:
    return InstrumentMaster()


@pytest.fixture()
def master_con_universo() -> InstrumentMaster:
    df = pd.DataFrame(
        {
            "Ticker": ["AAPL", "GGAL", "XCUSTOM"],
            "Ratio": ["20:1", "1", "5"],
            "Nombre": ["Apple Inc", "Grupo Galicia", "Custom Corp"],
            "Sector": ["Tecnología", "Bancos", ""],
            "Tipo": ["CEDEAR", "ACCION_LOCAL", "CEDEAR"],
        }
    )
    return InstrumentMaster(df)


class TestNormalizarTipo:
    def test_canonicos_pasan(self):
        for t in ("CEDEAR", "ON_USD", "BONO_USD", "FCI", "ETF"):
            assert normalizar_tipo(t) == t

    def test_alias_accion(self):
        assert normalizar_tipo("ACCION") == "ACCION_LOCAL"
        assert normalizar_tipo("acción") == "ACCION_LOCAL"
        assert normalizar_tipo("LOCAL") == "ACCION_LOCAL"

    def test_basura_vacio(self):
        assert normalizar_tipo(None) == ""
        assert normalizar_tipo("nan") == ""
        assert normalizar_tipo("INVENTADO") == ""

    def test_taxonomia_incluye_rf_y_rv(self):
        assert "ON_USD" in TIPOS_CANONICOS
        assert "CEDEAR" in TIPOS_CANONICOS
        assert "BONCER" in TIPOS_CANONICOS


class TestConsolidacion:
    def test_cedear_de_config(self, master):
        inst = master.get("AAPL")
        assert inst is not None
        assert inst.tipo == "CEDEAR"
        assert inst.ratio_cedear and inst.ratio_cedear > 0

    def test_rf_manda_sobre_universo(self, master):
        # Todo ticker del catálogo RF debe reportar tipo RF, nunca CEDEAR
        algun_rf = next(iter(INSTRUMENTOS_RF))
        inst = master.get(algun_rf)
        assert inst is not None
        assert inst.es_renta_fija
        assert "catalogo_rf" in inst.fuentes

    def test_rf_tiene_meta(self, master):
        algun_rf = next(iter(INSTRUMENTOS_RF))
        inst = master.get(algun_rf)
        assert inst.emisor
        assert inst.vencimiento

    def test_universo_pisa_ratio(self, master_con_universo):
        assert master_con_universo.ratio("AAPL") == 20.0

    def test_universo_agrega_ticker_nuevo(self, master_con_universo):
        inst = master_con_universo.get("XCUSTOM")
        assert inst is not None
        assert inst.tipo == "CEDEAR"
        assert "universo" in inst.fuentes

    def test_accion_local_desde_universo(self, master_con_universo):
        assert master_con_universo.tipo("GGAL") == "ACCION_LOCAL"

    def test_ticker_desconocido(self, master):
        assert master.get("ZZZNOEXISTE") is None
        assert master.tipo("ZZZNOEXISTE") == ""
        assert master.ratio("ZZZNOEXISTE") == 1.0

    def test_case_insensitive(self, master):
        assert master.get("aapl") is not None

    def test_stats_cobertura(self, master):
        s = master.stats()
        assert s["total"] > 300  # ~312 CEDEARs + catálogo RF
        assert s.get("CEDEAR", 0) > 200


class TestValidacion:
    def test_valido_sin_observaciones(self, master):
        v = master.validar("AAPL", "CEDEAR")
        assert v.valido and not v.motivo
        assert v.tipo_resuelto == "CEDEAR"

    def test_vacio_invalido(self, master):
        assert not master.validar("").valido
        assert not master.validar("nan").valido

    def test_desconocido_con_sugerencias(self, master):
        v = master.validar("AAPLL")  # typo de AAPL
        assert not v.valido
        assert "AAPL" in v.sugerencias

    def test_tipo_discrepante_warning_no_bloquea(self, master):
        algun_rf = next(iter(INSTRUMENTOS_RF))
        v = master.validar(algun_rf, "CEDEAR")
        assert v.valido  # no bloquea
        assert v.motivo  # pero avisa
        assert v.tipo_resuelto != "CEDEAR"

    def test_tipos_rf_intercambiables_sin_warning(self, master):
        # Declarar BONO cuando el maestro dice ON_USD no debe chillar:
        # ambos son RF y el alta histórica usa tipos laxos.
        rf_usd = next(
            (t for t, m in INSTRUMENTOS_RF.items() if m.get("tipo") == "ON_USD"), None
        )
        if rf_usd is None:
            pytest.skip("catálogo sin ON_USD")
        v = master.validar(rf_usd, "BONO")
        assert v.valido and not v.motivo


class TestSingleton:
    def test_get_master_cachea(self):
        assert get_master() is get_master()

    def test_rebuild_con_universo_nuevo(self):
        m1 = get_master()
        df = pd.DataFrame({"Ticker": ["NUEVOX"], "Ratio": ["3"], "Tipo": ["CEDEAR"]})
        m2 = get_master(df)
        assert m2.existe("NUEVOX")
        assert m1 is not m2

    def test_validar_ticker_conveniencia(self):
        assert validar_ticker("AAPL").valido
