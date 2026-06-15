"""
services/plan_simulaciones.py — Lógica pura para Plan y simulaciones (Mi cartera).

Sin Streamlit. Reutilizable desde tests e informe HTML.
"""
from __future__ import annotations

import pandas as pd

from core.renta_fija_ar import es_renta_fija


def dias_desde_primera_compra(df_ag: pd.DataFrame | None) -> int | None:
    """Días calendario desde la FECHA_COMPRA mínima hasta hoy; None si no aplica."""
    if df_ag is None or df_ag.empty or "FECHA_COMPRA" not in df_ag.columns:
        return None
    try:
        from datetime import date

        fechas = pd.to_datetime(df_ag["FECHA_COMPRA"], errors="coerce").dropna()
        if fechas.empty:
            return None
        first = fechas.min()
        d0 = first.date() if hasattr(first, "date") else first
        return max(0, (date.today() - d0).days)
    except Exception:
        return None


def df_ag_tiene_posiciones_reales(df_ag: pd.DataFrame | None) -> bool:
    if df_ag is None or df_ag.empty:
        return False
    if "PESO_PCT" in df_ag.columns:
        return float(pd.to_numeric(df_ag["PESO_PCT"], errors="coerce").fillna(0.0).sum()) > 1e-9
    return True


def ideal_dict_desde_mix_plan(
    perfil_ui: str,
    ideal_perfil: dict,
    mix_plan: dict | None,
) -> tuple[dict, str]:
    """
    Si hay armado guardado (fracción RF), combina RF agregada + RV del CARTERA_IDEAL del perfil.
    Retorna (dict pesos ticker/bucket, etiqueta fuente).
    """
    if not isinstance(mix_plan, dict) or mix_plan.get("rf") is None:
        return dict(ideal_perfil or {}), "modelo_perfil"
    try:
        rf_target = float(mix_plan["rf"])
    except (TypeError, ValueError):
        return dict(ideal_perfil or {}), "modelo_perfil"
    rf_target = max(0.0, min(1.0, rf_target))
    rv_target = max(0.0, 1.0 - rf_target)
    base = dict(ideal_perfil or {})
    rf_mod = rv_mod = 0.0
    out: dict[str, float] = {}
    for k, v in base.items():
        ks = str(k).strip()
        if not ks:
            continue
        try:
            w = float(v)
        except (TypeError, ValueError):
            continue
        if ks.startswith("_") or es_renta_fija(ks.upper()):
            rf_mod += max(0.0, w)
        else:
            rv_mod += max(0.0, w)
    if rf_mod <= 1e-12 and rv_mod <= 1e-12:
        return dict(ideal_perfil or {}), "modelo_perfil"
    scale_r = rf_target / rf_mod if rf_mod > 1e-12 else 0.0
    scale_v = rv_target / rv_mod if rv_mod > 1e-12 else 0.0
    for k, v in base.items():
        ks = str(k).strip()
        if not ks:
            continue
        try:
            w = float(v)
        except (TypeError, ValueError):
            continue
        if ks.startswith("_") or es_renta_fija(ks.upper()):
            nv = max(0.0, w) * scale_r
        else:
            nv = max(0.0, w) * scale_v
        if nv > 1e-9:
            out[ks] = nv
    sm = sum(out.values())
    if sm > 1e-9:
        out = {k: v / sm for k, v in out.items()}
    return out, "armado_app"


def agrupar_pesos_torta(
    wmap: dict[str, float],
    min_frac: float = 0.03,
) -> dict[str, float]:
    """Junta posiciones bajo `Otros` si peso relativo < min_frac."""
    if not wmap:
        return {}
    tot = sum(max(0.0, v) for v in wmap.values())
    if tot <= 0:
        return {}
    norm = {k: max(0.0, v) / tot for k, v in wmap.items()}
    keep: dict[str, float] = {}
    otros = 0.0
    for k, v in sorted(norm.items(), key=lambda x: -x[1]):
        if v >= float(min_frac):
            keep[k] = v
        else:
            otros += v
    if otros >= 1e-6:
        keep["Otros"] = keep.get("Otros", 0.0) + otros
    s2 = sum(keep.values())
    if s2 > 1e-9:
        return {k: v / s2 for k, v in keep.items()}
    return keep
