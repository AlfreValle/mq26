"""
ui/mq26_ux.py — Componentes de UX reutilizables MQ26 v9.
Onboarding, breadcrumbs, buscador, notificaciones, helpers de render.
"""
from __future__ import annotations

import datetime as dt
import html as html_module
import secrets

import pandas as pd
import streamlit as st


# ── MEJORA 51: Etiquetas por semáforo (colores vía CSS mq-sem-label-text--*) ─
SEMAFORO_CONFIG = {
    "verde":    {"label": "Cartera en orden"},
    "amarillo": {"label": "Hay ajustes recomendados"},
    "rojo":     {"label": "Cartera necesita atención"},
}


def _session_light_mode() -> bool:
    """Tema claro retail (`mq_light_mode`) para Plotly; default True si no hay sesión."""
    try:
        import streamlit as st

        return bool(st.session_state.get("mq_light_mode", True))
    except Exception:
        return True


def plotly_chart_layout_base(*, light: bool | None = None, **overrides) -> dict:
    """
    Layout Plotly alineado a tokens MQ26 (P3-UX-02): Barlow + color de eje legible
    en tema claro u oscuro (Plotly no lee variables CSS).
    """
    _light = _session_light_mode() if light is None else bool(light)
    # Oscuro: --c-text-2 (#a8a39a); claro: texto secundario slate (~--c-text-2 light)
    _color = "rgb(51, 65, 85)" if _light else "rgb(168, 163, 154)"
    base: dict = {
        "plot_bgcolor": "rgba(0,0,0,0)",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "font": dict(family="Barlow, sans-serif", size=12, color=_color),
    }
    base.update(overrides)
    return base


def dataframe_auto_height(
    rows_or_df,
    *,
    min_px: int = 140,
    max_px: int = 560,
    header_px: int = 56,
    row_px: int = 30,
) -> int:
    """
    Altura responsiva para st.dataframe (P3-UX-01): pocas filas → tabla baja;
    muchas filas → tope `max_px` (lectura notebook y desktop sin scroll infinito).

    Acepta DataFrame, Styler (pandas) o número de filas.
    """
    try:
        src = rows_or_df
        if hasattr(src, "data") and hasattr(src.data, "index"):
            src = src.data  # pandas.io.formats.style.Styler
        if hasattr(src, "index"):
            n = int(len(src.index))
        else:
            n = int(src)
    except Exception:
        n = 0
    n = max(0, n)
    h = int(header_px + (n * row_px))
    return max(int(min_px), min(int(max_px), h))


def hero_alignment_bar_html(pct: float, label: str = "Alineación con tu plan") -> str:
    """Barra hero 0–100% (snapshot del motor; solo presentación)."""
    p = max(0.0, min(100.0, float(pct)))
    lab = html_module.escape(label)
    return f"""
    <div class="mq-hero-gauge mq-hub-stack">
      <div class="mq-label mq-hero-gauge__label">{lab}</div>
      <div class="mq26-progress-bar-container mq-hero-gauge__track">
        <div class="mq26-progress-bar mq26-progress-verde" style="width:{p:.1f}%;max-width:100%;"></div>
      </div>
      <div class="mq-hero-number">{p:.0f} / 100</div>
    </div>
    """


def semaforo_html(valor: str, score: float | None = None,
                  titulo: str = "") -> str:
    """
    Genera HTML del semáforo con dot animado + score + título.

    MEJORA 52: dot pulsante con glow según estado.
    """
    _k = str(valor).lower()
    cfg = SEMAFORO_CONFIG.get(_k, SEMAFORO_CONFIG["amarillo"])
    score_txt = f" · {score:.0f}/100" if score is not None else ""
    titulo_txt = html_module.escape(titulo) if titulo else cfg["label"]
    _cls = _k if _k in ("verde", "amarillo", "rojo") else "neutro"
    return f"""
    <div class="mq-sem-wrap">
        <div class="mq-sem-dot mq-sem-dot--{_cls}"></div>
        <div class="mq-sem-label">
            <span class="mq-sem-label-text mq-sem-label-text--{_cls}">{titulo_txt}</span>
            <span class="mq-sem-score">{score_txt}</span>
        </div>
    </div>
    """


