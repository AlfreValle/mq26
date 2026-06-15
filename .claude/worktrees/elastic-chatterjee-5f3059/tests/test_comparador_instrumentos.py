# tests/test_comparador_instrumentos.py
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch


def _mock_download(tickers, start=None, progress=False, auto_adjust=True):
    """Mock de yf.download que retorna precios sintéticos."""
    if isinstance(tickers, str):
        tickers_list = [tickers]
    elif isinstance(tickers, list):
        tickers_list = tickers
    else:
        tickers_list = list(tickers)

    n = 264
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range(start or "2005-01-01", periods=n * 5, freq="B")[: n * 5]

    # Filtrar tickers especiales que no tienen precio de acción real
    cols = [t for t in tickers_list if t not in ("ARS=X",)]
    if not cols:
        # Para ARS=X devolver serie simple
        df = pd.DataFrame(
            {"Close": 100 * np.cumprod(1 + rng.normal(0.003, 0.005, len(idx)))},
            index=idx,
        )
        return df

    data = {c: 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, len(idx))) for c in cols}
    if len(cols) == 1:
        return pd.DataFrame({"Close": data[cols[0]]}, index=idx)
    inner = pd.DataFrame(data, index=idx)
    return pd.concat({"Close": inner}, axis=1)


def test_generar_comparador_retorna_figura():
    with patch("services.comparador_instrumentos.yf.download", side_effect=_mock_download):
        import importlib
        import services.comparador_instrumentos as m
        importlib.reload(m)
        import plotly.graph_objects as go
        fig = m.generar_comparador_instrumentos(start="2020-01-01", capital=1000.0)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 4, "Debe tener al menos 4 series"


def test_generar_comparador_fallback_sin_yfinance():
    """Sin yfinance, debe retornar figura válida con datos sintéticos."""
    with patch(
        "services.comparador_instrumentos.yf.download",
        side_effect=Exception("sin red"),
    ):
        import importlib
        import services.comparador_instrumentos as m
        importlib.reload(m)
        import plotly.graph_objects as go
        fig = m.generar_comparador_instrumentos(start="2020-01-01")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 4


def test_serie_plazo_fijo_crece():
    from services.comparador_instrumentos import _serie_plazo_fijo
    s = _serie_plazo_fijo(start="2020-01-01", capital=1000.0)
    assert float(s.iloc[-1]) > 1000.0, "El plazo fijo debe crecer (tasas positivas)"
    assert s.isna().sum() == 0, "Sin NaN"


def test_comparador_capital_se_preserva_en_inicio():
    with patch("services.comparador_instrumentos.yf.download", side_effect=_mock_download):
        import importlib
        import services.comparador_instrumentos as m
        importlib.reload(m)
        s = m._serie_spy(start="2020-01-01", capital=5000.0)
    assert abs(float(s.iloc[0]) - 5000.0) < 200, (
        f"El primer valor debe ser ~5000, es {float(s.iloc[0]):.2f}"
    )
