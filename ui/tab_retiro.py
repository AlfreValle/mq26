"""
tab_retiro.py — Módulo de Planificación de Retiro MQ26.

Fusiona la calculadora BDI (3 modos: Clásica / Metas / Monte Carlo) con los
datos REALES de la cartera activa:
  · Capital inicial ← valor USD actual del portfolio
  · Retorno base    ← CAGR histórico calculado por cartera_service
  · Monte Carlo     ← bootstrap sobre retornos diarios reales de la cartera

Ventaja sobre la calculadora BDI standalone: los supuestos de retorno y
volatilidad se derivan del portfolio real, no de sliders genéricos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.structured_logging import log_degradacion
from services.retiro_proyeccion import (
    ProyeccionClasica,
    ResultadoMonteCarlo,
    inputs_desde_cartera,
    montecarlo_retiro,
    proyeccion_clasica,
    resultado_metas,
)
from ui.mq26_ux import chart_description_html, error_message_html

# ── Colores alineados con el design system MQ26 ───────────────────────────────
_VERDE   = "#22c55e"
_CYAN    = "#17BEBB"
_LIMA    = "#84cc16"
_NARANJA = "#f59e0b"
_ROJO    = "#ef4444"
_GRIS    = "#94a3b8"
_BG      = "rgba(30,41,59,0.6)"

# ── Helpers de formato ────────────────────────────────────────────────────────

def _usd(v: float, decimals: int = 0) -> str:
    fmt = f":,.{decimals}f"
    return f"${v:{fmt[1:]}}"


def _pct(v: float, decimals: int = 1) -> str:
    return f"{v:.{decimals}f}%"


def _kpi(col, label: str, valor: str, delta: str = "", color: str = _VERDE) -> None:
    # #83 mq-kpi-label + #82 mq-mono aplicados via CSS global
    col.markdown(
        f"""
<div class="mq-card-interactive" style="background:{_BG};padding:1rem;text-align:center;min-height:88px;">
    <div class="mq-kpi-label" style="margin-bottom:4px;">{label}</div>
    <div class="mq-mono" style="font-size:1.35rem;font-weight:700;color:{color};">
        {valor}
    </div>
    {"" if not delta else f'<div style="font-size:0.72rem;color:{_GRIS};margin-top:3px;">{delta}</div>'}
