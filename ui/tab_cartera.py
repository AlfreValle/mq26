"""
ui/tab_cartera.py — Tab 1: Cartera & Libro Mayor
Combina: Posición Neta (P&L + Motor de Salida + Kelly) + Libro Mayor (reemplaza CRM)
"""
import html
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from core.structured_logging import log_degradacion

# Sub-tabs extraídas a ui/cartera/ (Fase 2.1) — re-export para compatibilidad
# (tests de contrato sprint7 verifican estos atributos en este módulo).
from ui.cartera.libro_mayor import _render_libro_mayor  # noqa: F401
from ui.cartera.posicion_neta import (  # noqa: F401
    _paridad_implicita_pct_on_usd_desde_fila,
    _render_posicion_neta,
)
from ui.mq26_ux import dataframe_auto_height
from ui.rbac import can_action as _can_action_rbac


def _render_cobertura_precios(ctx: dict) -> None:
    """Badges LIVE / parcial / estimado según cobertura de precios (+ detalle accionable)."""
    coverage = float(ctx.get("price_coverage_pct", 0) or 0)
    sin_precio = ctx.get("tickers_sin_precio", []) or []
    _va = ctx.get("valoracion_audit") or {}
    _por_tipo = _va.get("por_tipo") or {}
    # ── Badges de cobertura de precios (D27 Must) ─────────────────────────
    if coverage >= 95:
        st.markdown(
            '<span class="mq-pill mq-pill--ok">● LIVE</span>'
            '<span style="font-size:0.72rem;color:var(--c-text-3);margin-left:8px;">'
            f"{coverage:.0f}% del valor con precio en tiempo real</span>",
            unsafe_allow_html=True,
        )
    elif coverage >= 60:
        st.markdown(
            '<span class="mq-pill mq-pill--warn">◐ PARCIAL</span>'
            '<span style="font-size:0.72rem;color:var(--c-text-3);margin-left:8px;">'
            f"{coverage:.0f}% live · resto: último precio conocido</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="mq-pill mq-pill--bad">○ ESTIMADO</span>'
            '<span style="font-size:0.72rem;color:var(--c-text-3);margin-left:8px;">'
            f"Solo {coverage:.0f}% live</span>",
            unsafe_allow_html=True,
        )
    if _por_tipo:
        _partes = [
            f"{t}: {info.get('pct_valor_live', 0):.0f}%"
            for t, info in sorted(_por_tipo.items())
            if info.get("pct_valor_live", 100) < 95
        ]
        if _partes:
            st.caption("Por tipo: " + " · ".join(_partes))
    # ── Tickers sin precio: errores accionables (U45 Must) ────────────────
    if sin_precio:
        with st.expander(
            f"⚠ {len(sin_precio)} activo(s) sin cotización live", expanded=False
        ):
            st.markdown(
                "Estos activos usan el **último precio conocido**. "
                "El valor total puede diferir del precio de mercado actual."
            )
            for _t in sin_precio[:10]:
                _c1, _c2 = st.columns([2, 8])
                _c1.code(_t)
                _c2.caption(
                    "Sin precio en yfinance. Valorado con último PPC conocido."
                )
            if len(sin_precio) > 10:
                st.caption(f"... y {len(sin_precio) - 10} más.")
            st.info(
                "Para precios en tiempo real de acciones locales y ONs, "
                "configurá `MQ26_BYMA_API_URL` en el `.env` cuando tengas "
                "acceso a un proveedor BYMA."
            )


