"""C02 — winsorizado de retornos."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.returns_sanitize import winsorize_returns_panel


def test_winsor_recorta_extremos():
    rng = np.random.default_rng(0)
    n = 200
    r = rng.normal(0.001, 0.01, n)
    r[5] = 0.50
    r[6] = -0.40
    df = pd.DataFrame({"A": r}, index=pd.date_range("2024-01-01", periods=n, freq="B"))
    out, rep = winsorize_returns_panel(df, lower_q=0.01, upper_q=0.99)
    assert rep["n_recortes_total"] >= 2
    assert out["A"].max() < 0.49
    assert out["A"].min() > -0.39


def test_vacio_no_crash():
    df = pd.DataFrame()
    out, rep = winsorize_returns_panel(df)
    assert out.empty
    assert rep["n_recortes_total"] == 0