</div>""",
        unsafe_allow_html=True,
    )


# ── Gráficos ──────────────────────────────────────────────────────────────────

def _chart_clasica(clasica: ProyeccionClasica, capital_ini: float) -> go.Figure:
    """Stacked bar: composición del capital por año."""
    df = clasica.df_anual
    fig = go.Figure()
    fig.add_bar(
        x=df["anio"], y=[capital_ini] * len(df),
        name="Capital inicial", marker_color=_VERDE, opacity=0.85,
    )
    aportes_sin_ini = df["aportes_acum"] - capital_ini - df["anio"].apply(lambda a: 0)
    # aportes acumulados excluyendo capital_ini
    aportes_puros = df["aportes_acum"] - capital_ini
    fig.add_bar(
        x=df["anio"], y=aportes_puros,
        name="Aportes mensuales", marker_color=_CYAN, opacity=0.85,
    )
    fig.add_bar(
        x=df["anio"], y=df["intereses_acum"],
        name="Intereses (compuesto)", marker_color=_LIMA, opacity=0.9,
    )
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Año", gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title="USD", gridcolor="rgba(255,255,255,0.07)", tickprefix="$",
                   tickformat=",.0f"),
        margin=dict(l=10, r=10, t=30, b=10),
        height=340,
    )
    return fig


def _chart_pie(clasica: ProyeccionClasica, capital_ini: float) -> go.Figure:
    """Pie de composición del capital final."""
    aportes_puros = clasica.aportes_totales - capital_ini
    labels = ["Capital inicial", "Aportes mensuales", "Intereses proyectados"]
    values = [capital_ini, aportes_puros, clasica.intereses_ganados]
    colors = [_VERDE, _CYAN, _LIMA]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors),
        hole=0.45,
        textinfo="label+percent",
        textfont=dict(size=11),
        hovertemplate="%{label}<br>%{value:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=260,
    )
    return fig


def _chart_gauge(pct: float) -> go.Figure:
    """Gauge de cobertura de meta."""
    color = _VERDE if pct >= 100 else (_CYAN if pct >= 70 else _NARANJA)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=min(pct, 100),
        number=dict(suffix="%", font=dict(size=28, color=color)),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor=_GRIS),
            bar=dict(color=color, thickness=0.25),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0, 70],  color="rgba(239,68,68,0.15)"),
                dict(range=[70, 100], color="rgba(23,190,187,0.15)"),
            ],
            threshold=dict(
                line=dict(color=_VERDE, width=3),
                thickness=0.75,
                value=100,
            ),
        ),
        domain=dict(x=[0, 1], y=[0, 1]),
    ))
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0"),
        height=220,
        margin=dict(l=20, r=20, t=20, b=0),
    )
    return fig


def _chart_montecarlo(mc: ResultadoMonteCarlo, meta_capital: float, anios: int) -> go.Figure:
    """Gráfico de trayectorias + banda P10-P90."""
    df_b = mc.df_bandas
    fig = go.Figure()

    # Banda P10-P90
    fig.add_trace(go.Scatter(
        x=list(df_b["anio"]) + list(df_b["anio"])[::-1],
        y=list(df_b["p90"]) + list(df_b["p10"])[::-1],
        fill="toself",
        fillcolor="rgba(132,204,22,0.12)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Banda P10–P90",
        hoverinfo="skip",
    ))

    # Líneas de escenarios
    for label, valores, color, dash, ancho in [
        ("Pesimista", list(df_b["p10"]), _GRIS, "dash", 1.5),
        ("Base (retorno fijo)", list(df_b["p50"]), _VERDE, "solid", 2.5),
        ("Optimista", list(df_b["p90"]), _CYAN, "solid", 1.5),
    ]:
        fig.add_trace(go.Scatter(
            x=list(df_b["anio"]),
            y=valores,
            name=label,
            line=dict(color=color, dash=dash, width=ancho),
            hovertemplate=f"{label}<br>Año %{{x}}: %{{y:$,.0f}}<extra></extra>",
        ))

    # Línea de meta
    if meta_capital > 0:
        fig.add_hline(
            y=meta_capital,
            line_dash="dot",
            line_color=_NARANJA,
            annotation_text=f"Meta {_usd(meta_capital)}",
            annotation_position="top right",
            annotation_font=dict(color=_NARANJA, size=11),
        )

    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(title="Año", gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title="USD", gridcolor="rgba(255,255,255,0.07)",
                   tickprefix="$", tickformat=",.0f"),
        margin=dict(l=10, r=10, t=30, b=10),
        height=380,
    )
    return fig


# ── RENDER PRINCIPAL ──────────────────────────────────────────────────────────

def _calcular_retornos_portfolio(ctx: dict) -> np.ndarray | None:
    """
    Calcula retornos diarios del portfolio usando historia real de yfinance.
    Ponderado por PESO_PCT de cada ticker en df_ag.
    Resultado cacheado en session_state para evitar re-descargas en el mismo run.
    """
    cache_key = f"_ret_retiro_{ctx.get('cartera_activa', '')}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    df_ag = ctx.get("df_ag")
    cached_historico = ctx.get("cached_historico")
    if df_ag is None or df_ag.empty or cached_historico is None:
        return None
    if "TICKER" not in df_ag.columns or "PESO_PCT" not in df_ag.columns:
        return None

    tickers = df_ag["TICKER"].dropna().unique().tolist()
    pesos = df_ag.groupby("TICKER")["PESO_PCT"].sum() / 100.0

    try:
        hist = cached_historico(tuple(tickers), "2y")
    except Exception:
        return None

    if hist is None or hist.empty:
        return None

    # Normalizar columnas — puede venir MultiIndex o flat
    try:
        if isinstance(hist.columns, pd.MultiIndex):
            close = hist["Close"] if "Close" in hist.columns.get_level_values(0) else hist.iloc[:, 0:len(tickers)]
        else:
            close = hist[["Close"]] if "Close" in hist.columns else hist
    except Exception:
        return None

    # Retornos diarios ponderados
    try:
        ret = close.pct_change().dropna()
        # Alinear pesos con columnas disponibles
        cols_disp = [c for c in ret.columns if c in pesos.index]
        if not cols_disp:
            return None
        w = pesos[cols_disp]
        w = w / w.sum()  # renormalizar
        ret_portfolio = (ret[cols_disp] * w.values).sum(axis=1).dropna().values
    except Exception:
        return None

    result = np.asarray(ret_portfolio, dtype=float)
    st.session_state[cache_key] = result
    return result if len(result) >= 42 else None


def render_tab_retiro(ctx: dict) -> None:
    """
    Punto de entrada del módulo de retiro.
    ctx debe incluir todos los campos del ctx global de MQ26.
    Los retornos diarios del portfolio se calculan lazily desde historia real.
    """
    # #93 Error boundary a nivel de tab
    try:
        _render_tab_retiro_inner(ctx)
    except Exception as _e_top:
        log_degradacion("ui.tab_retiro", "render_tab_retiro_fallo", _e_top)
        st.markdown(
            error_message_html(
                "Error al cargar Planificador de Retiro",
                "No se pudo calcular la proyección patrimonial.",
                cta="Verificá que la cartera tenga datos y recargá (F5).",
            ),
            unsafe_allow_html=True,
        )
        with st.expander("🔍 Detalles técnicos", expanded=False):
            st.code(str(_e_top)[:1500], language="text")


def _render_tab_retiro_inner(ctx: dict) -> None:
    """Implementación interna del planificador de retiro."""
    metricas: dict        = ctx.get("metricas") or {}
    # Intentar obtener retornos reales del portfolio (lazy, cacheado)
    r_diarios: np.ndarray | None = _calcular_retornos_portfolio(ctx)
    cliente_nombre: str   = ctx.get("cliente_nombre", "")
    cliente_perfil: str   = ctx.get("cliente_perfil", "Moderado")

    # ── Inputs desde la cartera real ─────────────────────────────────────────
    ccl = float(ctx.get("ccl") or 0.0)
    df_ag_ctx = ctx.get("df_ag")
    inp_cartera = inputs_desde_cartera(
        metricas,
        ccl=ccl,
        df_ag=df_ag_ctx if isinstance(df_ag_ctx, pd.DataFrame) else None,
    )
    cap_ini_cartera = inp_cartera["capital_inicial"]
    ret_cartera     = inp_cartera["retorno_anual"]
    sig_cartera     = inp_cartera["sigma_anual"]
    ret_fuente      = str(inp_cartera.get("retorno_fuente") or "")
    tiene_cartera   = cap_ini_cartera > 0

    # ── Header ───────────────────────────────────────────────────────────────
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,rgba(34,197,94,0.12),rgba(23,190,187,0.08));
            border:1px solid rgba(34,197,94,0.25);border-radius:14px;
            padding:1.2rem 1.5rem;margin-bottom:1.2rem;">
    <div style="font-size:0.65rem;color:{_GRIS};text-transform:uppercase;
                letter-spacing:0.1em;">Planificación de Retiro</div>
    <div style="font-size:1.5rem;font-weight:700;color:#f1f5f9;margin:4px 0;">
        {'🏦 ' + cliente_nombre if cliente_nombre else '📈 Planificador de Retiro'}
    </div>
    <div style="font-size:0.8rem;color:{_GRIS};">
        {'Capital inicial pre-llenado desde la cartera activa · ' if tiene_cartera else ''}
        Monte Carlo con retornos {f'<b style="color:{_VERDE}">reales</b> del portfolio' if r_diarios is not None and len(r_diarios) > 21 else 'sintéticos (cargá datos históricos para mayor precisión)'}
    </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Inputs compartidos (panel lateral dentro del tab) ────────────────────
    with st.expander("⚙️ Parámetros base", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            capital_ini_label = (
                f"Capital inicial (USD)\n*Cartera actual: {_usd(cap_ini_cartera)}*"
                if tiene_cartera else "Capital inicial (USD)"
            )
            capital_inicial = st.number_input(
                "Capital inicial (USD)",
                min_value=0.0,
                value=float(round(cap_ini_cartera, -2)) if cap_ini_cartera > 0 else 5_000.0,
                step=1_000.0,
                format="%.0f",
                help=f"Cartera activa: {_usd(cap_ini_cartera)}" if tiene_cartera else "Ingresá tu capital de partida.",
                key="ret_capital_ini",
            )
            if tiene_cartera and abs(capital_inicial - cap_ini_cartera) > 100:
                st.caption(f"📌 Cartera actual: {_usd(cap_ini_cartera)}")
        with col2:
            aporte_mensual = st.number_input(
                "Aporte mensual (USD)",
                min_value=0.0,
                value=200.0,
                step=50.0,
                format="%.0f",
                key="ret_aporte",
            )
        with col3:
            anios = st.slider(
                "Plazo (años)",
                min_value=1, max_value=50, value=25,
                key="ret_anios",
            )
        with col4:
            ret_pct_default = round(ret_cartera * 100, 1) if ret_cartera > 0 else 8.0
            _es_cagr = ret_fuente == "cagr"
            retorno_pct = st.slider(
                "Retorno anual (%)",
                min_value=1.0, max_value=25.0,
                value=float(min(max(ret_pct_default, 1.0), 25.0)),
                step=0.5,
                help=(
                    f"CAGR de la cartera: {_pct(ret_cartera*100)}"
                    if _es_cagr
                    else "No hay antigüedad confiable: se usa 8% anual (no el P&L acumulado)."
                    if ret_fuente == "default_sin_tenencia"
                    else "Estimado histórico del portfolio."
                ),
                key="ret_retorno_pct",
            )
            if _es_cagr:
                st.caption(f"📌 CAGR portfolio: **{_pct(ret_cartera*100)}**")
            elif ret_fuente == "default_sin_tenencia":
                st.caption(
                    f"📌 Sin fecha de alta confiable: **{_pct(ret_cartera*100)} anual por defecto** "
                    "(no se usa el P&L acumulado como si fuera retorno anual)."
                )
        retorno_anual = retorno_pct / 100.0

    # ── Tres modos en tabs — #78 heading hierarchy ───────────────────────────
    st.markdown('<h2 class="mq-h2">Proyección patrimonial</h2>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📈 Clásica", "🎯 Metas", "🎲 Monte Carlo"])

    # ════════════════════════════════════════════════════════════════════════
    # TAB 1: CLÁSICA
    # ════════════════════════════════════════════════════════════════════════
    with t1:
        clasica = proyeccion_clasica(capital_inicial, aporte_mensual, anios, retorno_anual)

        # Hero
        st.markdown(
            f"""
