"""
ui/tab_inversor.py — Vista del inversor individual (tier IN).

Secciones: resumen + lista legible, carga, plata nueva, proyección.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.diagnostico_types import (
    CARTERA_IDEAL,
    RENDIMIENTO_MODELO_YTD_REF,
    perfil_diagnostico_valido,
)
from core.renta_fija_ar import (
    es_renta_fija,
)
from services.copy_inversor import (
    GLOSARIO_INVERSOR,
    antes_despues_defensivo,
    copy_rebalanceo_humano,
    pasos_onboarding_hub,
    patrimonio_dual_line,
)
from services.investor_hub_snapshot import build_investor_hub_snapshot
from services.plan_simulaciones import (
    agrupar_pesos_torta,
    df_ag_tiene_posiciones_reales,
    dias_desde_primera_compra,
    ideal_dict_desde_mix_plan,
)
from ui.inversor._helpers import (
    _get_diagnostico_cached,
    _horizonte_ui,
    _ticker_desde_fila_pos,
)
from ui.inversor.paneles_kpi import (
    _render_panel_rf_kpis,
    _render_panel_rv_kpis,
)
from ui.inversor.plata_nueva import _render_bloque_plata_nueva
from ui.inversor.posiciones import (
    _df_alineacion_activos,
    _df_salud_referencias_posicion,
    _render_posiciones_con_targets,
    _render_tabla_posiciones_resumen,
)
from ui.inversor.primera_cartera import _render_bienvenida_inversor
from ui.inversor.proyeccion import _render_proyeccion_y_pie_inversor
from ui.mq26_ux import (
    dataframe_auto_height,
    defensive_bar_html,
    fig_torta_ideal,
    obs_card_html,
    plotly_chart_layout_base,
    semaforo_html,
)

_OBS_PRIO_MAP = {
    "critica": "critica", "alta": "alta",
    "media": "media", "baja": "baja",
}


# ── Perfiles para el selector visual ──────────────────────────────────────────
# Colores del sistema de diseño (tokens --c-*), no hex Material sueltos:
# gradiente de riesgo verde→azul→amarillo→rojo. El "bg" usa el muted del token
# para que las tarjetas se adapten al tema (claro/oscuro) sin grises fijos.
_PERFILES_INFO: dict[str, dict] = {
    "Conservador": {
        "icono": "🛡️",
        "lema": "Priorizo no perder.",
        "rf_rv": "60% RF · 40% RV",
        "color": "var(--c-green)",
        "bg": "var(--c-green-muted)",
    },
    "Moderado": {
        "icono": "⚖️",
        "lema": "Equilibrio riesgo/retorno.",
        "rf_rv": "50% RF · 50% RV",
        "color": "var(--c-accent)",
        "bg": "var(--c-accent-muted)",
    },
    "Arriesgado": {
        "icono": "📈",
        "lema": "Acepto volatilidad.",
        "rf_rv": "35% RF · 65% RV",
        "color": "var(--c-yellow)",
        "bg": "var(--c-yellow-muted)",
    },
    "Muy arriesgado": {
        "icono": "🚀",
        "lema": "Máximo potencial.",
        "rf_rv": "30% RF · 70% RV",
        "color": "var(--c-red)",
        "bg": "var(--c-red-muted)",
    },
}


# ── Selector de perfil minimalista (visual, una sola decisión del inversor) ──
def _render_selector_perfil_cards(ctx: dict) -> None:
    """
    4 tarjetas visuales para elegir perfil de riesgo.
    El inversor solo presiona una — es la única decisión requerida.
    """
    from core.db_manager import actualizar_cliente

    cid = ctx.get("cliente_id")
    dbm = ctx.get("dbm")
    perfil_actual = str(ctx.get("cliente_perfil", "Moderado"))

    st.markdown(
        "<p style='font-size:0.7rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.08em;margin:0 0 0.4rem 0;'>"
        "Mi perfil de riesgo</p>",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for col, (nombre, info) in zip(cols, _PERFILES_INFO.items(), strict=False):
        activo = nombre == perfil_actual
        borde = f"2px solid {info['color']}" if activo else "1px solid var(--c-border)"
        bg = info["bg"] if activo else "transparent"
        with col:
            st.markdown(
                f"<div style='border:{borde};border-radius:8px;padding:0.55rem 0.6rem;"
                f"background:{bg};text-align:center;'>"
                f"<div style='font-size:1.4rem;'>{info['icono']}</div>"
                f"<div style='font-size:0.78rem;font-weight:700;color:{info['color']};'>{nombre}</div>"
                f"<div style='font-size:0.68rem;color:var(--c-text-3);'>{info['rf_rv']}</div>"
                f"<div style='font-size:0.63rem;color:var(--c-text-3);margin-top:0.15rem;'>{info['lema']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if not activo and cid and dbm:
                if st.button(
                    "Elegir",
                    key=f"btn_perfil_{nombre.replace(' ', '_')}",
                    use_container_width=True,
                ):
                    try:
                        horizonte_act = str(ctx.get("cliente_horizonte_label", "1 año"))
                        capital_act = float(ctx.get("cliente_capital_usd", 0) or 0)
                        nombre_act = str(ctx.get("cliente_nombre", "")).split("|")[0].strip()
                        actualizar_cliente(
                            int(cid), nombre_act or "—", nombre,
                            capital_act, "Persona", horizonte_act,
                            tenant_id=str(ctx.get("tenant_id") or "default"),
                        )
                        st.session_state["cliente_perfil"] = nombre
                        st.session_state.pop("inv_diagnostico", None)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"No se pudo cambiar el perfil: {_e}")
            elif activo:
                st.markdown(
                    f"<div style='text-align:center;font-size:0.65rem;"
                    f"color:{info['color']};font-weight:600;margin-top:0.15rem;'>Activo</div>",
                    unsafe_allow_html=True,
                )


@st.cache_data(ttl=1800)
def _benchmark_ytd_pct(symbol: str) -> float | None:
    """Retorno YTD aproximado (%) vía yfinance; None si no hay datos."""
    try:
        import yfinance as yf

        h = yf.Ticker(symbol).history(period="ytd")
        if h is None or len(h) < 2:
            return None
        c = h["Close"].dropna()
        if len(c) < 2:
            return None
        return float(c.iloc[-1] / c.iloc[0] - 1.0) * 100.0
    except Exception:
        return None


def _ideal_rf_rv_fracciones(ideal_d: dict) -> tuple[float, float]:
    """Suma pesos renta fija vs variable del dict CARTERA_IDEAL."""
    rf = rv = 0.0
    for k, v in (ideal_d or {}).items():
        try:
            w = float(v)
        except (TypeError, ValueError):
            continue
        ks = str(k).strip()
        if not ks:
            continue
        if ks.startswith("_") or es_renta_fija(ks.upper()):
            rf += max(0.0, w)
        else:
            rv += max(0.0, w)
    return rf, rv


def _inversor_sin_posiciones_cargadas(df_ag: pd.DataFrame | None) -> bool:
    """True si no hay activos reales: bienvenida + primera cartera / sugerencia."""
    if df_ag is None or df_ag.empty:
        return True
    if "TICKER" not in df_ag.columns:
        return True
    s = df_ag["TICKER"].astype(str).str.strip().str.upper()
    s = s[s.ne("") & s.ne("NAN") & s.ne("NONE")]
    return s.empty


def _render_config_perfil(ctx: dict) -> None:
    from core.db_manager import actualizar_cliente

    cid = ctx.get("cliente_id")
    dbm = ctx.get("dbm")
    if not cid or not dbm:
        return

    nombre_actual = str(ctx.get("cliente_nombre", "")).split("|")[0].strip()
    perfil_actual = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte_actual = _horizonte_ui(ctx)
    cap_ref = float(ctx.get("cliente_capital_usd", 0) or 0)

    perfiles = ["Conservador", "Moderado", "Arriesgado", "Muy arriesgado"]
    horizontes = ["1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años"]
    perfil_desc = {
        "Conservador": "Priorizo no perder. Acepto menor ganancia.",
        "Moderado": "Busco equilibrio entre riesgo y rendimiento.",
        "Arriesgado": "Acepto volatilidad. Busco mayor rendimiento.",
        "Muy arriesgado": "Máximo potencial. Alta tolerancia a la volatilidad.",
    }

    col_n, col_p = st.columns(2)
    with col_n:
        nuevo_nombre = st.text_input("Mi nombre", value=nombre_actual, key="cfg_nombre")
    with col_p:
        idx_p = perfiles.index(perfil_actual) if perfil_actual in perfiles else 1
        nuevo_perfil = st.selectbox("Mi perfil de riesgo", perfiles, index=idx_p, key="cfg_perfil")

    st.caption(f"📌 {perfil_desc.get(nuevo_perfil, '')}")

    col_h, col_c = st.columns(2)
    with col_h:
        idx_h = horizontes.index(horizonte_actual) if horizonte_actual in horizontes else 3
        nuevo_horizonte = st.selectbox(
            "Mi horizonte de inversión",
            horizontes,
            index=idx_h,
            key="cfg_horizonte",
            help="¿En cuánto tiempo podrías necesitar este dinero?",
        )
    with col_c:
        nuevo_capital = st.number_input(
            "Capital de referencia (USD)",
            min_value=0.0,
            value=cap_ref,
            step=1_000.0,
            format="%.0f",
            key="cfg_capital",
        )

    if st.button("💾 Guardar cambios", key="btn_guardar_perfil", type="primary"):
        try:
            actualizar_cliente(
                int(cid),
                nuevo_nombre.strip() or nombre_actual,
                nuevo_perfil,
                float(nuevo_capital),
                "Persona",
                nuevo_horizonte,
                tenant_id=str(ctx.get("tenant_id") or "default"),
            )
            st.session_state["cliente_nombre"] = nuevo_nombre.strip()
            st.session_state["cliente_perfil"] = nuevo_perfil
            st.session_state["cliente_horizonte_label"] = nuevo_horizonte
            st.session_state["horizonte_label"] = nuevo_horizonte
            st.session_state.pop("inv_diagnostico", None)
            st.success("✓ Perfil actualizado.")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")


def _render_inv_onboarding_hub() -> None:
    """Onboarding ligero (3 pasos). Tras verlo queda colapsado pero SIEMPRE
    accesible (antes se ocultaba para siempre — callejón sin salida)."""
    seen = bool(st.session_state.get("inv_hub_onboarding_done"))
    with st.expander("🧭 Tu recorrido sugerido (3 pasos)", expanded=not seen):
        for tit, txt in pasos_onboarding_hub():
            st.markdown(f"**{tit}** — {txt}")
        if not seen:
            if st.button("Listo, ya lo vi", key="inv_hub_onboarding_btn"):
                st.session_state["inv_hub_onboarding_done"] = True
                st.rerun()
        else:
            st.caption("Esta guía queda acá por si querés volver a verla.")


@st.cache_data(ttl=300, show_spinner=False)
def _estado_universo_inversor_cached() -> tuple[dict, pd.DataFrame]:
    from services.estado_universo_mq26 import (
        dataframe_estado_universo,
        resumen_estado_universo_mq26,
    )

    r = resumen_estado_universo_mq26(
        max_scan_cedears=80,
        max_scan_merval=40,
        max_scan_on=60,
        max_scan_bonos=30,
    )
    return r, dataframe_estado_universo(r)


def render_tab_inversor(ctx: dict) -> None:
    if st.session_state.pop("inv_degradado_ui", False):
        st.warning("Algunas funciones se ejecutaron en modo degradado. Revisá datos antes de confirmar operaciones.")
    # ── Selector de perfil — primera y única decisión del inversor ─────────────
    _render_selector_perfil_cards(ctx)
    st.divider()

    df_ag = ctx.get("df_ag")
    metricas = ctx.get("metricas") or {}
    ccl = float(ctx.get("ccl") or 1.0)

    if _inversor_sin_posiciones_cargadas(df_ag):
        _render_bienvenida_inversor(ctx)
        return

    diag = _get_diagnostico_cached(ctx)

    uxb = st.session_state.pop("inv_ux_before_load", None)
    if isinstance(uxb, dict) and "pct" in uxb:
        nuevo_pct = float(getattr(diag, "pct_defensivo_actual", 0.0) or 0.0) * 100.0
        st.success(antes_despues_defensivo(float(uxb["pct"]), nuevo_pct))

    pnl_ars_frac = float(metricas.get("pnl_pct_total", 0) or 0.0)
    pnl_papel_frac = float(metricas.get("pnl_pct_total_usd", 0) or 0.0)
    valor_total = float(metricas.get("total_valor", 0) or 0)
    valor_usd = valor_total / max(ccl, 1e-9)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)
    pct_def_frac = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
    pct_def_req_frac = float(getattr(diag, "pct_defensivo_requerido", 0) or 0) or 0.4

    hub = build_investor_hub_snapshot(diag, metricas, ccl, valor_total_ars=valor_total)

    _render_inv_onboarding_hub()

    st.markdown(
        '<h2 class="mq-inv-h2-hero mq-inv-h2-hero--compact">Mi cartera</h2>',
        unsafe_allow_html=True,
    )
    st.caption(patrimonio_dual_line(valor_usd, valor_total, ccl))

    # Ancla CSS (M484–M486): tabs internos estilo “capítulo” sin afectar otras vistas.
    st.markdown(
        '<div class="mq-inv-inner-tabs-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    tab_res, tab_rfv, tab_salud, tab_plan, tab_reb = st.tabs([
        "📋 Resumen",
        "📊 RF · RV",
        "❤️ Salud y alineación",
        "🎯 Plan y simulaciones",
        "⚖️ Rebalanceo y oportunidades",
    ])

    _def_ok = pct_def_frac >= pct_def_req_frac
    _rv_frac = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - pct_def_frac)) or 0.0)
    _def_label = (
        "✓ Renta fija en rango vs tu plan"
        if _def_ok
        else f"Falta renta fija ({pct_def_req_frac:.0%} sugerido para tu perfil)"
    )

    with tab_res:
        # Ancla M471–M473: primera fila de KPIs (grid + tabular nums vía CSS scoped).
        st.markdown(
            '<div class="mq-inv-resumen-kpi-hook" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Valor cartera", f"ARS {valor_total:,.0f}")
        m2.metric("Equivalente USD", f"USD {valor_usd:,.0f}")
        m3.metric(
            "P&L sobre costo (ARS)",
            f"{pnl_ars_frac * 100:+.1f}%",
            help="Ganancia o pérdida en pesos respecto del capital histórico cargado "
            "(en CEDEARs incluye el efecto del tipo de cambio implícito).",
        )
        m4.metric(
            "Rendimiento USD (%)",
            f"{pnl_papel_frac * 100:+.1f}%",
            help="Rendimiento sobre la base en USD × CCL vigente (costo del certificado) o, en locales, "
            "el costo en ARS comparable a esa pata dólar. Complementa el P&L en pesos histórico de la tarjeta anterior.",
        )
        st.caption(
            "Patrimonio en **ARS** y equivalente **USD**; P&L y rendimiento USD según costos "
            "y reglas del diagnóstico (ver ayuda en cada tarjeta)."
        )
        st.markdown(
            '<h4 class="mq-inv-resumen-positions-head">Tus posiciones</h4>',
            unsafe_allow_html=True,
        )
        _render_tabla_posiciones_resumen(ctx)

    # ── Tab RF · RV: paneles separados con KPIs distintos ─────────────────────
    with tab_rfv:
        st.caption(
            "Renta Fija y Renta Variable tienen KPIs distintos. "
            "El objetivo RF/RV está definido por tu perfil de riesgo."
        )
        with st.expander("Estado de situación — universo analizado", expanded=False):
            st.caption(
                "Cuántos instrumentos (CEDEARs, acciones, bonos, ON) analizó el "
                "motor en esta sesión para sugerirte. Un universo más grande da "
                "más opciones; no es algo que tengas que tocar."
            )
            try:
                _, df_est = _estado_universo_inversor_cached()
                st.dataframe(df_est, hide_index=True, use_container_width=True)
            except Exception as exc:
                st.warning(f"No se pudo cargar el resumen del universo: {exc}")
        _render_panel_rf_kpis(ctx, df_ag, ccl, diag)
        st.divider()
        _render_panel_rv_kpis(ctx, df_ag, metricas, ccl, diag)
        # Barra de alineación general
        st.divider()
        st.markdown(
            defensive_bar_html(pct_def_frac, pct_def_req_frac, _def_label),
            unsafe_allow_html=True,
        )
        from ui.monitor_on_usd import render_monitor_on_usd
        render_monitor_on_usd(expanded=False)

    with tab_salud:
        st.markdown(
            "<p class='mq-hub-lead'>Salud financiera</p>",
            unsafe_allow_html=True,
        )
        _score_hub = float(hub.get("alignment_score_pct") or 0.0)
        st.metric(
            "Salud de la cartera (puntaje único 0–100)",
            f"{_score_hub:.0f}",
            help=GLOSARIO_INVERSOR["salud_score"],
        )
        st.progress(min(1.0, max(0.0, _score_hub / 100.0)))
        st.caption(
            "Un solo número resume el diagnóstico; el semáforo y el texto de abajo amplían el mismo resultado."
        )
        h1, h2, h3 = st.columns([1.1, 1.1, 0.45])
        with h1:
            _sem = getattr(diag, "semaforo", None)
            sem_val = (
                str(getattr(_sem, "value", "")) if _sem is not None else ""
            ) or str(hub.get("semaforo") or "amarillo")
            st.markdown(
                semaforo_html(
                    valor=sem_val,
                    score=diag.score_total,
                    titulo=str(getattr(diag, "titulo_semaforo", "") or ""),
                ),
                unsafe_allow_html=True,
            )
            st.caption(GLOSARIO_INVERSOR["semaforo"])
        with h2:
            _tit_sem = str(getattr(diag, "titulo_semaforo", "") or "").strip()
            if _tit_sem:
                st.markdown(f"**{_tit_sem}**")
            st.caption(
                "Progreso visual alineado al mismo puntaje; no es un segundo score distinto."
            )
        with h3:
            if st.button("Actualizar", key="btn_refresh_diag_inversor", use_container_width=True):
                st.session_state.pop("inv_diagnostico", None)
                st.rerun()
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Renta fija en cartera",
            f"{pct_def_frac * 100:.1f}%",
            help="Porcentaje del patrimonio en renta fija (bonos, ON, letras).",
        )
        k2.metric(
            "Objetivo RF (perfil)",
            f"{pct_def_req_frac * 100:.1f}%",
            help="Renta fija objetivo según tu perfil de riesgo.",
        )
        k3.metric(
            "Renta variable",
            f"{_rv_frac * 100:.1f}%",
            help="Porcentaje del patrimonio en CEDEARs y acciones (precio fluctúa más).",
        )
        with st.expander("Glosario rápido", expanded=False):
            st.markdown(
                f"**Renta fija vs variable**  \n{GLOSARIO_INVERSOR['rf_rv']}\n\n"
                f"**CCL**  \n{GLOSARIO_INVERSOR['ccl']}\n\n"
                f"**Target y stop**  \n{GLOSARIO_INVERSOR['target_stop']}\n\n"
                f"**Rebalanceo**  \n{GLOSARIO_INVERSOR['rebalanceo']}"
            )
        st.markdown("##### Objetivos por activo (target RV · TIR renta fija)")
        _ref_df = _df_salud_referencias_posicion(ctx, df_ag)
        if not _ref_df.empty:
            st.dataframe(
                _ref_df,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(_ref_df, min_px=140, max_px=320),
            )
        st.caption(
            "**CEDEARs / acciones:** precio objetivo en ARS según el motor de salida (perfil y señales). "
            "**Renta fija:** TIR de referencia del catálogo MQ26 y vencimiento; no aplica un ‘target’ tipo acción."
        )
        st.markdown("##### ¿Cada activo está razonablemente alineado?")
        _al = _df_alineacion_activos(
            df_ag, diag, ctx.get("df_analisis"), ctx.get("universo_df"),
        )
        if not _al.empty:
            st.dataframe(
                _al,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(_al, min_px=160, max_px=360),
            )
        st.caption(
            "**RF/RV en columnas:** porcentajes del **total de la cartera** frente al **objetivo del perfil** (mismos valores en cada fila; sirve para leer cartera vs plan junto a cada activo). "
            "**Motor (score):** señal técnica 0–10 del análisis del universo (y **ESTADO** si viene cargado). "
            f"Ruleset del mix: **{getattr(diag, 'ruleset_version', '') or '—'}**. "
            "**Chequeo:** concentración fuerte en un ticker (según el diagnóstico). "
            "No reemplaza asesoramiento personalizado."
        )

        with st.expander("RF vs RV: comparativa con tu perfil", expanded=True):
            st.caption(
                "**Renta fija:** bonos, ONs, letras. **Renta variable:** CEDEARs y acciones. "
                f"RV ~{_rv_frac:.0%}. Reglas: **{getattr(diag, 'ruleset_version', '') or '—'}**."
            )
            st.markdown(
                defensive_bar_html(pct_def_frac, pct_def_req_frac, _def_label),
                unsafe_allow_html=True,
            )

        _res_ej = (hub.get("resumen_ejecutivo") or "").strip()
        if _res_ej:
            st.markdown("##### Qué resume el motor")
            st.markdown(
                f"<div style='font-size:0.9rem;color:var(--c-text-2);line-height:1.45;"
                f"margin-bottom:0.75rem;'>{html.escape(_res_ej[:1200])}"
                f"{'…' if len(_res_ej) > 1200 else ''}</div>",
                unsafe_allow_html=True,
            )

        with st.expander("Observaciones del diagnóstico", expanded=False):
            for o in getattr(diag, "observaciones", [])[:6]:
                prio = str(getattr(o.prioridad, "value",
                                  str(o.prioridad))).lower()
                st.markdown(
                    obs_card_html(
                        icono=o.icono,
                        titulo=o.titulo,
                        texto=o.texto_corto,
                        cifra=o.cifra_clave,
                        prioridad=_OBS_PRIO_MAP.get(prio, "media"),
                    ),
                    unsafe_allow_html=True,
                )

    with tab_plan:
        perfil_ui = perfil_diagnostico_valido(str(ctx.get("cliente_perfil", "Moderado")))
        ideal_d_base = CARTERA_IDEAL.get(perfil_ui, CARTERA_IDEAL["Moderado"])
        _mix_st = st.session_state.get("inv_mix_plan")
        ideal_dict, ideal_src = ideal_dict_desde_mix_plan(
            perfil_ui, ideal_d_base, _mix_st if isinstance(_mix_st, dict) else None
        )
        _d_plan_days = dias_desde_primera_compra(df_ag)
        _ccl_plan = float(ctx.get("ccl") or 1150.0)
        _tiene_pos = df_ag_tiene_posiciones_reales(df_ag)

        st.caption(
            "Proyecciones y benchmarks **ilustrativos**: no son promesa de resultado ni asesoramiento personalizado."
        )
        st.markdown(
            "<p style='font-size:0.85rem;color:var(--c-text-2);margin:0 0 0.75rem 0;'>"
            "En esta pestaña: <strong>prioridades</strong>, <strong>mix</strong> vs referencia, "
            "<strong>comparativas de rendimiento</strong> (con matices de período) y una "
            "<strong>proyección</strong> con escenarios.</p>",
            unsafe_allow_html=True,
        )
        with st.expander("Qué asumimos en los números de abajo", expanded=False):
            st.markdown(
                "- **Referencia ideal:** cartera modelo del perfil, o —si guardaste un armado— "
                "esa fracción de renta fija combinada con la RV del modelo.\n"
                "- **Tu cartera:** P&amp;L acumulado en USD de referencia usa la misma base que el diagnóstico "
                "(no es necesariamente año calendario).\n"
                "- **SPY / QQQ:** retorno **YTD calendario** USA desde yfinance (precios ajustados).\n"
                "- **Proyección:** escenarios fijos y opcional Montecarlo con historia SPY (semilla fija 42)."
            )

        st.markdown(
            "<p style='font-size:0.65rem;font-weight:600;color:var(--c-text-3);"
            "text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.35rem;'>Estado de datos</p>",
            unsafe_allow_html=True,
        )
        _ed1, _ed2, _ed3 = st.columns(3)
        _ed1.metric("CCL (referencia)", f"{_ccl_plan:,.2f}")
        _ed2.metric("Posiciones", str(int(hub.get("n_posiciones") or 0)))
        if _d_plan_days is not None:
            _ed3.metric("Días desde 1ª compra", str(int(_d_plan_days)))
        else:
            _ed3.metric("Días desde 1ª compra", "—")
        if not _tiene_pos:
            st.warning(
                "No hay pesos de cartera cargados o la cartera está vacía. Importá posiciones "
                "para ver el mix real y comparativas con sentido."
            )
            if st.button(
                "Abrir importación del broker",
                key="inv_plan_cta_import",
                use_container_width=True,
            ):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "importar"
                st.rerun()

        st.markdown(
            '<div class="mq-inv-plan-subtabs-anchor" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        plan_s1, plan_s2, plan_s3 = st.tabs(
            ["1 · Prioridades y mix", "2 · Rendimiento (orientativo)", "3 · Proyección y descarga"],
        )

        with plan_s1:
            st.markdown("##### Prioridades (primeras acciones)")
            for a in hub.get("acciones_top") or []:
                st.markdown(
                    f"**{a.get('titulo', '—')}** ({a.get('prioridad', '')}) — _{a.get('cifra', '')}_"
                )
            st.divider()
            st.markdown("##### Cartera ideal vs tu mix actual")
            _ideal_lbl = (
                "Incluye el **mix RF que guardaste** al armar en la app (resto según modelo del perfil)."
                if ideal_src == "armado_app"
                else f"Referencia **CARTERA_IDEAL** del perfil **{html.escape(perfil_ui)}**."
            )
            st.caption(_ideal_lbl)
            _cmp: list[dict] = []
            try:
                for k, v in (ideal_dict or {}).items():
                    ks = str(k).strip()
                    if not ks:
                        continue
                    if ks.startswith("_") and ks != "_RENTA_AR":
                        continue
                    lbl = "Renta fija AR (otros)" if ks == "_RENTA_AR" else ks
                    _cmp.append({"Bucket": lbl, "Peso objetivo %": round(float(v) * 100.0, 1)})
            except Exception:
                _cmp = []
            if _cmp:
                _df_cmp_responsive = pd.DataFrame(_cmp)
                st.dataframe(
                    _df_cmp_responsive,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(_df_cmp_responsive, min_px=120, max_px=260),
                )
            _c1, _c2 = st.columns(2)
            with _c1:
                cap_ideal = "**Ideal** (tu armado + modelo)" if ideal_src == "armado_app" else "**Ideal** del modelo (perfil)"
                st.caption(cap_ideal)
                fig_t_ideal = fig_torta_ideal(perfil_ui, ideal_dict or {})
                if fig_t_ideal:
                    st.plotly_chart(fig_t_ideal, use_container_width=True, key="inv_pie_ideal")
            with _c2:
                st.caption("**Tu mix** actual (pesos en cartera)")
                fig_t_actual = None
                if df_ag is not None and not df_ag.empty and "PESO_PCT" in df_ag.columns:
                    wmap: dict[str, float] = {}
                    for _, rw in df_ag.iterrows():
                        tk = _ticker_desde_fila_pos(rw)
                        if not tk:
                            continue
                        try:
                            w = float(rw.get("PESO_PCT", 0) or 0)
                        except (TypeError, ValueError):
                            w = 0.0
                        if w <= 0:
                            continue
                        wmap[tk] = wmap.get(tk, 0.0) + w
                    wmap = agrupar_pesos_torta(wmap, min_frac=0.03)
                    if wmap:
                        fig_t_actual = go.Figure(
                            data=[
                                go.Pie(
                                    labels=list(wmap.keys()),
                                    values=[max(0.0, v) for v in wmap.values()],
                                    hole=0.45,
                                    textinfo="label+percent",
                                    hoverinfo="label+percent",
                                    marker=dict(line=dict(color="rgba(15,23,42,0.35)", width=1)),
                                )
                            ]
                        )
                        fig_t_actual.update_layout(
                            **plotly_chart_layout_base(
                                title=dict(
                                    text=f"Tu cartera — {len(wmap)} segmento(s)",
                                    font=dict(size=14),
                                ),
                                margin=dict(t=40, b=10, l=10, r=10),
                                height=280,
                                showlegend=False,
                            ),
                        )
                if fig_t_actual:
                    st.plotly_chart(fig_t_actual, use_container_width=True, key="inv_pie_actual")
                else:
                    st.info("Sin posiciones para armar la torta de tu mix.")

            st.markdown("##### RF / RV: tu cartera vs referencia ideal")
            rf_i, rv_i = _ideal_rf_rv_fracciones(ideal_dict)
            rf_tu = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
            rv_tu = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - rf_tu)) or 0)
            _xl = ["Tu cartera", "Referencia ideal"]
            fig_stack = go.Figure(
                data=[
                    go.Bar(
                        name="Renta fija",
                        x=_xl,
                        y=[rf_tu * 100.0, rf_i * 100.0],
                        marker_color="#3b82f6",
                    ),
                    go.Bar(
                        name="Renta variable",
                        x=_xl,
                        y=[rv_tu * 100.0, rv_i * 100.0],
                        marker_color="#10b981",
                    ),
                ]
            )
            fig_stack.update_layout(
                **plotly_chart_layout_base(
                    barmode="stack",
                    height=320,
                    yaxis=dict(title="% del patrimonio", rangemode="tozero"),
                    xaxis=dict(title=""),
                    margin=dict(t=24, b=40, l=50, r=16),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                ),
            )
            st.plotly_chart(fig_stack, use_container_width=True, key="inv_bar_rf_rv")
            st.caption(
                "Referencia ideal: pesos anteriores (modelo o armado). "
                "Tu cartera: mix del diagnóstico. "
                "El detalle de alineación por activo está en **Salud y alineación**."
            )

        with plan_s2:
            st.markdown("##### Rendimiento: referencias orientativas")
            ytd_tu = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0)
            ytd_mod = float(RENDIMIENTO_MODELO_YTD_REF.get(perfil_ui, 0.0869)) * 100.0
            ytd_bench_diag = float(getattr(diag, "benchmark_ytd_pct", 0.0) or 0.0)
            ytd_spy = _benchmark_ytd_pct("SPY")
            ytd_qqq = _benchmark_ytd_pct("QQQ")
            _bench_rows: list[tuple[str, float, str]] = [
                ("Tu cartera — acumulado ref. USD", ytd_tu, "desde primera compra (diagnóstico); no es YTD calendario."),
                ("Objetivo rendimiento motor (prorrateado)", ytd_bench_diag, "benchmark interno del diagnóstico; coherente con observaciones."),
                ("Referencia estática perfil MQ26", ytd_mod, "número de estilo; no es un fondo cotizable."),
            ]
            if ytd_spy is not None:
                _bench_rows.append(("SPY (USA, YTD calendario)", ytd_spy, "yfinance, precios ajustados."))
            if ytd_qqq is not None:
                _bench_rows.append(("QQQ (USA, YTD calendario)", ytd_qqq, "yfinance, precios ajustados."))
            _bx = [a for a, _, _ in _bench_rows]
            _by = [b for _, b, _ in _bench_rows]
            _colors = ["#6366f1", "#94a3b8", "#f59e0b", "#22c55e", "#0ea5e9", "#a78bfa"]
            fig_ytd = go.Figure(
                data=[
                    go.Bar(
                        x=_bx,
                        y=_by,
                        marker_color=_colors[: len(_bx)],
                        text=[f"{v:+.1f}%" for v in _by],
                        textposition="outside",
                    )
                ]
            )
            _perd_txt = (
                f"Desde la **primera fecha de compra** registrada: **{_d_plan_days}** días (~{(_d_plan_days or 0) / 365.25:.2f} años)."
                if _d_plan_days is not None
                else "Sin fechas de compra: el % de tu cartera sigue al diagnóstico, pero no mostramos un largo de período."
            )
            fig_ytd.update_layout(
                **plotly_chart_layout_base(
                    height=360,
                    yaxis=dict(title="Porcentaje (%)"),
                    xaxis=dict(tickangle=-22),
                    margin=dict(t=40, b=120, l=50, r=24),
                    annotations=[
                        dict(
                            text=_perd_txt[:220],
                            xref="paper",
                            yref="paper",
                            x=0,
                            y=-0.42,
                            showarrow=False,
                            xanchor="left",
                            font=dict(size=11, color="rgb(148, 163, 184)"),
                        ),
                    ],
                ),
            )
            st.plotly_chart(fig_ytd, use_container_width=True, key="inv_bar_ytd_bench")
            st.caption(
                "Las barras **no comparten el mismo período**: tu cartera y el objetivo del motor usan tu historial; "
                "SPY/QQQ usan **año calendario** en USA. No las interpretés como ranking de fondos."
            )
            try:
                _df_bench = pd.DataFrame(
                    [{"Serie": a, "%": round(b, 2), "Nota": c} for a, b, c in _bench_rows]
                )
                st.dataframe(
                    _df_bench,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(_df_bench, min_px=120, max_px=260),
                )
            except Exception:
                pass

        with plan_s3:
            _render_proyeccion_y_pie_inversor(ctx, diag, metricas, hub)

        st.caption(
            "Para **RF vs objetivo por activo**, abrí la pestaña **Salud y alineación**."
        )

    with tab_reb:
        st.markdown(copy_rebalanceo_humano())
        _render_bloque_plata_nueva(ctx, df_ag, diag, ccl)
        st.markdown("##### Objetivos por posición (target / stop / señal)")
        _render_posiciones_con_targets(ctx, diag)

        _ccl_v = float(ctx.get("ccl") or 1150.0)
        with st.expander("💵 Efectivo para sumar al patrimonio", expanded=False):
            _cc1, _cc2 = st.columns(2)
            _cash_ars = _cc1.number_input(
                "En ARS",
                min_value=0.0, value=0.0, step=10_000.0, format="%.0f",
                key="inv_cash_ars",
            )
            _cash_usd = _cc2.number_input(
                "En USD",
                min_value=0.0, value=0.0, step=100.0, format="%.0f",
                key="inv_cash_usd",
            )
            _cash_total_usd = _cash_ars / max(_ccl_v, 1.0) + _cash_usd
            if _cash_total_usd > 0:
                _val_cartera_usd = float(getattr(diag, "valor_cartera_usd", 0) or 0)
                _total_patrimon = _val_cartera_usd + _cash_total_usd
                _val_cartera_ars = _val_cartera_usd * _ccl_v
                _efectivo_ars = float(_cash_ars) + float(_cash_usd) * _ccl_v
                _total_ars = _val_cartera_ars + _efectivo_ars
                st.markdown(
                    f"<div style='background:var(--c-surface-2);border:1px solid "
                    f"var(--c-border);border-radius:8px;padding:0.7rem 1rem;"
                    f"margin-top:0.4rem;'>"
                    f"<div style='font-size:0.65rem;color:var(--c-text-3);"
                    f"text-transform:uppercase;letter-spacing:0.06em;"
                    f"margin-bottom:3px;'>Patrimonio total (pesos)</div>"
                    f"<div style='font-family:var(--font-mono),monospace;font-size:1.25rem;"
                    f"font-weight:500;color:var(--c-text);'>"
                    f"ARS {_total_ars:,.0f}</div>"
                    f"<div style='font-size:0.7rem;color:var(--c-text-3);margin-top:2px;'>"
                    f"Cartera ~ ARS {_val_cartera_ars:,.0f} · "
                    f"Efectivo ~ ARS {_efectivo_ars:,.0f} · "
                    f"ref. USD {_total_patrimon:,.0f}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("### Agregar o importar")
        st.session_state.setdefault("inv_carga_open", False)
        if st.button(
            "📝 Registrar venta",
            key="inv_open_venta_manual",
            use_container_width=True,
            help="Abre el asistente para registrar una venta manualmente o importar el extracto del broker.",
        ):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "venta"
            st.rerun()
        st.caption("Para vaciar toda la cartera y empezar de cero, usá el panel **🧹 Vaciar cartera** en la columna izquierda.")
        st.checkbox(
            "Mostrar asistente para sumar compras o importar archivo del broker",
            key="inv_carga_open",
        )
        if st.session_state.get("inv_carga_open"):
            _fn = ctx.get("render_carga_activos_fn")
            if _fn is None:
                from ui.carga_activos import render_carga_activos as _fn
            _fn(ctx)
