"""tests/test_mq26_ux_dataframe_height.py — P3-UX-01: helper altura tablas."""
import pandas as pd

from ui.mq26_ux import dataframe_auto_height


def test_dataframe_auto_height_mismo_resultado_con_styler():
    df = pd.DataFrame({"a": range(5)})
    sty = df.style.format({"a": "{:d}"})
    h_df = dataframe_auto_height(df)
    h_sty = dataframe_auto_height(sty)
    assert h_df == h_sty
    assert h_df == 56 + 5 * 30  # header_px + n*row_px por defecto


def test_dataframe_auto_height_respeta_max():
    df = pd.DataFrame({"x": range(100)})
    assert dataframe_auto_height(df, max_px=400) == 400
