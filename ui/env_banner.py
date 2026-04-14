"""
ui/env_banner.py — Indicador Dev vs Prod (Excelencia Industrial #66).
"""
from __future__ import annotations

import os

import streamlit as st


def render_environment_banner() -> None:
    """Muestra una franja discreta si no estamos en producción explícita."""
    raw = (os.environ.get("MQ26_ENV") or os.environ.get("RAILWAY_ENVIRONMENT") or "").strip().lower()
    if raw in ("production", "prod", "live"):
        return
    # Desarrollo / staging / vacío
    label = raw.upper() if raw else "DESARROLLO"
    st.markdown(
        f"<div class='mq-env-banner mq-env-banner--warn' role='status'>"
        f"<span class='mq-env-banner__dot'></span>"
        f"Entorno: <strong>{label}</strong> · los datos pueden ser de prueba."
        f"</div>",
        unsafe_allow_html=True,
    )
