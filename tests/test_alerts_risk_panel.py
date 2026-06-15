"""Panel HTML de riesgo de cartera (pedagogía + umbrales)."""
from __future__ import annotations

from config import (
    CONCENTRACION_ACTIVO_ALERTA,
    CONCENTRACION_SECTOR_ALERTA,
    NOTA_ALERTA,
)
from ui.components.alerts import build_cartera_riesgo_panel_html


def test_risk_panel_warn_includes_threshold_copy_and_mod23_legend():
    html_out = build_cartera_riesgo_panel_html(
        alertas_activo=[
            {"ticker": "SPY", "peso": 0.35, "limite": CONCENTRACION_ACTIVO_ALERTA},
        ],
        alertas_sector=[
            {"sector": "Otros", "peso": 0.46, "limite": CONCENTRACION_SECTOR_ALERTA},
        ],
        exceso_tickers=["SPY", "TLCTO"],
        peso_max_pct=18.0,
        alertas_tecnicas=[
            {"ticker": "AMZN", "score": 1.0, "estado": "BAJISTA"},
        ],
        umbral_activo_frac=CONCENTRACION_ACTIVO_ALERTA,
        umbral_sector_frac=CONCENTRACION_SECTOR_ALERTA,
        umbral_mod23=NOTA_ALERTA,
    )
    assert "tres chequeos distintos" in html_out
    assert "Diversificaci" in html_out and "(estructura)" in html_out
    assert "Tope por posici" in html_out and "regla operativa" in html_out
    assert "18.0%" in html_out
    assert f"{NOTA_ALERTA:g}" in html_out
    assert "<strong>1</strong>" in html_out
    assert "bajo el umbral" in html_out
    assert "mq-risk-tech-wrap" in html_out


def test_risk_panel_ok_state():
    html_out = build_cartera_riesgo_panel_html(
        alertas_activo=[],
        alertas_sector=[],
        exceso_tickers=[],
        peso_max_pct=18.0,
        alertas_tecnicas=[],
    )
    assert "mq-risk-panel--ok" in html_out
    assert "Tres revisiones independientes" in html_out