# ── MEJORA 53: Card de métrica HTML ──────────────────────────────────────────
def metric_card_html(label: str, value: str, delta: str = "",
                     delta_ok: bool | None = None,
                     icon: str = "") -> str:
    """Genera una card de métrica con tipografía mono y delta coloreado."""
    if delta_ok is True:
        delta_cls, delta_icon = "delta-pos", "↑"
    elif delta_ok is False:
        delta_cls, delta_icon = "delta-neg", "↓"
    else:
        delta_cls, delta_icon = "delta-neu", ""

    icon_html = f'<div class="mq-icon">{icon}</div>' if icon else ""
    delta_html = (
        f'<div class="delta {delta_cls}">'
        f'{delta_icon} {delta}</div>'
    ) if delta else ""

    return f"""
    <div class="mq26-metric-card">
        {icon_html}
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        {delta_html}
    </div>
    """


# ── MEJORA 54: Progress bar defensivo ────────────────────────────────────────
def defensive_bar_html(pct_actual: float, pct_required: float,
                        label: str = "Defensivo") -> str:
    """
    Barra de progreso que muestra % defensivo vs requerido.
    Verde si cumple, amarillo si está cerca, rojo si falta.
    """
    ratio = pct_actual / max(pct_required, 0.01)
    if ratio >= 1.0:
        clase = "mq26-progress-verde"
        estado = "✓"
    elif ratio >= 0.75:
        clase = "mq26-progress-yellow"
        estado = "~"
    else:
        clase = "mq26-progress-danger"
        estado = "!"
    width_pct = min(pct_actual / max(pct_required, 0.01) * 100, 100)
    return f"""
    <div class="mq-def-bar-wrap">
        <div class="mq-def-bar-head">
            <span class="mq-def-bar-label">{label}</span>
            <span class="mq-def-bar-value">
                {estado} {pct_actual:.1%} / {pct_required:.1%}
            </span>
        </div>
        <div class="mq26-progress-bar-container">
            <div class="mq26-progress-bar {clase}"
                 style="width:{width_pct:.1f}%"></div>
        </div>
    </div>
    """


# ── MEJORA 55: Observación de diagnóstico ─────────────────────────────────────
def obs_card_html(icono: str, titulo: str, texto: str,
                  cifra: str, prioridad: str = "media") -> str:
    """Card de observación del motor de diagnóstico."""
    t = html_module.escape(str(titulo))
    x = html_module.escape(str(texto))
    c = html_module.escape(str(cifra))
    return f"""
    <div class="mq-obs mq-obs--{prioridad.lower()}">
        <div class="mq-obs__title">{icono} {t}</div>
        <div class="mq-obs__body">{x}</div>
        <div class="mq-obs__cifra">{c}</div>
    </div>
    """


