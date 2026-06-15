"""
Señales 60/20/20 para ON USD — misma lógica que CEDEARs/bonos (scoring_engine).
"""
from __future__ import annotations

import pandas as pd

from core.renta_fija_ar import get_meta, tir_al_precio
from services.scoring_engine import calcular_score_total, universo_ons_tickers


def on_usd_advisory_table(byma_live: dict[str, dict] | None = None) -> pd.DataFrame:
    rows: list[dict] = []
    byma_live = byma_live or {}
    for t in universo_ons_tickers():
        r = calcular_score_total(t, "ON Corporativa")
        m = get_meta(t) or {}
        try:
            tir = float(m.get("tir_ref")) if m.get("tir_ref") is not None else None
        except (TypeError, ValueError):
            tir = None
        try:
            par = float(m.get("paridad_ref")) if m.get("paridad_ref") is not None else None
        except (TypeError, ValueError):
            par = None
        live = byma_live.get(str(t).upper().strip()) if isinstance(byma_live, dict) else None
        par_actual = None
        if isinstance(live, dict):
            try:
                _p = live.get("paridad_ref")
                if _p is not None:
                    par_actual = float(_p)
            except (TypeError, ValueError):
                par_actual = None
        if par_actual is None:
            par_actual = par
        tir_actual = tir_al_precio(str(t), float(par_actual)) if par_actual else None
        rows.append({
            "Ticker": t,
            "Emisor": str(m.get("emisor") or "—"),
            "TIR ref. %": round(tir, 2) if tir is not None else None,
            "TIR actual %": round(float(tir_actual), 2) if tir_actual is not None else None,
            "Paridad %": round(par, 2) if par is not None else None,
            "Score": r.get("Score_Total"),
            "Fund.": r.get("Score_Fund"),
            "Téc.": r.get("Score_Tec"),
            "Ctx.": r.get("Score_Sector"),
            "Señal": r.get("Senal", "—"),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values("Score", ascending=False, na_position="last").reset_index(drop=True)
    return df
