"""SSOT RF/RV por perfil."""
import pytest

from core.perfil_allocation import (
    RULESET_VERSION,
    TARGET_RF_RV_BY_PERFIL,
    exceso_rv_muy_arriesgado,
    target_rf_efectivo,
    target_rv_efectivo,
)


def test_ruleset_version_presente():
    assert RULESET_VERSION


def test_target_rf_conservador():
    rf, rv = TARGET_RF_RV_BY_PERFIL["Conservador"]
    assert rf == pytest.approx(0.60)
    assert rv == pytest.approx(0.40)
    assert target_rf_efectivo("Conservador", "3 años") == pytest.approx(0.60)
    assert target_rv_efectivo("Conservador", "3 años") == pytest.approx(0.40)


def test_horizonte_corto_sube_rf():
    assert target_rf_efectivo("Moderado", "3 meses") == pytest.approx(0.60)


def test_muy_arriesgado_bandas_rv():
    assert exceso_rv_muy_arriesgado(0.72) == ""
    assert exceso_rv_muy_arriesgado(0.76) == "amarillo"
    assert exceso_rv_muy_arriesgado(0.86) == "rojo"
