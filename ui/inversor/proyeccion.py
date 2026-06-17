"""ui/inversor/proyeccion.py — bloque de proyección patrimonial + Montecarlo.

Extraído de ui/tab_inversor.py (Fase 2.1). Incluye los dos helpers que solo usa
este bloque (_bloque_competitivo, _spy_daily_returns_log_returns_cached).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.diagnostico_types import (
    RENDIMIENTO_MODELO_YTD_REF,
    perfil_diagnostico_valido,
)
from core.renta_fija_ar import (
    ladder_vencimientos,
    tir_ponderada_cartera,
    top_instrumentos_rf,
)
from ui.mq26_ux import plotly_chart_layout_base


def _bloque_competitivo(ctx: dict, diag: object) -> dict:
    perfil_v = perfil_diagnostico_valido(str(ctx.get("cliente_perfil", "Moderado")))
    modelo_f = float(RENDIMIENTO_MODELO_YTD_REF.get(perfil_v, 0.09))
    df_ag = ctx.get("df_ag")
    pnl = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0.0)
    cmpd = {
        "cliente": pnl,
        "modelo": modelo_f * 100.0,
        "spy": None,
    }
    if df_ag is None or df_ag.empty:
        return {
            "tir_ponderada_cliente": None,
            "ladder": [],
            "top_rf": top_instrumentos_rf(4),
            "rendimiento_modelo_frac": modelo_f,
            "comparacion_rendimientos_pct": cmpd,
            "series_comparacion": None,
        }
    return {
        "tir_ponderada_cliente": tir_ponderada_cartera(df_ag),
        "ladder": ladder_vencimientos(df_ag),
        "top_rf": top_instrumentos_rf(4),
        "rendimiento_modelo_frac": modelo_f,
        "comparacion_rendimientos_pct": cmpd,
        "series_comparacion": ctx.get("series_comparacion_informe"),
    }


@st.cache_data(ttl=1800)
def _spy_daily_returns_log_returns_cached() -> list[float] | None:
    """Retornos diarios simples (close/close prev - 1) SPY; ~10y auto_adjust. None si falla."""
    try:
        import yfinance as yf

        h = yf.Ticker("SPY").history(period="10y", auto_adjust=True)
        if h is None or len(h) < 60:
            return None
        c = h["Close"].astype(float)
        prev = c.shift(1)
        r = ((c - prev) / prev).dropna()
        out = [float(x) for x in r.values if pd.notna(x)]
        return out if len(out) >= 50 else None
    except Exception:
        return None


def _render_proyeccion_y_pie_inversor(
    ctx: dict, diag, metricas: dict, _hub: dict | None = None,
) -> None:
    """Proyección determinística + opcional MC, meta y descarga de informe."""
    from core.retirement_goal import (
        calcular_aporte_necesario,
        serie_patrimonio_mensual,
        simulate_retirement,
    )

    st.markdown(
        "<p style='font-size:0.72rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.07em;'>Proyección patrimonial</p>",
        unsafe_allow_html=True,
    )

    ccl_v = float(ctx.get("ccl") or 1150.0)
    val_actual_usd = float(getattr(diag, "valor_cartera_usd", 0) or 0)

    col_a, col_b, col_c = st.columns(3)
    aporte_ars = col_a.number_input(
        "Aporte mensual (ARS)",
        min_value=0.0,
        value=float(st.session_state.get("inversor_aporte_ars", 50_000.0)),
        step=10_000.0,
        format="%.0f",
        key="inversor_aporte_ars",
    )
    horizonte_opts = {"1 año": 12, "3 años": 36, "5 años": 60, "10 años": 120}
    horizonte_sel = col_b.selectbox(
        "Horizonte",
        list(horizonte_opts.keys()),
        index=1,
        key="inversor_horiz_label",
    )
    meses_sel = int(horizonte_opts[horizonte_sel])
    meses_override = col_c.number_input(
        "Meses (opcional; 0 = usar arriba)",
        min_value=0,
        max_value=480,
        value=0,
        step=1,
        key="inversor_meses_override",
    )
    meses = int(meses_override) if int(meses_override) > 0 else meses_sel
    horiz_txt = f"{meses} meses" if int(meses_override) > 0 else horizonte_sel

    aporte_usd = aporte_ars / max(ccl_v, 1.0)
    g1, g2 = st.columns(2)
    obj_usd = g1.number_input(
        "Patrimonio objetivo (USD; 0 = no calcular aporte extra)",
        min_value=0.0,
        value=float(st.session_state.get("inversor_obj_usd", 0.0) or 0.0),
        step=1_000.0,
        format="%.0f",
        key="inversor_obj_usd",
    )
    st.caption(
        "Los cálculos **no incluyen** comisiones, impuestos ni impacto de cambiar el CCL. "
        "Referencia **USD** alineada al diagnóstico."
    )

    escenarios: dict[str, float] = {}
    series_m: dict[str, list[float]] = {}
    for label, ret_anual in [("Pesimista", 0.04), ("Base", 0.09), ("Optimista", 0.15)]:
        sim = simulate_retirement(
            capital_inicial_usd=val_actual_usd,
            aporte_mensual_usd=aporte_usd,
            retorno_anual=ret_anual,
            meses=meses,
        )
        escenarios[label] = float(sim.get("capital_final_usd", 0.0))
        series_m[label] = serie_patrimonio_mensual(
            capital_inicial_usd=val_actual_usd,
            aporte_mensual_usd=aporte_usd,
            retorno_anual=ret_anual,
            meses=meses,
        )

    with g2:
        if obj_usd > 0 and meses > 0:
            ap_req = calcular_aporte_necesario(
                val_actual_usd,
                obj_usd,
                max(meses / 12.0, 1e-6),
                0.09,
            )
            st.markdown(
                f"<div style='font-size:0.88rem;color:var(--c-text-2);padding-top:1.4rem;'>"
                f"Aporte mensual **extra** estimado (escenario base 9% anual): "
                f"<strong>USD {ap_req:,.0f}</strong> (~ ARS <strong>{ap_req * ccl_v:,.0f}</strong>)</div>",
                unsafe_allow_html=True,
            )
            base_fv = escenarios.get("Base", 0.0)
            if base_fv + 1.0 < obj_usd and aporte_ars <= 0:
                st.warning(
                    "Con el aporte actual en cero, el escenario base queda lejos del objetivo. "
                    "Subí el aporte mensual o el horizonte."
                )

    COLORS = {"Pesimista": "#ef4444", "Base": "#3b82f6", "Optimista": "#10b981"}
    escenarios_ars = {k: float(v) * ccl_v for k, v in escenarios.items()}
    fig_proy = go.Figure(
        data=[
            go.Bar(
                x=list(escenarios_ars.keys()),
                y=list(escenarios_ars.values()),
                marker_color=[COLORS[k] for k in escenarios_ars],
                text=[f"{v:,.0f} ARS" for v in escenarios_ars.values()],
                textposition="outside",
            )
        ]
    )
    fig_proy.update_layout(
        **plotly_chart_layout_base(
            height=280,
            showlegend=False,
            yaxis=dict(
                title="Patrimonio estimado fin de período (ARS)",
                tickformat=",.0f",
                ticksuffix=" ARS",
                gridcolor="rgba(148,163,184,0.12)",
            ),
            xaxis=dict(tickfont=dict(size=13)),
            margin=dict(t=20, b=20, l=10, r=10),
        ),
    )
    st.plotly_chart(fig_proy, use_container_width=True, key="inv_bar_proy_final")

    if meses > 0:
        _xmes = list(range(1, meses + 1))
        fig_lines = go.Figure()
        for label in ("Pesimista", "Base", "Optimista"):
            yv = series_m.get(label, [])
            if yv:
                fig_lines.add_trace(
                    go.Scatter(
                        x=_xmes,
                        y=[y * ccl_v for y in yv],
                        name=label,
                        mode="lines",
                        line=dict(width=2, color=COLORS[label]),
                    )
                )
        if obj_usd > 0:
            fig_lines.add_hline(
                y=obj_usd * ccl_v,
                line_dash="dash",
                line_color="rgba(148,163,184,0.8)",
                annotation_text="Objetivo ARS",
            )
        fig_lines.update_layout(
            **plotly_chart_layout_base(
                height=340,
                xaxis=dict(title="Mes"),
                yaxis=dict(title="Patrimonio estimado (ARS)", tickformat=",.0f"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                margin=dict(t=40, b=40, l=50, r=20),
            ),
        )
        st.plotly_chart(fig_lines, use_container_width=True, key="inv_lines_proy_meses")

    base_val = escenarios.get("Base", 0)
    base_val_ars = escenarios_ars.get("Base", 0.0)
    delta_pct = ((base_val - val_actual_usd) / max(val_actual_usd, 1)) * 100 if val_actual_usd else 0
    st.markdown(
        f"<p style='font-size:0.78rem;color:var(--c-text-2);text-align:center;'>"
        f"Escenario base: tu patrimonio podría crecer "
        f"<strong style='color:var(--c-accent);'>+{delta_pct:.0f}%</strong> en {horiz_txt}, "
        f"llegando a unos <strong style='color:var(--c-accent);'>ARS {base_val_ars:,.0f}</strong> "
        f"(~ USD {base_val:,.0f})</p>",
        unsafe_allow_html=True,
    )

    st.markdown("##### Montecarlo (bootstrap SPY, ilustrativo)")
    n_sim_ui = int(st.session_state.get("mc_n_escenarios_select", 3000) or 3000)
    st.caption(
        f"Usa **{n_sim_ui}** simulaciones (selector global «Simulaciones MC» en la barra lateral). "
        "Semilla **42**. Historia diaria SPY ~10 años; si no hay datos, se omite."
    )
    mc_on = st.checkbox("Incluir Montecarlo SPY en resultados", value=False, key="inv_plan_mc_on")
    mc_res: dict | None = None
    r_spy = _spy_daily_returns_log_returns_cached()
    if mc_on and r_spy is not None:
        arr = np.asarray(r_spy, dtype=float)
        umbral = float(obj_usd) if obj_usd > 0 else None
        mc_res = simulate_retirement(
            aporte_mensual=aporte_usd,
            n_meses_acum=meses,
            retiro_mensual=0.0,
            n_meses_desacum=0,
            retornos_diarios=arr,
            n_sim=min(max(500, n_sim_ui), 10_000),
            capital_inicial_usd=val_actual_usd,
            objetivo_umbral_usd=umbral,
            mc_seed=42,
        )
        c_mc1, c_mc2, c_mc3 = st.columns(3)
        c_mc1.metric("P10 final (USD)", f"{mc_res.get('p10', 0):,.0f}")
        c_mc2.metric("P50 final (USD)", f"{mc_res.get('p50', 0):,.0f}")
        c_mc3.metric("P90 final (USD)", f"{mc_res.get('p90', 0):,.0f}")
        if umbral and umbral > 0 and "prob_supera_objetivo" in mc_res:
            st.metric(
                "Prob. patrimonio final ≥ objetivo",
                f"{float(mc_res['prob_supera_objetivo']) * 100:.1f}%",
            )
    elif mc_on:
        st.info("No se pudieron cargar retornos SPY; probá «Actualizar precios» o revisá la conexión.")

    bloque_plan = {
        "horizonte_label": horiz_txt,
        "meses": meses,
        "aporte_mensual_ars": float(aporte_ars),
        "aporte_mensual_usd": float(aporte_usd),
        "objetivo_usd": float(obj_usd),
        "capital_inicial_usd": float(val_actual_usd),
        "escenarios_det": {k: float(v) for k, v in escenarios.items()},
        "montecarlo": mc_res,
        "ccl": ccl_v,
    }

    fc2, fc3 = st.columns(2)
    with fc2:
        if st.button("Importar del broker", use_container_width=True, key="inv_foot_imp"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "importar"
            st.rerun()
    with fc3:
        if st.button("Actualizar precios", use_container_width=True, key="inv_foot_px"):
            try:
                st.cache_data.clear()
            except Exception:
                pass
            st.session_state.pop("inv_diagnostico", None)
            st.rerun()

    with st.expander("Descargar informe HTML"):
        from services.reporte_inversor import generar_reporte_inversor

        rr_dl = (st.session_state.get("inv_recomendacion") or {}).get("rr")
        aporte_usd_rep = float(st.session_state.get("inversor_aporte_ars", 0) or 0) / max(
            float(ctx.get("ccl") or 1.0), 1e-9
        )
        horiz_rep = int(meses)
        html_rep = generar_reporte_inversor(
            diag,
            rr_dl,
            metricas,
            aporte_mensual_usd=aporte_usd_rep,
            horizon_meses=int(horiz_rep),
            bloque_competitivo=_bloque_competitivo(ctx, diag),
            df_ag=ctx.get("df_ag"),
            bloque_plan_simulacion=bloque_plan,
        )
        st.download_button(
            "Descargar informe",
            data=html_rep,
            file_name="mq26_informe.html",
            mime="text/html",
            use_container_width=True,
        )
