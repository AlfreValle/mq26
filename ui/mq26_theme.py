"""
Tokens de diseño MQ26 (SaaS) y tema retail claro.
Sin Streamlit: solo strings CSS y constantes para contraste WCAG AA en modo claro.
"""
from __future__ import annotations

import os

# Referencia documental (no sustituye auditoría de accesibilidad completa)
TOKENS_LIGHT = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "text": "#0f172a",
    "text_muted": "#475569",
    "border": "rgba(15,23,42,0.12)",
    "accent": "#2563eb",
    "success": "#059669",
    "warning": "#d97706",
    "danger": "#dc2626",
}


def use_retail_light_theme() -> bool:
    """Tema claro retail por defecto; desactivar con MQ26_RETAIL_LIGHT=0|false."""
    raw = (os.environ.get("MQ26_RETAIL_LIGHT", "1") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def css_hub_responsive_block() -> str:
    """Una columna en viewports estrechos; tablas con scroll horizontal."""
    return """
@media (max-width: 768px) {
  .mq-hub-stack { display: flex; flex-direction: column !important; gap: 0.75rem; }
  .mq-hub-hero-col { width: 100% !important; max-width: 100% !important; }
  .mq-dataframe-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }
  div[data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
  }
  div[data-testid="column"] {
    width: 100% !important;
    min-width: unset !important;
    flex: 1 1 100% !important;
  }
  div[data-testid="stDataFrame"] {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
}
"""


def inject_theme_css_fragments() -> str:
    """Fragmentos adicionales inyectados tras style.css (run_mq26)."""
    return css_hub_responsive_block()
