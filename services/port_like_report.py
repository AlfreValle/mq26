"""
J02 — Resumen estilo informe PORT (exposición, concentración, top posiciones).

Salida dict serializable para PDF/Markdown downstream.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_port_style_summary(df_pos: pd.DataFrame) -> dict[str, Any]:
    """
    Requiere columnas ``TICKER`` y ``VALOR_ARS`` o ``PRECIO_ARS``*``CANTIDAD``.
    """
    if df_pos is None or df_pos.empty:
        return {"n_positions": 0, "total_valor_ars": 0.0, "hhi": 0.0, "top": []}

    d = df_pos.copy()
    if "VALOR_ARS" in d.columns:
        v = d["VALOR_ARS"].astype(float)
    elif "PRECIO_ARS" in d.columns and "CANTIDAD" in d.columns:
        v = d["PRECIO_ARS"].astype(float) * d["CANTIDAD"].astype(float)
    else:
        return {"n_positions": 0, "total_valor_ars": 0.0, "hhi": 0.0, "top": []}

    d["_v"] = v
    total = float(d["_v"].sum())
    if total <= 0:
        return {"n_positions": len(d), "total_valor_ars": 0.0, "hhi": 0.0, "top": []}

    w = (d["_v"] / total).values
    hhi = float(np.sum(w**2))
    top = (
        d.assign(weight=w)
        .sort_values("_v", ascending=False)
        .head(10)[["TICKER", "_v", "weight"]]
        .rename(columns={"_v": "valor_ars"})
        .to_dict(orient="records")
    )
    return {
        "n_positions": int(len(d)),
        "total_valor_ars": total,
        "hhi": hhi,
        "top": top,
    }
