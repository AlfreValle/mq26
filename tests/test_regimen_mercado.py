"""Tests de la detección de régimen de mercado (H2)."""
from __future__ import annotations

import math

from services.regimen_mercado import detectar_regimen


def test_serie_alcista_sostenida_es_tendencial_alcista():
    precios = [100 * (1.004 ** i) for i in range(120)]  # sube ~0.4%/período, suave
    r = detectar_regimen(precios)
    assert r.regimen == "tendencial_alcista"
    assert r.tendencia_pct > 0 and r.efficiency_ratio > 0.3


def test_serie_bajista_sostenida_es_tendencial_bajista():
    precios = [100 * (0.996 ** i) for i in range(120)]
    r = detectar_regimen(precios)
    assert r.regimen == "tendencial_bajista"
    assert r.tendencia_pct < 0


def test_serie_lateral_es_lateral():
    # Oscilación PEQUEÑA alrededor de 100 (±0.3): baja vol y bajo efficiency
    # ratio → sin dirección. (Swings grandes alternados serían caótico, no lateral.)
    precios = [100 + (0.3 if i % 2 == 0 else -0.3) for i in range(120)]
    r = detectar_regimen(precios)
    assert r.regimen == "lateral"
    assert r.vol_anual < 0.40 and r.efficiency_ratio < 0.30


def test_serie_muy_volatil_es_caotico():
    # Swings grandes alternados → vol anualizada altísima.
    precios = [100 * (1.15 if i % 2 == 0 else 0.87) for i in range(120)]
    r = detectar_regimen(precios)
    assert r.regimen == "caotico"
    assert r.vol_anual >= 0.40


def test_serie_corta_es_indeterminado():
    assert detectar_regimen([100, 101, 102]).regimen == "indeterminado"
    assert detectar_regimen([]).regimen == "indeterminado"


def test_robusto_a_nan_y_valores_malos():
    precios = [100, float("nan"), 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    r = detectar_regimen(precios)
    assert r.regimen in {"tendencial_alcista", "lateral", "caotico", "tendencial_bajista"}
    assert not math.isnan(r.vol_anual)


def test_cada_regimen_trae_descripcion_y_sugerencia():
    r = detectar_regimen([100 * (1.004 ** i) for i in range(120)])
    assert r.descripcion and r.sugerencia  # alcista trae ambas
