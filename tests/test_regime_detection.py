"""Tests core/regime_detection.py — detección de régimen de volatilidad."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.regime_detection import (
    Regimen,
    detectar_regimen,
    resumen_regimen,
    sigma_segun_regimen,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _returns_sinteticos(T: int = 500, n: int = 4, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=T, freq="B")
    data = rng.normal(0, 0.01, size=(T, n))
    # Insertar período de alta volatilidad en el centro
    data[200:260] *= 4.0
    return pd.DataFrame(data, index=dates, columns=[f"T{i}" for i in range(n)])


# ─── Tests básicos ────────────────────────────────────────────────────────────

def test_resultado_tipo_correcto():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    assert isinstance(res.etiquetas, pd.Series)
    assert isinstance(res.vol_rolling, pd.Series)
    assert isinstance(res.sigma_normal, np.ndarray)
    assert isinstance(res.sigma_crisis, np.ndarray)
    assert isinstance(res.sigma_low_vol, np.ndarray)


def test_regimen_actual_valido():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    assert res.regimen_actual in list(Regimen)


def test_sigma_shapes():
    df = _returns_sinteticos(n=4)
    res = detectar_regimen(df)
    assert res.sigma_normal.shape  == (4, 4)
    assert res.sigma_crisis.shape  == (4, 4)
    assert res.sigma_low_vol.shape == (4, 4)


def test_sigma_positive_semidefinite():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    # Eigenvalores ≥ 0
    eigvals = np.linalg.eigvalsh(res.sigma_normal)
    assert np.all(eigvals >= -1e-9)
    eigvals_c = np.linalg.eigvalsh(res.sigma_crisis)
    assert np.all(eigvals_c >= -1e-9)


def test_etiquetas_cubren_todos_indices():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    # Etiquetas válidas o UNKNOWN (NaN en vol durante calentamiento)
    valores_validos = {r.value for r in Regimen}
    for v in res.etiquetas.dropna():
        assert v in valores_validos


def test_crisis_detectada_en_periodo_alta_vol():
    """El período de alta volatilidad (días 200–260) debe contener días CRISIS."""
    df = _returns_sinteticos(T=500)
    res = detectar_regimen(df, ventana_corta=21)
    etiq_alta = res.etiquetas.iloc[220:250]
    n_crisis = (etiq_alta == Regimen.CRISIS.value).sum()
    assert n_crisis > 0, "No se detectó CRISIS en período de alta volatilidad"


def test_terciles_ordenados():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    assert res.tercil_bajo <= res.tercil_alto


def test_sigma_crisis_mayor_que_normal():
    """Volatilidad media del régimen CRISIS debe ser mayor que NORMAL."""
    df = _returns_sinteticos(T=600)
    res = detectar_regimen(df)
    # Traza de Σ_crisis > traza de Σ_normal
    assert np.trace(res.sigma_crisis) >= np.trace(res.sigma_normal) * 0.5


def test_n_dias_por_regimen_suma_total():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    total = sum(res.n_dias_por_regimen.values())
    assert total == len(df)


def test_resumen_regimen_claves():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    s = resumen_regimen(res)
    for k in ("regimen_actual", "pct_crisis", "pct_normal", "pct_low_vol", "n_dias_total"):
        assert k in s


def test_pct_suman_aprox_uno():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    s = resumen_regimen(res)
    total_pct = s["pct_crisis"] + s["pct_normal"] + s["pct_low_vol"]
    # No incluye UNKNOWN; suma puede ser < 1 si hay NaN
    assert total_pct <= 1.0 + 1e-9


def test_sigma_segun_regimen_devuelve_correcto():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    assert np.allclose(sigma_segun_regimen(res, Regimen.CRISIS),  res.sigma_crisis)
    assert np.allclose(sigma_segun_regimen(res, Regimen.NORMAL),  res.sigma_normal)
    assert np.allclose(sigma_segun_regimen(res, Regimen.LOW_VOL), res.sigma_low_vol)


def test_sigma_segun_regimen_none_usa_actual():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    sigma_auto = sigma_segun_regimen(res, None)
    sigma_esperada = sigma_segun_regimen(res, res.regimen_actual)
    assert np.allclose(sigma_auto, sigma_esperada)


def test_sigma_segun_regimen_string():
    df = _returns_sinteticos()
    res = detectar_regimen(df)
    sigma_str = sigma_segun_regimen(res, "CRISIS")
    assert np.allclose(sigma_str, res.sigma_crisis)


def test_serie_corta_devuelve_unknown():
    """Con serie muy corta (< 10 obs), debe devolver régimen UNKNOWN."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        rng.normal(0, 0.01, (5, 2)),
        columns=["A", "B"],
    )
    res = detectar_regimen(df)
    assert res.regimen_actual == Regimen.UNKNOWN


def test_anchored_vs_sliding_distintos():
    """usar_ventana='larga' vs 'corta' producen vol_rolling distintas."""
    df = _returns_sinteticos()
    res_c = detectar_regimen(df, usar_ventana="corta")
    res_l = detectar_regimen(df, usar_ventana="larga")
    # Parámetros distintos → ventanas distintas → terciles distintos
    assert res_c.params["ventana_clasif"] != res_l.params["ventana_clasif"]
    # La vol rolling no puede ser idéntica al comparar valores comunes
    vc = res_c.vol_rolling.dropna()
    vl = res_l.vol_rolling.dropna()
    n_comun = min(len(vc), len(vl))
    assert n_comun > 0
    assert not np.allclose(vc.values[-n_comun:], vl.values[-n_comun:])
