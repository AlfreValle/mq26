"""Tests del tilt táctico régimen→recomendador (H2)."""
from __future__ import annotations

from core.cartera_optima import PERFIL_CONSTRAINTS, _asignar_pct_clases
from services.regimen_mercado import tilt_rf_por_regimen


def test_tilt_signo_por_regimen():
    assert tilt_rf_por_regimen("caotico") > 0          # más defensivo
    assert tilt_rf_por_regimen("tendencial_bajista") > 0
    assert tilt_rf_por_regimen("tendencial_alcista") < 0  # más RV
    assert tilt_rf_por_regimen("lateral") == 0.0
    assert tilt_rf_por_regimen("indeterminado") == 0.0
    assert tilt_rf_por_regimen(None) == 0.0


def test_sin_regimen_no_cambia_la_asignacion():
    base = _asignar_pct_clases("Moderado")
    igual = _asignar_pct_clases("Moderado", regimen=None)
    assert base == igual  # backward-compatible


def test_caotico_sube_rf_y_alcista_la_baja():
    base = _asignar_pct_clases("Moderado")
    caos = _asignar_pct_clases("Moderado", regimen="caotico")
    alza = _asignar_pct_clases("Moderado", regimen="tendencial_alcista")
    assert caos["RF"] > base["RF"]    # caótico → más renta fija
    assert alza["RF"] < base["RF"]    # alcista → menos renta fija
    # RF+RV se conserva (no cambia perlas/renta_ar)
    for d in (base, caos, alza):
        assert abs((d["RF"] + d["RV"]) - (base["RF"] + base["RV"])) < 1e-9


def test_tilt_respeta_la_banda_del_perfil():
    # Aun con el régimen más defensivo, la RF no supera rf_max del perfil ni
    # deja la RV en cero.
    for perfil in ("Conservador", "Moderado", "Arriesgado"):
        c = PERFIL_CONSTRAINTS[perfil]
        for reg in ("caotico", "tendencial_bajista", "tendencial_alcista", "lateral"):
            d = _asignar_pct_clases(perfil, regimen=reg)
            assert d["RF"] <= c["rf_max"] + 1e-9, (perfil, reg, d["RF"])
            assert d["RF"] >= min(c["rf_min"], d["RF"]) - 1e-9
            assert d["RV"] >= 0.0
