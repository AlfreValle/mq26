"""
Tokens de diseño MQ26 (SaaS) y tema retail claro.
Sin Streamlit: solo strings CSS y constantes para contraste WCAG AA en modo claro.
"""
from __future__ import annotations

import os
from pathlib import Path

# Tokens del design system Blue-Tech Dark v11
TOKENS_LIGHT = {
    "bg": "#0e1117",
    "surface": "#161b27",
    "surface_2": "#1e2538",
    "surface_3": "#252d42",
    "text": "#e8ecf4",
    "text_muted": "#8892aa",
    "border": "rgba(42,51,80,0.9)",
    "accent": "#4f8ef7",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
}


def use_retail_light_theme() -> bool:
    """Tema retail: dark por defecto. Activar modo claro con MQ26_RETAIL_LIGHT=1."""
    raw = (os.environ.get("MQ26_RETAIL_LIGHT", "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


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


def css_blue_tech_components() -> str:
    """Componentes Blue-Tech Dark v11: ticker badges, P&L pills, sidebar avatar, etc."""
    return """
/* ── Ticker badge (estilo storytelling) ────────────────────────────────── */
.mq-ticker-badge {
  display: inline-block;
  background: rgba(79, 142, 247, 0.12);
  color: #5b97f8;
  border-radius: 4px;
  padding: 1px 6px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-weight: 700;
  font-size: 0.78rem;
  letter-spacing: 0.02em;
}

/* ── Pills de P&L (ganancia / pérdida) ─────────────────────────────────── */
.mq-pill-up {
  display: inline-block;
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 0.72rem;
  font-weight: 700;
}
.mq-pill-down {
  display: inline-block;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 0.72rem;
  font-weight: 700;
}
.mq-pill-neutral {
  display: inline-block;
  background: rgba(136, 146, 170, 0.15);
  color: #8892aa;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 0.72rem;
  font-weight: 700;
}

/* ── Avatar / rol block en sidebar ─────────────────────────────────────── */
.mq-avatar-block {
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
}
.mq-avatar-name { font-weight: 700; font-size: 0.88rem; color: var(--c-text); }
.mq-avatar-role {
  display: inline-block;
  background: rgba(79, 142, 247, 0.15);
  color: #5b97f8;
  border-radius: 999px;
  padding: 1px 8px;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-top: 3px;
}

/* ── Metric card: value coloreado por variante ──────────────────────────── */
.mq26-metric-card .value.green { color: var(--c-green) !important; }
.mq26-metric-card .value.blue  { color: var(--c-accent) !important; }
.mq26-metric-card .value.red   { color: var(--c-red) !important; }
.mq26-metric-card .value.yellow{ color: var(--c-yellow) !important; }

/* ── Sidebar Streamlit: fondo oscuro azulado ────────────────────────────── */
[data-testid="stSidebar"] {
  background: #12161f !important;
  border-right: 1px solid rgba(42, 51, 80, 0.9) !important;
}
[data-testid="stSidebar"] > div:first-child {
  background: #12161f !important;
}

/* ── Tabs: estilo blue-tech ─────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tab"] {
  font-family: 'Inter', system-ui, sans-serif !important;
  font-size: 0.85rem !important;
  font-weight: 500 !important;
  color: #8892aa !important;
  border-radius: 6px 6px 0 0 !important;
  transition: color 0.15s, background 0.15s !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: #4f8ef7 !important;
  background: rgba(79, 142, 247, 0.08) !important;
  border-bottom: 2px solid #4f8ef7 !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
  color: #e8ecf4 !important;
  background: rgba(79, 142, 247, 0.06) !important;
}

/* ── Botones primary: gradiente azul/púrpura ────────────────────────────── */
[data-testid="baseButton-primary"],
.stButton > button[kind="primary"],
button[data-baseweb="button"][kind="primary"] {
  background: linear-gradient(135deg, #4f8ef7, #7c5cbf) !important;
  border: none !important;
  color: #fff !important;
  font-weight: 600 !important;
  box-shadow: 0 4px 16px rgba(79,142,247,0.3) !important;
}
[data-testid="baseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 6px 24px rgba(79,142,247,0.45) !important;
  transform: translateY(-1px) !important;
}

/* ── Main app background ────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="block-container"],
.main .block-container {
  background: #0e1117 !important;
}

/* ── Login form: centrado y elegante ────────────────────────────────────── */
[data-testid="stForm"] {
  background: #161b27 !important;
  border: 1px solid rgba(42,51,80,0.9) !important;
  border-radius: 12px !important;
  padding: 1.5rem !important;
  box-shadow: 0 8px 40px rgba(0,0,0,0.4) !important;
}

/* ── Header / métricas Streamlit nativas ────────────────────────────────── */
[data-testid="stMetric"] {
  background: #161b27 !important;
  border: 1px solid rgba(42,51,80,0.9) !important;
  border-radius: 10px !important;
  padding: 0.8rem 1rem !important;
}
[data-testid="stMetricValue"] {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 1.4rem !important;
  font-weight: 700 !important;
  color: #4f8ef7 !important;
}
[data-testid="stMetricDelta"] svg { display: none; }
[data-testid="stMetricDeltaIcon-Up"]   ~ div { color: #22c55e !important; }
[data-testid="stMetricDeltaIcon-Down"] ~ div { color: #ef4444 !important; }

/* ── Dataframe: fondo dark ──────────────────────────────────────────────── */
[data-testid="stDataFrame"] iframe {
  border-radius: 8px !important;
}

/* ── Input fields ───────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] select,
[data-baseweb="input"] input {
  background: #1e2538 !important;
  border-color: rgba(42,51,80,0.9) !important;
  color: #e8ecf4 !important;
  border-radius: 8px !important;
}
[data-baseweb="input"]:focus-within {
  border-color: #4f8ef7 !important;
  box-shadow: 0 0 0 2px rgba(79,142,247,0.2) !important;
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0e1117; }
::-webkit-scrollbar-thumb { background: #2a3350; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #4f8ef7; }
"""


def inject_theme_css_fragments() -> str:
    """Fragmentos adicionales inyectados tras style.css (run_mq26)."""
    return css_hub_responsive_block() + css_blue_tech_components()


def build_theme_css_bundle(base_dir: Path, *, use_light: bool) -> tuple[str, str]:
    """
    Carga style.css + fragmentos; opcionalmente style_retail_light.css (segundo bloque).
    Usado en run_mq26 y app_main para misma apariencia (login legible en claro).
    """
    _css_path = base_dir / "assets" / "style.css"
    _extra = _css_path.read_text(encoding="utf-8") if _css_path.exists() else ""
    _extra += inject_theme_css_fragments()
    _light = ""
    if use_light:
        _light_path = base_dir / "assets" / "style_retail_light.css"
        if _light_path.exists():
            _light = _light_path.read_text(encoding="utf-8")
    return _extra, _light
