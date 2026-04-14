"""Alertas y pistas UX mínimas."""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from config import (
    CONCENTRACION_ACTIVO_ALERTA,
    CONCENTRACION_SECTOR_ALERTA,
    NOTA_ALERTA,
)


def dedupe_alertas_mod23(alertas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Una entrada por ticker. Si el análisis trae filas duplicadas, conserva el peor score.
    """
    best: dict[str, dict[str, Any]] = {}
    for a in alertas:
        t = str(a.get("ticker", "")).upper().strip()
        if not t:
            continue
        sc = float(a.get("score", 99.0))
        if t not in best or sc < float(best[t].get("score", 99.0)):
            best[t] = {**a, "ticker": t, "score": sc}
    return sorted(
        best.values(),
        key=lambda x: (float(x.get("score", 0.0)), str(x.get("ticker", ""))),
    )


def build_cartera_riesgo_panel_html(
    *,
    alertas_activo: list[dict[str, Any]],
    alertas_sector: list[dict[str, Any]],
    exceso_tickers: list[str],
    peso_max_pct: float,
    alertas_tecnicas: list[dict[str, Any]],
    umbral_activo_frac: float | None = None,
    umbral_sector_frac: float | None = None,
    umbral_mod23: float | None = None,
) -> str:
    """
    Panel HTML: diversificación (activo/sector), tope por línea y tabla MOD-23.
    Umbrales mostrados alineados con ``config`` salvo que se pasen explícitos.
    """
    ua = float(CONCENTRACION_ACTIVO_ALERTA if umbral_activo_frac is None else umbral_activo_frac)
    us = float(CONCENTRACION_SECTOR_ALERTA if umbral_sector_frac is None else umbral_sector_frac)
    um = float(NOTA_ALERTA if umbral_mod23 is None else umbral_mod23)

    ha = len(alertas_activo) > 0
    hs = len(alertas_sector) > 0
    hx = len(exceso_tickers) > 0
    ht = len(alertas_tecnicas) > 0
    any_risk = ha or hs or hx or ht

    parts: list[str] = []

    if not any_risk:
        parts.append('<div class="mq-risk-panel mq-risk-panel--ok">')
        parts.append('<div class="mq-risk-panel__head">')
        parts.append(
            '<p class="mq-risk-panel__title">Diversificación y señales</p>'
            '<p class="mq-risk-panel__sub">'
            "Tres revisiones independientes (estructura de la cartera, tope por línea y "
            "puntaje técnico MOD-23). Ahora no hay incumplimientos respecto de los umbrales "
            "configurados para tu cartera."
            "</p>"
            "</div>"
            '<div class="mq-risk-panel__footer"><span class="mq-pill mq-pill--ok">'
            "En rango</span></div>"
            "</div>"
        )
        return "".join(parts)

    parts.append('<div class="mq-risk-panel mq-risk-panel--warn">')
    parts.append('<div class="mq-risk-panel__head">')
    parts.append(
        '<p class="mq-risk-panel__title">Riesgo de concentración y señales técnicas</p>'
        '<p class="mq-risk-panel__sub">'
        "Este panel agrupa <strong>tres chequeos distintos</strong>: cuánto pesan los activos "
        "y los sectores, si alguna línea supera el tope operativo por posición, y si el "
        "puntaje técnico MOD-23 de cada ticker está por debajo del umbral. "
        "No son la misma medida: un activo puede aparecer en más de un bloque si rompe varias reglas. "
        "Los porcentajes de concentración y el tope por línea provienen de la configuración del estudio."
        "</p>"
        "</div>"
    )

    if ha or hs:
        parts.append('<div class="mq-risk-panel__block">')
        parts.append(
            '<p class="mq-risk-panel__block-title">Diversificación (estructura)</p>'
            '<p class="mq-risk-panel__hint">¿Demasiado peso en pocos activos o en un solo sector? '
            "Mirá el reparto; concentrarte demasiado aumenta el riesgo que no se diluye con el mercado.</p>"
        )
        if ha:
            parts.append(
                f'<p class="mq-risk-panel__rule">Por activo: se alerta si un ticker supera '
                f"<strong>{ua:.0%}</strong> del valor de la cartera.</p>"
                '<ul class="mq-risk-panel__list">'
            )
            for it in alertas_activo:
                tk = html.escape(str(it.get("ticker", "")))
                pw = float(it.get("peso", 0.0))
                lm = float(it.get("limite", ua))
                parts.append(
                    "<li class='mq-risk-panel__li mq-risk-panel__li--asset'>"
                    f"<span class='mq-risk-panel__li-main'>{tk}</span>"
                    "<span class='mq-risk-panel__li-meta'>"
                    f"{pw:.0%} del portafolio · umbral {lm:.0%}"
                    "</span>"
                    "</li>"
                )
            parts.append("</ul>")
        if hs:
            parts.append(
                f'<p class="mq-risk-panel__rule">Por sector: se alerta si un sector agrupa más de '
                f"<strong>{us:.0%}</strong> del total.</p>"
                '<ul class="mq-risk-panel__list">'
            )
            for it in alertas_sector:
                sec = html.escape(str(it.get("sector", "")))
                pw = float(it.get("peso", 0.0))
                lm = float(it.get("limite", us))
                parts.append(
                    "<li class='mq-risk-panel__li mq-risk-panel__li--sector'>"
                    f"<span class='mq-risk-panel__li-main'>Sector {sec}</span>"
                    "<span class='mq-risk-panel__li-meta'>"
                    f"{pw:.0%} del total · umbral {lm:.0%}"
                    "</span>"
                    "</li>"
                )
            parts.append("</ul>")
        parts.append("</div>")

    if hx:
        parts.append('<div class="mq-risk-panel__block">')
        parts.append(
            '<p class="mq-risk-panel__block-title">Tope por posición (regla operativa)</p>'
            '<p class="mq-risk-panel__hint">Es el límite máximo de peso por línea en una sola posición. '
            f"Es independiente de la alerta por activo ({ua:.0%}): el tope de línea suele ser más estricto. "
            "Un mismo ticker puede listarse acá y en el bloque anterior.</p>"
            f'<p class="mq-risk-panel__rule">Límite actual: <strong>{peso_max_pct:.1f}%</strong> del capital por ticker.</p>'
            '<p class="mq-risk-panel__p mq-risk-panel__p--tight">Superan ese tope:</p>'
            '<div class="mq-risk-panel__chips">'
        )
        for t in exceso_tickers:
            parts.append(
                f"<span class='mq-risk-chip'>{html.escape(str(t).strip())}</span>"
            )
        parts.append("</div></div>")

    if ht:
        n_t = len(alertas_tecnicas)
        parts.append('<div class="mq-risk-panel__block">')
        parts.append(
            '<p class="mq-risk-panel__block-title">Señal técnica (MOD-23)</p>'
            '<p class="mq-risk-panel__hint">Puntaje técnico del análisis MOD-23 por activo, en escala '
            "<strong>0 a 100</strong> (síntesis de tendencia, momentum y lectura relativa). "
            f"Se considera alerta cuando el puntaje queda <strong>por debajo de {um:g}</strong> sobre 100. "
            "No es una recomendación automática de venta: indica que conviene revisar la tesis de la posición.</p>"
            f'<p class="mq-risk-panel__summary"><strong>{n_t}</strong> '
            f"{'posición' if n_t == 1 else 'posiciones'} bajo el umbral técnico.</p>"
            '<div class="mq-risk-tech-wrap" tabindex="0">'
            '<table class="mq-risk-tech" role="grid">'
            "<thead><tr>"
            "<th scope='col'>Activo</th>"
            "<th scope='col'>Puntaje</th>"
            "<th scope='col'>Estado</th>"
            "</tr></thead><tbody>"
        )
        for a in alertas_tecnicas:
            tk = html.escape(str(a.get("ticker", "")))
            sc = float(a.get("score", 0.0))
            st_l = html.escape(str(a.get("estado", "—")))
            sc_cls = "mq-risk-tech-score--bad" if sc < um else "mq-risk-tech-score--warn"
            parts.append(
                "<tr>"
                f"<td><strong>{tk}</strong></td>"
                f"<td class='{sc_cls}'>{sc:.0f}/100</td>"
                f"<td>{st_l}</td>"
                "</tr>"
            )
        parts.append("</tbody></table></div>")
        parts.append(
            '<p class="mq-risk-panel__scroll-hint">Desplazá la tabla si hay muchas filas.</p>'
            "</div>"
        )

    parts.append("</div>")
    return "".join(parts)


def fail_over_message(key: str = "mq26_failover_msg") -> None:
    st.error(
        st.session_state.get(key)
        or "Servicio momentáneamente fuera de servicio. Reintentá en unos minutos.",
    )


def scroll_hint_row() -> None:
    """Pista para tablas anchas (#20)."""
    st.caption("Deslizá horizontalmente o usá el scroll para ver toda la tabla →")
