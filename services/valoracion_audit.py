"""
services/valoracion_audit.py — Auditoría de cobertura de precios por tipo de activo.

Usa fuentes explícitas (PriceRecord del PriceEngine) o inferencia live vs fallback.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _tipo_row(row: pd.Series) -> str:
    t = row.get("TIPO", row.get("_TIPO_NORM", ""))
    return str(t or "OTRO").strip().upper() or "OTRO"


def auditar_valoracion_por_tipo(
    df_ag: pd.DataFrame,
    records: dict[str, Any],
) -> dict[str, Any]:
    """
    Agrupa VALOR_ARS por TIPO y por categoría de fuente (live vs no-live).

    `records`: dict ticker -> objeto con atributos `source` (Enum PriceSource o similar)
    y `precio_cedear_ars`, o dict con claves "source" / "precio_cedear_ars".
    """
    if df_ag is None or df_ag.empty or not records:
        return {
            "total_valor_ars": 0.0,
            "pct_valor_live": 0.0,
            "pct_valor_no_live": 0.0,
            "por_tipo": {},
            "tickers_sin_precio": [],
        }

    def _source_is_live(rec: Any) -> bool:
        src = getattr(rec, "source", None) or (rec.get("source") if isinstance(rec, dict) else None)
        if src is None:
            return False
        if hasattr(src, "is_live"):
            return bool(src.is_live)
        s = str(src).lower()
        return "live" in s and "missing" not in s

    def _precio_rec(rec: Any) -> float:
        if hasattr(rec, "precio_cedear_ars"):
            return float(rec.precio_cedear_ars or 0)
        if isinstance(rec, dict):
            return float(rec.get("precio_cedear_ars", 0) or 0)
        return 0.0

    total = 0.0
    valor_live = 0.0
    valor_no_live = 0.0
    por_tipo: dict[str, dict[str, float]] = {}
    sin_precio: list[str] = []

    for _, row in df_ag.iterrows():
        tkr = str(row.get("TICKER", "")).upper().strip()
        if not tkr:
            continue
        val = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
        tipo = _tipo_row(row)
        rec = records.get(tkr) or records.get(tkr.upper())
        if rec is None:
            sin_precio.append(tkr)
            continue
        px = _precio_rec(rec)
        if px <= 0 or val <= 0:
            if val > 0:
                sin_precio.append(tkr)
            continue

        total += val
        live = _source_is_live(rec)
        if live:
            valor_live += val
        else:
            valor_no_live += val

        bucket = por_tipo.setdefault(tipo, {"valor_total": 0.0, "valor_live": 0.0, "valor_no_live": 0.0})
        bucket["valor_total"] += val
        if live:
            bucket["valor_live"] += val
        else:
            bucket["valor_no_live"] += val

    pct_live = round(100.0 * valor_live / total, 2) if total > 0 else 0.0
    pct_no = round(100.0 * valor_no_live / total, 2) if total > 0 else 0.0

    for _tipo, b in por_tipo.items():
        vt = b["valor_total"]
        b["pct_valor_live"] = round(100.0 * b["valor_live"] / vt, 2) if vt > 0 else 0.0
        b["pct_valor_no_live"] = round(100.0 * b["valor_no_live"] / vt, 2) if vt > 0 else 0.0

    return {
        "total_valor_ars": round(total, 2),
        "valor_live_ars": round(valor_live, 2),
        "valor_no_live_ars": round(valor_no_live, 2),
        "pct_valor_live": pct_live,
        "pct_valor_no_live": pct_no,
        "por_tipo": por_tipo,
        "tickers_sin_precio": sorted(set(sin_precio)),
    }


def auditar_inferido_live_vs_resto(
    df_ag: pd.DataFrame,
    precios_live: dict[str, float],
    precios_final: dict[str, float],
) -> dict[str, Any]:
    """
    Inferencia sin PriceRecord: "live" = cotización inicial > 0 en precios_live;
    el valor de cartera se toma de VALOR_ARS (ya con precios_final).
    """
    if df_ag is None or df_ag.empty:
        return {
            "total_valor_ars": 0.0,
            "pct_valor_live": 0.0,
            "por_tipo": {},
        }

    live_map = {str(k).upper(): float(v or 0) for k, v in (precios_live or {}).items()}
    tot = 0.0
    v_live = 0.0
    por_tipo: dict[str, dict[str, float]] = {}

    for _, row in df_ag.iterrows():
        tkr = str(row.get("TICKER", "")).upper().strip()
        val = float(pd.to_numeric(row.get("VALOR_ARS", 0), errors="coerce") or 0.0)
        tipo = _tipo_row(row)
        tot += val
        if live_map.get(tkr, 0) > 0:
            v_live += val
        b = por_tipo.setdefault(tipo, {"valor_total": 0.0, "valor_live": 0.0})
        b["valor_total"] += val
        if live_map.get(tkr, 0) > 0:
            b["valor_live"] += val

    for _, b in por_tipo.items():
        vt = b["valor_total"]
        b["pct_valor_live"] = round(100.0 * b["valor_live"] / vt, 2) if vt > 0 else 0.0

    return {
        "total_valor_ars": round(tot, 2),
        "pct_valor_live": round(100.0 * v_live / tot, 2) if tot > 0 else 0.0,
        "por_tipo": por_tipo,
    }
