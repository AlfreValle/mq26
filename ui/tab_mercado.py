"""
ui/tab_mercado.py — Tab Mercado: señales + oportunidades en tiempo real.

3 sub-páginas:
  A) Renta Variable — CEDEARs y Acciones por separado con señal MOD-23 + target
  B) Renta Fija     — ONs (TIR), Bonos (TIR), Letras (tasa mensual)
  C) Cartera Óptima — Optimizador por perfil, siempre actualizado con precios BYMA

Precio siempre de BYMA Open Data. Sin hardcoding.
"""
from __future__ import annotations

import streamlit as st
from typing import Any
from core.structured_logging import log_degradacion
from services.byma_watchdog import check_byma_status

_LOG_NAME = "ui.tab_mercado"


def _get_ccl(ctx: dict) -> float:
    """CCL del contexto, con fallback seguro."""
    try:
        ccl = float(ctx.get("ccl") or 0)
        return ccl if ccl > 0 else 1400.0
    except Exception:
        return 1400.0


def _get_perfil(ctx: dict) -> str:
    return str(ctx.get("cliente_perfil") or "Moderado").strip()


def _check_byma_connection() -> dict[str, Any]:
    status = check_byma_status()
    if not status.get("ok"):
        st.warning(
            f"⚠️ {status.get('mensaje', 'BYMA Open Data no responde')}",
            icon="📡",
        )
    elif status.get("latencia_ms") and float(status["latencia_ms"]) > 3000.0:
        st.info(
            f"BYMA responde lento ({status['latencia_ms']:.0f} ms). Los datos pueden demorar.",
            icon="🐢",
        )
    return status


# ── SUB-PÁGINA A: RENTA VARIABLE ──────────────────────────────────────────────

def _render_rv(ctx: dict) -> None:
    """CEDEARs y Acciones locales con señal MOD-23, score y precio target."""
    import pandas as pd
    from services.byma_universo import universo_rv_con_señales

    ccl    = _get_ccl(ctx)
    perfil = _get_perfil(ctx)
    _check_byma_connection()

    st.markdown(
        f"Señales MOD-23 sobre el universo BYMA completo · perfil **{perfil}** · "
        f"CCL ${ccl:,.0f} · precio siempre de BYMA Open Data",
    )

    if st.button("🔄 Actualizar precios y señales", key="mkt_rv_refresh"):
        st.cache_data.clear()

    with st.spinner("Consultando BYMA y calculando señales..."):
        try:
            df = universo_rv_con_señales(ccl=ccl, perfil=perfil, n_max=120)
        except Exception as _e:
            log_degradacion(_LOG_NAME, "rv_universo_error", _e)
            st.error("No se pudo obtener el universo de BYMA. Intentá en unos minutos.")
            return

    if df.empty:
        st.warning("Sin datos de mercado en este momento.")
        return

    # Split CEDEARs vs Acciones
    tab_ced, tab_acc = st.tabs(["🌎 CEDEARs", "🇦🇷 Acciones argentinas"])

    def _render_rv_tabla(df_filt: "pd.DataFrame", key_prefix: str) -> None:
        if df_filt.empty:
            st.info("Sin instrumentos de este tipo con datos en este momento.")
            return

        # Filtro de señal
        señales_disp = sorted(df_filt["Señal"].unique())
        sel = st.multiselect(
            "Filtrar señal",
            options=señales_disp,
            default=señales_disp,
            key=f"{key_prefix}_filtro_senal",
        )
        df_v = df_filt[df_filt["Señal"].isin(sel)] if sel else df_filt

        # Columnas a mostrar
        cols_show = [
            "Ticker", "Descripción", "Precio ARS", "Var. %",
            "Score", "Señal", "Target ARS", "Stop ARS",
        ]
        cols_show = [c for c in cols_show if c in df_v.columns]

        def _color_senal(val: str) -> str:
            v = str(val).upper()
            if "COMPRAR"  in v: return "color:var(--c-green);font-weight:bold"
            if "ACUMULAR" in v: return "color:var(--c-green)"
            if "REDUCIR"  in v: return "color:var(--c-yellow)"
            if "SALIR"    in v: return "color:var(--c-red);font-weight:bold"
            return ""

        styler = df_v[cols_show].style
        if "Señal"   in cols_show: styler = styler.map(_color_senal, subset=["Señal"])
        if "Var. %"  in cols_show:
            styler = styler.map(
                lambda v: "color:var(--c-green)" if (v or 0) > 0 else
                          "color:var(--c-red)"   if (v or 0) < 0 else "",
                subset=["Var. %"],
            )

        st.dataframe(styler, use_container_width=True, hide_index=True, height=520)
        st.caption(
            f"{len(df_v)} instrumentos · Target y Stop calculados por motor_salida "
            f"según perfil {perfil} · precio de entrada = último precio BYMA"
        )

        # Leyenda señales
        with st.expander("📖 Qué significa cada señal", expanded=False):
            st.markdown(
                "| Señal | Score | Qué hacer |\n"
                "|-------|-------|-----------|\n"
                "| 🟢 COMPRAR  | ≥ 75 | Señal técnica fuerte + fundamental sólido |\n"
                "| 🟡 ACUMULAR | 60–74 | Señal positiva — sumar gradualmente |\n"
                "| ⚪ MANTENER | 45–59 | Neutro — conservar posición |\n"
                "| 🟠 REDUCIR  | 30–44 | Señal negativa — empezar a salir |\n"
                "| 🔴 SALIR    | < 30 | Señal de venta — stop activo |"
            )

    with tab_ced:
        _render_rv_tabla(df[df["Tipo"] == "CEDEAR"], "ced")

    with tab_acc:
        _render_rv_tabla(df[df["Tipo"] == "ACCION_LOCAL"], "acc")


