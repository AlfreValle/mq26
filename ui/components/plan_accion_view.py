"""
ui/components/plan_accion_view.py — render del PlanAccion (Pilar 3).

La cara visible de services/recomendador_explicable.py: cada sugerencia con
sus motivos expandibles, badge de confianza según frescura de datos, y link
a la ficha integral (Pilar 2) como "por qué profundo".
"""
from __future__ import annotations

import streamlit as st

from services.recomendador_explicable import (
    CONFIANZA_ALTA,
    CONFIANZA_BAJA,
    PlanAccion,
    RecomendacionExplicada,
)

_BADGE_CONFIANZA = {
    CONFIANZA_ALTA: ("🟢 Datos frescos", "Precio en vivo del proveedor."),
    "MEDIA": ("🟡 Datos de referencia", "Precio de cierre/fallback dentro del umbral de su tipo."),
    CONFIANZA_BAJA: ("🔴 Datos viejos", "El precio superó el umbral de frescura — verificá antes de operar."),
}

_ICONO_ACCION = {"COMPRAR": "🛒", "VENDER": "🔴", "REVISAR": "👀"}


def _render_recomendacion(r: RecomendacionExplicada, *, key_prefix: str) -> None:
    icono = _ICONO_ACCION.get(r.accion, "•")
    monto_txt = f" · ARS {r.monto_ars:,.0f}" if r.monto_ars else ""
    unidades_txt = f" · {r.unidades:.0f} u." if r.unidades else ""
    titulo = f"{icono} {r.accion} {r.ticker}{unidades_txt}{monto_txt}"
    with st.expander(titulo, expanded=False):
        badge, badge_help = _BADGE_CONFIANZA.get(r.confianza, _BADGE_CONFIANZA["MEDIA"])
        c1, c2 = st.columns([3, 1])
        with c1:
            if r.tesis:
                st.markdown(f"**{r.tesis}**")
        with c2:
            st.caption(badge, help=badge_help)
        if r.motivos:
            st.markdown("**Por qué:**")
            for m in r.motivos:
                if str(m.texto).strip():
                    st.markdown(f"- {m.texto}")
        for adv in r.advertencias:
            st.warning(adv, icon="⚠️")
        if r.tiene_ficha:
            ficha_key = f"{key_prefix}_ficha_{r.ticker}"
            if not st.session_state.get(ficha_key):
                if st.button(
                    f"📑 Ver ficha integral de {r.ticker}",
                    key=f"{ficha_key}_btn",
                ):
                    st.session_state[ficha_key] = True
                    st.rerun()
            else:
                from ui.components.ficha_ticker_view import render_ficha_ticker

                render_ficha_ticker(r.ticker, key_prefix=f"{key_prefix}_{r.ticker}")


def render_plan_accion(plan: PlanAccion, *, key_prefix: str = "plan") -> None:
    """Renderiza el plan completo: resumen, alerta, compras y revisiones."""
    if plan is None:
        return
    st.markdown(
        f"<div style='padding:0.7rem 1rem;background:var(--c-bg-2, rgba(148,163,184,0.08));"
        f"border-radius:10px;font-size:0.9rem;line-height:1.55;'>"
        f"🧭 <strong>Plan explicado</strong> — {plan.resumen}</div>",
        unsafe_allow_html=True,
    )
    if plan.alerta_mercado:
        st.warning(plan.alerta_mercado, icon="⚠️")
    if plan.comprar:
        st.markdown("##### Compras sugeridas — con su porqué")
        for r in plan.comprar:
            _render_recomendacion(r, key_prefix=f"{key_prefix}_c")
    if plan.vender_revisar:
        st.markdown("##### Posiciones que piden atención")
        for r in plan.vender_revisar:
            _render_recomendacion(r, key_prefix=f"{key_prefix}_v")
    st.caption(
        "Cada sugerencia queda registrada con sus motivos en la auditoría de MQ26. "
        "Es información para decidir, no una orden: la decisión final es tuya."
    )