def _render_resumen_cliente_cartera(ctx: dict, df_ag: pd.DataFrame) -> None:
    """
    Resumen compacto al inicio de Cartera (asesor/estudio/admin): semáforo, score, patrimonio.
    Inversor: ya lo ve en su suite; acá se omite.
    """
    if str(ctx.get("user_role", "")).lower() == "inversor":
        return
    if df_ag is None or df_ag.empty:
        return

    from services.diagnostico_cartera import diagnosticar

    diag = ctx.get("ultimo_diagnostico")
    nombre = str(ctx.get("cliente_nombre", "") or "").split("|")[0].strip()
    if not nombre:
        nombre = "Cliente"
    ccl = float(ctx.get("ccl") or 1150.0)
    perfil = str(ctx.get("cliente_perfil", "Moderado"))

    if diag is None:
        try:
            diag = diagnosticar(
                df_ag=df_ag,
                perfil=perfil,
                horizonte_label=str(ctx.get("cliente_horizonte_label") or ctx.get("horizonte_label") or "1 año"),
                metricas=dict(ctx.get("metricas") or {}),
                ccl=ccl,
                universo_df=ctx.get("universo_df"),
                senales_salida=None,
                cliente_nombre=str(ctx.get("cliente_nombre", "") or ""),
            )
        except Exception as exc:
            log_degradacion(
                __name__,
                "resumen_cliente_diagnostico_fallo",
                exc,
                cliente=str(ctx.get("cliente_nombre", "")),
            )
            return

    sem_v = str(getattr(getattr(diag, "semaforo", None), "value", "neutro") or "neutro")
    score = float(getattr(diag, "score_total", 0) or 0)
    sem_color = {"verde": "#10b981", "amarillo": "#f59e0b", "rojo": "#ef4444"}.get(sem_v, "#64748b")
    sem_emoji = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(sem_v, "⚪")

    valor_ars = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()) if "VALOR_ARS" in df_ag.columns else 0.0
    valor_usd = valor_ars / max(ccl, 1.0)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)
    pnl = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0)
    pnl_color = "var(--c-green)" if pnl >= 0 else "var(--c-red)"

    obs_list = getattr(diag, "observaciones", []) or []
    obs_txt = ""
    if obs_list:
        o = obs_list[0]
        obs_txt = html.escape(
            f"{getattr(o, 'icono', '')} {getattr(o, 'titulo', '')}".strip()[:55]
        )

    nom_esc = html.escape(nombre)
    perf_esc = html.escape(perfil)
    st.markdown(
        f"""
    <div class="mq-cartera-resumen" style="border-left-color:{sem_color};">
        <div class="mq-cartera-resumen-left">
            <span class="mq-cartera-resumen-emoji">{sem_emoji}</span>
            <div>
                <div class="mq-cartera-resumen-title mq-font-title">{nom_esc}</div>
                <div class="mq-cartera-resumen-sub mq-font-body">
                    {perf_esc} · Score {score:.0f}/100 · {obs_txt}
                </div>
            </div>
        </div>
        <div class="mq-cartera-resumen-right">
            <div class="mq-cartera-resumen-kpi">
                <div class="mq-cartera-resumen-kpi-label">Patrimonio</div>
                <div class="mq-cartera-resumen-kpi-value">
                    USD {valor_usd:,.0f}
                </div>
            </div>
            <div class="mq-cartera-resumen-kpi">
                <div class="mq-cartera-resumen-kpi-label">Resultado ref.</div>
                <div class="mq-cartera-resumen-kpi-value" style="color:{pnl_color};">
                    {'+' if pnl >= 0 else ''}{pnl:.1f}%
                </div>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_tab_cartera(ctx: dict) -> None:
    df_ag           = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
    if df_ag is not None and not df_ag.empty:
        _render_resumen_cliente_cartera(ctx, df_ag)
    tickers_cartera = ctx["tickers_cartera"]
    coverage = ctx.get("price_coverage_pct", 100.0)
    sin_precio = ctx.get("tickers_sin_precio", [])
    _render_cobertura_precios(ctx)
    precios_dict    = ctx["precios_dict"]
    ccl             = ctx["ccl"]
    cartera_activa  = ctx["cartera_activa"]
    prop_nombre     = ctx["prop_nombre"]
    df_clientes     = ctx["df_clientes"]
    df_analisis     = ctx["df_analisis"]
    metricas        = ctx.get("metricas", {})
    PESO_MAX_CARTERA = ctx["PESO_MAX_CARTERA"]
    dbm             = ctx["dbm"]
    cs              = ctx["cs"]
    m23svc          = ctx["m23svc"]
    ab              = ctx["ab"]
    lm              = ctx["lm"]
    bi              = ctx["bi"]
    gr              = ctx["gr"]
    engine_data     = ctx["engine_data"]
    asignar_sector  = ctx["asignar_sector"]
    _boton_exportar = ctx["_boton_exportar"]
    BASE_DIR        = ctx["BASE_DIR"]
    cliente_perfil  = ctx.get("cliente_perfil", "Moderado")
    _can_write      = _can_action_rbac(ctx, "write")
    _is_viewer      = not _can_write

    _is_inversor = str(ctx.get("user_role", "admin")).lower() == "inversor"

    if _is_inversor:
        sub_pos, sub_rendtipo, sub_lm = st.tabs([
            "📊 Posición actual",
            "📈 Rendimiento",
            "📋 Libro mayor",
        ])
        sub_multi = None
    else:
        sub_pos, sub_rendtipo, sub_multi, sub_lm = st.tabs([
            "📊 Posición actual",
            "📈 Rendimiento",
            "🌐 Vista consolidada",
            "📋 Libro mayor",
        ])

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 1: POSICIÓN NETA
    # ══════════════════════════════════════════════════════════════════
    with sub_pos:
        _render_posicion_neta(
            ctx, df_ag, tickers_cartera, coverage, sin_precio,
            precios_dict, ccl, cartera_activa, prop_nombre,
            df_analisis, metricas, PESO_MAX_CARTERA,
            cs, m23svc, ab, asignar_sector, _boton_exportar,
            cliente_perfil)

    with sub_rendtipo:
        _render_rendimiento_tipo(ctx, df_ag, cartera_activa, ccl, cs, _boton_exportar)

    if sub_multi is not None:
        with sub_multi:
            _render_vista_consolidada(ctx, df_ag, df_analisis, engine_data, ccl)

    with sub_lm:
        _render_libro_mayor(
            ctx, df_ag, tickers_cartera, precios_dict, ccl,
            cartera_activa, df_clientes, cs, dbm, lm, bi, gr,
            engine_data, BASE_DIR, _boton_exportar)



def _render_rendimiento_tipo(ctx, df_ag, cartera_activa, ccl, cs, _boton_exportar):
    """Sub-tab 2: Rendimiento por Tipo de Activo BYMA."""
    st.subheader("Cómo rindió cada parte de la cartera")
    st.caption(
        "Comparativa por tipo de activo: acciones, bonos, fondos, etc.",
    )

    if cartera_activa == "-- Todas las carteras --":
        st.info(
            "Elegí una **cartera concreta** en el sidebar: **📁 Cartera activa** "
            "(debajo del cliente). La opción «-- Todas las carteras --» no carga posiciones en esta vista."
        )
    elif df_ag.empty:
        st.warning("La cartera seleccionada no tiene posiciones.")
    else:
        df_trans_ctx = ctx.get("df_trans", pd.DataFrame())

        df_rend = cs.calcular_rendimiento_por_tipo(df_ag, df_trans_ctx)
        resumen_global = cs.calcular_rendimiento_global_anual(df_rend, df_trans_ctx)

        if df_rend.empty:
            st.info("No hay suficientes datos para calcular rendimientos por tipo.")
        else:
            # ── KPIs globales ──────────────────────────────────────────────────
            kg1, kg2, kg3, kg4 = st.columns(4)
            with kg1:
                st.metric(
                    "CAGR Global ARS",
                    f"{resumen_global['cagr_global_ars']:+.1f}%",
                    help="Retorno anual compuesto de toda la cartera en pesos",
                )
            with kg2:
                st.metric(
                    "CAGR Global USD",
                    f"{resumen_global['cagr_global_usd']:+.1f}%",
                    help="Retorno anual compuesto en dólares (sin efecto devaluación ARS)",
                )
            with kg3:
                st.metric(
                    "Mejor clase",
                    resumen_global["mejor_tipo"],
                    delta="↑ top performer",
                    delta_color="normal",
                )
            with kg4:
                st.metric(
                    "Peor clase",
                    resumen_global["peor_tipo"],
                    delta="↓ rezagado",
                    delta_color="inverse",
                )

            st.divider()

            col_g1, col_g2 = st.columns([3, 2])

            with col_g1:
                # ── Barras comparativas ARS vs USD por tipo ────────────────────
                import plotly.graph_objects as go
                fig_barras = go.Figure()
                tipos_sorted = df_rend.sort_values("Inv. ARS", ascending=False)["Tipo"].tolist()
                fig_barras.add_trace(go.Bar(
                    name="Rend. ARS %",
                    x=tipos_sorted,
                    y=[df_rend.set_index("Tipo").loc[t, "Rend. ARS %"] for t in tipos_sorted],
                    marker_color="#2196F3",
                    text=[f"{df_rend.set_index('Tipo').loc[t,'Rend. ARS %']:+.1f}%" for t in tipos_sorted],
                    textposition="outside",
                ))
                fig_barras.add_trace(go.Bar(
                    name="Rend. USD %",
                    x=tipos_sorted,
                    y=[df_rend.set_index("Tipo").loc[t, "Rend. USD %"] for t in tipos_sorted],
                    marker_color="#FF9800",
                    text=[f"{df_rend.set_index('Tipo').loc[t,'Rend. USD %']:+.1f}%" for t in tipos_sorted],
                    textposition="outside",
                ))
                fig_barras.update_layout(
                    title="Rendimiento Total por Clase de Activo",
                    barmode="group", height=340,
                    xaxis_title="", yaxis_title="%",
                    legend=dict(orientation="h", y=-0.2),
                    margin=dict(t=50, b=40, l=20, r=20),
                )
                st.plotly_chart(fig_barras, use_container_width=True, key="barras_rend_tipo")

            with col_g2:
                # ── CAGR anualizado por tipo ───────────────────────────────────
                fig_cagr = go.Figure()
                colores_cagr = [
                    "#4CAF50" if v >= 0 else "#F44336"
                    for v in df_rend["CAGR ARS %"].tolist()
                ]
                fig_cagr.add_trace(go.Bar(
                    name="CAGR ARS %",
                    x=df_rend["Tipo"].tolist(),
                    y=df_rend["CAGR ARS %"].tolist(),
                    marker_color=colores_cagr,
                    text=[f"{v:+.1f}%" for v in df_rend["CAGR ARS %"].tolist()],
                    textposition="outside",
                ))
                fig_cagr.update_layout(
                    title="CAGR Anualizado por Tipo (ARS)",
                    height=340, showlegend=False,
                    xaxis_title="", yaxis_title="% anual",
                    margin=dict(t=50, b=40, l=20, r=20),
                )
                st.plotly_chart(fig_cagr, use_container_width=True, key="cagr_tipo")

            # ── Waterfall: contribución al P&L total ──────────────────────────
            # Mapeo interno → etiqueta legible
            _LABEL_TIPO = {
                "CEDEAR":       "CEDEARs",
                "ACCION_LOCAL": "Acciones Arg.",
                "BONO":         "Bonos ARS",
                "BONO_USD":     "Bonos USD",
                "LETRA":        "Letras",
                "ON":           "Oblig. Neg.",
                "ON_USD":       "Oblig. Neg. USD",
                "FCI":          "Fondos (FCI)",
            }
            # Agrupación Renta Fija / Variable
            _RF = {"BONO", "BONO_USD", "LETRA", "ON", "ON_USD"}
            _RV = {"CEDEAR", "ACCION_LOCAL", "FCI"}

            _wf_col1, _wf_col2, _wf_col3 = st.columns([2, 2, 2])
            with _wf_col1:
                _wf_moneda = st.radio(
                    "Moneda del gráfico", ["ARS", "USD"],
                    horizontal=True, key="wf_moneda"
                )
            with _wf_col2:
                _wf_grupo = st.radio(
                    "Agrupación", ["Por tipo", "Renta Fija / Variable"],
                    horizontal=True, key="wf_grupo"
                )

            _pnl_col = "P&L ARS" if _wf_moneda == "ARS" else "P&L USD aprox"
            _moneda_sym = "$" if _wf_moneda == "ARS" else "U$S"

            _df_wf_base = df_rend.copy()

            if _wf_grupo == "Renta Fija / Variable":
                _df_wf_base["_GRUPO"] = _df_wf_base["Tipo"].apply(
                    lambda t: "Renta Fija" if t in _RF else "Renta Variable"
                )
                _df_wf_base = (
                    _df_wf_base.groupby("_GRUPO", as_index=False)
                    .agg({_pnl_col: "sum"})
                    .rename(columns={"_GRUPO": "Tipo"})
                )
            else:
                _df_wf_base["Tipo"] = _df_wf_base["Tipo"].map(
                    lambda t: _LABEL_TIPO.get(t, t)
                )
                _df_wf_base = _df_wf_base[["Tipo", _pnl_col]]

            _df_wf_base = _df_wf_base.sort_values(_pnl_col, ascending=False)
            _pnl_total = _df_wf_base[_pnl_col].sum()
            _medidas_wf = ["relative"] * len(_df_wf_base) + ["total"]
            _valores_wf = _df_wf_base[_pnl_col].tolist() + [_pnl_total]
            _labels_wf  = _df_wf_base["Tipo"].tolist() + ["TOTAL"]

            fig_wf = go.Figure(go.Waterfall(
                orientation="v",
                measure=_medidas_wf,
                x=_labels_wf,
                y=_valores_wf,
                connector={"line": {"color": "#424242"}},
                increasing={"marker": {"color": "#4CAF50"}},
                decreasing={"marker": {"color": "#F44336"}},
                totals={"marker": {"color": "#2196F3"}},
                text=[f"{_moneda_sym}{abs(v):,.0f}" for v in _valores_wf],
                textposition="outside",
            ))
            fig_wf.update_layout(
                title=f"Contribución al P&L Total ({_wf_moneda})",
                height=380,
                margin=dict(t=50, b=30, l=20, r=20),
                yaxis_title=_wf_moneda,
            )
            st.plotly_chart(fig_wf, use_container_width=True, key="waterfall_pnl")



def _render_historial_timeline(ctx, df_ag, ccl):
    """Sub-tab 3: Historial Timeline + Heatmap mensual."""
    st.subheader("📅 Historial de Posiciones — Timeline")
    if df_ag.empty:
        st.info("Seleccioná una cartera activa para ver el historial.")
    else:
        try:
            import sys
            from pathlib import Path as _Path
            _svc_dir = str(_Path(__file__).resolve().parent.parent / "services")
            if _svc_dir not in sys.path:
                sys.path.insert(0, _svc_dir)
            from timeline_posiciones import render_timeline_posiciones

            # Preparar df con columnas que espera el timeline
            _df_tl = df_ag.copy()

            # FECHA_INICIAL: primera compra de cada ticker en df_trans
            _df_trans_tl = ctx.get("df_trans", pd.DataFrame())
            if not _df_trans_tl.empty and "FECHA_COMPRA" in _df_trans_tl.columns:
                _fecha_col_tl = _df_trans_tl[_df_trans_tl["CANTIDAD"] > 0].groupby("TICKER")["FECHA_COMPRA"].min().reset_index()
                _fecha_col_tl.columns = ["TICKER", "FECHA_INICIAL"]
                _df_tl = _df_tl.merge(_fecha_col_tl, on="TICKER", how="left")
            else:
                _df_tl["FECHA_INICIAL"] = str(datetime.now().date())

            # Renombrar columnas al formato esperado por render_timeline_posiciones
            _df_tl = _df_tl.rename(columns={
                "CANTIDAD_TOTAL": "Cantidad",
                "PPC_USD_PROM":   "PPC_USD",
            })
            _df_tl["Ticker"] = _df_tl["TICKER"]

            render_timeline_posiciones(
                df_posiciones   = _df_tl,
                precios_actuales= ctx.get("precios_dict", {}),
                ccl             = ctx.get("ccl", 1465.0),
            )
        except Exception as e:
            # Fallback: gráfico de barras simple
            df_bar = df_ag.copy()
            if "VALOR_ARS" in df_bar.columns and "TICKER" in df_bar.columns:
                _color_col = "PNL_PCT" if "PNL_PCT" in df_bar.columns else "VALOR_ARS"
                fig_bar = px.bar(
                    df_bar.sort_values("VALOR_ARS", ascending=True),
                    x="VALOR_ARS", y="TICKER", orientation="h",
                    color=_color_col,
                    color_continuous_scale="RdYlGn",
                    title="Cartera actual por valor ARS",
                    labels={"VALOR_ARS": "Valor ARS", "TICKER": "Activo"},
                )
                fig_bar.update_layout(template="plotly_dark", height=max(300, len(df_bar) * 42))
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.warning(f"Timeline: {e}")

        # MQ2-V7: Heatmap de retornos mensuales (calendar heatmap)
        st.divider()
        st.markdown("##### 🗓️ Heatmap de Retornos Mensuales")
        _df_trans_hm = ctx.get("df_trans", pd.DataFrame())
        if not _df_trans_hm.empty:
            try:
                import plotly.graph_objects as _go_hm_safe
                _tickers_hm = df_ag["TICKER"].str.upper().tolist()[:5] if not df_ag.empty else []
                if _tickers_hm:
                    _hist_hm = ctx.get("cached_historico", lambda t,p: pd.DataFrame())(tuple(_tickers_hm), "2y")
                    if not _hist_hm.empty:
                        _pesos_hm = {t: 1.0/len(_tickers_hm) for t in _tickers_hm if t in _hist_hm.columns}
                        _ret_hm = _hist_hm[[t for t in _tickers_hm if t in _hist_hm.columns]].pct_change().dropna()
                        _w_hm = [_pesos_hm.get(t, 0) for t in _ret_hm.columns]
                        _ret_port_hm = (_ret_hm.values @ _w_hm)
                        _series_hm = pd.Series(_ret_port_hm, index=_ret_hm.index)
                        _monthly_hm = _series_hm.resample("ME").apply(lambda x: (1+x).prod()-1)
                        _hm_df = _monthly_hm.to_frame("retorno")
                        _hm_df["anio"] = _hm_df.index.year
                        _hm_df["mes"]  = _hm_df.index.month
                        _pivot_hm = _hm_df.pivot(index="anio", columns="mes", values="retorno")
                        _pivot_hm.columns = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][:len(_pivot_hm.columns)]
                        fig_hm = _go_hm_safe.Figure(_go_hm_safe.Heatmap(
                            z=(_pivot_hm.values * 100).tolist(),
                            x=_pivot_hm.columns.tolist(),
                            y=_pivot_hm.index.tolist(),
                            colorscale="RdYlGn", zmid=0,
                            text=[[f"{v:.1f}%" if pd.notna(v) else "" for v in row] for row in _pivot_hm.values * 100],
                            texttemplate="%{text}",
                        ))
                        fig_hm.update_layout(
                            title="Retorno Mensual de la Cartera (%)", height=300,
                            template="plotly_dark", margin=dict(t=40, b=20, l=60, r=20),
                        )
                        st.plotly_chart(fig_hm, use_container_width=True, key="heatmap_mensual")
            except Exception as _e_hm:
                st.caption(f"Heatmap no disponible: {_e_hm}")


def _render_vista_consolidada(ctx, df_ag, df_analisis, engine_data, ccl):
    """Sub-tab 4: Dashboard Consolidado multicuenta."""
    st.subheader("🌐 Dashboard Consolidado — Todas las Carteras")
    if not engine_data or df_analisis.empty:
        st.info("Cargá al menos una cartera para ver el dashboard consolidado.")
    else:
        try:
            import sys
            from pathlib import Path as _Path
            _svc_d = str(_Path(__file__).resolve().parent.parent / "services")
            if _svc_d not in sys.path:
                sys.path.insert(0, _svc_d)
            try:
                from dashboard_ejecutivo import render_dashboard_ejecutivo
                _df_trans = ctx.get("df_trans", pd.DataFrame())
                if not _df_trans.empty:
                    render_dashboard_ejecutivo(_df_trans, engine_data, ccl)
                else:
                    st.info("Importá operaciones de múltiples carteras para ver el dashboard consolidado.")
            except ImportError:
                # Vista simplificada si el módulo no está disponible
                _df_trans_mc = ctx.get("df_trans", pd.DataFrame())
                if not _df_trans_mc.empty and "CARTERA" in _df_trans_mc.columns:
                    carteras_todas = _df_trans_mc["CARTERA"].dropna().unique().tolist()
                    st.markdown(f"**{len(carteras_todas)} carteras detectadas:**")
                    resumen_rows = []
                    for _c in carteras_todas:
                        _df_c = engine_data.agregar_cartera(_df_trans_mc, _c)
                        if not _df_c.empty:
                            resumen_rows.append({
                                "Cartera": _c,
                                "Posiciones": len(_df_c),
                                "Tickers": ", ".join(_df_c["TICKER"].tolist()[:5]),
                            })
                    if resumen_rows:
                        _df_res_rows = pd.DataFrame(resumen_rows)
                        st.dataframe(
                            _df_res_rows,
                            use_container_width=True,
                            hide_index=True,
                            height=dataframe_auto_height(_df_res_rows, min_px=120, max_px=280),
                        )
                else:
                    st.info("No hay datos de múltiples carteras.")

                # MQ2-U8: Comparador multi-cartera con métricas clave
                if not _df_trans_mc.empty and "CARTERA" in _df_trans_mc.columns:
                    st.divider()
                    st.markdown("#### 📊 Comparador de métricas entre carteras")
                    _carteras_cmp = _df_trans_mc["CARTERA"].dropna().unique().tolist()
                    if len(_carteras_cmp) > 1:
                        _metricas_cmp = []
                        for _cart_c in _carteras_cmp:
                            try:
                                _df_pos_c = engine_data.agregar_cartera(_df_trans_mc, _cart_c)
                                if not _df_pos_c.empty:
                                    _pnl_c  = _df_pos_c.get("PNL_ARS", pd.Series([0])).sum()
                                    _inv_c  = _df_pos_c.get("INV_ARS", pd.Series([0])).sum()
                                    _val_c  = _df_pos_c.get("VALOR_ARS", pd.Series([0])).sum()
                                    _rend_c = _pnl_c / _inv_c if _inv_c > 0 else 0.0
                                    _n_pos  = len(_df_pos_c)
                                    _max_peso = float(_df_pos_c.get("PESO_PCT", pd.Series([0])).max()) if "PESO_PCT" in _df_pos_c.columns else 0.0
                                    _metricas_cmp.append({
                                        "Cartera":       _cart_c,
                                        "Posiciones":    _n_pos,
                                        "Valor ARS":     _val_c,
                                        "Inv. ARS":      _inv_c,
                                        "P&L ARS":       _pnl_c,
                                        "Rend. %":       _rend_c * 100,
                                        "Concentración": _max_peso * 100,
                                    })
                            except Exception:
                                pass
                        if _metricas_cmp:
                            _df_cmp = pd.DataFrame(_metricas_cmp)
                            st.dataframe(_df_cmp, hide_index=True, use_container_width=True,
                                         column_config={
                                             "Valor ARS":  st.column_config.NumberColumn("Valor ARS", format="$%.0f"),
                                             "Inv. ARS":   st.column_config.NumberColumn("Inv. ARS", format="$%.0f"),
                                             "P&L ARS":    st.column_config.NumberColumn("P&L ARS", format="$%.0f"),
                                             "Rend. %":    st.column_config.NumberColumn("Rend. %", format="+%.1f%%"),
                                             "Concentración": st.column_config.ProgressColumn("Concentr. %", min_value=0, max_value=100, format="%.1f%%"),
                                         })
        except Exception as e:
            st.error(f"Error en dashboard consolidado: {e}")