# ── SUB-PÁGINA B: RENTA FIJA ──────────────────────────────────────────────────

def _render_rf(ctx: dict) -> None:
    """ONs (TIR), Bonos soberanos (TIR), Letras (tasa mensual)."""
    import pandas as pd
    from services.byma_universo import fetch_rf_completo

    ccl = _get_ccl(ctx)
    _check_byma_connection()

    st.markdown(
        "Instrumentos de renta fija desde BYMA Open Data · "
        "TIR de ONs y Bonos · Tasa mensual de Letras"
    )

    if st.button("🔄 Actualizar", key="mkt_rf_refresh"):
        st.cache_data.clear()

    with st.spinner("Consultando BYMA renta fija..."):
        try:
            rf = fetch_rf_completo(ccl=ccl)
        except Exception as _e:
            log_degradacion(_LOG_NAME, "rf_fetch_error", _e)
            st.error("No se pudieron obtener datos de renta fija de BYMA.")
            return

    tab_on, tab_bonos, tab_letras = st.tabs([
        "🏢 ONs corporativas",
        "🇦🇷 Bonos soberanos",
        "📄 Letras",
    ])

    # ── ONs ──
    with tab_on:
        st.caption(
            "Obligaciones Negociables · precio en ARS (normalizado ÷100 desde BYMA) · "
            "TIR de referencia desde catálogo MQ26 · denominación USD"
        )
        df_on = rf.get("on", pd.DataFrame())
        if df_on.empty:
            st.warning("Sin datos de ONs en este momento.")
        else:
            cols = [c for c in [
                "Ticker", "Descripción", "Emisor", "Último ARS",
                "Var. %", "TIR ref. %", "Paridad %", "Vencimiento",
            ] if c in df_on.columns]
            st.dataframe(
                df_on[cols].style.format(
                    {"TIR ref. %": "{:.2f}%", "Paridad %": "{:.1f}%",
                     "Último ARS": "${:,.2f}"}
                ),
                use_container_width=True, hide_index=True, height=420,
            )
            st.caption(
                "⚠️ TIR de referencia estimada — no es rendimiento garantizado. "
                "Para decisiones de inversión consultar prospecto del emisor."
            )

    # ── Bonos ──
    with tab_bonos:
        st.caption(
            "Bonos soberanos argentinos · precio en ARS desde BYMA · "
            "TIR de referencia cuando disponible en catálogo"
        )
        df_b = rf.get("bonos", pd.DataFrame())
        if df_b.empty:
            st.warning("Sin datos de bonos soberanos en este momento.")
        else:
            cols = [c for c in [
                "Ticker", "Descripción", "Último", "Cierre ant.",
                "Var. %", "TIR ref. %", "Vol. Nominal",
            ] if c in df_b.columns]
            st.dataframe(
                df_b[cols],
                use_container_width=True, hide_index=True, height=420,
            )
            st.caption(
                "⚠️ TIR de referencia orientativa — precio BYMA puede diferir del "
                "valor técnico según condiciones de mercado."
            )

    # ── Letras ──
    with tab_letras:
        st.caption(
            "LECAP, LETES, LECER y similares · "
            "Tasa mensual efectiva estimada desde precio de mercado BYMA"
        )
        df_l = rf.get("letras", pd.DataFrame())
        if df_l.empty:
            st.warning("Sin datos de letras en este momento.")
        else:
            cols = [c for c in [
                "Ticker", "Descripción", "Último", "Cierre ant.",
                "Var. %", "Tasa mensual %", "Vol. Nominal",
            ] if c in df_l.columns]
            st.dataframe(
                df_l[cols],
                use_container_width=True, hide_index=True, height=420,
            )
            with st.expander("📖 Cómo se calcula la tasa mensual", expanded=False):
                st.markdown(
                    "**Fórmula:** TEM = (100 / Precio_BYMA − 1) × 100\n\n"
                    "Es una estimación del rendimiento al período según el precio "
                    "de mercado en tiempo real. Para períodos exactos se necesita "
                    "la fecha de vencimiento de cada letra — ver prospecto CNV."
                )


# ── SUB-PÁGINA C: CARTERA ÓPTIMA ──────────────────────────────────────────────

