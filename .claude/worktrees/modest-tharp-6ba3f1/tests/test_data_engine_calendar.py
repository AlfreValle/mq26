"""C03 — alineación de calendario en panel de precios (inner join de fechas)."""
from __future__ import annotations

import pandas as pd

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "1_Scripts_Motor"))
from data_engine import alinear_panel_precios_cierre


def test_inner_drop_fechas_sin_todos_los_tickers():
    idx = pd.to_datetime(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    )
    df = pd.DataFrame(
        {
            "A": [100.0, 101.0, float("nan"), 103.0],
            "B": [200.0, float("nan"), 202.0, 204.0],
        },
        index=idx,
    )
    out = alinear_panel_precios_cierre(df, strict_inner=True)
    # Solo fechas con ambos activos sin NaN (2024-01-02 y 2024-01-05).
    assert len(out) == 2
    assert pd.Timestamp("2024-01-02") in out.index
    assert out.loc[pd.Timestamp("2024-01-02"), "A"] == 100.0


def test_relaxed_ffill_recupera_alguna_fila():
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    df = pd.DataFrame(
        {"X": [1.0, 2.0, float("nan"), 4.0, 5.0], "Y": [10.0] * 5},
        index=idx,
    )
    out = alinear_panel_precios_cierre(df, strict_inner=False, ffill_limit=2)
    assert len(out) >= 3
    assert not out.isna().any().any()