# ── MEJORA 56: Topline bar enriquecida ──────────────────────────────────────
def topline_html(cartera: str, cliente: str, perfil: str,
                 valor_txt: str, pnl_pct: float, ccl: float,
                 n_pos: int = 0) -> str:
    """Barra superior de cartera con info completa."""
    import html as _html
    if pnl_pct > 0.005:
        pnl_cls, pnl_sign = "mq-topline__pnl--ok",  "+"
    elif pnl_pct < -0.005:
        pnl_cls, pnl_sign = "mq-topline__pnl--bad", ""
    else:
        pnl_cls, pnl_sign = "mq-topline__pnl--mid", ""

    perfil_skin = {
        "Conservador": ("var(--c-green-muted)", "var(--c-green)"),
        "Moderado": ("var(--c-yellow-muted)", "var(--c-yellow)"),
        "Arriesgado": ("var(--c-red-muted)", "var(--c-red)"),
        "Muy arriesgado": ("var(--c-red-muted)", "var(--c-red)"),
        "Agresivo": ("var(--c-red-muted)", "var(--c-red)"),
    }
    bg_c, fg_c = perfil_skin.get(perfil, ("var(--c-accent-muted)", "var(--c-accent)"))

    pos_txt = f"· {n_pos} pos." if n_pos else ""
    return f"""
    <div class="mq-topline">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <span class="mq-topline__portfolio">{_html.escape(cartera)}</span>
            <span class="mq-topline__client">{_html.escape(cliente)}</span>
            <span style="
                background:{bg_c};
                color:{fg_c};
                font-size:0.62rem;font-weight:600;
                padding:1px 7px;border-radius:999px;
                text-transform:uppercase;letter-spacing:0.05em;
            ">{_html.escape(perfil)}</span>
        </div>
        <div class="mq-topline__right">
            <span class="mq-topline__value">{_html.escape(valor_txt)}</span>
            <span class="mq-topline__pnl {pnl_cls}">
                {pnl_sign}{pnl_pct:.1%}
            </span>
            <span class="mq-topline__meta">
                CCL {ccl:,.0f} {pos_txt}
            </span>
        </div>
    </div>
    """


# ── MEJORA 57: Onboarding rediseñado ─────────────────────────────────────────
def render_onboarding(dbm) -> None:
    if st.session_state.get("onboarding_completado"):
        return
    if dbm.obtener_config("onboarding_completado") == "1":
        st.session_state["onboarding_completado"] = True
        return

    paso = st.session_state.get("onboarding_paso", 1)
    pasos = [
        ("📁", "Tu cartera activa",
         "Elegí el cliente en el sidebar. Podés tener múltiples carteras "
         "y cambiar entre ellas sin perder datos."),
        ("💱", "Tipo de cambio CCL",
         "El CCL (Contado con Liquidación) convierte USD → ARS para valorar tus "
         "CEDEARs. Se actualiza automáticamente desde yfinance."),
        ("🔬", "Motor de optimización",
         "9 modelos cuantitativos: Sharpe, Kelly, Black-Litterman, HRP y más. "
         "El sistema te dice exactamente cuánto comprar de cada activo."),
    ]
    icono, titulo, texto = pasos[paso - 1]

    st.markdown(f"""
    <div class="onboarding-step">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:0.75rem;">
            <div style="
                font-size:1.25rem;
                width:38px;height:38px;
                background:var(--c-accent-muted);
                border-radius:10px;
                display:flex;align-items:center;justify-content:center;
            ">{icono}</div>
            <div>
                <div style="font-weight:600;font-size:0.9rem;
                            color:var(--c-text);letter-spacing:-0.01em;">
                    Paso {paso} de 3 — {titulo}
                </div>
            </div>
        </div>
        <p style="font-size:0.8125rem;color:var(--c-text-2);
                  line-height:1.6;margin:0;">{texto}</p>
    </div>
    """, unsafe_allow_html=True)

    st.progress(paso / 3)
    col1, col2 = st.columns([2, 8])
    with col1:
        if paso < 3:
            if st.button("Siguiente →", key=f"onb_next_{paso}",
                         type="primary", use_container_width=True):
                st.session_state["onboarding_paso"] = paso + 1
                st.rerun()
        else:
            if st.button("Empezar ✓", key="onb_done",
                         type="primary", use_container_width=True):
                st.session_state["onboarding_completado"] = True
                dbm.guardar_config("onboarding_completado", "1")
                st.rerun()
    with col2:
        if st.button("Omitir", key="onb_skip", use_container_width=False):
            st.session_state["onboarding_completado"] = True
            dbm.guardar_config("onboarding_completado", "1")
            st.rerun()
    st.divider()


