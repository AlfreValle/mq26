"""
Control de privacidad en pantalla (Excelencia #84): ocultar montos en uso público.

Lee ``st.session_state["mq26_privacy_hide_amounts"]`` (toggle en sidebar).
"""
from __future__ import annotations

from typing import Any


def privacy_hide_amounts(session_state: Any | None = None) -> bool:
    """Si True, la UI debe enmascarar montos (métricas, tablas clave)."""
    if session_state is not None:
        return bool(getattr(session_state, "get", lambda _: None)("mq26_privacy_hide_amounts"))
    try:
        import streamlit as st

        return bool(st.session_state.get("mq26_privacy_hide_amounts"))
    except Exception:
        return False


def maybe_mask_money_display(formatted: str, *, session_state: Any | None = None) -> str:
    """Devuelve un placeholder si el modo privacidad está activo."""
    if formatted == "—":
        return "—"
    if not privacy_hide_amounts(session_state):
        return formatted
    return "••••••"