def _render_cartera_optima(ctx: dict) -> None:
    """Cartera óptima según perfil, siempre actualizada con precios BYMA."""
    import pandas as pd
    from services.byma_universo import universo_rv_con_señales, fetch_rf_completo
    from core.perfil_allocation import get_mix_rf_rv

    ccl    = _get_ccl(ctx)
    perfil = _get_perfil(ctx)
    _check_byma_connection()

    st.markdown(
        f"**¿En qué invertir ahora?** Cartera sugerida según perfil **{perfil}** "
        f"con precios BYMA en tiempo real"
    )

    # Editar perfil si el usuario quiere simular otro
    perfil_sim = st.selectbox(
        "Simular con perfil:",
        ["Conservador", "Moderado", "Agresivo"],
        index=["Conservador", "Moderado", "Agresivo"].index(
            perfil if perfil in ["Conservador", "Moderado", "Agresivo"] else "Moderado"
        ),
        key="mkt_opt_perfil",
    )

    if st.button("🔄 Calcular cartera óptima", key="mkt_opt_calc", type="primary"):
        st.cache_data.clear()

    # Mix RF/RV según perfil
    try:
        mix = get_mix_rf_rv(perfil_sim)
        pct_rf = mix.get("rf_pct", 40.0)
        pct_rv = mix.get("rv_pct", 60.0)
    except Exception:
        # Defaults razonables si el módulo no existe aún
        _defaults = {"Conservador": (60, 40), "Moderado": (40, 60), "Agresivo": (20, 80)}
        pct_rf, pct_rv = _defaults.get(perfil_sim, (40, 60))

    col_rf, col_rv = st.columns(2)
    col_rf.metric("Renta Fija target", f"{pct_rf:.0f}%",
                  help=f"Porcentaje sugerido para perfil {perfil_sim}")
    col_rv.metric("Renta Variable target", f"{pct_rv:.0f}%",
                  help="CEDEARs + Acciones locales")

    st.divider()

    # Top oportunidades RV (señales COMPRAR + ACUMULAR)
    st.markdown("#### 🟢 Mejores oportunidades de compra (Renta Variable)")
    with st.spinner("Calculando señales..."):
        try:
            df_rv = universo_rv_con_señales(ccl=ccl, perfil=perfil_sim, n_max=80)
        except Exception as _e:
            log_degradacion(_LOG_NAME, "cartera_optima_rv_error", _e)
            df_rv = pd.DataFrame()

    if not df_rv.empty:
        df_compras = df_rv[
            df_rv["Señal"].str.upper().str.contains("COMPRAR|ACUMULAR", na=False)
        ].head(10)
        if not df_compras.empty:
            cols = [c for c in [
                "Ticker", "Tipo", "Precio ARS", "Score", "Señal", "Target ARS"
            ] if c in df_compras.columns]
            st.dataframe(df_compras[cols], use_container_width=True,
                         hide_index=True, height=300)
        else:
            st.info("En este momento no hay señales de COMPRAR o ACUMULAR en RV.")
    else:
        st.warning("Sin datos de renta variable disponibles.")

    st.divider()

    # ONs sugeridas (TIR más alta disponible)
    st.markdown("#### 🏢 ONs sugeridas (mayor TIR de referencia)")
    with st.spinner("Consultando ONs..."):
        try:
            rf = fetch_rf_completo(ccl=ccl)
            df_on = rf.get("on", pd.DataFrame())
        except Exception as _e:
            log_degradacion(_LOG_NAME, "cartera_optima_rf_error", _e)
            df_on = pd.DataFrame()

    if not df_on.empty and "TIR ref. %" in df_on.columns:
        df_top_on = df_on.dropna(subset=["TIR ref. %"]) \
                         .sort_values("TIR ref. %", ascending=False).head(5)
        cols = [c for c in ["Ticker", "Emisor", "Último ARS", "TIR ref. %",
                             "Paridad %", "Vencimiento"] if c in df_top_on.columns]
        st.dataframe(df_top_on[cols], use_container_width=True,
                     hide_index=True, height=220)
    else:
        st.info("Sin datos de ONs disponibles.")

    st.divider()
    st.caption(
        "⚠️ Esta cartera es una sugerencia algorítmica basada en señales técnicas "
        "y fundamentales. No es asesoramiento de inversión. "
        "Consultá con tu asesor antes de operar."
    )


# ── ORQUESTADOR PRINCIPAL ─────────────────────────────────────────────────────

def render_tab_mercado(ctx: dict) -> None:
    """
    Tab Mercado — 3 sub-páginas: RV / RF / Cartera óptima.
    Precio siempre de BYMA. Señales del motor MOD-23.
    """
    pag_rv, pag_rf, pag_opt = st.tabs([
        "📈 Renta Variable",
        "💰 Renta Fija",
        "🎯 Cartera Óptima",
    ])

    with pag_rv:
        _render_rv(ctx)

    with pag_rf:
        _render_rf(ctx)

    with pag_opt:
        _render_cartera_optima(ctx)