# ── MEJORA 58: Breadcrumbs ────────────────────────────────────────────────────
def render_breadcrumb(tab_nombre: str, subtab: str = "") -> None:
    partes = ["MQ26", tab_nombre] + ([subtab] if subtab else [])
    sep = '<span class="sep">›</span>'
    html_parts = sep.join(
        f'<span style="color:{"var(--c-text-2)" if i==len(partes)-1 else "var(--c-text-3)"}">'
        f'{p}</span>'
        for i, p in enumerate(partes)
    )
    st.markdown(
        f'<p class="mq-breadcrumb">{html_parts}</p>',
        unsafe_allow_html=True,
    )


# ── MEJORA 59: Búsqueda de ticker en sidebar ──────────────────────────────────
def render_busqueda_ticker(universo_df: pd.DataFrame | None = None) -> str | None:
    st.sidebar.markdown(
        '<p style="font-size:0.65rem;font-weight:600;color:var(--c-text-3);'
        'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.35rem;">'
        'Búsqueda rápida</p>',
        unsafe_allow_html=True,
    )
    query = st.sidebar.text_input(
        "Ticker",
        placeholder="AAPL, MSFT, GGAL…",
        key="busqueda_ticker_sidebar",
        label_visibility="collapsed",
    )
    if query and len(query) >= 2:
        q = query.strip().upper()
        if universo_df is not None and not universo_df.empty:
            col_t = "TICKER" if "TICKER" in universo_df.columns else universo_df.columns[0]
            matches = universo_df[
                universo_df[col_t].str.upper().str.contains(q, na=False)
            ][col_t].head(5).tolist()
        else:
            matches = [q]
        if matches:
            sel = st.sidebar.selectbox("", matches, key="busq_sel_ticker",
                                       label_visibility="collapsed")
            if st.sidebar.button("Ver señales →", key="btn_busq_ir",
                                  use_container_width=True):
                st.session_state["ticker_preseleccionado"] = sel
                st.session_state["nav_tab"] = "universo"
                st.rerun()
            return sel
    return None


