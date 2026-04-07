"""tests/test_rf_panel_taxonomy.py — Taxonomía panel BYMA (heurística MVP)."""
from core.rf_panel_taxonomy import FamiliaPanelRF, familia_desde_prefijos


def test_prefijo_bopreal():
    assert familia_desde_prefijos("BPY26") == FamiliaPanelRF.BOPREAL


def test_familia_a_tipo_incluye_bopreal():
    from core.rf_panel_taxonomy import FAMILIA_A_TIPO_MQ26

    assert FAMILIA_A_TIPO_MQ26[FamiliaPanelRF.BOPREAL] == "BOPREAL"