<div style="text-align:center;padding:1rem 0 0.5rem;">
    <div style="font-size:0.72rem;color:{_GRIS};text-transform:uppercase;
                letter-spacing:0.1em;">Tu inversión podría valer</div>
    <div style="font-size:2.8rem;font-weight:800;
                color:{_VERDE};font-family:'DM Mono',monospace;line-height:1.1;">
        {_usd(clasica.capital_final)}
    </div>
    <div style="font-size:0.75rem;color:{_GRIS};margin-top:4px;">(proyección, no garantía)</div>
    <div style="font-size:0.85rem;color:{_GRIS};">
        en {anios} años · asumiendo retorno {_pct(retorno_pct)} constante
    </div>
</div>""",
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # KPIs fila 1
        c1, c2, c3, c4 = st.columns(4)
        _kpi(c1, "Capital inicial", _usd(capital_inicial), color=_VERDE)
        _aportes_netos = clasica.aportes_totales - capital_inicial
        _kpi(c2, "Aportes mensuales acum.", _usd(_aportes_netos),
             delta=f"+{_usd(aporte_mensual)}/mes × {anios * 12} meses", color=_CYAN)
        _kpi(c3, "Intereses proyectados", _usd(clasica.intereses_ganados),
             delta=f"+{_pct(clasica.retorno_acumulado_pct)} retorno acum.", color=_LIMA)
        _kpi(c4, "Ingreso mensual (4%)", _usd(clasica.ingreso_mensual_4pct),
             delta="regla de Bengen", color=_NARANJA)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

        # Gráficos
        col_pie, col_bar = st.columns([1, 2])
        with col_pie:
            st.markdown("**Composición del capital final**")
            st.plotly_chart(_chart_pie(clasica, capital_inicial), use_container_width=True, config={"displayModeBar": False})
            # #90 Chart caption
            st.markdown(chart_description_html("Composición capital final", "Distribución entre capital aportado e intereses generados al horizonte de retiro."), unsafe_allow_html=True)
        with col_bar:
            st.markdown("**Crecimiento año a año**")
            st.plotly_chart(_chart_clasica(clasica, capital_inicial), use_container_width=True, config={"displayModeBar": False})
            # #90 Chart caption
            st.markdown(chart_description_html("Crecimiento anual", "Evolución del saldo acumulado año a año incluyendo aportes e intereses compuestos."), unsafe_allow_html=True)

        # #55 Tabla año a año mejorada
        with st.expander("📋 Ver tabla anual completa"):
            df_show = clasica.df_anual.copy()
            df_show.columns = ["Año", "Saldo USD", "Aportes acum.", "Intereses acum."]
            df_show["Retorno anual %"] = df_show["Saldo USD"].pct_change().fillna(0).mul(100).round(1)
            # Formato de moneda
            for c in ["Saldo USD", "Aportes acum.", "Intereses acum."]:
                df_show[c] = df_show[c].apply(lambda v: f"${v:,.0f}")
            df_show["Retorno anual %"] = df_show["Retorno anual %"].apply(lambda v: f"{v:.1f}%")
            st.dataframe(df_show, use_container_width=True, hide_index=True, height=min(520, 44 + 26 * len(df_show)))

        # #54 Comparación de 3 escenarios (pesimista / base / optimista)
        st.divider()
        st.markdown("#### 🎯 Tres escenarios comparados")
        _ret_pes = max(1.0, retorno_pct - 3.0) / 100.0
        _ret_opt = min(25.0, retorno_pct + 3.0) / 100.0
        _clasica_pes = proyeccion_clasica(capital_inicial, aporte_mensual, anios, _ret_pes)
        _clasica_opt = proyeccion_clasica(capital_inicial, aporte_mensual, anios, _ret_opt)

        _esc_data = [
            ("🔴 Pesimista", _ret_pes, _clasica_pes, _ROJO),
            ("🟡 Base", retorno_anual, clasica, _NARANJA),
            ("🟢 Optimista", _ret_opt, _clasica_opt, _VERDE),
        ]
        _sc1, _sc2, _sc3 = st.columns(3)
        for (_sc_col, (_esc_label, _esc_ret, _esc_cl, _esc_color)) in zip(
            [_sc1, _sc2, _sc3], _esc_data, strict=True
        ):
            with _sc_col:
                st.markdown(
                    f'<div style="background:rgba(30,41,59,0.7);border:1px solid rgba(255,255,255,0.08);'
                    f'border-radius:10px;padding:1rem;text-align:center;">'
                    f'<div style="font-size:0.75rem;color:#94a3b8;margin-bottom:4px;">{_esc_label}</div>'
                    f'<div style="font-size:0.68rem;color:#64748b;">{_pct(_esc_ret * 100)} anual</div>'
                    f'<div style="font-size:1.6rem;font-weight:800;color:{_esc_color};'
                    f'font-family:monospace;margin:6px 0;">{_usd(_esc_cl.capital_final)}</div>'
                    f'<div style="font-size:0.72rem;color:#94a3b8;">'
                    f'Ingresos: {_usd(_esc_cl.ingreso_mensual_4pct)}/mes</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # #56 Indicador visual si el objetivo patrimonial fue definido
        _objetivo_pat = float(st.session_state.get("ret_objetivo_nw", 0.0) or 0.0)
        if _objetivo_pat > 0:
            _pct_objetivo = min(clasica.capital_final / _objetivo_pat, 2.0)
            _alcanza = clasica.capital_final >= _objetivo_pat
            st.markdown(
                f'<div style="margin-top:1rem;padding:0.6rem 1rem;border-radius:8px;'
                f'background:{"rgba(34,197,94,0.1)" if _alcanza else "rgba(239,68,68,0.1)"};'
                f'border:1px solid {"rgba(34,197,94,0.3)" if _alcanza else "rgba(239,68,68,0.3)"};">'
                f'{"✅" if _alcanza else "⚠️"} '
                f'Objetivo patrimonial: {_usd(_objetivo_pat)} — '
                f'Proyección cubre el <strong>{_pct_objetivo*100:.0f}%</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ════════════════════════════════════════════════════════════════════════
    # TAB 2: METAS
    # ════════════════════════════════════════════════════════════════════════
    with t2:
        col_inp, col_res = st.columns([1, 2])
        with col_inp:
            ingreso_meta = st.number_input(
                "Meta de ingreso pasivo mensual (USD)",
                min_value=100.0,
                value=2_500.0,
                step=100.0,
                format="%.0f",
                key="ret_ingreso_meta",
            )
            tasa_retiro_pct = st.slider(
                "Tasa de retiro segura (%)",
                min_value=2.0, max_value=6.0, value=4.0, step=0.25,
                help="4% = regla de Bengen (30+ años). Más conservador → menor tasa.",
                key="ret_tasa_retiro",
            )
            st.caption(
                "**Regla del 4%**: en el estudio Trinity (1998), ~95% de las secuencias "
                "históricas permitieron retirar el 4% anual sin agotar el capital en 30 años. "
                "No es una garantía."
            )

        tasa_retiro = tasa_retiro_pct / 100.0
        metas = resultado_metas(
            capital_inicial, aporte_mensual, anios, retorno_anual,
            ingreso_meta, tasa_retiro,
        )

        with col_res:
            # Capital necesario vs proyectado
            c1, c2 = st.columns(2)
            _kpi(c1, "Capital necesario", _usd(metas.capital_necesario),
                 delta=f"para {_usd(ingreso_meta)}/mes", color=_NARANJA)
            color_proy = _VERDE if metas.meta_alcanzada else _ROJO
            _kpi(c2, "Capital proyectado", _usd(metas.capital_proyectado),
                 delta="en " + str(anios) + " años", color=color_proy)

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

            # Gauge
            st.markdown(f"**¿Llegás a tu meta?** &nbsp; {_pct(metas.pct_meta_cubierta)} cubierto")
            st.plotly_chart(
                _chart_gauge(metas.pct_meta_cubierta), use_container_width=True,
                config={"displayModeBar": False},
            )
            # #90 Chart caption
            st.markdown(chart_description_html("Cobertura de meta", f"Gauge de progreso: {_pct(metas.pct_meta_cubierta)} del capital objetivo cubierto por la proyección."), unsafe_allow_html=True)

        if metas.meta_alcanzada:
            excedente = metas.capital_proyectado - metas.capital_necesario
            st.success(
                f"🎯 **La proyección supera la meta** por "
                f"**{_usd(excedente)}**. "
                f"El retiro ilustrado sería **{_usd(ingreso_meta)}/mes** "
                f"(tasa {_pct(tasa_retiro_pct)}; no es una garantía)."
            )
        else:
            brecha = metas.capital_necesario - metas.capital_proyectado
            st.warning(
                f"📉 Falta **{_usd(brecha)}** para cubrir la meta. "
                f"Ajustá alguna de las variables a continuación."
            )
            st.markdown("#### 🔧 Cómo cerrar la brecha")
            s = metas.sugerencias
            cs1, cs2, cs3 = st.columns(3)
            _kpi(cs1, "Subir aporte mensual a",
                 _usd(s.get("aporte_necesario", 0)),
                 delta=f"desde {_usd(aporte_mensual)}/mes", color=_CYAN)
            _kpi(cs2, "Extender plazo a",
                 f"{s.get('plazo_necesario', anios)} años",
                 delta=f"desde {anios} años", color=_CYAN)
            _kpi(cs3, "Capital inicial de",
                 _usd(s.get("capital_ini_necesario", 0)),
                 delta=f"desde {_usd(capital_inicial)}", color=_CYAN)

        # Guardar objetivo en BD
        if st.button("💾 Guardar objetivo de retiro", key="btn_guardar_retiro"):
            try:

                import streamlit as _st

                from core.db_manager import ObjetivosInversion, get_session

                cliente_id = _st.session_state.get("cliente_id")
                if cliente_id:
                    with get_session() as s:
                        obj = ObjetivosInversion(
                            cliente_id=int(cliente_id),
                            ticker="RETIRO",
                            monto_ars=0.0,
                            plazo_label=f"{anios} años",
                            plazo_dias=anios * 365,
                            motivo=(
                                f"Meta retiro: {_usd(ingreso_meta)}/mes · "
                                f"Capital necesario: {_usd(metas.capital_necesario)} · "
                                f"Tasa retiro: {_pct(tasa_retiro_pct)}"
                            ),
                            target_pct=None,
                            estado="ACTIVO",
                            tenant_id=_st.session_state.get("mq26_tenant_id", "default"),
                        )
                        s.add(obj)
                        s.commit()
                    st.success("✓ Objetivo de retiro guardado en la base de datos.")
                else:
                    st.warning("Seleccioná un cliente primero para guardar el objetivo.")
            except Exception as e:
                st.error(f"No se pudo guardar: {e}")

    # ════════════════════════════════════════════════════════════════════════
    # TAB 3: MONTE CARLO
    # ════════════════════════════════════════════════════════════════════════
    with t3:
        usa_retornos_reales = r_diarios is not None and len(r_diarios) >= 42

        col_mc_inp, col_mc_res = st.columns([1, 2])
        with col_mc_inp:
            if usa_retornos_reales:
                st.success(
                    f"✅ **Bootstrap sobre retornos reales** — {len(r_diarios):,} días de historia. "
                    "El Monte Carlo usa la distribución empírica de tu portfolio, "
                    "no una distribución normal asumida."
                )
                sigma_pct = sig_cartera * 100   # referencia; no se usa en bootstrap
            else:
                st.info(
                    "ℹ️ Sin historia suficiente — usando distribución normal. "
                    "Con más datos históricos el Monte Carlo será más preciso."
                )
                sig_pct_def = round(sig_cartera * 100, 1) if sig_cartera > 0 else 15.0
                sigma_pct = st.slider(
                    "Volatilidad anual (%)",
                    min_value=5.0, max_value=40.0,
                    value=float(min(max(sig_pct_def, 5.0), 40.0)),
                    step=0.5, key="ret_sigma_pct",
                )

            n_sim = st.select_slider(
                "Simulaciones", options=[100, 250, 500, 1000, 2000],
                value=1000, key="ret_n_sim",
            )
            meta_capital_mc = st.number_input(
                "Meta de capital final (USD, opcional)",
                min_value=0.0, value=0.0, step=10_000.0, format="%.0f",
                key="ret_meta_mc",
                help="Si ingresás una meta verás la probabilidad de alcanzarla.",
            )
            n_anios_seq = st.slider(
                "Años críticos (secuencia de retornos)",
                min_value=1, max_value=10, value=5, key="ret_seq_anios",
                help="Primeros N años donde el orden de retornos impacta más.",
            )
            simular = st.button("▶ Simular", type="primary", key="btn_simular_mc", use_container_width=True)

        # Guardar resultado en session_state para persistir entre reruns
        if simular or "ret_mc_result" not in st.session_state:
            with st.spinner("Simulando…"):
                mc = montecarlo_retiro(
                    capital_inicial=capital_inicial,
                    aporte_mensual=aporte_mensual,
                    anios=anios,
                    retornos_diarios=np.asarray(r_diarios) if usa_retornos_reales else None,
                    retorno_anual_base=retorno_anual,
                    sigma_anual=sigma_pct / 100.0,
                    n_sim=int(n_sim),
                    meta_capital=float(meta_capital_mc),
                    seed=42,
                    n_anios_seq=n_anios_seq,
                )
            st.session_state["ret_mc_result"] = mc
        else:
            mc: ResultadoMonteCarlo = st.session_state["ret_mc_result"]

        with col_mc_res:
            # KPIs de escenarios
            c1, c2, c3 = st.columns(3)
            _kpi(c1, "Pesimista (cuartil inferior)", _usd(mc.pesimista),
                 delta="malos retornos iniciales", color=_ROJO)
            _kpi(c2, "Base (determinístico)", _usd(mc.base),
                 delta=f"retorno fijo {_pct(retorno_pct)}", color=_VERDE)
            _kpi(c3, "Optimista (cuartil superior)", _usd(mc.optimista),
                 delta="buenos retornos iniciales", color=_CYAN)

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # Probabilidades
            cp1, cp2 = st.columns(2)
            prob_base_pct = mc.prob_supera_base * 100
            prob_meta_pct = mc.prob_supera_meta * 100
            color_pb = _VERDE if prob_base_pct >= 50 else _NARANJA
            color_pm = _VERDE if prob_meta_pct >= 50 else _ROJO
            _kpi(cp1, "% simulaciones superan base",
                 _pct(prob_base_pct), color=color_pb)
            if meta_capital_mc > 0:
                _kpi(cp2, f"% simulaciones superan {_usd(meta_capital_mc)}",
                     _pct(prob_meta_pct), color=color_pm)
            else:
                _kpi(cp2, "Percentil 50 (mediana)", _usd(mc.p50),
                     delta="resultado más probable", color=_VERDE)

        # Gráfico de trayectorias
        st.markdown("**Trayectorias simuladas — banda P10/P90**")
        st.plotly_chart(
            _chart_montecarlo(mc, float(meta_capital_mc), anios), use_container_width=True,
            config={"displayModeBar": False},
        )
        # #90 Chart caption
        st.markdown(chart_description_html("Monte Carlo — Trayectorias", "Simulación de escenarios patrimoniales: banda P10-P90. La línea media es el resultado más probable."), unsafe_allow_html=True)

        # Insight didáctico
        with st.expander("❓ ¿Por qué el orden de los retornos importa?"):
            st.markdown(
                """
