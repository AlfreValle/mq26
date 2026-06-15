"""
ui/tab_portfolio_optimizer.py — Tab Plan Multi-Objetivo CP/MP/LP

Interfaz para el motor services/portfolio_optimizer.py.

Secciones:
  1. Configuración del plan (objetivos, capital, flujo mensual, CCL)
  2. Resumen: tabla de tramos + distribución de capital (torta)
  3. Proyección por tramo (gráfico de líneas)
  4. Detalle de instrumentos por tramo (tabla expandible)
  5. Advertencias y disclaimers
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from core.logging_config import get_logger
from services.portfolio_optimizer import (
    CATALOGO_OBJETIVOS,
    PlanMultifuncional,
    asignacion_pie_df,
    calcular_plan_multifuncional,
    objetivo_info,
    proyeccion_consolidada_df,
    resumen_plan_df,
    CCL_DEFAULT,
)

_log = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
#  PALETA Y CONSTANTES UI
# ──────────────────────────────────────────────────────────────────────────────

_COLORES_OBJETIVO: dict[str, str] = {
    "CP1": "#2ECC71",   # verde menta — liquidez
    "CP2": "#27AE60",   # verde oscuro — operativo
    "CP3": "#F39C12",   # naranja — oportunidad
    "MP1": "#3498DB",   # azul — renta ON
    "MP2": "#9B59B6",   # violeta — CER
    "MP3": "#1ABC9C",   # teal — CEDEAR
    "LP1": "#E67E22",   # naranja oscuro — ON largas
    "LP2": "#E74C3C",   # rojo — FIRE/jubilación
    "LP3": "#2980B9",   # azul oscuro — crecimiento
}

_HORIZONTE_LABEL: dict[str, str] = {
    "CP": "⚡ Corto Plazo",
    "MP": "📈 Mediano Plazo",
    "LP": "🏦 Largo Plazo",
}

_DISCLAIMER = (
    "⚠️ **Disclaimer**: Esta herramienta es **educativa** y no constituye asesoramiento "
    "financiero. Los retornos proyectados son estimaciones basadas en datos de catálogo; "
    "no garantizan resultados futuros. La TIR de instrumentos de renta fija y el rendimiento "
    "de CEDEARs son referenciales al {fecha}. Consulte con un asesor financiero matriculado "
    "antes de invertir."
)


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _label_objetivo(cod: str) -> str:
    cfg = CATALOGO_OBJETIVOS.get(cod)
    if cfg is None:
        return cod
    hz = _HORIZONTE_LABEL.get(cfg.horizonte, cfg.horizonte)
    return f"{hz} · {cfg.codigo} — {cfg.nombre}"


def _tooltip_objetivo(cod: str) -> str:
    info = objetivo_info(cod)
    if info is None:
        return ""
    return (
        f"**{info['nombre']}**  \n"
        f"{info['descripcion']}  \n"
        f"Retorno esperado USD: ~{info['retorno_esperado_usd_anual']:.1f}% anual  \n"
        f"Liquidez: {info['liquidez']}  \n"
        f"Perfil mínimo: {info['perfil_minimo']}"
    )


def _fmt_usd(v: float | None, decimals: int = 0) -> str:
    if v is None:
        return "—"
    fmt = f"{v:,.{decimals}f}"
    return f"USD {fmt}"


def _fmt_ars(v: float | None) -> str:
    if v is None:
        return "—"
    return f"ARS {v:,.0f}"


# ──────────────────────────────────────────────────────────────────────────────
#  SECCIÓN 1 — CONFIGURACIÓN
# ──────────────────────────────────────────────────────────────────────────────

def _render_configuracion(ctx: dict) -> tuple[list[str], float, float, float]:
    """Renderiza el panel de configuración y devuelve (objetivos, capital, flujo, ccl)."""
    st.markdown("### ⚙️ Configurar Plan")

    # Agrupamos objetivos por horizonte para el multiselect
    options_cp = [f"{cod} — {CATALOGO_OBJETIVOS[cod].nombre}" for cod in ("CP1", "CP2", "CP3")]
    options_mp = [f"{cod} — {CATALOGO_OBJETIVOS[cod].nombre}" for cod in ("MP1", "MP2", "MP3")]
    options_lp = [f"{cod} — {CATALOGO_OBJETIVOS[cod].nombre}" for cod in ("LP1", "LP2", "LP3")]
    todas_opciones = options_cp + options_mp + options_lp

    # Mapa inverso: "CP2 — Capital de Trabajo" → "CP2"
    _codigo_de_label: dict[str, str] = {
        f"{cod} — {CATALOGO_OBJETIVOS[cod].nombre}": cod
        for cod in CATALOGO_OBJETIVOS
    }

    col_obj, col_params = st.columns([3, 2], gap="large")

    with col_obj:
        st.markdown("#### 🎯 Objetivos activos")
        # Valor por defecto: CP2 + MP1 + LP3 (caso del usuario)
        default_labels = [
            "CP2 — Capital de Trabajo",
            "MP1 — Renta Semestral ON USD",
            "LP3 — Crecimiento USD Acciones",
        ]
        seleccionadas = st.multiselect(
            "Seleccionar 1 a 9 objetivos",
            options=todas_opciones,
            default=default_labels,
            key="opt_objetivos",
            help=(
                "CP = Corto Plazo (≤12 meses) · MP = Mediano Plazo (12-36 meses) "
                "· LP = Largo Plazo (3-15 años)"
            ),
        )
        objetivos = [_codigo_de_label[lbl] for lbl in seleccionadas if lbl in _codigo_de_label]

        # Mostrar descripción de cada objetivo seleccionado
        if objetivos:
            with st.expander("📋 Descripción de objetivos seleccionados", expanded=False):
                for cod in objetivos:
                    cfg = CATALOGO_OBJETIVOS[cod]
                    hz = _HORIZONTE_LABEL.get(cfg.horizonte, cfg.horizonte)
                    st.markdown(
                        f"**{hz} · {cod} — {cfg.nombre}**  \n"
                        f"{cfg.descripcion}  \n"
                        f"*Retorno esperado USD ~{cfg.retorno_esperado_usd_anual:.1f}%/año · "
                        f"Liquidez: {cfg.liquidez} · Perfil: {cfg.perfil_minimo}*"
                    )
                    st.divider()

    with col_params:
        st.markdown("#### 💰 Capital y flujo")
        capital = st.number_input(
            "Capital inicial (USD)",
            min_value=0.0,
            max_value=10_000_000.0,
            value=5_000.0,
            step=500.0,
            format="%.0f",
            key="opt_capital",
            help="Capital disponible en dólares para distribuir entre los objetivos.",
        )
        flujo = st.number_input(
            "Aporte mensual recurrente (USD)",
            min_value=0.0,
            max_value=100_000.0,
            value=350.0,
            step=50.0,
            format="%.0f",
            key="opt_flujo",
            help="Monto que se suma cada mes al plan (puede ser $0).",
        )
        ccl_default = float(ctx.get("ccl") or CCL_DEFAULT)
        ccl = st.number_input(
            "CCL ARS/USD",
            min_value=100.0,
            max_value=50_000.0,
            value=ccl_default,
            step=10.0,
            format="%.0f",
            key="opt_ccl",
            help=f"Tipo de cambio CCL (referencia 2026-05-27: AR$ {CCL_DEFAULT:,.0f}).",
        )

    return objetivos, float(capital), float(flujo), float(ccl)


# ──────────────────────────────────────────────────────────────────────────────
#  SECCIÓN 2 — RESUMEN
# ──────────────────────────────────────────────────────────────────────────────

def _render_resumen(plan: PlanMultifuncional) -> None:
    st.markdown("### 📊 Resumen del Plan")

    # KPIs globales
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Capital total", _fmt_usd(plan.capital_total_usd))
    col2.metric("Flujo mensual", _fmt_usd(plan.flujo_mensual_total_usd))
    col3.metric("Objetivos activos", len(plan.tramos))
    col4.metric("CCL", f"AR$ {plan.ccl:,.0f}")

    st.divider()

    col_tabla, col_torta = st.columns([3, 2], gap="large")

    with col_tabla:
        df_res = resumen_plan_df(plan)
        if not df_res.empty:
            # Formatear columnas monetarias
            df_display = df_res.copy()
            df_display["Capital USD"] = df_display["Capital USD"].apply(
                lambda v: _fmt_usd(v) if pd.notna(v) else "—"
            )
            df_display["Flujo mes. USD"] = df_display["Flujo mes. USD"].apply(
                lambda v: _fmt_usd(v) if pd.notna(v) else "—"
            )
            df_display["FV USD"] = df_display["FV USD"].apply(
                lambda v: _fmt_usd(v) if pd.notna(v) else "—"
            )
            df_display["FV ARS"] = df_display["FV ARS"].apply(
                lambda v: _fmt_ars(v) if pd.notna(v) else "—"
            )
            df_display["TIR pond. %"] = df_display["TIR pond. %"].apply(
                lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
            )
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
            )

    with col_torta:
        df_pie = asignacion_pie_df(plan)
        if not df_pie.empty:
            df_pie["label"] = df_pie["objetivo"] + "<br>" + df_pie["nombre"].str[:20]
            fig_pie = px.pie(
                df_pie,
                names="label",
                values="capital_usd",
                title="Distribución de capital",
                color="objetivo",
                color_discrete_map=_COLORES_OBJETIVO,
                hole=0.4,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=40, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_pie, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SECCIÓN 3 — PROYECCIÓN
# ──────────────────────────────────────────────────────────────────────────────

def _render_proyeccion(plan: PlanMultifuncional) -> None:
    st.markdown("### 📈 Proyección Valor Futuro por Objetivo")

    df_proy = proyeccion_consolidada_df(plan)
    if df_proy.empty:
        st.info("Sin datos de proyección.")
        return

    fig = go.Figure()
    for t in plan.tramos:
        sub = df_proy[df_proy["objetivo"] == t.objetivo]
        if sub.empty:
            continue
        color = _COLORES_OBJETIVO.get(t.objetivo, "#888888")
        fig.add_trace(go.Scatter(
            x=sub["fecha"],
            y=sub["valor_usd"],
            mode="lines+markers",
            name=f"{t.objetivo} — {t.nombre}",
            line=dict(color=color, width=2),
            marker=dict(size=4),
            hovertemplate=(
                f"<b>{t.objetivo}</b><br>"
                "Mes: %{x}<br>"
                "FV: USD %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Proyección mensual FV (USD) por objetivo",
        xaxis_title="Fecha",
        yaxis_title="Valor en USD",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=420,
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)")
    st.plotly_chart(fig, use_container_width=True)

    # KPIs de crecimiento
    st.markdown("#### 🏁 Valor final por objetivo")
    cols = st.columns(min(len(plan.tramos), 4))
    for i, t in enumerate(plan.tramos):
        col = cols[i % len(cols)]
        retorno_total = t.valor_final_usd - t.capital_inicial_usd
        retorno_pct = (retorno_total / t.capital_inicial_usd * 100) if t.capital_inicial_usd > 0 else 0
        col.metric(
            label=f"{t.objetivo} ({t.horizonte_meses}m)",
            value=_fmt_usd(t.valor_final_usd),
            delta=f"+{_fmt_usd(retorno_total)} ({retorno_pct:.1f}%)" if retorno_total >= 0
                  else _fmt_usd(retorno_total),
        )


# ──────────────────────────────────────────────────────────────────────────────
#  SECCIÓN 4 — DETALLE DE INSTRUMENTOS
# ──────────────────────────────────────────────────────────────────────────────

def _render_instrumentos(plan: PlanMultifuncional) -> None:
    st.markdown("### 🔎 Instrumentos por Tramo")

    for t in plan.tramos:
        color = _COLORES_OBJETIVO.get(t.objetivo, "#888")
        hz_label = _HORIZONTE_LABEL.get(
            CATALOGO_OBJETIVOS[t.objetivo].horizonte
            if t.objetivo in CATALOGO_OBJETIVOS else "",
            ""
        )
        header = (
            f"{hz_label} · **{t.objetivo} — {t.nombre}** "
            f"| Capital: {_fmt_usd(t.capital_inicial_usd)} "
            f"| TIR pond.: {t.tir_ponderada_pct:.1f}% "
            f"| FV {t.horizonte_meses}m: {_fmt_usd(t.valor_final_usd)}"
        )
        with st.expander(header, expanded=False):
            if t.advertencias:
                for adv in t.advertencias:
                    st.warning(adv)

            if not t.instrumentos:
                st.info("Sin instrumentos asignados para este tramo.")
                continue

            rows = []
            for instr in t.instrumentos:
                rows.append({
                    "Ticker":        instr.ticker,
                    "Nombre":        instr.nombre[:40],
                    "Tipo":          instr.tipo,
                    "Peso %":        f"{instr.peso_pct:.1f}%",
                    "Capital USD":   _fmt_usd(instr.capital_usd, 2),
                    "Capital ARS":   _fmt_ars(instr.capital_ars),
                    "TIR ref. %":    f"{instr.tir_ref:.1f}%" if instr.tir_ref is not None else "—",
                    "Vencimiento":   instr.vencimiento or "—",
                    "Calificación":  instr.calificacion or "—",
                    "Estrategia":    instr.razon[:60] if instr.razon else "—",
                })

            df_instr = pd.DataFrame(rows)
            st.dataframe(df_instr, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────────────────────────────────────────
#  SECCIÓN 5 — ADVERTENCIAS
# ──────────────────────────────────────────────────────────────────────────────

def _render_advertencias(plan: PlanMultifuncional) -> None:
    if plan.advertencias_globales:
        st.markdown("### ⚠️ Advertencias del plan")
        for adv in plan.advertencias_globales:
            st.warning(adv)

    from datetime import date
    st.markdown("---")
    st.caption(_DISCLAIMER.format(fecha=date.today().isoformat()))


# ──────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def render_tab_portfolio_optimizer(ctx: dict | None = None) -> None:
    """
    Entry point del tab. Llamar desde la app principal:

        from ui.tab_portfolio_optimizer import render_tab_portfolio_optimizer
        with tab_opt:
            render_tab_portfolio_optimizer(ctx)

    ctx puede incluir:
        - "ccl": float — tipo de cambio CCL (si está disponible del contexto app)
        - "cliente_id": str — para logging
    """
    if ctx is None:
        ctx = {}

    st.title("🗂️ Plan Multi-Objetivo CP/MP/LP")
    st.markdown(
        "Diseñá tu plan de inversión dividido en tramos de **Corto**, **Mediano** y **Largo Plazo**. "
        "Cada objetivo se mapea a instrumentos del catálogo MQ26 y proyecta el valor futuro al horizonte."
    )

    # ── Configuración ────────────────────────────────────────────────────────
    objetivos, capital, flujo, ccl = _render_configuracion(ctx)

    if not objetivos:
        st.info("👆 Seleccioná al menos un objetivo para generar el plan.")
        return

    # ── Botón de cálculo ──────────────────────────────────────────────────────
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        calcular = st.button("🚀 Calcular Plan", type="primary", use_container_width=True)
    with col_info:
        st.markdown(
            f"**{len(objetivos)} objetivo(s)** · Capital: **{_fmt_usd(capital)}** · "
            f"Flujo: **{_fmt_usd(flujo)}/mes** · CCL: **AR$ {ccl:,.0f}**"
        )

    # Estado: recalcular solo si cambia algo o se presiona el botón
    plan_key = f"plan_{'-'.join(sorted(objetivos))}_{capital}_{flujo}_{ccl}"
    if calcular or st.session_state.get("_opt_last_key") != plan_key:
        try:
            with st.spinner("Calculando plan..."):
                plan = calcular_plan_multifuncional(
                    objetivos,
                    capital_inicial_usd=capital,
                    flujo_mensual_usd=flujo,
                    ccl=ccl,
                )
            st.session_state["_opt_plan"] = plan
            st.session_state["_opt_last_key"] = plan_key
            _log.info(
                "PORTFOLIO_OPTIMIZER: %s objetivos=%s capital=%.0f flujo=%.0f ccl=%.0f",
                ctx.get("cliente_id", "anon"), objetivos, capital, flujo, ccl,
            )
        except Exception as exc:
            st.error(f"Error al calcular el plan: {exc}")
            _log.exception("PORTFOLIO_OPTIMIZER error: %s", exc)
            return
    else:
        plan = st.session_state.get("_opt_plan")

    if plan is None:
        st.info("Presioná **Calcular Plan** para generar el análisis.")
        return

    # ── Renderizar secciones ─────────────────────────────────────────────────
    _render_advertencias(plan)
    st.divider()
    _render_resumen(plan)
    st.divider()
    _render_proyeccion(plan)
    st.divider()
    _render_instrumentos(plan)
