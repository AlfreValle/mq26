"""
ui/suite_shell.py — Cabeceras y secciones para suites Asesor / Estudio / Admin.

Tipografía: Barlow / Barlow Semi Condensed (tokens --font-ui / --font-heading).
Borde de acento y superficies del design system (comité 2026).
"""
from __future__ import annotations

import html as html_module

import streamlit as st


def render_suite_hero(*, badge: str, title: str, subtitle: str) -> None:
    """Bloque hero institucional (arriba de la suite o de la pestaña)."""
    t_esc = html_module.escape(title)
    st.markdown(
        f'<div class="mq-suite-hero" role="region" aria-label="{t_esc}">'
        f'<span class="mq-suite-badge">{html_module.escape(badge)}</span>'
        f'<p class="mq-suite-hero__title">{t_esc}</p>'
        f'<p class="mq-suite-hero__subtitle">{html_module.escape(subtitle)}</p>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_suite_section_title(text: str) -> None:
    """Título de sección con regla inferior (Barlow Semibold)."""
    st.markdown(
        f'<h3 class="mq-suite-section-title">{html_module.escape(text)}</h3>',
        unsafe_allow_html=True,
    )


def render_suite_microhint(text: str) -> None:
    """Línea auxiliar uppercase / tracking (kicker) bajo el hero o entre bloques."""
    st.markdown(
        f'<p class="mq-suite-microhint">{html_module.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def suite_divider() -> None:
    st.markdown('<hr class="mq-suite-divider" />', unsafe_allow_html=True)
