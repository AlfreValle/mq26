"""tests/test_valoracion_audit.py — Cobertura live vs fallback por tipo."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.price_engine import PriceRecord, PriceSource
from services.valoracion_audit import auditar_inferido_live_vs_resto, auditar_valoracion_por_tipo


def test_pct_valor_live_correcto():
    df = pd.DataFrame({
        "TICKER": ["A", "B"],
        "TIPO": ["CEDEAR", "FCI"],
        "VALOR_ARS": [60_000.0, 40_000.0],
    })
    rec = {
        "A": PriceRecord(
            "A", 1.0, 1.0, 1.0, 1.0, PriceSource.LIVE_YFINANCE, datetime.now(),
        ),
        "B": PriceRecord(
            "B", 1.0, 1.0, 1.0, 1.0, PriceSource.FALLBACK_HARD, datetime.now(),
        ),
    }
    r = auditar_valoracion_por_tipo(df, rec)
    assert r["pct_valor_live"] == 60.0
    assert r["por_tipo"]["CEDEAR"]["pct_valor_live"] == 100.0
    assert r["por_tipo"]["FCI"]["pct_valor_live"] == 0.0


def test_auditar_inferido():
    df = pd.DataFrame({
        "TICKER": ["X"],
        "TIPO": ["RV"],
        "VALOR_ARS": [10_000.0],
    })
    r = auditar_inferido_live_vs_resto(df, {"X": 1.0}, {"X": 1.0})
    assert r["pct_valor_live"] == 100.0