# ── MEJORA 60: Centro de notificaciones compacto ──────────────────────────────
def render_centro_notificaciones(dbm, limite: int = 10) -> None:
    with st.sidebar.expander("🔔 Notificaciones", expanded=False):
        try:
            from core.db_manager import AlertaLog
            with dbm.get_session() as s:
                alertas = (
                    s.query(AlertaLog)
                    .order_by(AlertaLog.id.desc())
                    .limit(limite)
                    .all()
                )
            if not alertas:
                st.caption("Sin notificaciones recientes.")
                return
            iconos = {
                "VAR_BREACH": "🔴", "DRAWDOWN": "🔴",
                "SELL_SIGNAL": "🟡", "AUDITORIA": "🔵",
                "ACCESO": "⚪", "OBJETIVO_VENCE": "⏰",
            }
            for a in alertas:
                ico = iconos.get(str(a.tipo_alerta), "📌")
                ts = (a.created_at.strftime("%d/%m %H:%M")
                      if hasattr(a, "created_at") and a.created_at else "")
                st.markdown(
                    f'<div class="mq-notif-item">'
                    f'<span>{ico}</span>'
                    f'<span>{str(a.mensaje)[:55]}'
                    f'<br><small style="color:var(--c-text-3)">{ts}</small></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        except Exception as e:
            st.caption(f"Sin datos: {e}")


# ── MEJORA 61-65: Helpers para tooltips y métricas ────────────────────────────
TOOLTIPS_METRICAS: dict[str, str] = {
    "Sharpe":   "Retorno ajustado por riesgo. Mayor = mejor.",
    "Sortino":  "Como Sharpe pero penaliza solo volatilidad negativa.",
    "Kelly":    "Fracción óptima del capital a invertir (criterio matemático).",
    "CVaR":     "Pérdida esperada en el peor 5% de escenarios.",
    "TWRR":     "Retorno que aísla el efecto de depósitos y retiros.",
    "Alpha":    "Retorno en exceso vs benchmark. Alpha > 0 = superás al mercado.",
    "Beta":     "Sensibilidad al mercado. Beta > 1 = más volátil.",
    "Max DD":   "Caída máxima desde pico hasta valle en el período.",
    "VaR 95%":  "Pérdida máxima esperada en el 95% de los días.",
    "Calmar":   "Retorno anualizado / Max Drawdown.",
}


def get_tooltip(metrica: str) -> str:
    return TOOLTIPS_METRICAS.get(metrica, "")


# ── MEJORA 66-70: Token compartible ──────────────────────────────────────────
def generar_token_reporte(cliente_id: int, dbm) -> str:
    token = secrets.token_urlsafe(16)
    expira = (dt.datetime.utcnow() + dt.timedelta(hours=24)).isoformat()
    dbm.guardar_config(f"reporte_token_{token}", f"{cliente_id}|{expira}")
    return token


def verificar_token_reporte(token: str, dbm) -> int | None:
    raw = dbm.obtener_config(f"reporte_token_{token}")
    if not raw:
        return None
    try:
        cid_str, expira_str = raw.split("|")
        if dt.datetime.utcnow() > dt.datetime.fromisoformat(expira_str):
            return None
        return int(cid_str)
    except Exception:
        return None


def highlight_pnl_target_stop(df: pd.DataFrame,
                               objetivos: pd.DataFrame | None) -> pd.DataFrame:
    df = df.copy()
    df["_estado_objetivo"] = ""
    if objetivos is None or objetivos.empty or "ticker" not in objetivos.columns:
        return df
    for _, obj in objetivos.iterrows():
        ticker = str(obj.get("ticker", "")).upper()
        target = float(obj.get("target_pct", 0) or 0)
        stop   = float(obj.get("stop_pct",   0) or 0)
        mask   = df["TICKER"].str.upper() == ticker
        if not mask.any():
            continue
        pnl = df.loc[mask, "PNL_PCT"].values[0] if "PNL_PCT" in df.columns else 0
        if pnl >= target > 0:
            df.loc[mask, "_estado_objetivo"] = "TARGET_ALCANZADO"
        elif pnl <= stop < 0:
            df.loc[mask, "_estado_objetivo"] = "STOP_ALCANZADO"
    return df


# ── Cold start / onboarding: torta de cartera modelo por perfil ───────────────
def fig_torta_ideal(perfil: str, ideal: dict[str, float]):
    """
    Dona con la distribución semilla (CARTERA_IDEAL) sugerida para el perfil.
    Incluye el bucket agregado _RENTA_AR como “Renta fija AR (otros)” en la torta SSOT.
    """
    import plotly.graph_objects as go

    _bucket_labels = {"_RENTA_AR": "Renta fija AR (otros)"}

    def _label(k: str) -> str:
        if str(k).startswith("_"):
            return _bucket_labels.get(k, str(k).lstrip("_"))
        return str(k)

    labels = [_label(k) for k in ideal.keys()]
    vals = [max(0.0, float(ideal[k])) for k in ideal.keys()]
    total = sum(vals)
    if total <= 0 or not labels:
        fig = go.Figure()
        fig.update_layout(
            **plotly_chart_layout_base(
                height=280,
                title=dict(text=f"Distribución semilla — {perfil}", font=dict(size=14)),
                margin=dict(t=40, b=10, l=10, r=10),
                annotations=[dict(text="Sin pesos", x=0.5, y=0.5, showarrow=False)],
            ),
        )
        return fig

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=vals,
                hole=0.45,
                textinfo="label+percent",
                hoverinfo="label+percent",
                marker=dict(line=dict(color="rgba(15,23,42,0.35)", width=1)),
            )
        ]
    )
    fig.update_layout(
        **plotly_chart_layout_base(
            title=dict(
                text=f"Distribución semilla sugerida — Perfil {perfil}",
                font=dict(size=14),
            ),
            margin=dict(t=40, b=10, l=10, r=10),
            height=280,
            showlegend=False,
        ),
    )
    return fig
