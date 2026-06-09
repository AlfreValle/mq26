"""
Presets de suite asesor: solo escribe session_state para claves de tab_optimizacion.
No toca optimization_service ni motores.
"""
from __future__ import annotations

import streamlit as st

_PRESETS = {
    "balanceado": {
        "label": "Balanceado (Sharpe, 1y, turnover 30%)",
        "comp_modelo": "Sharpe",
        "comp_period": "1y",
        "max_turnover": 30,
        "comp_lambda_trade": 0.0,
        "comp_sanitize_ret": False,
        "comp_hard_l1": False,
    },
    "rf_conservador": {
        "label": "Enfoque conservador (Sortino, 2y, turnover 20%)",
        "comp_modelo": "Sortino",
        "comp_period": "2y",
        "max_turnover": 20,
        "comp_lambda_trade": 0.5,
        "comp_sanitize_ret": True,
        "comp_hard_l1": False,
    },
    "rv_crecimiento": {
        "label": "Enfoque crecimiento (Sharpe, 1y, turnover 45%)",
        "comp_modelo": "Sharpe",
        "comp_period": "1y",
        "max_turnover": 45,
        "comp_lambda_trade": 0.1,
        "comp_sanitize_ret": False,
        "comp_hard_l1": False,
    },
}


def aplicar_preset_asesor(preset_id: str) -> None:
    p = _PRESETS.get(preset_id) or _PRESETS["balanceado"]
    for k, v in p.items():
        if k == "label":
            continue
        st.session_state[k] = v
    st.session_state["mq26_asesor_suite_preset"] = preset_id


def render_asesor_suite_banner() -> None:
    """Expander antes de las pestañas del asesor."""
    st.session_state.setdefault("mq26_asesor_suite_preset", "balanceado")
    with st.expander("Suite asesor — presets de optimización (solo UI)", expanded=False):
        st.caption(
            "Ajusta valores por defecto de la sub-pestaña «Comparativa Actual vs Óptima». "
            "No modifica el motor cuant; solo precarga sliders y selectores. "
            "En **Cartera → Posición actual** tenés la misma vista resumen tipo broker que el inversor."
        )
        choice = st.radio(
            "Preset",
            list(_PRESETS.keys()),
            format_func=lambda k: _PRESETS[k]["label"],
            horizontal=True,
            key="mq26_asesor_suite_radio",
        )
        if st.button("Aplicar preset a la sesión", key="mq26_asesor_suite_apply"):
            aplicar_preset_asesor(str(choice))
            st.success("Preset aplicado. Abrí Optimización → Comparativa.")
            st.rerun()
