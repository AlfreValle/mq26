"""Smoke mínimo: tema, snapshot inversor, contenido mercado."""
from __future__ import annotations

import pandas as pd


def test_mq26_theme_exports():
    from ui.mq26_theme import TOKENS_LIGHT, inject_theme_css_fragments, use_retail_light_theme

    assert isinstance(TOKENS_LIGHT, dict)
    assert "bg" in TOKENS_LIGHT
    assert callable(use_retail_light_theme)
    assert len(inject_theme_css_fragments()) > 10


def test_investor_hub_snapshot_builds():
    from services.investor_hub_snapshot import build_investor_hub_snapshot

    class _Sem:
        value = "verde"

    class _D:
        score_total = 72.0
        semaforo = _Sem()
        titulo_semaforo = "Ok"
        resumen_ejecutivo = "Test"
        pct_defensivo_actual = 0.4
        pct_defensivo_requerido = 0.4
        valor_cartera_usd = 1000.0
        n_posiciones = 3
        rendimiento_ytd_usd_pct = 5.0
        modo_fallback = False
        observaciones = []

    snap = build_investor_hub_snapshot(_D(), {"total_valor": 1_000_000}, 1200.0)
    assert snap["alignment_score_pct"] == 72.0
    assert "acciones_top" in snap


def test_generar_top3_redes_basico():
    from services.contenido_mercado import DISCLAIMER_REDES, generar_top3_redes

    df = pd.DataFrame({
        "TICKER": ["AAA", "BBB", "CCC"],
        "Score_Total": [80.0, 90.0, 70.0],
    })
    out = generar_top3_redes(df, n=2, titulo_semana="Test")
    assert DISCLAIMER_REDES in out["texto_plano"]
    assert len(out["bullets"]) <= 2
