"""
services/resumen_natural.py — resumen de la cartera en lenguaje natural (H1).

Convierte el diagnóstico (que ya decide bien) en 2-4 frases que entiende
cualquiera, sin jerga. Es el "en una frase, cómo va tu plata" para el inversor
retail que no es experto. Sin Streamlit; no re-decide, traduce.
"""
from __future__ import annotations

from typing import Any

_SEMAFORO_PALABRA = {
    "verde": "saludable",
    "amarillo": "para revisar",
    "rojo": "necesita atención",
    "neutro": "sin datos suficientes",
}

_ACCION_POR_SEMAFORO = {
    "rojo": "Conviene que revises tu cartera pronto (mirá las observaciones más abajo).",
    "amarillo": "Hay algo para ajustar cuando puedas (lo ves en el detalle).",
}


def _semaforo_valor(diag: Any) -> str:
    sem = getattr(diag, "semaforo", None)
    val = getattr(sem, "value", None) or sem or "neutro"
    return str(val).strip().lower()


def resumen_natural_cartera(
    diag: Any,
    metricas: dict | None = None,
    *,
    ccl: float = 0.0,
    nombre: str = "",
) -> str:
    """2-4 frases en castellano simple sobre el estado de la cartera.

    Usa el diagnóstico (semáforo, score, rendimiento, primera observación) y las
    métricas (valor). Robusto a campos faltantes. Función pura.
    """
    metricas = metricas or {}
    nombre_corto = str(nombre or "").split("|")[0].strip()
    saludo = f"Hola {nombre_corto}. " if nombre_corto else ""

    # Valor en USD (preferir el del diagnóstico; si no, derivar de métricas).
    valor_usd = float(getattr(diag, "valor_cartera_usd", 0) or 0)
    if valor_usd <= 0:
        total_ars = float(metricas.get("total_valor", 0) or 0)
        if total_ars > 0 and ccl > 0:
            valor_usd = total_ars / ccl

    partes: list[str] = []
    if valor_usd > 0:
        partes.append(f"{saludo}Tu cartera vale hoy aproximadamente USD {valor_usd:,.0f}.")
    elif saludo:
        partes.append(saludo.strip())

    # Rendimiento desde el inicio (en USD).
    rend = getattr(diag, "rendimiento_ytd_usd_pct", None)
    if rend is None:
        rend = metricas.get("pnl_pct_total_usd")
    if rend is not None:
        try:
            r = float(rend) * (100.0 if abs(float(rend)) <= 1.5 else 1.0)
            verbo = "ganó" if r >= 0 else "perdió"
            partes.append(f"Desde que empezaste {verbo} {abs(r):.1f}% (medido en dólares).")
        except (TypeError, ValueError):
            pass

    # Estado general (semáforo + score).
    sem = _semaforo_valor(diag)
    estado = _SEMAFORO_PALABRA.get(sem, "sin datos suficientes")
    score = getattr(diag, "score_total", None)
    if score is not None:
        try:
            partes.append(f"Estado general: **{estado}** ({float(score):.0f}/100).")
        except (TypeError, ValueError):
            partes.append(f"Estado general: **{estado}**.")
    else:
        partes.append(f"Estado general: **{estado}**.")

    # Primera observación del diagnóstico (la más importante).
    obs_list = getattr(diag, "observaciones", None) or []
    if obs_list:
        o = obs_list[0]
        titulo = str(getattr(o, "titulo", "") or "").strip()
        if titulo:
            partes.append(f"Lo más importante: {titulo}.")

    # Acción sugerida según semáforo.
    accion = _ACCION_POR_SEMAFORO.get(sem)
    if accion:
        partes.append(accion)

    return " ".join(p for p in partes if p).strip()
