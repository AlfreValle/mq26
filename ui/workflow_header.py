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

    st.markdown(f"""
    <div style="
        background:{bg_hex};
        border:1px solid {color_hex}33;
        border-left:3px solid {color_hex};
        border-radius:8px;
        padding:0.6rem 1rem;
        margin-bottom:0.75rem;
        display:flex;
        align-items:center;
        gap:0.5rem;
    ">
        <span style="color:{color_hex};font-size:0.875rem;">{icon}</span>
        <span style="font-size:0.8125rem;color:#f1f5f9;">
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
        with cols[i]:
            st.markdown(f"""
            <div style="
                background:{bg};
                border:1px solid {c_hex}44;
                border-radius:8px;
                padding:0.6rem 0.5rem;
                text-align:center;
            ">
                <div style="font-size:1rem;margin-bottom:2px;">
                    {paso.get('icon','⏳')}
                </div>
                <div style="
                    font-size:0.65rem;font-weight:600;
                    color:#4b5563;text-transform:uppercase;
                    letter-spacing:0.05em;margin-bottom:2px;
                ">Paso {n}</div>
                <div style="font-size:0.7rem;color:#94a3b8;line-height:1.3;">
                    {paso.get('name','—')}
                </div>
                <div style="
                    font-size:0.65rem;font-weight:600;
                    color:{c_hex};margin-top:3px;
                ">{paso.get('label','—')}</div>
            </div>
            """, unsafe_allow_html=True)
