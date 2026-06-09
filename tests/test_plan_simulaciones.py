"""Tests services/plan_simulaciones.py"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from services.plan_simulaciones import (
    agrupar_pesos_torta,
    dias_desde_primera_compra,
    ideal_dict_desde_mix_plan,
)


def test_dias_desde_primera_compra():
    d0 = date.today() - timedelta(days=100)
    df = pd.DataFrame({"FECHA_COMPRA": [d0], "TICKER": ["SPY"], "PESO_PCT": [1.0]})
    n = dias_desde_primera_compra(df)
    assert n is not None
    assert 99 <= n <= 101


def test_ideal_dict_armado_app():
    from core.diagnostico_types import CARTERA_IDEAL
    from core.renta_fija_ar import es_renta_fija

    perfil = "Moderado"
    base = CARTERA_IDEAL[perfil]
    d, src = ideal_dict_desde_mix_plan(perfil, base, {"rf": 0.6, "ts": 1.0})
    assert src == "armado_app"
    assert abs(sum(d.values()) - 1.0) < 1e-6
    rf = sum(
        v for k, v in d.items()
        if str(k).startswith("_") or es_renta_fija(str(k).upper())
    )
    assert abs(rf - 0.6) < 0.02


def test_agrupar_pesos_torta():
    w = {"A": 0.5, "B": 0.02, "C": 0.02, "D": 0.46}
    g = agrupar_pesos_torta(w, min_frac=0.05)
    assert "Otros" in g or "B" not in g
    assert abs(sum(g.values()) - 1.0) < 1e-6
