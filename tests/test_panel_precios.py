import numpy as np
import pandas as pd

from core.panel_precios import validar_panel_precios


def test_panel_ok_datos_completos():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.01, size=(120, 3))
    p = 100 * np.exp(np.cumsum(r, axis=0))
    df = pd.DataFrame(p, columns=["A", "B", "C"])
    ok, msg = validar_panel_precios(df, ["A", "B", "C"], min_obs=30)
    assert ok is True
    assert "precios" in msg.lower()


def test_panel_falla_si_falta_ticker():
    df = pd.DataFrame({"A": [1.0] * 50, "B": [1.0] * 50})
    ok, msg = validar_panel_precios(df, ["A", "Z"], min_obs=30)
    assert ok is False
    assert "Z" in msg or "Falta" in msg


def test_panel_falla_obs_insuficientes():
    df = pd.DataFrame({"A": [np.nan] * 40 + [1.0] * 10, "B": [1.0] * 50})
    ok, _ = validar_panel_precios(df, ["A", "B"], min_obs=45)
    assert ok is False
