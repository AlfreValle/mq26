from __future__ import annotations

import services.on_usd_advisory as adv


def test_on_usd_advisory_incluye_tir_actual():
    df = adv.on_usd_advisory_table()
    assert "TIR actual %" in df.columns


def test_on_usd_advisory_tir_actual_usa_paridad_live(monkeypatch):
    monkeypatch.setattr(adv, "universo_ons_tickers", lambda: ["TLCTO"])
    monkeypatch.setattr(
        adv,
        "calcular_score_total",
        lambda *_a, **_k: {"Score_Total": 58.6, "Score_Fund": 60.7, "Score_Tec": 40, "Score_Sector": 71, "Senal": "⚪ MANTENER"},
    )
    monkeypatch.setattr(
        adv,
        "get_meta",
        lambda _t: {"emisor": "Telecom Argentina", "tir_ref": 8.0, "paridad_ref": 100.8},
    )

    df_ref = adv.on_usd_advisory_table(byma_live={})
    tir_ref_base = float(df_ref.iloc[0]["TIR actual %"])

    df_live = adv.on_usd_advisory_table(byma_live={"TLCTO": {"paridad_ref": 95.0}})
    tir_live = float(df_live.iloc[0]["TIR actual %"])

    assert tir_live != tir_ref_base
