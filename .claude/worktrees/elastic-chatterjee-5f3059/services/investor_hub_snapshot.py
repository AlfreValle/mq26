"""
Lente de producto Inversor: snapshot serializable desde DiagnosticoResult + métricas.
No duplica fórmulas del motor; solo expone campos ya calculados por diagnosticar().
"""
from __future__ import annotations

from typing import Any


def build_investor_hub_snapshot(
    diag: Any,
    metricas: dict | None,
    ccl: float,
    *,
    valor_total_ars: float | None = None,
) -> dict[str, Any]:
    """
    Retorna dict estable para UI (hub salud financiera).

    - alignment_score_pct: proxy único hero (0–100) = score_total del diagnóstico.
    - cold_start: False si hay posiciones con valor; True si el motor indicó fallback extremo.
    """
    metricas = metricas or {}
    score = float(getattr(diag, "score_total", 0.0) or 0.0)
    sem = getattr(diag, "semaforo", None)
    sem_val = str(getattr(sem, "value", sem) or "").lower() if sem is not None else ""

    pct_def_a = float(getattr(diag, "pct_defensivo_actual", 0.0) or 0.0)
    pct_def_r = float(getattr(diag, "pct_defensivo_requerido", 0.0) or 0.0)
    pct_rv_a = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - pct_def_a)) or 0.0)
    def_ratio = (pct_def_a / max(pct_def_r, 1e-9)) if pct_def_r > 0 else 1.0

    acciones: list[dict[str, str]] = []
    for o in (getattr(diag, "observaciones", None) or [])[:3]:
        try:
            prio = str(getattr(getattr(o, "prioridad", None), "value", o.prioridad)).lower()
        except Exception:
            prio = "media"
        acciones.append({
            "titulo": str(getattr(o, "titulo", "")),
            "prioridad": prio,
            "cifra": str(getattr(o, "cifra_clave", "") or ""),
        })

    return {
        "alignment_score_pct": round(min(100.0, max(0.0, score)), 1),
        "semaforo": sem_val or "amarillo",
        "titulo_semaforo": str(getattr(diag, "titulo_semaforo", "") or ""),
        "resumen_ejecutivo": str(getattr(diag, "resumen_ejecutivo", "") or ""),
        "pct_defensivo_actual": pct_def_a,
        "pct_defensivo_requerido": pct_def_r,
        "pct_rv_actual": pct_rv_a,
        "ruleset_version": str(getattr(diag, "ruleset_version", "") or ""),
        "defensivo_ratio_vs_objetivo": round(min(2.0, def_ratio), 3),
        "valor_cartera_usd": float(getattr(diag, "valor_cartera_usd", 0.0) or 0.0),
        "n_posiciones": int(getattr(diag, "n_posiciones", 0) or 0),
        "rendimiento_ytd_usd_pct": float(getattr(diag, "rendimiento_ytd_usd_pct", 0.0) or 0.0),
        "patrimonio_total_ars": float(metricas.get("total_valor", 0) or 0) if valor_total_ars is None else float(valor_total_ars),
        "ccl": float(ccl or 0.0),
        "cold_start": bool(getattr(diag, "modo_fallback", False)),
        "acciones_top": acciones,
        "perfil": str(getattr(diag, "perfil", "") or ""),
        "horizonte": str(getattr(diag, "horizonte_label", "") or ""),
    }
