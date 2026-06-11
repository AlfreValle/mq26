"""
ui/components/ficha_ticker_view.py — render Streamlit de la ficha unificada.

Pilar 2 sprint 2: la cara visible de services/ficha_ticker.py. Un solo
componente para asesor e inversor (el inversor ve lo mismo con menos jerga:
las explicaciones ya vienen en lenguaje humano desde el servicio).
"""
from __future__ import annotations

import streamlit as st

from services.ficha_ticker import FichaTicker, ficha_ticker_html, generar_ficha_ticker

_RECO_BADGE = {
    "COMPRAR": "🟢",
    "MANTENER": "🟡",
    "VENDER": "🔴",
    "VER FICHA RF": "🔵",
    "SIN DATOS": "⚪",
}


@st.cache_data(ttl=900, show_spinner=False)
def _ficha_cacheada(ticker: str) -> FichaTicker:
    return generar_ficha_ticker(ticker)


def _badge(reco: str) -> str:
    return f"{_RECO_BADGE.get(reco, '⚪')} {reco}"


def _render_seccion(s, titulo: str, *, expanded: bool = False) -> None:
    icono = "✅" if s.ok else "➖"
    with st.expander(f"{icono} {titulo}", expanded=expanded):
        st.markdown(s.explicacion or s.error or "Sin datos.")
        if s.ok and s.datos:
            with st.popover("Ver datos crudos"):
                st.json(s.datos, expanded=False)


def _render_velas_opcional(ticker: str) -> None:
    """Gráfico de velas 6 meses (empresa_ficha) — sección opcional best-effort."""
    if not st.toggle("Ver gráfico de velas (6 meses)", key=f"ficha_velas_{ticker}"):
        return
    try:
        from services.empresa_ficha import generar_ficha_activo

        with st.spinner("Descargando precios…"):
            ficha_legacy = generar_ficha_activo(ticker)
        fig = (ficha_legacy or {}).get("figura_velas")
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True, key=f"ficha_fig_{ticker}")
        else:
            st.caption("Sin datos de precio para graficar.")
    except Exception:
        st.caption("No se pudo descargar el histórico de precios (proveedor caído).")


def render_ficha_ticker(ticker: str, *, key_prefix: str = "ficha") -> None:
    """Busca y muestra la ficha unificada de un ticker."""
    tu = str(ticker or "").strip().upper()
    if not tu:
        return
    with st.spinner(f"Armando ficha de {tu}…"):
        try:
            ficha = _ficha_cacheada(tu)
        except Exception as exc:
            st.error(f"No se pudo generar la ficha de {tu}: {exc}")
            return

    # ── Header: recomendación + score + cobertura ────────────────────────────
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.markdown(f"### {tu} {_badge(ficha.recomendacion)}")
    if ficha.score_global is not None:
        c2.metric("Score multifactor", f"{ficha.score_global:.0f}/100")
    c3.metric("Cobertura de datos", ficha.cobertura)

    st.markdown(
        f"<div style='padding:0.7rem 1rem;background:var(--c-bg-2, rgba(148,163,184,0.08));"
        f"border-radius:10px;font-size:0.9rem;line-height:1.55;'>{ficha.resumen}</div>",
        unsafe_allow_html=True,
    )

    # ── Dimensiones del score en columnas (si hay multifactor) ──────────────
    if ficha.multifactor.ok:
        d = ficha.multifactor.datos
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Valor (35%)", f"{float(d.get('score_valor', 0)):.0f}")
        m2.metric("Calidad (30%)", f"{float(d.get('score_calidad', 0)):.0f}")
        m3.metric("Momentum (20%)", f"{float(d.get('score_momentum', 0)):.0f}")
        m4.metric("Sectorial (15%)", f"{float(d.get('score_sectorial', 0)):.0f}")
        flags = d.get("flags_alerta") or []
        for f in flags[:5]:
            st.caption(str(f))

    # ── Secciones detalladas ─────────────────────────────────────────────────
    _render_seccion(ficha.multifactor, "Score multifactor — desglose", expanded=False)
    _render_seccion(ficha.valuacion_dcf, "Valuación DCF")
    _render_seccion(ficha.comparables, "Comparables de industria")
    _render_seccion(ficha.fundamentals, "Fundamentals")
    _render_seccion(ficha.identidad, "Identidad del instrumento")

    if not ficha.identidad.datos.get("es_renta_fija"):
        _render_velas_opcional(tu)

    # ── Descarga HTML ────────────────────────────────────────────────────────
    st.download_button(
        "📄 Descargar ficha (HTML)",
        data=ficha_ticker_html(ficha),
        file_name=f"mq26_ficha_{tu}.html",
        mime="text/html",
        key=f"{key_prefix}_dl_{tu}",
        use_container_width=True,
    )


def render_buscador_ficha(ctx: dict, *, key_prefix: str = "ficha") -> None:
    """Buscador de ticker + ficha. Pensado para sub-tab de tab_universo."""
    st.subheader("📑 Ficha de ticker")
    st.caption(
        "Análisis integral: score multifactor explicado, valuación DCF, "
        "comparables de industria y fundamentals — con calidad de datos visible."
    )
    from core.instrument_master import get_master

    master = get_master(ctx.get("universo_df"))
    col_in, col_btn = st.columns([3, 1])
    ticker_in = col_in.text_input(
        "Ticker (CEDEAR, acción local o ETF)",
        placeholder="AAPL, GGAL, MELI…",
        key=f"{key_prefix}_input",
    ).strip().upper()
    buscar = col_btn.button("Generar ficha", type="primary", key=f"{key_prefix}_btn",
                            use_container_width=True)
    # Persistir el último ticker buscado: el botón solo es True en el run del
    # click, y sin esto la ficha desaparecería al tocar el toggle de velas.
    estado_key = f"{key_prefix}_last_ticker"
    if buscar and ticker_in:
        st.session_state[estado_key] = ticker_in
    ticker_activo = str(st.session_state.get(estado_key) or "")
    if not ticker_activo:
        return
    v = master.validar(ticker_activo)
    if not v.valido:
        msg = f"**{ticker_activo}** no está en el maestro de instrumentos."
        if v.sugerencias:
            msg += f" ¿Quisiste decir **{', '.join(v.sugerencias)}**?"
        st.warning(msg)
        return
    render_ficha_ticker(ticker_activo, key_prefix=key_prefix)
