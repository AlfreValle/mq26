import pandas as pd
import pytest

from core.fx_panel import panel_precios_a_moneda_base


def test_fx_convierte_ars_a_usd():
    df = pd.DataFrame({"GGAL": [1500.0, 3000.0], "SPY": [400.0, 410.0]})
    out = panel_precios_a_moneda_base(
        df, {"GGAL"}, moneda_base="USD", ccl_ars_por_usd=1500.0,
    )
    assert out["GGAL"].iloc[0] == pytest.approx(1.0)
    assert out["SPY"].iloc[0] == pytest.approx(400.0)


def test_misma_moneda_ars_sin_conversion():
    df = pd.DataFrame({"A": [1.0]})
    out = panel_precios_a_moneda_base(df, {"A"}, moneda_base="ARS", ccl_ars_por_usd=1500.0)
    assert out["A"].iloc[0] == pytest.approx(1.0)