**El riesgo de secuencia** (sequence-of-returns risk) describe cómo el **orden** en que
se producen los retornos afecta el resultado final, incluso si el promedio es idéntico.

- **Malos retornos al inicio** → pérdidas cuando el capital es grande → difícil de recuperar.
- **Buenos retornos al inicio** → el compuesto trabaja sobre una base mayor → acelera el crecimiento.

Esto es especialmente crítico en la **fase de desacumulación** (cuando retirás dinero):
un mercado bajista en los primeros años de retiro puede agotar el capital antes de tiempo.

MQ26 clasifica las simulaciones por el retorno promedio de los primeros años
para mostrarte el rango real de resultados posibles según la secuencia.
                """
            )

        # Info sobre ventaja frente a calculadoras genéricas
        if usa_retornos_reales:
            with st.expander("🏆 ¿Por qué este Monte Carlo es superior a calculadoras genéricas?"):
                st.markdown(
                    f"""
Las calculadoras tradicionales (como la BDI standalone) asumen que los retornos siguen
una **distribución normal** con media y sigma fijos. Esta es una simplificación importante.

MQ26 usa **bootstrap histórico**: re-muestrea los **{len(r_diarios):,} días reales** de tu
portfolio para construir las trayectorias. Esto captura:
- La distribución real de retornos (colas gordas, asimetría)
- Autocorrelación y clustering de volatilidad
- Shocks específicos del portfolio (no retornos genéricos de índice)

Resultado: una estimación de riesgo más honesta y personalizada.
                    """
                )
