"""
ui/tab_riesgo.py — Tab 4: Riesgo & Simulación (Risk Analytics)
Dual-portfolio analysis: Cartera Actual + Cartera Óptima (de Tab 3)
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ── Glosario de métricas de riesgo en lenguaje humano (U39 Must) ─────────
_GLOSARIO_RIESGO = {
    "VaR 95%": (
        "En el 95% de los días, la cartera no pierde más de este monto. "
        "En el 5% peor, puede perder más."
    ),
    "CVaR / Expected Shortfall": (
        "Pérdida promedio en el peor 5% de días. Más conservador que el VaR."
    ),
    "Sharpe": (
        "Retorno por unidad de riesgo. Sharpe > 1 es bueno; > 2, excelente."
    ),
    "Sortino": (
        "Como Sharpe, pero penaliza solo las caídas (volatilidad negativa)."
    ),
    "Max Drawdown": (
        "Caída máxima desde el pico hasta el valle en el período. "
        "-20% = la cartera cayó 20% desde su máximo."
    ),
    "Beta": (
        "Sensibilidad al mercado. Beta = 1: se mueve igual que el S&P 500. "
        "Beta < 1: más estable."
    ),
    "Volatilidad anualizada": (
        "Dispersión del retorno. < 10%: estable. 10-20%: normal. > 20%: alta variabilidad."
    ),
    "Calmar": (
        "Retorno anualizado dividido por el Max Drawdown. "
        "Mide eficiencia ajustada al riesgo de caída."
    ),
}
# Compat: tooltips y código que aún busque la clave corta "CVaR"
GLOSARIO_RIESGO = dict(_GLOSARIO_RIESGO)
GLOSARIO_RIESGO["CVaR"] = _GLOSARIO_RIESGO["CVaR / Expected Shortfall"]


def _tooltip_riesgo(metrica: str) -> str:
    return _GLOSARIO_RIESGO.get(metrica, GLOSARIO_RIESGO.get(metrica, ""))


def _run_montecarlo(w, ret_d, tickers_ok, n_sim, horiz, shock_ret, shock_vol, rf,
                    rng: np.random.Generator | None = None):
    """Helper: ejecuta Montecarlo y devuelve (ret_finales, valores, métricas)."""
    _rng = rng if rng is not None else np.random.default_rng(seed=42)
    w = w / w.sum() if w.sum() > 0 else w
    mu      = ret_d.mean().values + shock_ret
    cov_mat = ret_d.cov().values * (shock_vol ** 2)
    eps     = 1e-8 * np.eye(len(tickers_ok))
    L       = np.linalg.cholesky(cov_mat + eps)
    z       = _rng.normal(size=(horiz, n_sim, len(tickers_ok)))
    sh      = (z.reshape(-1, len(tickers_ok)) @ L.T).reshape(horiz, n_sim, len(tickers_ok))
    ret_sim = mu.reshape(1,1,-1) + sh
    ret_p   = np.sum(ret_sim * w.reshape(1,1,-1), axis=2)
    vals    = np.cumprod(1 + ret_p, axis=0)
    rf_fin  = vals[-1] - 1.0
    var95   = float(np.percentile(rf_fin, 5))
    cvar95  = float(rf_fin[rf_fin <= var95].mean()) if np.any(rf_fin <= var95) else var95
    dds     = vals / np.maximum.accumulate(vals, axis=0) - 1.0
    mdd95   = float(np.percentile(dds.min(axis=0), 5))
    med_r   = float(rf_fin.mean())
    vol_r   = float(rf_fin.std())
    sharpe  = (med_r - rf * horiz / 252) / vol_r if vol_r > 0 else 0.0
    return rf_fin, vals, {"var95": var95, "cvar95": cvar95, "mdd95": mdd95,
                          "media": med_r, "vol": vol_r, "sharpe": sharpe}


def render_tab_riesgo(ctx: dict) -> None:
    _glos_visto = st.session_state.get("riesgo_glosario_visto", False)
    with st.expander("📖 Guía de métricas de riesgo", expanded=not _glos_visto):
        for _met, _desc in _GLOSARIO_RIESGO.items():
            st.markdown(f"**{_met}:** {_desc}")
        st.session_state["riesgo_glosario_visto"] = True
    st.markdown("")

    df_ag_guard = ctx.get("df_ag")
    if df_ag_guard is None or df_ag_guard.empty:
        st.info(
            "Riesgo y simulación necesitan **al menos un activo en cartera** "
            "(pesos, volatilidad conjunta y escenarios)."
        )
        st.markdown(
            "**Próximo paso:** en **Cartera y Libro Mayor** cargá posiciones o pedí al cliente "
            "que use **Empezar de cero con sugerencia** en su vista Inversor."
        )
        return

    RISK_FREE_RATE   = ctx["RISK_FREE_RATE"]

    N_SIM_DEFAULT    = ctx["N_SIM_DEFAULT"]
    df_ag            = ctx["df_ag"]
    tickers_cartera  = ctx["tickers_cartera"]
    prop_nombre      = ctx["prop_nombre"]
    bt               = ctx["bt"]
    ab               = ctx["ab"]
    RiskEngine       = ctx["RiskEngine"]
    cached_historico = ctx["cached_historico"]

    # Pesos dual: actuales vs óptimos
    pesos_opt   = st.session_state.get("pesos_opt", {})
    pesos_act   = st.session_state.get("pesos_actuales", {})
    modelo_opt  = st.session_state.get("modelo_opt", "Óptima")

    # Si no hay pesos actuales calculados, derivarlos de df_ag (equal weight fallback)
    if not pesos_act and not df_ag.empty:
        val_total = df_ag.get("VALOR_ARS", pd.Series(dtype=float)).sum()
        if val_total > 0:
            pesos_act = {str(r.get("TICKER","")): float(r.get("VALOR_ARS",0))/val_total
                         for _, r in df_ag.iterrows()}
        else:
            pesos_act = {t: 1/len(tickers_cartera) for t in tickers_cartera}

    tiene_dual = bool(pesos_act) and bool(pesos_opt)

    (sub_bt, sub_stress, sub_corr, sub_ccl, sub_bt_real,
     sub_hist, sub_beta, sub_roll_corr, sub_cf_var, sub_sens, sub_contrib, sub_escenarios) = st.tabs([
        "📈 Backtest vs Benchmark",
        "🔮 Stress Test Montecarlo",
        "🔥 Correlaciones",
        "💱 Escenarios CCL",
        "📊 Backtest Real",
        "📉 Histograma Retornos",
        "🧮 Descomposición Beta",
        "📡 Correlación Dinámica",      # MQ2-U3
        "📐 VaR Cornish-Fisher",        # MQ2-U4
        "⚙️ Sensibilidad Parámetros",   # MQ2-U5
        "🎯 Contribución Marginal Riesgo",  # MQ2-U6
        "📜 Escenarios Históricos",     # S4: StressTestEngine
    ])

    # ── SUB-TAB: BACKTEST DUAL ───────────────────────────────────────────────────
    with sub_bt:
        st.subheader("📈 Backtest vs Benchmark — Cartera Actual + Óptima")
        if tiene_dual:
            st.success(f"Comparando: **Cartera Actual** vs **Cartera Óptima ({modelo_opt})**")
        else:
            st.info("Para ver el análisis dual ejecutá la **Comparativa** en Tab 3. "
                    "Por ahora se muestra solo la cartera óptima.")

        pesos_bt  = pesos_opt if pesos_opt else pesos_act
        if not pesos_bt:
            st.warning("Primero ejecutá la optimización en Tab 3.")
        else:
            col_bt1, col_bt2, col_bt3, col_bt4 = st.columns(4)
            with col_bt1:
                period_bt = st.selectbox("Período:", ["1y","2y","3y","5y"], index=1, key="riesgo_period")
            with col_bt2:
                benchmark_bt = st.selectbox("Benchmark:", ["SPY","QQQ","EWZ"], index=0, key="riesgo_bench")
            with col_bt3:
                rebalanceo_bt = st.checkbox("Rebalanceo mensual", value=True, key="riesgo_reb")
            with col_bt4:
                costo_rb_bt = st.slider(
                    "Costo rebalanceo:", 0.0, 0.02, 0.006, 0.001, key="riesgo_costo_rb",
                    help="Fracción del turnover (comisión + spread) por rebalanceo mensual.",
                )

            _hist_test_ss = st.session_state.get("lab_hist_test")
            _meta_split   = st.session_state.get("lab_split_meta")
            _oos_disponible = (
                isinstance(_hist_test_ss, pd.DataFrame)
                and not _hist_test_ss.empty
                and _meta_split is not None
                and getattr(_meta_split, "n_test", 0) > 0
            )
            usar_oos_bt = st.checkbox(
                "Backtest fuera de muestra (OOS) — tramo test del Lab Quant",
                value=False,
                key="riesgo_oos",
                disabled=not _oos_disponible,
                help="Usa solo fechas posteriores al entrenamiento definido en Tab 3 (Lab Quant con partición train/test).",
            )
            if _oos_disponible and _meta_split is not None:
                st.caption(
                    f"Train hasta **{_meta_split.train_end}** · Test desde **{_meta_split.test_start}** "
                    f"({_meta_split.n_test} filas)."
                )
            elif usar_oos_bt:
                st.warning("No hay tramo test en sesión. Ejecutá el Lab en Tab 3 con «Partición train/OOS» activada.")

            if st.button("⚡ Ejecutar Backtest Dual", type="primary", key="btn_bt_dual"):
                with st.spinner("Calculando equity curves..."):
                    try:
                        tickers_bt = list(pesos_bt.keys())
                        hist_nueva = cached_historico(tuple(tickers_bt), period_bt)

                        precios_opt_bt = hist_nueva
                        modo_label = "Ventana completa (puede incluir datos de entrenamiento)"
                        if usar_oos_bt and _oos_disponible:
                            ht = _hist_test_ss[[c for c in tickers_bt if c in _hist_test_ss.columns]]
                            if len(ht) >= 10:
                                precios_opt_bt = ht
                                modo_label = "Fuera de muestra (OOS) — solo tramo test"
                            else:
                                st.warning("Tramo test demasiado corto; se usa descarga completa.")

                        # Backtest cartera óptima
                        result_opt = bt.run_backtest(
                            precios=precios_opt_bt, pesos=pesos_opt if pesos_opt else pesos_bt,
                            benchmark_ticker=benchmark_bt, rf_anual=RISK_FREE_RATE,
                            periodo_label=period_bt, modelo=modelo_opt,
                            rebalanceo_mensual=rebalanceo_bt,
                            costo_rebalanceo_pct=float(costo_rb_bt),
                        )
                        st.session_state["bt_modo_evaluacion"] = modo_label

                        result_act = None
                        if tiene_dual:
                            tickers_act_bt = [t for t in pesos_act.keys() if t in precios_opt_bt.columns]
                            if len(tickers_act_bt) >= 2:
                                result_act = bt.run_backtest(
                                    precios=precios_opt_bt, pesos=pesos_act,
                                    benchmark_ticker=benchmark_bt, rf_anual=RISK_FREE_RATE,
                                    periodo_label=period_bt, modelo="Actual",
                                    rebalanceo_mensual=rebalanceo_bt,
                                    costo_rebalanceo_pct=float(costo_rb_bt),
                                )

                        st.session_state["bt_result"]      = result_opt
                        st.session_state["bt_result_act"]  = result_act

                        if result_opt is None:
                            st.error("No se pudo calcular el backtest óptimo.")
                        else:
                            _modo_ev = st.session_state.get("bt_modo_evaluacion", "")
                            if _modo_ev:
                                st.info(f"**Modo de evaluación:** {_modo_ev}")
                            if getattr(result_opt, "bench_fallback_usado", False):
                                st.warning(f"⚠️ Datos caché para {benchmark_bt}.")

                            # Métricas comparativas
                            st.divider()
                            col_lbl, col_opt, col_actm, col_bench = st.columns([1,2,2,2])
                            col_lbl.markdown("**Métrica**")
                            col_opt.markdown(f"**Óptima ({modelo_opt})**")
                            col_actm.markdown("**Actual**" if result_act else "*(sin datos)*")
                            col_bench.markdown(f"**{benchmark_bt}**")

                            metricas_rows = [
                                ("Ret. Anual",      f"{result_opt.retorno_anual_estrategia:.1%}",
                                 f"{result_act.retorno_anual_estrategia:.1%}" if result_act else "—",
                                 f"{result_opt.retorno_anual_benchmark:.1%}"),
                                ("Sharpe",          f"{result_opt.sharpe_estrategia:.2f}",
                                 f"{result_act.sharpe_estrategia:.2f}" if result_act else "—",
                                 f"{result_opt.sharpe_benchmark:.2f}"),
                                ("Sortino",         f"{result_opt.sortino_estrategia:.2f}",
                                 f"{result_act.sortino_estrategia:.2f}" if result_act else "—", "—"),
                                ("Max DD",          f"{result_opt.max_dd_estrategia:.1%}",
                                 f"{result_act.max_dd_estrategia:.1%}" if result_act else "—",
                                 f"{result_opt.max_dd_benchmark:.1%}"),
                                ("Calmar",          f"{result_opt.calmar_estrategia:.2f}", "—", "—"),
                                ("Info. Ratio",     f"{getattr(result_opt,'information_ratio',0):.3f}",
                                 f"{getattr(result_act,'information_ratio',0):.3f}" if result_act else "—", "—"),
                                ("Beta vs bench",   f"{getattr(result_opt,'beta_vs_benchmark',1):.3f}",
                                 f"{getattr(result_act,'beta_vs_benchmark',1):.3f}" if result_act else "—", "1.000"),
                                ("Correlación",     f"{getattr(result_opt,'correlacion_benchmark',1):.3f}",
                                 f"{getattr(result_act,'correlacion_benchmark',1):.3f}" if result_act else "—", "1.000"),
                            ]
                            df_met_bt = pd.DataFrame(metricas_rows,
                                                      columns=["Métrica", f"Óptima ({modelo_opt})", "Actual", benchmark_bt])
                            st.dataframe(df_met_bt, use_container_width=True, hide_index=True)

                            # Equity curve unificada
                            fechas_str = [str(f)[:10] for f in result_opt.fechas]
                            fig_eq_dual = go.Figure()
                            fig_eq_dual.add_trace(go.Scatter(
                                x=fechas_str, y=result_opt.equity_strategy,
                                name=f"Óptima ({modelo_opt})", line=dict(color="#27AE60", width=2.5)))
                            if result_act:
                                n_f = min(len(fechas_str), len(result_act.equity_strategy))
                                fig_eq_dual.add_trace(go.Scatter(
                                    x=fechas_str[:n_f], y=result_act.equity_strategy[:n_f],
                                    name="Actual", line=dict(color="#2E86AB", width=2)))
                            fig_eq_dual.add_trace(go.Scatter(
                                x=fechas_str, y=result_opt.equity_benchmark,
                                name=benchmark_bt, line=dict(color="#888", width=1.5, dash="dash")))
                            fig_eq_dual.add_hline(y=1.0, line_dash="dot", line_color="gray")
                            fig_eq_dual.update_layout(
                                title=f"Equity Curve Dual — {period_bt}",
                                template="plotly_dark", hovermode="x unified", height=420)
                            st.plotly_chart(fig_eq_dual, use_container_width=True)

                            # Alpha acumulado
                            fig_alpha = px.area(
                                pd.DataFrame({"Fecha": fechas_str, "Alpha": result_opt.alpha_acumulado}),
                                x="Fecha", y="Alpha",
                                title=f"Alpha Acumulado Óptima vs {benchmark_bt}",
                                color_discrete_sequence=["#27AE60"])
                            fig_alpha.add_hline(y=0, line_dash="solid", line_color="white")
                            fig_alpha.update_layout(template="plotly_dark")
                            st.plotly_chart(fig_alpha, use_container_width=True)

                    except Exception as e:
                        st.error(f"Error en backtest: {e}")

    # ── SUB-TAB: STRESS TEST DUAL ────────────────────────────────────────────────
    with sub_stress:
        st.subheader("🔮 Stress Test Montecarlo — Cartera Actual + Óptima")
        if tiene_dual:
            st.success(f"Simulando **dos carteras** en paralelo: Actual vs Óptima ({modelo_opt})")

        pesos_st = pesos_opt if pesos_opt else pesos_act
        if not pesos_st and not df_ag.empty:
            pesos_st = {t: 1.0 / len(tickers_cartera) for t in tickers_cartera}

        if not pesos_st:
            st.warning("Ejecutá la optimización (Tab 3) o cargá una cartera.")
        else:
            col_st1, col_st2, col_st3, col_st4 = st.columns(4)
            with col_st1:
                n_sim_st = st.selectbox("Simulaciones:", [1000, 3000, 5000, 10000], index=2, key="mc_nsim")
            with col_st2:
                horiz_st = st.selectbox("Horizonte (días):", [63, 126, 252, 504], index=2, key="mc_horiz")
            with col_st3:
                umbral_var = st.slider("Umbral VaR alerta (%):", -50, -5, -20, key="mc_umbral")
            with col_st4:
                mc_seed_st = st.number_input(
                    "Semilla MC:", min_value=0, max_value=2_147_483_647, value=42, step=1,
                    key="mc_seed_ui", help="Reproducibilidad: misma semilla ⇒ mismos resultados.",
                )

            escenarios_hist = {
                "Base (normal)":         {"shock_ret": 0.0,    "shock_vol": 1.0},
                "Crisis 2008 (-50%)":    {"shock_ret": -0.003, "shock_vol": 2.5},
                "COVID Mar 2020 (-34%)": {"shock_ret": -0.005, "shock_vol": 3.0},
                "Inflación 2022 (-19%)": {"shock_ret": -0.001, "shock_vol": 1.8},
            }
            esc_sel = st.selectbox("Escenario de estrés:", list(escenarios_hist.keys()), key="mc_esc")

            if st.button("⚡ Simular Montecarlo Dual", type="primary", key="btn_mc_dual"):
                with st.spinner(f"Corriendo {n_sim_st:,} escenarios × {horiz_st} días (dos carteras)..."):
                    try:
                        tickers_mc = list(pesos_st.keys())
                        hist_mc    = cached_historico(tuple(tickers_mc), "2y")
                        tickers_ok = [t for t in tickers_mc if t in hist_mc.columns]

                        if len(tickers_ok) < 1:
                            st.error("Sin datos históricos.")
                        else:
                            esc       = escenarios_hist[esc_sel]
                            ret_d_mc  = hist_mc[tickers_ok].pct_change().dropna()
                            _mc_rng   = np.random.default_rng(int(mc_seed_st))

                            w_opt_mc = np.array([pesos_opt.get(t, 0.0) for t in tickers_ok])
                            rf_opt, vals_opt, met_opt = _run_montecarlo(
                                w_opt_mc, ret_d_mc, tickers_ok, n_sim_st, horiz_st,
                                esc["shock_ret"], esc["shock_vol"], RISK_FREE_RATE, rng=_mc_rng)

                            rf_act_mc, vals_act_mc, met_act_mc = None, None, None
                            if tiene_dual and pesos_act:
                                w_act_mc = np.array([pesos_act.get(t, 0.0) for t in tickers_ok])
                                _mc_rng_act = np.random.default_rng(int(mc_seed_st) + 17)
                                rf_act_mc, vals_act_mc, met_act_mc = _run_montecarlo(
                                    w_act_mc, ret_d_mc, tickers_ok, n_sim_st, horiz_st,
                                    esc["shock_ret"], esc["shock_vol"], RISK_FREE_RATE, rng=_mc_rng_act)

                            # Métricas comparativas
                            st.divider()
                            df_met_mc = pd.DataFrame({
                                "Métrica": ["VaR 95%", "CVaR 95%", "Max DD 95%", "Retorno Medio", "Sharpe Sim."],
                                f"Óptima ({modelo_opt})": [
                                    f"{met_opt['var95']*100:.2f}%",
                                    f"{met_opt['cvar95']*100:.2f}%",
                                    f"{met_opt['mdd95']*100:.2f}%",
                                    f"{met_opt['media']*100:.1f}%",
                                    f"{met_opt['sharpe']:.2f}",
                                ],
                                "Actual": [
                                    f"{met_act_mc['var95']*100:.2f}%" if met_act_mc else "—",
                                    f"{met_act_mc['cvar95']*100:.2f}%" if met_act_mc else "—",
                                    f"{met_act_mc['mdd95']*100:.2f}%" if met_act_mc else "—",
                                    f"{met_act_mc['media']*100:.1f}%" if met_act_mc else "—",
                                    f"{met_act_mc['sharpe']:.2f}" if met_act_mc else "—",
                                ],
                            })
                            st.dataframe(df_met_mc, use_container_width=True, hide_index=True)

                            if met_opt["var95"] * 100 < umbral_var:
                                st.error(f"🚨 VaR Óptima {met_opt['var95']*100:.1f}% supera umbral {umbral_var}%")
                                ab.alerta_var_breach("CARTERA", met_opt["var95"], umbral_var / 100, prop_nombre)

                            # Histogramas superpuestos
                            fig_hist = go.Figure()
                            fig_hist.add_trace(go.Histogram(
                                x=rf_opt * 100, name=f"Óptima ({modelo_opt})",
                                nbinsx=60, opacity=0.6, marker_color="#27AE60"))
                            if rf_act_mc is not None:
                                fig_hist.add_trace(go.Histogram(
                                    x=rf_act_mc * 100, name="Actual",
                                    nbinsx=60, opacity=0.5, marker_color="#2E86AB"))
                            fig_hist.add_vline(x=met_opt["var95"]*100, line_dash="dash",
                                               line_color="#E74C3C", annotation_text="VaR Óptima")
                            fig_hist.update_layout(
                                barmode="overlay",
                                title=f"Distribución de Retornos — {esc_sel}",
                                template="plotly_dark", height=380)
                            st.plotly_chart(fig_hist, use_container_width=True)

                            # Trayectorias del óptimo
                            idx_s   = np.argsort(rf_opt)
                            n_show  = min(6, len(idx_s))
                            idx_sel = np.concatenate([idx_s[:n_show//2],
                                                      idx_s[len(idx_s)//2:len(idx_s)//2+n_show//2]])
                            df_tray = pd.DataFrame(
                                vals_opt[:, idx_sel],
                                columns=[f"Esc. {i+1}" for i in range(n_show)]
                            )
                            df_tray["Día"] = np.arange(1, horiz_st + 1)
                            fig_tray = px.line(df_tray, x="Día",
                                               y=[c for c in df_tray.columns if c != "Día"],
                                               title=f"Trayectorias Óptima — {esc_sel}")
                            fig_tray.update_layout(template="plotly_dark", showlegend=False)
                            st.plotly_chart(fig_tray, use_container_width=True)

                    except Exception as e:
                        st.error(f"Error en Montecarlo: {e}")

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB: CORRELACIONES (H2)
    # ══════════════════════════════════════════════════════════════════
    with sub_corr:
        st.subheader("🔥 Heatmap de Correlaciones — Cartera Activa")
        if not tickers_cartera:
            st.info("Seleccioná una cartera activa para ver las correlaciones.")
        else:
            col_c1, col_c2 = st.columns([2, 1])
            with col_c1:
                period_corr = st.selectbox("Período:", ["6mo","1y","2y"], index=1, key="corr_period")
            with col_c2:
                umbral_corr = st.slider("Umbral alerta pares:", 0.5, 0.95, 0.75, 0.05, key="corr_umbral")
            if st.button("🔥 Calcular correlaciones", key="btn_corr"):
                with st.spinner("Descargando datos de correlaciones..."):
                    try:
                        hist_c = cached_historico(tuple(tickers_cartera), period_corr)
                        tickers_c = [t for t in tickers_cartera if t in hist_c.columns]
                        if len(tickers_c) < 2:
                            st.error("Insuficientes datos históricos.")
                        else:
                            ret_c = hist_c[tickers_c].pct_change().dropna()
                            corr_mat = ret_c.corr()
                            # Heatmap
                            fig_hm = go.Figure(data=go.Heatmap(
                                z=corr_mat.values,
                                x=tickers_c, y=tickers_c,
                                colorscale="RdYlGn",
                                zmin=-1, zmax=1,
                                text=corr_mat.round(2).values,
                                texttemplate="%{text}",
                                textfont={"size": 10},
                            ))
                            fig_hm.update_layout(
                                title="Matriz de Correlaciones (Pearson, retornos diarios)",
                                height=420, template="plotly_dark",
                            )
                            st.plotly_chart(fig_hm, use_container_width=True)

                            # Alertas de pares altamente correlacionados
                            pares_alerta = []
                            for i in range(len(tickers_c)):
                                for j in range(i+1, len(tickers_c)):
                                    c = float(corr_mat.iloc[i, j])
                                    if abs(c) >= umbral_corr:
                                        pares_alerta.append({
                                            "Par": f"{tickers_c[i]} — {tickers_c[j]}",
                                            "Correlación": round(c, 3),
                                            "Tipo": "Alta positiva" if c > 0 else "Alta negativa",
                                        })
                            if pares_alerta:
                                st.warning(f"⚠️ {len(pares_alerta)} pares con correlación > {umbral_corr:.0%} — Riesgo de concentración")
                                st.dataframe(pd.DataFrame(pares_alerta), use_container_width=True, hide_index=True)
                            else:
                                st.success(f"✅ Ningún par supera el umbral de correlación de {umbral_corr:.0%}")

                            # Estadísticas
                            corr_vals = corr_mat.values[np.triu_indices_from(corr_mat.values, k=1)]
                            col_cs1, col_cs2, col_cs3 = st.columns(3)
                            with col_cs1:
                                st.metric("Correlación promedio", f"{corr_vals.mean():.3f}")
                            with col_cs2:
                                st.metric("Correlación máxima", f"{corr_vals.max():.3f}")
                            with col_cs3:
                                st.metric("Pares > umbral", len(pares_alerta))
                    except Exception as e:
                        st.error(f"Error en correlaciones: {e}")

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB: ESCENARIOS CCL (H8)
    # ══════════════════════════════════════════════════════════════════
    with sub_ccl:
        st.subheader("💱 Simulación de Escenarios de Tipo de Cambio")
        st.caption("Impacto en la cartera si el CCL varía respecto al valor actual")

        ccl_actual = ctx.get("ccl", 1500.0)
        valor_usd  = float(df_ag.get("VALOR_USD", pd.Series(dtype=float)).sum()) if not df_ag.empty else 0.0
        pnl_usd    = float(df_ag.get("PNL_USD", df_ag.get("PNL", pd.Series(dtype=float))).sum()) if not df_ag.empty else 0.0

        if valor_usd <= 0:
            st.info("No hay posiciones en cartera para simular escenarios de CCL.")
        else:
            st.markdown(f"**CCL actual:** ${ccl_actual:,.0f} | **Valor cartera:** USD {valor_usd:,.2f}")

            variaciones = [-60, -40, -20, -10, 0, +10, +20, +40, +60]
            rows_ccl = []
            for var_pct in variaciones:
                ccl_sim = ccl_actual * (1 + var_pct / 100)
                valor_ars_sim = valor_usd * ccl_sim
                pnl_ars_sim   = pnl_usd * ccl_sim
                rows_ccl.append({
                    "Variación CCL %": f"{var_pct:+.0f}%",
                    "CCL Simulado": round(ccl_sim, 0),
                    "Valor Cartera ARS": round(valor_ars_sim, 0),
                    "P&L ARS (aprox)": round(pnl_ars_sim, 0),
                    "Valor Cartera USD": round(valor_usd, 2),
                })

            df_ccl = pd.DataFrame(rows_ccl)
            # Highlight la fila actual (var = 0)
            def _ccl_color(row):
                if row["Variación CCL %"] == " +0%":
                    return ["background-color: rgba(46,134,171,0.2)"] * len(row)
                return [""] * len(row)

            st.dataframe(
                df_ccl.style.format({
                    "CCL Simulado": "{:,.0f}",
                    "Valor Cartera ARS": "${:,.0f}",
                    "P&L ARS (aprox)": "${:,.0f}",
                    "Valor Cartera USD": "${:,.2f}",
                }).apply(_ccl_color, axis=1), use_container_width=True, hide_index=True,
            )

            # Gráfico
            fig_ccl = go.Figure()
            fig_ccl.add_trace(go.Bar(
                x=df_ccl["Variación CCL %"],
                y=df_ccl["Valor Cartera ARS"],
                marker_color=["#E74C3C" if "−" in str(r) or "-" in str(r)
                               else "#27AE60" for r in df_ccl["Variación CCL %"]],
                name="Valor ARS",
            ))
            fig_ccl.update_layout(
                title="Valor de la Cartera ARS según escenario CCL",
                xaxis_title="Variación CCL", yaxis_title="Valor ARS",
                height=350, template="plotly_dark",
            )
            st.plotly_chart(fig_ccl, use_container_width=True)
            st.caption("💡 Los valores USD no cambian; solo varía la expresión en ARS.")

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB: BACKTEST REAL (H3) — desde historial de operaciones reales
    # ══════════════════════════════════════════════════════════════════
    with sub_bt_real:
        st.subheader("📊 Backtest Real — Equity Curve desde Operaciones Históricas")
        st.caption(
            "Reconstruye la equity curve real del cliente a partir de sus operaciones registradas. "
            "A diferencia del backtest teórico, usa los precios de compra/venta reales."
        )
        try:
            import sys
            from pathlib import Path as _Path
            sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
            from services.backtester_real import run_backtest_real

            _trans = ctx.get("engine_data")
            if _trans:
                _df_trans = _trans.cargar_transaccional()
            else:
                _df_trans = pd.DataFrame()

            _cartera_bt_real = ctx.get("cartera_activa", "")
            if _df_trans.empty or not _cartera_bt_real or _cartera_bt_real == "-- Todas las carteras --":
                st.info("Seleccioná una cartera activa para ver el backtest real.")
            else:
                _df_trans_cart = _df_trans[_df_trans["CARTERA"] == _cartera_bt_real].copy() \
                    if "CARTERA" in _df_trans.columns else _df_trans

                col_btr1, col_btr2 = st.columns(2)
                with col_btr1:
                    btr_bench = st.selectbox("Benchmark:", ["SPY","QQQ","EWZ","GLD"], key="btr_bench")
                with col_btr2:
                    btr_capital_inicial = st.number_input(
                        "Capital inicial USD:", min_value=100.0, value=10_000.0, step=1_000.0,
                        key="btr_capital"
                    )

                if st.button("📊 Calcular Backtest Real", type="primary", key="btn_btr"):
                    with st.spinner("Reconstruyendo equity curve real..."):
                        try:
                            res_btr = run_backtest_real(
                                df_transacciones=_df_trans_cart,
                                capital_inicial_usd=btr_capital_inicial,
                                benchmark_ticker=btr_bench,
                            )
                            if res_btr and not res_btr.get("error"):
                                st.session_state["btr_result"] = res_btr
                                st.toast("✅ Backtest real completado", icon="📊")
                            else:
                                st.warning(f"Backtest real: {res_btr.get('error','Sin datos')}")
                        except Exception as _e:
                            st.warning(f"Backtest real no disponible: {_e}")

                if "btr_result" in st.session_state:
                    _btr = st.session_state["btr_result"]
                    if _btr and "equity_real" in _btr:
                        fig_btr = go.Figure()
                        fig_btr.add_trace(go.Scatter(
                            x=_btr.get("fechas", []), y=_btr["equity_real"],
                            name="Cartera Real", line=dict(color="#27AE60", width=2.5)
                        ))
                        if "equity_benchmark" in _btr:
                            fig_btr.add_trace(go.Scatter(
                                x=_btr.get("fechas", []), y=_btr["equity_benchmark"],
                                name=btr_bench, line=dict(color="#888", dash="dash", width=1.5)
                            ))
                        fig_btr.update_layout(
                            title="Equity Curve Real vs Benchmark",
                            yaxis_title="Capital (base inicial)", height=400,
                            template="plotly_dark",
                        )
                        st.plotly_chart(fig_btr, use_container_width=True)

                        # Métricas del backtest real
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.metric("Retorno Real Total", f"{_btr.get('retorno_total',0):.1%}")
                        col_m2.metric("Max Drawdown Real",  f"{_btr.get('max_dd',0):.1%}")
                        col_m3.metric("Valor Final",        f"USD {_btr.get('valor_final',0):,.0f}")
        except ImportError:
            st.info("backtester_real.py no disponible. Verificá la instalación del módulo.")
        except Exception as _ex:
            st.warning(f"Backtest real: {_ex}")

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB: HISTOGRAMA DE RETORNOS (H9)
    # ══════════════════════════════════════════════════════════════════
    with sub_hist:
        st.subheader("📉 Distribución de Retornos — VaR y CVaR Históricos")
        st.caption(
            "Histograma de retornos diarios reales de la cartera. "
            "Permite visualizar fat tails y comparar VaR histórico vs Montecarlo."
        )

        pesos_hist_h9 = pesos_opt if pesos_opt else pesos_act
        if not pesos_hist_h9 or not tickers_cartera:
            st.info("Ejecutá el Lab Quant o seleccioná una cartera activa para ver el histograma.")
        else:
            _period_h9 = st.selectbox("Período histórico:", ["1y","2y","3y"], index=1, key="h9_period")
            if st.button("📉 Calcular distribución de retornos", key="btn_h9"):
                with st.spinner("Descargando histórico..."):
                    try:
                        _tickers_h9 = list(pesos_hist_h9.keys())
                        _hist_h9 = cached_historico(tuple(_tickers_h9), _period_h9)
                        _tickers_ok_h9 = [t for t in _tickers_h9 if t in _hist_h9.columns]

                        if len(_tickers_ok_h9) < 1:
                            st.error("Sin datos históricos.")
                        else:
                            _w_h9 = np.array([pesos_hist_h9.get(t, 0.0) for t in _tickers_ok_h9])
                            _w_h9 = _w_h9 / _w_h9.sum() if _w_h9.sum() > 0 else _w_h9
                            _ret_h9 = _hist_h9[_tickers_ok_h9].pct_change().dropna().values @ _w_h9
                            st.session_state["ret_hist_h9"] = _ret_h9
                    except Exception as _eh9:
                        st.error(f"Error: {_eh9}")

            if "ret_hist_h9" in st.session_state:
                _ret_h9 = st.session_state["ret_hist_h9"]
                _var95    = float(np.percentile(_ret_h9, 5))
                _cvar95   = float(_ret_h9[_ret_h9 <= _var95].mean()) if (_ret_h9 <= _var95).any() else _var95
                _var99    = float(np.percentile(_ret_h9, 1))
                _media    = float(_ret_h9.mean())
                _vol      = float(_ret_h9.std())
                _skew     = float(pd.Series(_ret_h9).skew())
                _kurt     = float(pd.Series(_ret_h9).kurt())

                # Métricas
                col_h1, col_h2, col_h3, col_h4 = st.columns(4)
                col_h1.metric("VaR 95% (diario)",  f"{_var95:.2%}", help="Pérdida máxima esperada el 5% de los días más malos")
                col_h2.metric("CVaR 95% (diario)", f"{_cvar95:.2%}", help="Pérdida promedio en el 5% peor de los días")
                col_h3.metric("VaR 99% (diario)",  f"{_var99:.2%}", help="Pérdida máxima esperada el 1% más extremo")
                col_h4.metric("Sesgo / Curtosis",  f"{_skew:.2f} / {_kurt:.2f}",
                               help="Sesgo < 0 = más pérdidas extremas. Curtosis > 3 = fat tails.")

                # Histograma
                _fig_hist = go.Figure()
                _fig_hist.add_trace(go.Histogram(
                    x=_ret_h9 * 100, nbinsx=60, name="Retornos diarios",
                    marker_color="#2E86AB", opacity=0.7,
                ))
                # Líneas VaR/CVaR
                for _val, _col, _lbl in [
                    (_var95 * 100, "#E74C3C", f"VaR 95% ({_var95:.2%})"),
                    (_cvar95 * 100, "#C0392B", f"CVaR 95% ({_cvar95:.2%})"),
                    (_var99 * 100, "#8E44AD", f"VaR 99% ({_var99:.2%})"),
                    (_media * 100, "#27AE60", f"Media ({_media:.3%})"),
                ]:
                    _fig_hist.add_vline(x=_val, line_dash="dash", line_color=_col,
                                        annotation_text=_lbl, annotation_position="top")
                _fig_hist.update_layout(
                    title="Distribución de Retornos Diarios — Cartera",
                    xaxis_title="Retorno diario (%)", yaxis_title="Frecuencia",
                    height=420, template="plotly_dark",
                )
                st.plotly_chart(_fig_hist, use_container_width=True)

                # Normal overlay para detectar fat tails
                _x_norm = np.linspace(_ret_h9.min(), _ret_h9.max(), 200) * 100
                _y_norm = (1 / (_vol * np.sqrt(2 * np.pi))) * np.exp(
                    -0.5 * ((_x_norm / 100 - _media) / _vol) ** 2
                ) * len(_ret_h9) * (_ret_h9.max() - _ret_h9.min()) / 60
                _fig_hist.add_trace(go.Scatter(
                    x=_x_norm, y=_y_norm, name="Normal teórica",
                    line=dict(color="#F39C12", dash="dot", width=2),
                ))
                st.plotly_chart(_fig_hist, use_container_width=True, key="fig_hist_overlay")

                st.caption(
                    f"**Interpretación:** Sesgo={_skew:.2f} ({'negativo → más pérdidas extremas' if _skew < 0 else 'positivo → más ganancias extremas'}), "
                    f"Curtosis excess={_kurt:.2f} ({'fat tails → distribución no-normal' if abs(_kurt) > 1 else 'distribución aproximadamente normal'})"
                )

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB: DESCOMPOSICIÓN BETA
    # ══════════════════════════════════════════════════════════════════════════
    with sub_beta:
        st.subheader("🧮 Descomposición Beta — Riesgo Sistemático vs Idiosincrático")
        st.caption(
            "Separa cuánto del riesgo total de la cartera se explica por el mercado (beta sistemático) "
            "y cuánto es propio de los activos seleccionados (riesgo idiosincrático). "
            "Alpha de Jensen = retorno en exceso del esperado por CAPM."
        )

        pesos_beta = pesos_opt if pesos_opt else pesos_act
        if not pesos_beta:
            st.warning("Ejecutá la optimización o seleccioná una cartera primero.")
        else:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                bench_beta = st.selectbox("Benchmark:", ["SPY", "QQQ", "EWZ", "IWM"],
                                          index=0, key="beta_bench")
                period_beta = st.selectbox("Período:", ["1y", "2y", "3y", "5y"],
                                           index=1, key="beta_period")

            with st.spinner("Calculando descomposición beta..."):
                try:
                    from risk_engine import calcular_descomposicion_beta

                    tickers_beta = list(pesos_beta.keys())
                    tickers_yf   = tickers_beta + [bench_beta]
                    # Usar cached_historico del ctx para evitar re-descargas en cada rerun
                    cached_hist_fn = ctx.get("cached_historico")
                    if cached_hist_fn:
                        hist_beta = cached_hist_fn(tuple(tickers_yf), period_beta)
                        if hist_beta is not None and not hist_beta.empty:
                            if "Close" in hist_beta.columns:
                                hist_beta = hist_beta["Close"].dropna(how="all")
                            else:
                                hist_beta = hist_beta.dropna(how="all")
                        else:
                            hist_beta = pd.DataFrame()
                    else:
                        # Fallback si cached_historico no está disponible en ctx
                        import yfinance as _yf_beta
                        hist_beta = _yf_beta.download(
                            tickers_yf, period=period_beta,
                            auto_adjust=True, progress=False
                        )["Close"].dropna(how="all")

                    if hist_beta.empty or bench_beta not in hist_beta.columns:
                        st.warning("No se pudo descargar el benchmark. Intentá con otro o más tarde.")
                    else:
                        ret_all   = hist_beta.pct_change(fill_method=None).dropna()
                        ret_bench = ret_all[bench_beta]

                        # Retorno del portfolio ponderado
                        tickers_ok = [t for t in tickers_beta if t in ret_all.columns]
                        if not tickers_ok:
                            st.warning("No hay tickers comunes con datos históricos.")
                        else:
                            w_arr = np.array([pesos_beta.get(t, 0) for t in tickers_ok])
                            if w_arr.sum() > 0:
                                w_arr = w_arr / w_arr.sum()
                            ret_port_serie = (ret_all[tickers_ok] * w_arr).sum(axis=1)

                            result_beta = calcular_descomposicion_beta(
                                retornos_cartera=ret_port_serie,
                                retorno_benchmark=ret_bench,
                                retornos_individuales=ret_all[tickers_ok],
                            )

                            # ── KPIs superiores ───────────────────────────────────────
                            kb1, kb2, kb3, kb4 = st.columns(4)
                            with kb1:
                                st.metric(
                                    "β Portfolio",
                                    f"{result_beta['beta_portfolio']:.2f}",
                                    help="Beta > 1: más volátil que el mercado. Beta < 1: más defensivo.",
                                )
                            with kb2:
                                st.metric(
                                    "R² (% explicado por mercado)",
                                    f"{result_beta['r2_portfolio']*100:.1f}%",
                                    help="Porcentaje de la varianza del portfolio explicado por el benchmark.",
                                )
                            with kb3:
                                alpha_color = "normal" if result_beta["alpha_jensen_anual"] >= 0 else "inverse"
                                st.metric(
                                    "Alpha de Jensen (anual)",
                                    f"{result_beta['alpha_jensen_anual']:+.2f}%",
                                    delta=f"{'Genera' if result_beta['alpha_jensen_anual']>=0 else 'Destruye'} valor vs CAPM",
                                    delta_color=alpha_color,
                                    help="Retorno en exceso del esperado por CAPM. Positivo = el portfolio supera al mercado ajustado por riesgo.",
                                )
                            with kb4:
                                st.metric(
                                    "Volatilidad total",
                                    f"{result_beta['riesgo_total_anual']:.1f}%",
                                    help="Volatilidad anualizada del portfolio.",
                                )

                            _fac_cols = [c for c in ("SPY", "QQQ", "EEM") if c in hist_beta.columns]
                            _u_cols = list(dict.fromkeys([t for t in tickers_ok if t in hist_beta.columns] + _fac_cols))
                            if len(_u_cols) >= 2 and _fac_cols:
                                try:
                                    _sub = hist_beta[_u_cols].dropna(how="all").ffill().bfill()
                                    if _sub.shape[0] > 40:
                                        _re_fac = RiskEngine(_sub)
                                        _pw = {
                                            t: float(pesos_beta.get(t, 0.0))
                                            for t in tickers_ok if t in _re_fac.activos
                                        }
                                        _ts = sum(_pw.values())
                                        if _ts > 1e-12:
                                            _pw = {k: v / _ts for k, v in _pw.items()}
                                        _fac = _re_fac.calcular_factor_exposure(_pw)
                                        st.markdown("##### Exposición factorial (B04) — β vs SPY / QQQ / EEM")
                                        fx1, fx2, fx3 = st.columns(3)
                                        with fx1:
                                            st.metric("β SPY", f"{_fac.get('beta_spy', 0):.2f}")
                                        with fx2:
                                            st.metric("β QQQ", f"{_fac.get('beta_qqq', 0):.2f}")
                                        with fx3:
                                            st.metric("β EEM", f"{_fac.get('beta_eem', 0):.2f}")
                                except Exception:
                                    pass

                            st.divider()

                            # ── Gráfico de torta: descomposición del riesgo ───────────────
                            col_g1, col_g2 = st.columns(2)
                            with col_g1:
                                fig_pie = go.Figure(go.Pie(
                                    labels=["Riesgo Sistemático (β)", "Riesgo Idiosincrático"],
                                    values=[
                                        result_beta["riesgo_sistematico_pct"],
                                        result_beta["riesgo_idiosinc_pct"],
                                    ],
                                    hole=0.5,
                                    marker_colors=["#2196F3", "#FF9800"],
                                    textinfo="label+percent",
                                ))
                                fig_pie.update_layout(
                                    title="Composición del Riesgo Total",
                                    height=300, margin=dict(t=50, b=20, l=20, r=20),
                                    showlegend=False,
                                )
                                st.plotly_chart(fig_pie, use_container_width=True, key="beta_pie")

                            with col_g2:
                                # Barras: riesgo total vs sistemático vs idiosincrático
                                fig_vol = go.Figure()
                                fig_vol.add_trace(go.Bar(
                                    name="Total", x=["Volatilidad"],
                                    y=[result_beta["riesgo_total_anual"]],
                                    marker_color="#9C27B0",
                                ))
                                fig_vol.add_trace(go.Bar(
                                    name="Sistemático", x=["Volatilidad"],
                                    y=[result_beta["riesgo_sistematico_anual"]],
                                    marker_color="#2196F3",
                                ))
                                fig_vol.add_trace(go.Bar(
                                    name="Idiosincrático", x=["Volatilidad"],
                                    y=[result_beta["riesgo_idiosinc_anual"]],
                                    marker_color="#FF9800",
                                ))
                                fig_vol.update_layout(
                                    title="Volatilidad Anualizada (%)",
                                    barmode="group", height=300,
                                    margin=dict(t=50, b=20, l=20, r=20),
                                    yaxis_title="%",
                                )
                                st.plotly_chart(fig_vol, use_container_width=True, key="beta_vol")

                            # ── Tabla beta por activo ─────────────────────────────────
                            if result_beta.get("por_activo"):
                                st.markdown("##### Beta por activo individual")
                                df_betas = pd.DataFrame([
                                    {"Ticker": t, **v}
                                    for t, v in result_beta["por_activo"].items()
                                ]).sort_values("beta", ascending=False).reset_index(drop=True)

                                # Clasificación por beta
                                def _clasif_beta(b):
                                    if b > 1.3:   return "Alto riesgo sistémico"
                                    elif b > 0.8: return "Moderado"
                                    elif b > 0:   return "Defensivo"
                                    else:         return "Inverso"

                                df_betas["Clasificación"] = df_betas["beta"].apply(_clasif_beta)

                                st.dataframe(
                                    df_betas,
                                    hide_index=True, use_container_width=True,
                                    column_config={
                                        "Ticker":        st.column_config.TextColumn("Ticker"),
                                        "beta":          st.column_config.NumberColumn("Beta", format="%.2f"),
                                        "r2":            st.column_config.NumberColumn("R²", format="%.2f"),
                                        "alpha_anual":   st.column_config.NumberColumn("Alpha % (anual)", format="+%.2f%%"),
                                        "vol_anual":     st.column_config.NumberColumn("Vol % (anual)", format="%.1f%%"),
                                        "Clasificación": st.column_config.TextColumn("Clasificación"),
                                    },
                                )
                                st.caption(
                                    f"n={result_beta['n_observaciones']} observaciones | "
                                    f"Benchmark: {bench_beta} | Período: {period_beta}"
                                )
                except ImportError:
                    st.error("yfinance no disponible. Instalá con: `pip install yfinance`")
                except Exception as _e:
                    st.error(f"Error calculando beta: {_e}")

    # ══════════════════════════════════════════════════════════════════════════
    # MQ2-U3: CORRELACIÓN DINÁMICA (Rolling Correlations)
    # ══════════════════════════════════════════════════════════════════════════
    with sub_roll_corr:
        st.subheader("📡 Correlación Dinámica — Rolling")
        st.caption("Heatmap animado por ventana temporal deslizable. Alta correlación = menor diversificación efectiva.")

        if not tickers_cartera or len(tickers_cartera) < 2:
            st.info("Seleccioná una cartera con al menos 2 activos.")
        else:
            _col_rc1, _col_rc2 = st.columns(2)
            with _col_rc1:
                _ventana = st.selectbox("Ventana (días):", [20, 30, 60, 90], index=1, key="roll_ventana")
            with _col_rc2:
                _period_rc = st.selectbox("Histórico:", ["6mo","1y","2y"], index=1, key="roll_period")
            if st.button("📡 Calcular correlación dinámica", key="btn_roll_corr"):
                try:
                    _hist_rc = cached_historico(tuple(tickers_cartera), _period_rc)
                    _ret_rc  = _hist_rc[[t for t in tickers_cartera if t in _hist_rc.columns]].pct_change().dropna()
                    if _ret_rc.shape[1] >= 2 and len(_ret_rc) >= _ventana:
                        _corr_medio_ts = _ret_rc.rolling(_ventana).corr().groupby(level=0).mean()
                        _corr_actual   = _ret_rc.corr()
                        fig_roll = go.Figure(go.Heatmap(
                            z=_corr_actual.values,
                            x=_corr_actual.columns.tolist(),
                            y=_corr_actual.index.tolist(),
                            colorscale="RdBu_r", zmin=-1, zmax=1,
                            text=[[f"{v:.2f}" for v in row] for row in _corr_actual.values],
                            texttemplate="%{text}",
                        ))
                        fig_roll.update_layout(
                            title="Correlación estática — ventana completa",
                            height=400, template="plotly_dark",
                        )
                        st.plotly_chart(fig_roll, use_container_width=True, key="heatmap_corr_roll")

                        _corr_prom = _corr_actual.values[np.triu_indices(len(_corr_actual), k=1)].mean()
                        _nivel = "🔴 Alta correlación" if _corr_prom > 0.6 else (
                            "🟡 Correlación moderada" if _corr_prom > 0.3 else "🟢 Buena diversificación"
                        )
                        st.metric("Correlación promedio entre pares", f"{_corr_prom:.3f}", help=_nivel)
                        st.caption(_nivel)
                    else:
                        st.warning("Datos insuficientes para el cálculo rolling.")
                except Exception as _e_rc:
                    st.error(f"Error: {_e_rc}")

    # ══════════════════════════════════════════════════════════════════════════
    # MQ2-U4: VaR CORNISH-FISHER
    # ══════════════════════════════════════════════════════════════════════════
    with sub_cf_var:
        st.subheader("📐 VaR Cornish-Fisher — Ajustado por Sesgo y Curtosis")
        st.caption("Más preciso que el VaR gaussiano para activos CEDEAR con distribuciones fat-tailed.")

        _pesos_cf = pesos_opt if pesos_opt else pesos_act
        if not _pesos_cf:
            st.info("Ejecutá el Lab Quant o seleccioná una cartera primero.")
        else:
            if st.button("📐 Calcular VaR Cornish-Fisher", key="btn_cf_var"):
                try:
                    from scipy.stats import kurtosis as _kurt_fn
                    from scipy.stats import skew as _skew_fn
                    _hist_cf = cached_historico(tuple(list(_pesos_cf.keys())), "1y")
                    _ret_cf  = _hist_cf[[t for t in _pesos_cf if t in _hist_cf.columns]].pct_change().dropna()
                    _w_cf = np.array([_pesos_cf.get(t, 0) for t in _ret_cf.columns])
                    _w_cf /= _w_cf.sum() if _w_cf.sum() > 0 else 1
                    _ret_port_cf = (_ret_cf.values @ _w_cf)

                    _mu   = _ret_port_cf.mean()
                    _sig  = _ret_port_cf.std()
                    _s    = float(_skew_fn(_ret_port_cf))
                    _k    = float(_kurt_fn(_ret_port_cf, fisher=True))  # excess kurtosis

                    from scipy.stats import norm as _norm
                    for _alpha, _label in [(0.05, "95%"), (0.01, "99%")]:
                        _z = _norm.ppf(_alpha)
                        # Cornish-Fisher expansion
                        _z_cf = (_z + (_z**2 - 1) * _s / 6 +
                                 (_z**3 - 3*_z) * _k / 24 -
                                 (2*_z**3 - 5*_z) * _s**2 / 36)
                        _var_gauss = _mu + _z * _sig
                        _var_cf    = _mu + _z_cf * _sig

                        _c1, _c2, _c3 = st.columns(3)
                        _c1.metric(f"VaR Gaussiano {_label}", f"{_var_gauss:.3%}")
                        _c2.metric(f"VaR Cornish-Fisher {_label}", f"{_var_cf:.3%}",
                                   delta=f"{(_var_cf - _var_gauss):.3%} ajuste")
                        _c3.metric("Sesgo / Kurt. excess", f"{_s:.2f} / {_k:.2f}")
                        st.divider()
                    st.caption(
                        f"Sesgo {_s:.2f} ({'↓ más pérdidas extremas' if _s < 0 else '↑ más ganancias extremas'}), "
                        f"Curtosis {_k:.2f} ({'fat tails → VaR real > gaussiano' if _k > 1 else 'distribución normal'})"
                    )
                except Exception as _e_cf:
                    st.error(f"Error: {_e_cf}")

    # ══════════════════════════════════════════════════════════════════════════
    # MQ2-U5: SENSIBILIDAD DE PARÁMETROS
    # ══════════════════════════════════════════════════════════════════════════
    with sub_sens:
        st.subheader("⚙️ Análisis de Sensibilidad de Parámetros")
        st.caption("Variación del Sharpe y pesos óptimos según la tasa libre de riesgo (rf).")

        _pesos_sens = pesos_opt if pesos_opt else pesos_act
        if not _pesos_sens:
            st.info("Ejecutá el Lab Quant primero.")
        else:
            _rf_min = st.slider("rf mínima (%):", 0, 30, 0, key="sens_rf_min") / 100
            _rf_max = st.slider("rf máxima (%):", 0, 60, 40, key="sens_rf_max") / 100
            if st.button("⚙️ Calcular sensibilidad", key="btn_sens"):
                try:
                    _hist_s = cached_historico(tuple(list(_pesos_sens.keys())), "1y")
                    _ret_s  = _hist_s[[t for t in _pesos_sens if t in _hist_s.columns]].pct_change().dropna()
                    _w_s = np.array([_pesos_sens.get(t, 0) for t in _ret_s.columns])
                    _w_s /= _w_s.sum() if _w_s.sum() > 0 else 1
                    _ret_port_s = (_ret_s.values @ _w_s)
                    _mu_s, _sig_s = _ret_port_s.mean() * 252, _ret_port_s.std() * np.sqrt(252)

                    _rfs = np.linspace(_rf_min, _rf_max, 20)
                    _sharpes = [(_mu_s - _rf) / _sig_s if _sig_s > 0 else 0 for _rf in _rfs]
                    fig_sens = go.Figure(go.Scatter(
                        x=[f"{r:.0%}" for r in _rfs],
                        y=_sharpes, mode="lines+markers",
                        marker_color="#2196F3", line_width=2,
                    ))
                    fig_sens.add_hline(y=1.0, line_dash="dash", line_color="#4CAF50",
                                       annotation_text="Sharpe = 1.0 (bueno)")
                    fig_sens.add_hline(y=0.5, line_dash="dash", line_color="#FF9800",
                                       annotation_text="Sharpe = 0.5 (aceptable)")
                    fig_sens.update_layout(
                        title="Sensibilidad del Sharpe a la tasa libre de riesgo",
                        xaxis_title="Tasa libre de riesgo (rf)", yaxis_title="Sharpe Ratio",
                        height=360, template="plotly_dark",
                    )
                    st.plotly_chart(fig_sens, use_container_width=True, key="fig_sens")
                    st.caption(f"Sharpe con rf={RISK_FREE_RATE:.0%}: **{(_mu_s - RISK_FREE_RATE)/_sig_s:.3f}**")
                except Exception as _e_s:
                    st.error(f"Error: {_e_s}")

    # ══════════════════════════════════════════════════════════════════════════
    # MQ2-U6: CONTRIBUCIÓN MARGINAL AL RIESGO
    # ══════════════════════════════════════════════════════════════════════════
    with sub_contrib:
        st.subheader("🎯 Contribución Marginal al Riesgo")
        st.caption("Para cada activo: cuánto riesgo incremental aporta al total de la cartera. MRC = peso × covarianza marginal.")

        _pesos_mrc = pesos_opt if pesos_opt else pesos_act
        if not _pesos_mrc:
            st.info("Ejecutá el Lab Quant o seleccioná una cartera primero.")
        else:
            if st.button("🎯 Calcular contribución marginal", key="btn_mrc"):
                try:
                    _hist_mrc = cached_historico(tuple(list(_pesos_mrc.keys())), "1y")
                    _ticks_mrc = [t for t in _pesos_mrc if t in _hist_mrc.columns]
                    _ret_mrc   = _hist_mrc[_ticks_mrc].pct_change().dropna()
                    _w_mrc = np.array([_pesos_mrc.get(t, 0) for t in _ticks_mrc])
                    _w_mrc /= _w_mrc.sum() if _w_mrc.sum() > 0 else 1
                    _cov_mrc = _ret_mrc.cov().values * 252
                    _sigma_port = np.sqrt(_w_mrc @ _cov_mrc @ _w_mrc)
                    _marg_contrib = (_cov_mrc @ _w_mrc) / _sigma_port if _sigma_port > 0 else np.zeros(len(_w_mrc))
                    _risk_contrib = _w_mrc * _marg_contrib
                    _risk_contrib_pct = _risk_contrib / _risk_contrib.sum() * 100 if _risk_contrib.sum() > 0 else _risk_contrib

                    _df_mrc = pd.DataFrame({
                        "Ticker": _ticks_mrc,
                        "Peso %": (_w_mrc * 100).round(2),
                        "Contrib. Riesgo %": _risk_contrib_pct.round(2),
                        "Covarianza Marginal": (_cov_mrc @ _w_mrc).round(6),
                    }).sort_values("Contrib. Riesgo %", ascending=False)
                    st.dataframe(_df_mrc, hide_index=True, use_container_width=True,
                                 column_config={
                                     "Peso %": st.column_config.ProgressColumn("Peso %", min_value=0, max_value=100, format="%.1f%%"),
                                     "Contrib. Riesgo %": st.column_config.ProgressColumn("Contrib. Riesgo %", min_value=0, max_value=100, format="%.1f%%"),
                                 })
                    fig_mrc = go.Figure(go.Bar(
                        x=_df_mrc["Ticker"], y=_df_mrc["Contrib. Riesgo %"],
                        marker_color=["#E74C3C" if v > 20 else "#F39C12" if v > 10 else "#4CAF50"
                                      for v in _df_mrc["Contrib. Riesgo %"]],
                        text=[f"{v:.1f}%" for v in _df_mrc["Contrib. Riesgo %"]],
                        textposition="outside",
                    ))
                    fig_mrc.update_layout(
                        title="Contribución Marginal al Riesgo Total (%)",
                        height=320, template="plotly_dark", showlegend=False,
                    )
                    st.plotly_chart(fig_mrc, use_container_width=True, key="fig_mrc")
                except Exception as _e_mrc:
                    st.error(f"Error: {_e_mrc}")

    # ══════════════════════════════════════════════════════════════════════════
    # S4: ESCENARIOS HISTÓRICOS (StressTestEngine)
    # ══════════════════════════════════════════════════════════════════════════
    with sub_escenarios:
        st.subheader("📜 Escenarios Históricos")
        st.caption("Impacto de shocks históricos (Crisis 2008, COVID, devaluación ARS 2023, etc.) sobre la cartera actual.")
        ccl_riesgo = ctx.get("ccl", 1500.0)
        df_ag_riesgo = ctx.get("df_ag", pd.DataFrame())
        if df_ag_riesgo is None or df_ag_riesgo.empty:
            st.info("Seleccioná una cartera con posiciones para ver los escenarios.")
        else:
            try:
                from services.stress_test import StressTestEngine
                ste = StressTestEngine()
                df_str = ste.todos_los_escenarios(df_ag_riesgo, ccl_riesgo)
                if not df_str.empty:
                    st.dataframe(
                        df_str,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "escenario": st.column_config.TextColumn("Escenario", width="medium"),
                            "valor_original": st.column_config.NumberColumn("Valor original (ARS)", format="$%.0f"),
                            "valor_stress": st.column_config.NumberColumn("Valor bajo estrés (ARS)", format="$%.0f"),
                            "pct_perdida": st.column_config.NumberColumn("Pérdida %", format="%.1f%%"),
                        },
                    )
                st.divider()
                st.markdown("**Escenario custom**")
                c1, c2 = st.columns(2)
                with c1:
                    d_spy = st.slider("SPY shock %", -100, 50, -30, key="stress_custom_spy")
                with c2:
                    d_ccl = st.slider("CCL shock %", -50, 200, 0, key="stress_custom_ccl")
                res_custom = ste.escenario_custom(df_ag_riesgo, ccl_riesgo, d_spy / 100.0, d_ccl / 100.0)
                st.metric(
                    "Valor bajo estrés",
                    f"ARS {res_custom.get('valor_stress', 0):,.0f}",
                    delta=f"{res_custom.get('pct_perdida', 0):.1f}%",
                )
            except Exception as e_esc:
                st.error(f"Error al cargar escenarios: {e_esc}")
