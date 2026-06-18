"""
ui/navigation.py — Mapa único roles → pestañas principales.

Incluye: imports diferidos por pestaña (#2), enlace ?tab=<tab_id> (#6),
failover si un render falla (#7).
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import streamlit as st

AppKind = Literal["mq26", "app"]

__all__ = ["AppKind", "MainTabSpec", "get_main_tabs", "render_main_tabs"]
CtxRenderer = Callable[[dict], None]

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class MainTabSpec:
    """Una pestaña principal Streamlit (primer nivel)."""

    label: str
    tab_id: str
    render: CtxRenderer


def _lazy_render(module: str, attr: str) -> CtxRenderer:
    """Importa el módulo de la pestaña solo al ejecutar el render."""

    def _render(ctx: dict) -> None:
        mod = importlib.import_module(module)
        getattr(mod, attr)(ctx)

    return _render


def _normalize_role(role: str) -> str:
    return (role or "").strip().lower()


def _tab_specs_mq26_estudio() -> list[MainTabSpec]:
    return [
        MainTabSpec("👥 Mis Clientes", "estudio", _lazy_render("ui.tab_estudio", "render_tab_estudio")),
        MainTabSpec("📂 Cartera Activa", "cartera", _lazy_render("ui.tab_cartera", "render_tab_cartera")),
        MainTabSpec("📄 Informes", "reporte", _lazy_render("ui.tab_reporte", "render_tab_reporte")),
        MainTabSpec("🔍 Señales de Mercado", "universo", _lazy_render("ui.tab_universo", "render_tab_universo")),
    ]


def _tab_specs_six_flow() -> list[MainTabSpec]:
    """
    Flujo institucional (asesor y roles con 6 pestañas). Promesa por pestaña:

    - **cartera** — Tenencias, P&L y libro (fuente de datos operativos).
    - **universo** — Universo y señales de mercado (MOD-23 / screening).
    - **optimizacion** — Comparativa cartera actual vs cartera óptima (parámetros de optimización).
    - **riesgo** — Riesgo, simulaciones y stress (distinto de la óptima puntual).
    - **ejecucion** — Mesa de órdenes y ejecución.
    - **reporte** — Informes exportables para el cliente.
    """
    return [
        MainTabSpec("📂 Cartera", "cartera", _lazy_render("ui.tab_cartera", "render_tab_cartera")),
        MainTabSpec("🔍 Señales", "universo", _lazy_render("ui.tab_universo", "render_tab_universo")),
        MainTabSpec("⚙️ Optimizar", "optimizacion", _lazy_render("ui.tab_optimizacion", "render_tab_optimizacion")),
        MainTabSpec("📉 Riesgo", "riesgo", _lazy_render("ui.tab_riesgo", "render_tab_riesgo")),
        MainTabSpec("✅ Ejecutar", "ejecucion", _lazy_render("ui.tab_ejecucion", "render_tab_ejecucion")),
        MainTabSpec("📄 Informe", "reporte", _lazy_render("ui.tab_reporte", "render_tab_reporte")),
    ]


def get_main_tabs(app_kind: AppKind, role: str) -> list[MainTabSpec]:
    """
    Resuelve la lista ordenada de pestañas para el entrypoint y rol dados.

    Nota: en ``app`` el rol institucional no incluye ``tab_estudio`` ni ``tab_admin``
    en esta barra (convención actual de producto).
    """
    r = _normalize_role(role)

    if app_kind == "mq26":
        if r == "inversor":
            return [
                MainTabSpec(
                    "📊 Mi Cartera",
                    "mi_cartera",
                    _lazy_render("ui.tab_inversor", "render_tab_inversor"),
                ),
                MainTabSpec(
                    "🎯 Plan de Objetivos",
                    "plan_objetivos",
                    _lazy_render("ui.tab_portfolio_optimizer", "render_tab_portfolio_optimizer"),
                ),
                MainTabSpec(
                    "💎 Perlas",
                    "perlas",
                    _lazy_render("ui.tab_perlas", "render_tab_perlas"),
                ),
            ]
        if r == "estudio":
            return _tab_specs_mq26_estudio()
        if r == "asesor":
            return _tab_specs_six_flow()
        return [
            *_tab_specs_six_flow(),
            MainTabSpec(
                "🛠 Admin",
                "admin",
                _lazy_render("ui.tab_admin", "render_tab_admin"),
            ),
        ]

    if r == "inversor":
        return [
            MainTabSpec("📂 Cartera", "cartera", _lazy_render("ui.tab_cartera", "render_tab_cartera")),
            MainTabSpec(
                "📊 Cómo va tu inversión",
                "como_va",
                _lazy_render("ui.tab_inversor", "render_tab_inversor"),
            ),
            MainTabSpec("🛒 Mesa de ejecución", "ejecucion", _lazy_render("ui.tab_ejecucion", "render_tab_ejecucion")),
            MainTabSpec("📄 Reporte", "reporte", _lazy_render("ui.tab_reporte", "render_tab_reporte")),
        ]
    return [
        MainTabSpec(
            "📊 1. Cartera & Libro Mayor",
            "cartera",
            _lazy_render("ui.tab_cartera", "render_tab_cartera"),
        ),
        MainTabSpec(
            "🔍 2. Universo & Señales",
            "universo",
            _lazy_render("ui.tab_universo", "render_tab_universo"),
        ),
        MainTabSpec(
            "🔬 3. Optimización",
            "optimizacion",
            _lazy_render("ui.tab_optimizacion", "render_tab_optimizacion"),
        ),
        MainTabSpec(
            "📈 4. Riesgo & Simulación",
            "riesgo",
            _lazy_render("ui.tab_riesgo", "render_tab_riesgo"),
        ),
        MainTabSpec(
            "🛒 5. Mesa de Ejecución",
            "ejecucion",
            _lazy_render("ui.tab_ejecucion", "render_tab_ejecucion"),
        ),
        MainTabSpec("📄 6. Reporte", "reporte", _lazy_render("ui.tab_reporte", "render_tab_reporte")),
    ]


def _deeplink_tab_hint(specs: list[MainTabSpec]) -> None:
    """Si la URL trae ``?tab=<tab_id>``, avisar qué pestaña abrir (Streamlit no abre sola la tab)."""
    try:
        raw = st.query_params.get("tab")
    except Exception:
        return
    if not raw:
        return
    tid = (raw[0] if isinstance(raw, list) else str(raw)).strip().lower()
    if not tid:
        return
    labels = {s.tab_id: s.label for s in specs}
    if tid not in labels:
        return
    dedup = f"mq26_deeplink_ok_{tid}"
    if st.session_state.get(dedup):
        return
    st.session_state[dedup] = True
    st.info(
        f"Enlace **?tab={tid}**: seleccioná la pestaña **{labels[tid]}** arriba.",
        icon="🔗",
    )


def _label_sin_emoji(label: str) -> str:
    """Extrae el texto legible del label de una pestaña (descarta el emoji inicial)."""
    parts = label.strip().split()
    # Si el primer "token" es puro emoji (< 3 chars de texto), saltarlo
    text_parts = [p for p in parts if len(p.encode("utf-8")) == len(p)]
    return " ".join(text_parts).strip() if text_parts else label.strip()


def render_main_tabs(ctx: dict, app_kind: AppKind, role: str) -> None:
    """
    Crea ``st.tabs`` y ejecuta el render de cada pestaña.

    C19 — Tab loading indicator: cada pestaña muestra un spinner mientras su
    contenido se calcula. El spinner es visible solo en la pestaña activa;
    en pestañas inactivas el código se ejecuta igualmente (modelo Streamlit)
    pero el usuario no ve nada porque la pestaña está colapsada.
    """
    specs = get_main_tabs(app_kind, role)
    r = _normalize_role(role)

    if app_kind == "mq26" and r == "asesor":
        from ui.asesor_suite import render_asesor_suite_banner

        render_asesor_suite_banner()

    _deeplink_tab_hint(specs)

    tabs = st.tabs([s.label for s in specs])
    for tab_obj, spec in zip(tabs, specs, strict=True):
        with tab_obj:
            # Spinner visible mientras el tab calcula (C19).
            # Para tabs rápidas desaparece en milisegundos; para tabs
            # lentas (red / optimizador) el usuario ve que algo está pasando.
            _spinner_label = _label_sin_emoji(spec.label) or "pestaña"
            with st.spinner(f"Cargando {_spinner_label}…"):
                try:
                    spec.render(ctx)
                except Exception:
                    import uuid as _uuid

                    _err_id = _uuid.uuid4().hex[:8]
                    _LOG.exception(
                        "Fallo render pestaña tab_id=%s err_id=%s", spec.tab_id, _err_id
                    )
                    st.error(
                        "Esta sección tuvo un problema y no se pudo mostrar. "
                        "Reintentá en unos minutos; si persiste, pasale este código "
                        f"al equipo técnico: **{_err_id}**."
                    )
