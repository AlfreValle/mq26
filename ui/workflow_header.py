"""
ui/workflow_header.py — Header de workflow rediseñado v9.
5 pasos con indicadores visuales claros y banner de siguiente acción.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

_PASO_COLORES = {
    "red":       ("#ef4444", "rgba(239,68,68,0.12)"),
    "orange":    ("#f59e0b", "rgba(245,158,11,0.12)"),
    "green":     ("#10b981", "rgba(16,185,129,0.12)"),
    "gray":      ("#4b5563", "rgba(75,85,99,0.08)"),
    "lightgray": ("#374151", "rgba(55,65,81,0.06)"),
}


# ── MEJORA 71: Workflow header rediseñado ──────────────────────────────────────
def render_workflow_header(flow_resumen: dict[str, Any],
                            compact: bool = False) -> None:
    if not flow_resumen:
        return

    sig   = flow_resumen.get("siguiente_accion", {})
    msg   = html.escape(str(sig.get("mensaje", "Cartera en orden")))
    color = sig.get("color", "green")

    # ── MEJORA 72: Banner de siguiente acción con estilo ─────────────────────
    color_hex, bg_hex = _PASO_COLORES.get(color, _PASO_COLORES["gray"])
    icon_map = {
        "red": "⚠", "orange": "→", "green": "✓",
        "gray": "·", "lightgray": "·",
    }
    icon = icon_map.get(color, "·")
    bb = f"{color_hex}33" if color_hex.startswith("#") and len(color_hex) == 7 else color_hex

    st.markdown(f"""
    <div class="mq-wf-banner" style="--mq-wf-a:{color_hex};--mq-wf-bg:{bg_hex};--mq-wf-bb:{bb};">
        <span class="mq-wf-banner__icon">{icon}</span>
        <span class="mq-wf-banner__text">
            <strong>Siguiente:</strong> {msg}
        </span>
    </div>
    """, unsafe_allow_html=True)

    if compact:
        return

    # ── MEJORA 73: 5 pasos con grid compacto ──────────────────────────────────
    cols = st.columns(5)
    for i, n in enumerate(range(1, 6)):
        paso  = flow_resumen.get(n, {})
        c     = paso.get("color", "gray")
        c_hex, bg = _PASO_COLORES.get(c, _PASO_COLORES["gray"])
        br = f"{c_hex}44" if c_hex.startswith("#") and len(c_hex) == 7 else c_hex
        with cols[i]:
            st.markdown(f"""
            <div class="mq-wf-step" style="--mq-wf-a:{c_hex};--mq-wf-bg:{bg};--mq-wf-br:{br};">
                <div class="mq-wf-step__icon">{paso.get('icon','⏳')}</div>
                <div class="mq-wf-step__paso">Paso {n}</div>
                <div class="mq-wf-step__name">{paso.get('name','—')}</div>
                <div class="mq-wf-step__label">{paso.get('label','—')}</div>
            </div>
            """, unsafe_allow_html=True)
