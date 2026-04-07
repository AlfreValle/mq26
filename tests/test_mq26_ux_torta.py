"""tests/test_mq26_ux_torta.py — Torta ideal incluye bucket SSOT _RENTA_AR."""
from ui.mq26_ux import fig_torta_ideal


def test_fig_torta_ideal_incluye_renta_fija_bucket():
    fig = fig_torta_ideal("Moderado", {"_RENTA_AR": 0.15, "SPY": 0.85})
    pie = fig.data[0]
    labels = list(pie.labels)
    assert "Renta fija AR (otros)" in labels
    assert "SPY" in labels
