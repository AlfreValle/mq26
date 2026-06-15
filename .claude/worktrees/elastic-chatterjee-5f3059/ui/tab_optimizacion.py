"""
ui/tab_optimizacion.py — Tab 4: Optimización (Portfolio Construction)
Equivalente institucional: MSCI Barra / FactSet Portfolio Construction
Contiene: Lab Quant con 6 modelos simultáneos + radar comparativo + multi-objetivo
"""
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.logging_config import get_logger
from core.panel_precios import validar_panel_precios
from core.structured_logging import log_degradacion
from ui.rbac import can_action as _can_action_rbac
from ui.mq26_ux import dataframe_auto_height

_log = get_logger(__name__)


def _try_registrar_optimization_audit(ctx: dict, **kwargs) -> None:
    dbm = ctx.get("dbm")
    if dbm is None:
        return
    try:
        kwargs.setdefault("usuario", str(st.session_state.get("mq26_login_user", "") or "")[:100])
        kwargs.setdefault("cliente_id", ctx.get("cliente_id"))
        kwargs.setdefault("ccl", float(ctx.get("ccl") or 0) or None)
        kwargs.setdefault("run_id", datetime.now().strftime("%Y%m%d%H%M%S"))
        dbm.registrar_optimization_audit(**kwargs)
    except Exception as e:
        _log.warning("OPTIMIZATION_AUDIT (UI optimización): %s", e)

_MODELOS_LAB = ["Sharpe", "Sortino", "CVaR", "Paridad de Riesgo", "Kelly", "Min Drawdown", "Multi-Objetivo", "Black-Litterman"]
_COLORES_LAB = {
    "Sharpe":            "#2E86AB",
    "Sortino":           "#27AE60",
    "CVaR":              "#E74C3C",
    "Paridad de Riesgo": "#F39C12",
    "Kelly":             "#8E44AD",
    "Min Drawdown":      "#1ABC9C",
    "Multi-Objetivo":    "#E67E22",
    "Black-Litterman":   "#C0392B",
}


def _w_prev_desde_df_ag(df_ag: pd.DataFrame, tickers_subset: list[str]) -> dict[str, float] | None:
    """Pesos relativos a VALOR_ARS restringidos a tickers_subset (mayúsculas)."""
    if df_ag is None or df_ag.empty or not tickers_subset:
        return None
    ts = {str(t).upper() for t in tickers_subset}
    if "VALOR_ARS" not in df_ag.columns:
        return None
    vt = float(df_ag["VALOR_ARS"].sum())
    if vt <= 0:
        return None
    out: dict[str, float] = {}
    for _, r in df_ag.iterrows():
        t = str(r.get("TICKER", "")).upper()
        if t in ts:
            out[t] = float(r.get("VALOR_ARS", 0.0)) / vt
    if not out:
        return None
    s = sum(out.values())
    if s <= 0:
        return None
    return {k: v / s for k, v in out.items()}


def render_tab_optimizacion(ctx: dict) -> None:
    df_ag = ctx.get("df_ag")
    if df_ag is None or df_ag.empty:
        st.info(
            "El optimizador cuantitativo necesita **al menos un activo en cartera** "
            "para armar la matriz de covarianza y el histórico conjunto."
        )
        st.markdown(
            "**¿Qué hacer?** Cargá al menos una posición en "
            "**📂 Cartera → Libro mayor → Importar del broker**."
        )
        return

    tickers_cartera  = ctx["tickers_cartera"]
    prop_nombre      = ctx.get("prop_nombre", "")
    RISK_FREE_RATE   = ctx["RISK_FREE_RATE"]
    capital_nuevo    = ctx["capital_nuevo"]
    engine_data      = ctx["engine_data"]
    RiskEngine       = ctx["RiskEngine"]
    cached_historico = ctx["cached_historico"]
    _boton_exportar  = ctx["_boton_exportar"]
    horizonte_label  = ctx.get("horizonte_label", "1 año")
    cliente_perfil   = ctx.get("cliente_perfil", "Moderado")
    _can_write       = _can_action_rbac(ctx, "write")
    _is_viewer       = not _can_write

    _preset_suite = st.session_state.get("mq26_asesor_suite_preset")
    if _preset_suite:
        st.caption(
            f"Preset suite asesor en sesión: **{_preset_suite}** (solo precarga de controles en Comparativa)."
        )

    sub_comp, sub_lab, sub_ef, sub_bt, sub_multi = st.tabs([
        "📊 Comparativa Actual vs Óptima",
        "🔬 Lab Quant (8 Modelos)",
        "📈 Frontera Eficiente",
        "🎯 Backtest / Stress Test / Ejecución",
        "📊 Backtest Multi-Modelo",
    ])

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 1: COMPARATIVA AUTOMÁTICA — 3 MODELOS
    # ══════════════════════════════════════════════════════════════════
    with sub_comp:
        st.subheader("📊 Comparativa — Cartera Actual vs Mejores 3 Modelos")
        st.caption(f"Horizonte: **{horizonte_label}** | Perfil: **{cliente_perfil}** | Cartera: **{prop_nombre or 'activa'}**")

        if df_ag.empty or not tickers_cartera:
            st.info("Seleccioná una cartera activa para ver la comparativa.")
        else:
            _MODELOS_AUTO = ["Sharpe", "Sortino", "Paridad de Riesgo"]
            _COLORES = {"Actual": "#2E86AB", "Sharpe": "#27AE60", "Sortino": "#F39C12", "Paridad de Riesgo": "#9B59B6"}

            col_p1, col_p2 = st.columns([2, 3])
            with col_p1:
                period_comp = st.radio(
                    "Período histórico:", ["1y", "2y", "3y"],
                    horizontal=True, index=0, key="comp_period",
                )
            with col_p2:
                st.info("🤖 Los 3 modelos se calculan automáticamente con tu cartera actual.")

            if st.button("📊 Calcular comparativa", type="primary", key="btn_comp"):
                st.session_state.pop("comp_resultado", None)
                with st.spinner("Optimizando 3 modelos con tu cartera actual..."):
                    try:
                        hist_c = cached_historico(tuple(tickers_cartera), period_comp)
                        tickers_c_ok = [t for t in tickers_cartera if t in hist_c.columns]
                        # Incluir también tickers que hayan sido renombrados (mapeo YF→original)
                        if not tickers_c_ok:
                            tickers_c_ok = [c for c in hist_c.columns if c != "SPY"]

                        if len(tickers_c_ok) < 2:
                            st.error(f"Se necesitan al menos 2 activos con datos históricos. Disponibles: {list(hist_c.columns)}")
                        else:
                            _prices_ok, _prices_msg = validar_panel_precios(hist_c, tickers_c_ok, min_obs=20)
                            if not _prices_ok:
                                st.error(f"**Datos insuficientes:** {_prices_msg}")
                            else:
                                _wp = _w_prev_desde_df_ag(df_ag, tickers_c_ok)
                                risk_c = RiskEngine(
                                    hist_c[tickers_c_ok],
                                    w_prev=_wp,
                                    lambda_turnover=0.0,
                                    lambda_tc=0.0,
                                    sanitize_returns=True,
                                )
                                if not risk_c.cov_psd_ok:
                                    st.error("**Covarianza no utilizable:** " + str(getattr(risk_c, "cov_psd_message", "")))
                                else:
                                    # Pesos actuales
                                    val_total = float(df_ag.get("VALOR_ARS", pd.Series(dtype=float)).sum())
                                    pesos_actuales: dict[str, float] = {}
                                    for _, r in df_ag.iterrows():
                                        t = str(r.get("TICKER", "")).upper()
                                        if t in tickers_c_ok and val_total > 0:
                                            pesos_actuales[t] = float(r.get("VALOR_ARS", 0)) / val_total
                                    if not pesos_actuales:
                                        pesos_actuales = {t: 1/len(tickers_c_ok) for t in tickers_c_ok}

                                    # Optimizar 3 modelos
                                    resultados: dict[str, dict] = {}
                                    for modelo in _MODELOS_AUTO:
                                        try:
                                            pw = risk_c.optimizar(modelo)
                                            tot = sum(pw.values())
                                            if tot > 0:
                                                pw = {k: v/tot for k, v in pw.items()}
                                            resultados[modelo] = pw
                                        except Exception as _em:
                                            _log.warning("Modelo %s falló: %s", modelo, _em)

                                    if not resultados:
                                        st.error("Ningún modelo pudo optimizar con los datos disponibles.")
                                    else:
                                        st.session_state["comp_resultado"] = {
                                            "tickers":         tickers_c_ok,
                                            "hist":            hist_c,
                                            "pesos_actuales":  pesos_actuales,
                                            "resultados":      resultados,
                                            "period":          period_comp,
                                        }
                                        st.session_state["pesos_opt"]    = resultados.get("Sharpe", {})
                                        st.session_state["modelo_opt"]   = "Sharpe"
                                        st.session_state["tickers_opt"]  = tickers_c_ok
                                        st.session_state["hist_opt"]     = hist_c
                                        st.session_state["mq26_export_weights_ok"] = True
                    except Exception as e:
                        st.error(f"Error inesperado: {e}")
                        _log.exception("Comparativa automática falló")

            # ── Resultados ──────────────────────────────────────────────────
            comp_res = st.session_state.get("comp_resultado")
            if comp_res:
                tickers_co    = comp_res["tickers"]
                hist_co       = comp_res["hist"]
                pesos_act     = comp_res["pesos_actuales"]
                resultados    = comp_res["resultados"]
                ret_d         = hist_co[tickers_co].pct_change().dropna()

                def _metricas(w_dict: dict) -> dict:
                    w = np.array([w_dict.get(t, 0) for t in tickers_co])
                    s = w.sum()
                    if s > 0: w = w / s
                    r = (ret_d @ w).values
                    ret_a  = r.mean() * 252
                    vol_a  = r.std() * np.sqrt(252)
                    sharpe = (ret_a - RISK_FREE_RATE) / vol_a if vol_a > 0 else 0
                    down   = np.minimum(0, r)
                    sortino = (ret_a - RISK_FREE_RATE) / np.sqrt(np.mean(down**2) * 252) if np.mean(down**2) > 0 else 0
                    eq  = np.cumprod(1 + r)
                    mdd = float((eq / np.maximum.accumulate(eq) - 1).min()) if len(eq) > 0 else 0
                    return {"ret": ret_a, "vol": vol_a, "sharpe": sharpe, "sortino": sortino, "mdd": mdd, "r": r}

                met_act = _metricas(pesos_act)
                met_mod = {m: _metricas(pw) for m, pw in resultados.items()}

                # ── Tabla de métricas comparativa ─────────────────────────
                st.divider()
                st.markdown("#### 📊 Métricas clave — Cartera Actual vs 3 Modelos Óptimos")
                _nombres = ["Actual"] + list(resultados.keys())
                _met_all = [met_act] + [met_mod[m] for m in resultados]
                df_met = pd.DataFrame({
                    "Cartera":          _nombres,
                    "Retorno anual":    [f"{m['ret']:.1%}" for m in _met_all],
                    "Volatilidad":      [f"{m['vol']:.1%}" for m in _met_all],
                    "Sharpe":           [f"{m['sharpe']:.2f}" for m in _met_all],
                    "Sortino":          [f"{m['sortino']:.2f}" for m in _met_all],
                    "Max Drawdown":     [f"{m['mdd']:.1%}" for m in _met_all],
                })
                st.dataframe(
                    df_met,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(df_met),
                )

                # ── Tabla de pesos ─────────────────────────────────────────
                st.divider()
                st.markdown("#### ⚖️ Pesos por activo — Actual vs 3 Modelos")
                df_pesos = pd.DataFrame({"Ticker": tickers_co})
                df_pesos["Actual %"] = [round(pesos_act.get(t, 0) * 100, 1) for t in tickers_co]
                for m, pw in resultados.items():
                    df_pesos[f"{m} %"] = [round(pw.get(t, 0) * 100, 1) for t in tickers_co]
                for m in resultados:
                    col_name = f"{m} %"
                    df_pesos[f"Δ {m}"] = (df_pesos[col_name] - df_pesos["Actual %"]).round(1)
                df_pesos = df_pesos.sort_values("Actual %", ascending=False)

                def _color_delta(val):
                    try:
                        v = float(val)
                        if v >  3: return "color:#27AE60;font-weight:bold"
                        if v < -3: return "color:#E74C3C;font-weight:bold"
                    except Exception:
                        pass
                    return ""

                delta_cols = [c for c in df_pesos.columns if c.startswith("Δ")]
                pct_cols   = [c for c in df_pesos.columns if c.endswith("%")]
                styler = (
                    df_pesos.style
                    .format({c: "{:.1f}%" for c in pct_cols})
                    .format({c: "{:+.1f}pp" for c in delta_cols})
                    .map(_color_delta, subset=delta_cols)
                )
                st.dataframe(
                    styler,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(df_pesos),
                )

                # ── Radar ──────────────────────────────────────────────────
                st.divider()
                st.markdown("#### 🕸️ Radar comparativo — 4 dimensiones de riesgo/retorno")
                _dim = ["Retorno", "Sharpe", "Sortino", "Baja Volatilidad", "Bajo Drawdown"]
                all_met = [met_act] + list(met_mod.values())
                all_lbl = ["Actual"] + list(resultados.keys())
                _raw = [[m["ret"], m["sharpe"], m["sortino"], -m["vol"], -m["mdd"]] for m in all_met]
                _mn  = [min(v[i] for v in _raw) for i in range(5)]
                _mx  = [max(v[i] for v in _raw) for i in range(5)]
                def _n(v, mn, mx): return (v - mn) / (mx - mn) if mx > mn else 0.5
                fig_radar = go.Figure()
                for lbl, raw in zip(all_lbl, _raw):
                    normed = [_n(raw[i], _mn[i], _mx[i]) for i in range(5)]
                    fig_radar.add_trace(go.Scatterpolar(
                        r=normed + [normed[0]], theta=_dim + [_dim[0]],
                        fill="toself", name=lbl, opacity=0.35,
                        line=dict(color=_COLORES.get(lbl, "#999"), width=2),
                    ))
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                    height=420, showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                )
                st.plotly_chart(fig_radar, use_container_width=True)

                # ── Equity curves ──────────────────────────────────────────
                st.divider()
                st.markdown("#### 📈 Performance histórica — base 100")
                fig_eq = go.Figure()
                for lbl, met in zip(all_lbl, all_met):
                    eq = np.cumprod(1 + met["r"]) * 100
                    fig_eq.add_trace(go.Scatter(
                        x=list(ret_d.index[:len(eq)]), y=eq,
                        name=lbl, line=dict(color=_COLORES.get(lbl, "#999"), width=2),
                    ))
                if "SPY" in hist_co.columns:
                    spy_r  = hist_co["SPY"].pct_change().dropna()
                    spy_eq = np.cumprod(1 + spy_r.values) * 100
                    fig_eq.add_trace(go.Scatter(
                        x=list(spy_r.index[:len(spy_eq)]), y=spy_eq,
                        name="SPY Benchmark", line=dict(color="#888", width=1.5, dash="dash"),
                    ))
                fig_eq.update_layout(
                    title=f"Período: {comp_res['period']} | Todas las carteras base 100",
                    height=420, template="plotly_dark",
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2),
                )
                st.plotly_chart(fig_eq, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 2: LAB QUANT (contenido original)
    # ══════════════════════════════════════════════════════════════════
    with sub_lab:
        st.subheader("🔬 Lab Quant — Comparación Multi-Modelo")
        st.caption("Corre los 7 modelos + Black-Litterman simultáneamente y compará métricas, pesos y performance.")

        universo_df   = engine_data.universo_df
        todos_tickers = universo_df["Ticker"].dropna().tolist() if not universo_df.empty else []

        # Tickers de la cartera activa (incluir aunque no estén en el universo CSV)
        tickers_cartera_validos = [t for t in tickers_cartera if t]
        tiene_cartera = bool(tickers_cartera_validos)

        # Opciones del multiselect: universo completo + cualquier ticker de cartera que no esté
        opciones = todos_tickers.copy()
        for t in tickers_cartera_validos:
            if t not in opciones:
                opciones.insert(0, t)

        # Default: cartera activa (todos sus activos) o fallback genérico
        if tiene_cartera:
            default_inicial = tickers_cartera_validos
        else:
            fallback = ["AAPL", "MSFT", "AMZN", "GOOGL", "MELI"]
            # IMPORTANTE: Streamlit exige que `default` sea subconjunto de `opciones`.
            # Si el universo no contiene esos tickers (p.ej. solo BYMA), no podemos
            # dejar defaults "inventados".
            default_inicial = [t for t in fallback if t in opciones]
            if not default_inicial:
                default_inicial = opciones[:5] if opciones else []

        # ── Aplicar reset pendiente (viene del botón "Restaurar" del render anterior) ──
        # Streamlit no permite modificar session_state[key] DESPUÉS de instanciar el widget
        # con ese key. Por eso el botón guarda en "_lab_tickers_pending" y aquí lo aplicamos
        # ANTES de crear el multiselect.
        _PENDING_KEY = "_lab_tickers_pending"
        if _PENDING_KEY in st.session_state:
            st.session_state["lab_tickers"] = st.session_state.pop(_PENDING_KEY)

        # Inicializar session_state con los tickers de la cartera si nunca se tocó el widget
        # o si la cartera cambió respecto a la última carga
        _cartera_key = f"lab_cartera_origen_{prop_nombre}"
        if st.session_state.get(_cartera_key) != prop_nombre:
            st.session_state[_cartera_key] = prop_nombre
            st.session_state["_lab_tickers_pending"] = default_inicial

        # ── Aplicar el pendiente generado arriba inmediatamente si aún no hay widget ──
        if "_lab_tickers_pending" in st.session_state and "lab_tickers" not in st.session_state:
            st.session_state["lab_tickers"] = st.session_state.pop("_lab_tickers_pending")

        # Banner informativo
        if tiene_cartera:
            st.info(
                f"📌 **Cartera activa cargada:** {prop_nombre} — "
                f"{len(tickers_cartera_validos)} activos pre-seleccionados. "
                "Podés agregar o quitar activos del universo completo.",
                icon=None,
            )
        else:
            st.warning("No hay cartera activa. Seleccioná una en el panel lateral o elegí activos manualmente.")

        col_l1, col_l2, col_l3 = st.columns([3, 1, 1])
        with col_l1:
            # Sanear defaults antiguos SIEMPRE (por ejemplo, si quedó "AAPL" guardado pero ya no está en opciones).
            # Streamlit crashea al instanciar el widget si `default` contiene valores fuera de `opciones`.
            _PENDING_KEY = "_lab_tickers_pending"
            _default_raw = (
                st.session_state.pop(_PENDING_KEY, None)
                or st.session_state.get("lab_tickers")
                or default_inicial
                or []
            )
            _default_ok = [t for t in _default_raw if t in opciones]
            st.session_state["lab_tickers"] = _default_ok

            tickers_sel = st.multiselect(
                "Activos a optimizar:",
                opciones,
                default=st.session_state.get("lab_tickers", default_inicial),
                key="lab_tickers",
                help="Por defecto carga todos los activos de la cartera activa. Podés agregar más del universo.",
            )
        with col_l2:
            period_hist = st.selectbox("Histórico:", ["6mo","1y","2y","3y"], index=1, key="lab_period")
        with col_l3:
            conviccion = st.slider("Convicción mín. (%):", 1, 10, 3, key="lab_conv") / 100.0

        col_pen_a, col_pen_b, col_pen_c = st.columns(3)
        with col_pen_a:
            lab_lambda_trade = st.slider(
                "λ trading (objetivo)",
                0.0, 3.0, 0.0, 0.05,
                key="lab_lambda_trade",
                help="Misma penalización sobre ∑|w−w_cartera| que en comparativa.",
            )
        with col_pen_b:
            lab_sanitize = st.checkbox("Winsorizar retornos", value=False, key="lab_sanitize_ret")
        with col_pen_c:
            lab_l1_cap = st.checkbox(
                "Tope L1 en optimizador", value=False, key="lab_hard_l1",
                disabled=not tiene_cartera,
                help="Requiere cartera activa para definir w_prev. Máx. ≈ 80% del rango L1 posible.",
            )
            lab_l1_scale = st.slider(
                "Escala tope L1", 10, 100, 60, 5,
                key="lab_l1_scale_pct",
                disabled=not lab_l1_cap or not tiene_cartera,
                help="Porcentaje del valor de referencia ∑|w uniforme − w_prev|.",
            ) / 100.0

        col_tr0, col_tr1 = st.columns([2, 1])
        with col_tr0:
            lab_particion_train = st.checkbox(
                "Partición train / OOS (optimizar solo in-sample; backtest OOS en Tab 4)",
                value=True,
                key="lab_split_train_oos",
                help="Evita optimizar y evaluar sobre el mismo tramo temporal.",
            )
        with col_tr1:
            lab_train_frac = st.slider(
                "Fracción train:", 50, 90, 70, 5,
                key="lab_train_frac_pct",
                disabled=not lab_particion_train,
                help="Porcentaje de filas históricas para estimar μ y Σ; el resto queda para OOS.",
            ) / 100.0

        with st.expander("Multi-objetivo (A8) y λ aversión al riesgo (A9)", expanded=False):
            st.caption("Los pesos se renormalizan; λ penaliza σ² en el objetivo además del score.")
            _r1, _r2, _r3, _r4 = st.columns(4)
            with _r1:
                st.slider("w Sharpe", 0.0, 1.0, 0.40, 0.05, key="lab_mo_w_sharpe")
            with _r2:
                st.slider("w Retorno", 0.0, 1.0, 0.30, 0.05, key="lab_mo_w_ret")
            with _r3:
                st.slider("w Preservación", 0.0, 1.0, 0.20, 0.05, key="lab_mo_w_pres")
            with _r4:
                st.slider("w Paridad", 0.0, 1.0, 0.10, 0.05, key="lab_mo_w_div")
            st.slider(
                "λ aversión al riesgo (σ²)", 0.0, 10.0, 1.0, 0.1,
                key="lab_lambda_ra",
                help="Mayor λ → cartera con menor varianza dentro del multi-objetivo.",
            )

        # Botón para restaurar a los tickers de la cartera
        # IMPORTANTE: no se puede tocar session_state["lab_tickers"] aquí porque el widget
        # ya fue instanciado arriba. Se usa "_lab_tickers_pending" y se aplica en el próximo render.
        if tiene_cartera:
            if st.button("↩️ Restaurar activos de la cartera", key="btn_restaurar_cartera"):
                st.session_state["_lab_tickers_pending"] = tickers_cartera_validos
                st.rerun()

        # MQ2-U1: Views de usuario para Black-Litterman
        with st.expander("🎲 Views de usuario — Black-Litterman", expanded=False):
            st.caption("Ingresá tus expectativas para que el modelo BL las incorpore. Dejar vacío = pesos de mercado.")
            _bl_views_default = [{"ticker": t, "retorno_esperado_%": 0.0, "confianza_%": 50.0}
                                  for t in tickers_sel[:5]] if tickers_sel else []
            _bl_views_df = st.data_editor(
                pd.DataFrame(st.session_state.get("bl_views_df", _bl_views_default)),
                num_rows="dynamic", hide_index=True, key="bl_views_editor",
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "retorno_esperado_%": st.column_config.NumberColumn("Retorno esperado %", format="%.1f%%"),
                    "confianza_%": st.column_config.NumberColumn("Confianza %", min_value=1, max_value=99, format="%.0f%%"),
                }
            )
            if st.button("💾 Guardar views BL", key="btn_guardar_views", disabled=_is_viewer):
                st.session_state["bl_views_df"] = _bl_views_df.to_dict("records")
                st.success("Views guardados")

        _col_btn1, _col_btn2 = st.columns([2, 1])
        with _col_btn1:
            _btn_lab = st.button("🔬 Comparar todos los modelos", type="primary", key="btn_opt")
        with _col_btn2:
            # MQ2-U2: Guardar escenario actual
            if st.button("💾 Guardar escenario", key="btn_guardar_escenario",
                         disabled="lab_resultados" not in st.session_state or _is_viewer):
                try:
                    from services.portfolio_snapshot import guardar_snapshot
                    _res_actual = st.session_state.get("lab_resultados", {})
                    _modelo_activo = st.session_state.get("modelo_opt", "Sharpe")
                    _pesos_a = st.session_state.get("pesos_opt", {})
                    _met_a   = _res_actual.get(_modelo_activo, {}).get("metricas", {}) if _res_actual else {}
                    _snap_id = guardar_snapshot(
                        cartera=prop_nombre, modelo=_modelo_activo,
                        pesos=_pesos_a, metricas=_met_a,
                        cliente_id=ctx.get("cliente_id"),
                    )
                    st.success(f"✅ Escenario #{_snap_id} guardado")
                except Exception as _e_snap:
                    st.error(f"Error al guardar: {_e_snap}")

        # Panel de escenarios guardados
        with st.expander("📂 Escenarios guardados (últimos 5)", expanded=False):
            try:
                from services.portfolio_snapshot import listar_snapshots
                _snaps = listar_snapshots(cartera=prop_nombre, cliente_id=ctx.get("cliente_id"), limit=5)
                if _snaps.empty:
                    st.caption("No hay escenarios guardados para esta cartera.")
                else:
                    for _, _srow in _snaps.iterrows():
                        _met_s = _srow.get("metricas", {}) or {}
                        _sh_s  = _met_s.get("sharpe", "—")
                        st.caption(
                            f"**#{_srow['id']}** · {_srow['modelo']} · "
                            f"Sharpe: {_sh_s} · {_srow['timestamp']}"
                        )
            except Exception as _e_snaps:
                log_degradacion(
                    "ui.tab_optimizacion",
                    "listar_snapshots_lab",
                    _e_snaps,
                    cartera=str(prop_nombre)[:80],
                    cliente_id=ctx.get("cliente_id"),
                )
                st.caption("Escenarios no disponibles.")

        if _btn_lab:
            if not tickers_sel or len(tickers_sel) < 2:
                st.error("Seleccioná al menos 2 activos.")
            else:
                st.session_state["mq26_export_weights_ok"] = False
                with st.spinner("Corriendo 7 modelos de optimización (incluyendo Multi-Objetivo)..."):
                    try:
                        hist = cached_historico(tuple(tickers_sel), period_hist)
                        tickers_ok = [t for t in tickers_sel if t in hist.columns]
                        if len(tickers_ok) < 2:
                            st.error("Insuficientes datos históricos para al menos 2 activos. Verificá conexión a internet.")
                        else:
                            from services.temporal_split import split_precios_train_test

                            hist_full = hist[tickers_ok].sort_index()
                            if lab_particion_train:
                                hist_train, hist_test, split_meta = split_precios_train_test(
                                    hist_full, train_frac=float(lab_train_frac)
                                )
                            else:
                                hist_train = hist_full
                                hist_test = pd.DataFrame(columns=hist_full.columns)
                                split_meta = None

                            _prices_ok_lab, _prices_msg_lab = validar_panel_precios(
                                hist_train, tickers_ok, min_obs=30,
                            )
                            st.session_state["risk_prices_panel_ok"] = _prices_ok_lab
                            st.session_state["risk_prices_msg"] = _prices_msg_lab
                            if not _prices_ok_lab:
                                st.error("**Precios incompletos (E02):** " + _prices_msg_lab)
                                st.session_state.pop("lab_resultados", None)
                                st.session_state["risk_cov_psd_ok"] = False
                            else:
                                _wp_lab = _w_prev_desde_df_ag(df_ag, tickers_ok) if tiene_cartera else None
                                _l1_lab = None
                                if lab_l1_cap and _wp_lab is not None and tickers_ok:
                                    n = len(tickers_ok)
                                    u = np.ones(n) / n
                                    wv = np.array([_wp_lab.get(t, 0.0) for t in tickers_ok])
                                    ref = float(np.sum(np.abs(u - wv)))
                                    _l1_lab = max(1e-4, ref * lab_l1_scale) if ref > 0 else None
                                risk_eng = RiskEngine(
                                    hist_train,
                                    w_prev=_wp_lab,
                                    lambda_turnover=lab_lambda_trade,
                                    lambda_tc=lab_lambda_trade,
                                    max_turnover_l1=_l1_lab,
                                    sanitize_returns=lab_sanitize,
                                )
                                if (
                                    lab_sanitize
                                    and getattr(risk_eng, "returns_sanitize_report", None)
                                    and risk_eng.returns_sanitize_report.get("n_recortes_total", 0) > 0
                                ):
                                    st.warning(
                                        "Winsorizado: "
                                        + str(risk_eng.returns_sanitize_report["n_recortes_total"])
                                        + " retornos recortados (C02)."
                                    )
                                st.session_state["risk_cov_psd_ok"] = bool(risk_eng.cov_psd_ok)
                                st.session_state["risk_cov_psd_message"] = getattr(
                                    risk_eng, "cov_psd_message", ""
                                )
                                if not risk_eng.cov_psd_ok:
                                    st.session_state.pop("lab_resultados", None)
                                    st.error(
                                        "**Covarianza inválida:** no se puede optimizar de forma fiable. "
                                        + str(risk_eng.cov_psd_message)
                                    )
                                else:
                                    if split_meta and split_meta.n_test > 0:
                                        st.success(
                                            f"In-sample: **{split_meta.n_train}** sesiones hasta {split_meta.train_end} · "
                                            f"OOS: **{split_meta.n_test}** desde {split_meta.test_start}."
                                        )

                                    ret_d = risk_eng.retornos[tickers_ok]

                                    resultados = {}
                                    modelos_base = ["Sharpe", "Sortino", "CVaR", "Paridad de Riesgo", "Kelly", "Min Drawdown"]
                                    for modelo in modelos_base:
                                        try:
                                            pesos_m = risk_eng.optimizar(modelo)
                                            pesos_m = {t: p for t, p in pesos_m.items() if p >= conviccion}
                                            total_m = sum(pesos_m.values())
                                            if total_m > 0:
                                                pesos_m = {t: round(p/total_m, 4) for t, p in pesos_m.items()}
                                            w_arr = np.array([pesos_m.get(t, 0.0) for t in tickers_ok])
                                            w_arr /= w_arr.sum() if w_arr.sum() > 0 else 1
                                            ret_port = ret_d[tickers_ok].values @ w_arr
                                            resultados[modelo] = _calcular_metricas_modelo(
                                                ret_port, w_arr, pesos_m, tickers_ok, RISK_FREE_RATE
                                            )
                                        except Exception as _e_mod:
                                            log_degradacion(
                                                "ui.tab_optimizacion",
                                                "lab_quant_modelo_fallo",
                                                _e_mod,
                                                modelo=modelo,
                                                n_tickers=len(tickers_ok),
                                            )

                                    try:
                                        _mo_w = {
                                            "sharpe": st.session_state.get("lab_mo_w_sharpe", 0.40),
                                            "retorno_usd": st.session_state.get("lab_mo_w_ret", 0.30),
                                            "preservacion_ars": st.session_state.get("lab_mo_w_pres", 0.20),
                                            "dividendos": st.session_state.get("lab_mo_w_div", 0.10),
                                        }
                                        _mo_la = float(st.session_state.get("lab_lambda_ra", 1.0))
                                        pesos_mo = risk_eng.optimizar_multiobjetivo(
                                            pesos_componentes=_mo_w, lambda_aversion=_mo_la,
                                        )
                                        pesos_mo = {t: p for t, p in pesos_mo.items() if p >= conviccion}
                                        total_mo = sum(pesos_mo.values())
                                        if total_mo > 0:
                                            pesos_mo = {t: round(p/total_mo, 4) for t, p in pesos_mo.items()}
                                        w_mo = np.array([pesos_mo.get(t, 0.0) for t in tickers_ok])
                                        w_mo /= w_mo.sum() if w_mo.sum() > 0 else 1
                                        ret_port_mo = ret_d[tickers_ok].values @ w_mo
                                        resultados["Multi-Objetivo"] = _calcular_metricas_modelo(
                                            ret_port_mo, w_mo, pesos_mo, tickers_ok, RISK_FREE_RATE
                                        )
                                    except Exception as _e_mo:
                                        log_degradacion(
                                            "ui.tab_optimizacion",
                                            "lab_quant_multiobjetivo_fallo",
                                            _e_mo,
                                            n_tickers=len(tickers_ok),
                                        )

                                    try:
                                        _bl_views = st.session_state.get("bl_views_df", [])
                                        _horizon_d = int(ctx.get("horizonte_dias", 365) or 365)
                                        _views_dict = {
                                            v["ticker"]: (float(v.get("retorno_esperado_%", 0)) / 100,
                                                          float(v.get("confianza_%", 50)) / 100)
                                            for v in _bl_views
                                            if v.get("ticker") and v.get("retorno_esperado_%", 0) != 0
                                        }
                                        pesos_bl = risk_eng.optimizar_black_litterman(
                                            views=_views_dict if _views_dict else None,
                                            horizon_trading_days=_horizon_d,
                                        )
                                        pesos_bl = {t: p for t, p in pesos_bl.items() if p >= conviccion}
                                        total_bl = sum(pesos_bl.values())
                                        if total_bl > 0:
                                            pesos_bl = {t: round(p/total_bl, 4) for t, p in pesos_bl.items()}
                                        w_bl = np.array([pesos_bl.get(t, 0.0) for t in tickers_ok])
                                        w_bl /= w_bl.sum() if w_bl.sum() > 0 else 1
                                        ret_port_bl = ret_d[tickers_ok].values @ w_bl
                                        resultados["Black-Litterman"] = _calcular_metricas_modelo(
                                            ret_port_bl, w_bl, pesos_bl, tickers_ok, RISK_FREE_RATE
                                        )
                                    except Exception as _e_bl:
                                        log_degradacion(
                                            "ui.tab_optimizacion",
                                            "lab_quant_black_litterman_fallo",
                                            _e_bl,
                                            n_tickers=len(tickers_ok),
                                        )

                                    if not resultados:
                                        st.error("Ningún modelo pudo ejecutarse. Verificá que los activos tengan datos históricos suficientes.")
                                    else:
                                        modelo_ref = "Multi-Objetivo" if "Multi-Objetivo" in resultados else (
                                            "Sharpe" if "Sharpe" in resultados else list(resultados.keys())[0]
                                        )
                                        st.session_state["lab_resultados"]  = resultados
                                        st.session_state["lab_tickers_ok"]  = tickers_ok
                                        st.session_state["lab_hist"]        = hist_full
                                        st.session_state["lab_hist_train"]  = hist_train
                                        st.session_state["lab_hist_test"]   = hist_test
                                        st.session_state["lab_split_meta"]  = split_meta
                                        st.session_state["lab_ret_idx"]     = list(ret_d.index)
                                        st.session_state["pesos_opt"]       = resultados[modelo_ref]["pesos"]
                                        st.session_state["tickers_opt"]     = tickers_ok
                                        st.session_state["hist_opt"]        = hist_full
                                        st.session_state["modelo_opt"]      = modelo_ref
                                        st.session_state["mq26_export_weights_ok"] = True
                                        st.toast("✅ Lab Quant completado — resultados listos", icon="🔬")

                    except Exception as e:
                        st.error(f"Error en Lab Quant: {e}")

        # Resultados persisten entre reruns (fuera del if-button)
        if "lab_resultados" in st.session_state:
            _renderizar_resultados(ctx)

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 3: BACKTEST / STRESS TEST / EJECUCIÓN
    # ══════════════════════════════════════════════════════════════════

    with sub_ef:
        st.subheader("📈 Frontera Eficiente de Markowitz")
        st.caption("Ejecutá el Lab Quant primero para cargar el histórico.")
    # Frontera Eficiente (S2: RiskEngine.efficient_frontier + slider)
        st.divider()
        st.markdown("### 🌐 Frontera Eficiente de Markowitz")
        n_pts_fe = st.slider("Granularidad (puntos)", min_value=20, max_value=100, value=60, step=10, key="ef_n_puntos")
        try:
            _hist_tr = st.session_state.get("lab_hist_train")
            _hist_fe = _hist_tr if isinstance(_hist_tr, pd.DataFrame) and not _hist_tr.empty else (
                st.session_state.get("lab_hist", pd.DataFrame())
            )
            _tickers_fe = st.session_state.get("lab_tickers_ok", [])
            if not _hist_fe.empty and len(_tickers_fe) >= 2:
                _cols_ok = [t for t in _tickers_fe if t in _hist_fe.columns]
                if len(_cols_ok) < 2:
                    st.info("Se necesitan al menos 2 activos con histórico. Ejecutá el Lab primero.")
                else:
                    if isinstance(_hist_tr, pd.DataFrame) and not _hist_tr.empty:
                        st.caption("Frontera calculada sobre el **tramo in-sample (train)** del Lab.")
                    _risk_ef = RiskEngine(
                        _hist_fe[_cols_ok],
                        sanitize_returns=bool(st.session_state.get("lab_sanitize_ret", False)),
                    )
                    _df_ef = _risk_ef.efficient_frontier(n_puntos=n_pts_fe)
                    if _df_ef.empty:
                        st.warning("No se pudo calcular la frontera con los datos actuales.")
                    else:
                        fig_fe = go.Figure()
                        fig_fe.add_trace(go.Scatter(
                            x=_df_ef["volatilidad_pct"],
                            y=_df_ef["retorno_anual_pct"],
                            mode="lines+markers",
                            marker=dict(
                                color=_df_ef["sharpe"],
                                colorscale="Viridis",
                                size=7,
                                colorbar=dict(title="Sharpe"),
                                showscale=True,
                            ),
                            line=dict(color="rgba(100,100,100,0.3)", width=1),
                            name="Frontera eficiente",
                            hovertemplate="Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<br>Sharpe: %{marker.color:.2f}<extra></extra>",
                        ))
                        # Óptima (max Sharpe)
                        _best_idx = _df_ef["sharpe"].idxmax()
                        _row_opt = _df_ef.loc[_best_idx]
                        fig_fe.add_trace(go.Scatter(
                            x=[_row_opt["volatilidad_pct"]],
                            y=[_row_opt["retorno_anual_pct"]],
                            mode="markers+text",
                            text=["★ Óptima"],
                            textposition="top right",
                            marker=dict(color="#F39C12", size=18, symbol="star", line=dict(color="white", width=2)),
                            name="Cartera óptima",
                        ))
                        # Cartera actual
                        _pesos_act_fe = ctx.get("df_ag", pd.DataFrame())
                        if not _pesos_act_fe.empty and "PESO_PCT" in _pesos_act_fe.columns and "TICKER" in _pesos_act_fe.columns:
                            _w_act = {}
                            for t in _cols_ok:
                                if t in _pesos_act_fe["TICKER"].values:
                                    _w_act[t] = float(_pesos_act_fe.set_index("TICKER").loc[t, "PESO_PCT"]) / 100.0
                            _tot = sum(_w_act.values())
                            if _tot > 0:
                                _w_act = {t: w / _tot for t, w in _w_act.items()}
                            if _w_act and abs(sum(_w_act.values()) - 1.0) < 0.02:
                                _r_act, _v_act, _ = _risk_ef.calcular_metricas(_w_act)
                                fig_fe.add_trace(go.Scatter(
                                    x=[_v_act * 100], y=[_r_act * 100],
                                    mode="markers+text", text=["● Actual"], textposition="top right",
                                    marker=dict(color="#E74C3C", size=18, symbol="star", line=dict(color="white", width=2)),
                                    name="Cartera actual",
                                ))
                        # Libre de riesgo
                        fig_fe.add_trace(go.Scatter(
                            x=[0], y=[RISK_FREE_RATE * 100],
                            mode="markers+text", text=["◆ RF"], textposition="top right",
                            marker=dict(color="#27AE60", size=14, symbol="diamond", line=dict(color="white", width=2)),
                            name=f"Libre de riesgo ({RISK_FREE_RATE:.0%})",
                        ))
                        # Modelos Lab
                        for modelo, r in resultados.items():
                            _wm = {t: r["pesos"].get(t, 0.0) for t in _cols_ok}
                            if any(_wm.values()):
                                _rm, _vm, _ = _risk_ef.calcular_metricas(_wm)
                                fig_fe.add_trace(go.Scatter(
                                    x=[_vm * 100], y=[_rm * 100], mode="markers+text",
                                    marker=dict(color=_COLORES_LAB.get(modelo, "#fff"), size=12, symbol="star", line=dict(color="white", width=1)),
                                    text=[modelo[:8]], textposition="top center", name=modelo,
                                ))
                        fig_fe.update_layout(
                            title=f"Frontera Eficiente — {len(_df_ef)} puntos (Markowitz) | Escala Sharpe",
                            xaxis_title="Volatilidad anual (%)",
                            yaxis_title="Retorno anual (%)",
                            height=500,
                            template="plotly_dark",
                        )
                        st.plotly_chart(fig_fe, use_container_width=True)
            else:
                st.info("Ejecutá el **Lab Quant** primero para cargar histórico y ver la frontera.")
        except Exception as e:
            st.warning(f"No se pudo dibujar la frontera: {e}")

    with sub_bt:
        st.subheader("🎯 Modelo Activo — Backtest / Stress Test / Ejecución")

        modelos_disp = list(st.session_state.get("lab_resultados", {}).keys()) or \
                       ["Sharpe", "Sortino", "CVaR", "Paridad de Riesgo", "Kelly", "Min Drawdown", "Multi-Objetivo"]

        col_bt1, col_bt2 = st.columns([2, 3])
        with col_bt1:
            modelo_activo_bt = st.selectbox(
                "Modelo activo para downstream:",
                modelos_disp,
                index=0 if st.session_state.get("modelo_opt","") not in modelos_disp
                      else modelos_disp.index(st.session_state.get("modelo_opt", modelos_disp[0])),
                key="bt_modelo_elegido",
            )
            if st.button("✅ Usar este modelo", key="btn_usar_modelo", type="primary"):
                resultados_bt = st.session_state.get("lab_resultados", {})
                if modelo_activo_bt in resultados_bt:
                    st.session_state["pesos_opt"]  = resultados_bt[modelo_activo_bt]["pesos"]
                    st.session_state["modelo_opt"] = modelo_activo_bt
                    st.success(f"✅ Modelo **{modelo_activo_bt}** activado para Riesgo & Ejecución.")
                elif "pesos_optimos" in st.session_state:
                    st.session_state["modelo_opt"] = modelo_activo_bt
                    st.success(f"✅ Modelo **{modelo_activo_bt}** activado (pesos de Comparativa).")
                else:
                    st.warning("Primero ejecutá el Lab Quant o la Comparativa para generar pesos.")

        with col_bt2:
            pesos_act_bt = st.session_state.get("pesos_opt",
                           st.session_state.get("pesos_optimos", {}))
            if pesos_act_bt:
                st.markdown(f"**Pesos — {st.session_state.get('modelo_opt','—')}**")
                df_pesos_bt = pd.DataFrame(
                    [(t, round(p*100, 2)) for t, p in pesos_act_bt.items()],
                    columns=["Activo", "Peso %"]
                ).sort_values("Peso %", ascending=False)
                st.dataframe(
                    df_pesos_bt.style.format({"Peso %": "{:.2f}%"}),
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(df_pesos_bt),
                )
            else:
                st.info("Sin pesos activos. Ejecutá el Lab Quant o la Comparativa primero.")

        st.divider()
        st.info(
            "Los pesos del modelo activo se propagan automáticamente a:\n"
            "- **Tab 4: Riesgo & Simulación** → Backtest y Montecarlo\n"
            "- **Tab 5: Mesa de Ejecución** → Árbol de Decisión"
        )


def _calcular_metricas_modelo(ret_port, w_arr, pesos_m, tickers_ok, RISK_FREE_RATE):
    ret_a   = ret_port.mean() * 252
    vol_a   = ret_port.std() * np.sqrt(252)
    sharpe  = (ret_a - RISK_FREE_RATE) / vol_a if vol_a > 0 else 0
    down    = np.minimum(0, ret_port)
    sortino = ((ret_a - RISK_FREE_RATE) / (np.sqrt(np.mean(down**2) * 252))
               if np.mean(down**2) > 0 else 0)
    eq_c    = np.cumprod(1 + ret_port)
    max_dd  = float((eq_c / np.maximum.accumulate(eq_c) - 1).min()) if len(eq_c) > 0 else 0.0
    calmar  = ret_a / abs(max_dd) if max_dd < 0 else 0.0
    # Omega ratio: suma retornos positivos / suma |retornos negativos|
    pos_sum = float(ret_port[ret_port > 0].sum())
    neg_sum = float(abs(ret_port[ret_port < 0].sum()))
    omega   = pos_sum / neg_sum if neg_sum > 0 else 999.0
    var95   = float(np.percentile(ret_port, 5)) * 100
    cvar95  = float(ret_port[ret_port <= np.percentile(ret_port, 5)].mean()) * 100
    return {
        "pesos":    pesos_m,
        "ret_a":    ret_a,
        "vol_a":    vol_a,
        "sharpe":   sharpe,
        "sortino":  sortino,
        "max_dd":   max_dd,
        "calmar":   calmar,
        "omega":    omega,
        "var95":    var95,
        "cvar95":   cvar95,
        "ret_port": ret_port,
    }


def _renderizar_resultados(ctx: dict) -> None:
    resultados    = st.session_state["lab_resultados"]
    tickers_ok    = st.session_state.get("lab_tickers_ok", [])
    hist          = st.session_state.get("lab_hist", pd.DataFrame())
    ret_idx       = st.session_state.get("lab_ret_idx", [])
    modelo_activo = st.session_state.get("modelo_opt", list(resultados.keys())[0])
    capital_nuevo = ctx["capital_nuevo"]
    _boton_exportar = ctx["_boton_exportar"]
    RiskEngineCls = ctx["RiskEngine"]
    _cov_ok = st.session_state.get("risk_cov_psd_ok") is True
    _precios_ok = st.session_state.get("risk_prices_panel_ok") is True
    _export_ok = _cov_ok and _precios_ok and str(ctx.get("user_role", "admin")).lower() != "viewer"
    _role = str(ctx.get("user_role", "admin")).lower()
    _split_m = st.session_state.get("lab_split_meta")
    if _split_m is not None and getattr(_split_m, "n_test", 0) > 0:
        st.info(
            "Métricas del Lab calculadas sobre **in-sample (train)**. "
            "Usá Tab 4 con «Backtest OOS» para evaluar el tramo fuera de muestra."
        )
    if not _cov_ok:
        st.error(
            "**Exportación bloqueada:** covarianza no válida para este universo. "
            + str(st.session_state.get("risk_cov_psd_message", ""))
        )
    if not _precios_ok:
        st.error(
            "**Exportación bloqueada (E02):** panel de precios incompleto — "
            + str(st.session_state.get("risk_prices_msg", "re-ejecutá con datos válidos."))
        )
    if _role == "viewer":
        st.warning("Rol **visor**: no podés exportar archivos (Excel/PDF) desde el Lab.")

    # Tabla comparativa de métricas
    st.divider()
    st.markdown("### 📊 Comparación de métricas")

    filas_met = []
    for m, r in resultados.items():
        _hhi = RiskEngineCls.calcular_hhi(r["pesos"])
        filas_met.append({
            "Modelo":        m,
            "Retorno anual": r["ret_a"],
            "Volatilidad":   r["vol_a"],
            "Sharpe":        round(r["sharpe"], 3),
            "Sortino":       round(r["sortino"], 3),
            "Calmar":        round(r.get("calmar", 0.0), 3),
            "Omega":         round(r.get("omega", 0.0), 3),
            "HHI":           round(_hhi, 4),
            "Max Drawdown":  r["max_dd"],
            "VaR 95%":       r["var95"],
            "CVaR 95%":      r["cvar95"],
        })
    df_met = pd.DataFrame(filas_met).set_index("Modelo")

    def _color_met(val, col):
        if col in ("Retorno anual","Sharpe","Sortino","Calmar","Omega"):
            return "background-color:#1a5276;color:white;font-weight:bold" if val == df_met[col].max() else ""
        elif col in ("Volatilidad","Max Drawdown","VaR 95%","CVaR 95%","HHI"):
            return "background-color:#1a5276;color:white;font-weight:bold" if val == df_met[col].min() else ""
        return ""

    styled_met = df_met.style.format({
        "Retorno anual": "{:.1%}", "Volatilidad": "{:.1%}",
        "Sharpe": "{:.2f}", "Sortino": "{:.2f}", "Calmar": "{:.2f}", "Omega": "{:.2f}",
        "HHI": "{:.4f}",
        "Max Drawdown": "{:.1%}", "VaR 95%": "{:.2f}%", "CVaR 95%": "{:.2f}%",
    })
    for col in df_met.columns:
        styled_met = styled_met.map(lambda v, c=col: _color_met(v, c), subset=[col])
    # MQ2-V4: indicadores de calidad institucional por umbral
    def _color_umbral(val, col):
        if col == "Sharpe":
            if isinstance(val, (int, float)):
                return ("background:#27AE60;color:white" if val >= 1.0 else
                        "background:#F39C12;color:white" if val >= 0.5 else
                        "background:#E74C3C;color:white")
        if col == "Sortino":
            if isinstance(val, (int, float)):
                return ("background:#27AE60;color:white" if val >= 1.5 else
                        "background:#F39C12;color:white" if val >= 0.7 else
                        "background:#E74C3C;color:white")
        if col == "Max Drawdown":
            if isinstance(val, (int, float)):
                _v = float(str(val).replace("%",""))
                return ("background:#27AE60;color:white" if _v > -15 else
                        "background:#F39C12;color:white" if _v > -30 else
                        "background:#E74C3C;color:white")
        return _color_met(val, col)

    styled_met2 = df_met.style.format({
        "Retorno anual": "{:.1%}", "Volatilidad": "{:.1%}",
        "Sharpe": "{:.2f}", "Sortino": "{:.2f}", "Calmar": "{:.2f}", "Omega": "{:.2f}",
        "HHI": "{:.4f}",
        "Max Drawdown": "{:.1%}", "VaR 95%": "{:.2f}%", "CVaR 95%": "{:.2f}%",
    })
    for col in df_met.columns:
        styled_met2 = styled_met2.map(lambda v, c=col: _color_umbral(v, c), subset=[col])
    st.dataframe(
        styled_met2,
        use_container_width=True,
        hide_index=True,
        height=dataframe_auto_height(df_met),
    )
    st.caption("🟦 Azul = mejor en columna | 🟢 Verde = calidad institucional | 🟡 Amarillo = aceptable | 🔴 Rojo = bajo umbral")
    _col_exp1, _col_exp2 = st.columns(2)
    with _col_exp1:
        if _export_ok:
            _boton_exportar(
                df_met.reset_index(),
                f"lab_quant_metricas_{datetime.now().strftime('%Y%m%d')}",
                "📥 Exportar comparativa a Excel"
            )
        elif _role != "viewer":
            st.caption("Exportación deshabilitada (E02): optimización exitosa con Σ PSD y precios completos requerida.")
    with _col_exp2:
        # MQ2-U10: export PDF del Lab Quant
        if _export_ok and st.button("📄 Exportar comparativa PDF", key="btn_pdf_lab"):
            try:
                from fpdf import FPDF
                _pdf = FPDF()
                _pdf.add_page()
                _pdf.set_font("Helvetica", "B", 14)
                _pdf.cell(0, 10, "MQ26 Lab Quant - Comparativa Multi-Modelo", ln=True)
                _pdf.set_font("Helvetica", "", 10)
                _pdf.cell(0, 7, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
                _pdf.ln(4)
                _pdf.set_font("Helvetica", "B", 9)
                _cols_pdf = ["Modelo","Sharpe","Sortino","Ret. Anual","Volatil.","Max DD","VaR 95%"]
                _widths   = [40, 22, 22, 25, 22, 22, 22]
                for _c, _w in zip(_cols_pdf, _widths):
                    _pdf.cell(_w, 7, _c, border=1)
                _pdf.ln()
                _pdf.set_font("Helvetica", "", 8)
                for _idx, _row in df_met.iterrows():
                    _pdf.cell(40, 6, str(_idx), border=1)
                    _pdf.cell(22, 6, f"{_row.get('Sharpe',0):.2f}", border=1)
                    _pdf.cell(22, 6, f"{_row.get('Sortino',0):.2f}", border=1)
                    _pdf.cell(25, 6, f"{_row.get('Retorno anual',0):.1%}", border=1)
                    _pdf.cell(22, 6, f"{_row.get('Volatilidad',0):.1%}", border=1)
                    _pdf.cell(22, 6, f"{_row.get('Max Drawdown',0):.1%}", border=1)
                    _pdf.cell(22, 6, f"{_row.get('VaR 95%',0):.2f}%", border=1)
                    _pdf.ln()
                _pdf_bytes = bytes(_pdf.output())
                st.download_button(
                    "⬇️ Descargar PDF", data=_pdf_bytes,
                    file_name=f"lab_quant_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf", key="dl_pdf_lab",
                    disabled=not _export_ok,
                )
            except Exception as _e_pdf:
                st.error(f"Error generando PDF: {_e_pdf}")

    # Radar chart
    st.divider()
    st.markdown("### 🕸️ Radar comparativo")

    _met_radar = ["Sharpe","Sortino","Retorno anual","Volatilidad","Max Drawdown","HHI"]
    _sign      = [1, 1, 1, -1, -1, -1]
    radar_rows = []
    for i, met in enumerate(_met_radar):
        vals = df_met[met].values.astype(float)
        mn_v, mx_v = vals.min(), vals.max()
        rng = mx_v - mn_v
        for j, modelo in enumerate(df_met.index):
            norm = (vals[j] - mn_v) / rng if rng > 0 else 0.5
            if _sign[i] < 0:
                norm = 1 - norm
            radar_rows.append({"Métrica": met, "Modelo": modelo, "Score": round(norm, 3)})

    df_radar = pd.DataFrame(radar_rows)
    fig_radar = px.line_polar(
        df_radar, r="Score", theta="Métrica", color="Modelo",
        line_close=True, color_discrete_map=_COLORES_LAB,
        title="Perfil de riesgo/retorno normalizado por modelo",
    )
    fig_radar.update_traces(fill="toself", opacity=0.25)
    fig_radar.update_layout(height=480)
    st.plotly_chart(fig_radar, use_container_width=True)

    # Tabla de pesos
    st.divider()
    st.markdown("### ⚖️ Pesos asignados por modelo")

    df_pesos_comp = pd.DataFrame(
        {m: resultados[m]["pesos"] for m in resultados}
    ).fillna(0).sort_index()
    df_pesos_comp.index.name = "Activo"

    def _color_peso(val):
        try:
            v = float(val)
            if v >= 0.25: return "background-color:#1a5276;color:white;font-weight:bold"
            if v >= 0.15: return "background-color:#2980b9;color:white"
            if v >= 0.08: return "background-color:#aed6f1"
            if v > 0:     return "background-color:#d6eaf8"
        except Exception:
            pass
        return ""

    st.dataframe(
        df_pesos_comp.style.format("{:.1%}").map(_color_peso),
        use_container_width=True,
        hide_index=True,
        height=dataframe_auto_height(df_pesos_comp),
    )

    # Equity curves superpuestas
    st.divider()
    st.markdown("### 📈 Equity curves históricas — todos los modelos")

    fig_eq = go.Figure()
    for modelo, r in resultados.items():
        eq_serie = np.cumprod(1 + r["ret_port"]) * 100
        fig_eq.add_trace(go.Scatter(
            x=ret_idx[:len(eq_serie)], y=eq_serie, name=modelo,
            line=dict(color=_COLORES_LAB.get(modelo), width=2),
        ))
    if not hist.empty and "SPY" in hist.columns:
        spy_r  = hist["SPY"].pct_change().dropna()
        spy_eq = np.cumprod(1 + spy_r.values) * 100
        fig_eq.add_trace(go.Scatter(
            x=list(spy_r.index)[:len(spy_eq)], y=spy_eq,
            name="SPY (benchmark)",
            line=dict(color="#888888", width=1.5, dash="dash"),
        ))
    fig_eq.update_layout(
        title="Performance histórica — base 100",
        yaxis_title="Valor (base 100)", xaxis_title="Fecha",
        height=420, legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # Frontera Eficiente (S2: RiskEngine.efficient_frontier + slider)
    st.divider()
    st.markdown("### 🌐 Frontera Eficiente de Markowitz")
    n_pts_fe = st.slider("Granularidad (puntos)", min_value=20, max_value=100, value=60, step=10, key="ef_n_puntos_lab_results")
    try:
        _hist_tr_r = st.session_state.get("lab_hist_train")
        _hist_fe = _hist_tr_r if isinstance(_hist_tr_r, pd.DataFrame) and not _hist_tr_r.empty else (
            st.session_state.get("lab_hist", pd.DataFrame())
        )
        _tickers_fe = st.session_state.get("lab_tickers_ok", [])
        if not _hist_fe.empty and len(_tickers_fe) >= 2:
            _cols_ok = [t for t in _tickers_fe if t in _hist_fe.columns]
            if len(_cols_ok) < 2:
                st.info("Se necesitan al menos 2 activos con histórico. Ejecutá el Lab primero.")
            else:
                if isinstance(_hist_tr_r, pd.DataFrame) and not _hist_tr_r.empty:
                    st.caption("Frontera sobre **tramo train** (coherente con optimización in-sample).")
                _risk_ef = RiskEngine(
                    _hist_fe[_cols_ok],
                    sanitize_returns=bool(st.session_state.get("lab_sanitize_ret", False)),
                )
                _df_ef = _risk_ef.efficient_frontier(n_puntos=n_pts_fe)
                if _df_ef.empty:
                    st.warning("No se pudo calcular la frontera con los datos actuales.")
                else:
                    fig_fe = go.Figure()
                    fig_fe.add_trace(go.Scatter(
                        x=_df_ef["volatilidad_pct"],
                        y=_df_ef["retorno_anual_pct"],
                        mode="lines+markers",
                        marker=dict(
                            color=_df_ef["sharpe"],
                            colorscale="Viridis",
                            size=7,
                            colorbar=dict(title="Sharpe"),
                            showscale=True,
                        ),
                        line=dict(color="rgba(100,100,100,0.3)", width=1),
                        name="Frontera eficiente",
                        hovertemplate="Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<br>Sharpe: %{marker.color:.2f}<extra></extra>",
                    ))
                    # Óptima (max Sharpe)
                    _best_idx = _df_ef["sharpe"].idxmax()
                    _row_opt = _df_ef.loc[_best_idx]
                    fig_fe.add_trace(go.Scatter(
                        x=[_row_opt["volatilidad_pct"]],
                        y=[_row_opt["retorno_anual_pct"]],
                        mode="markers+text",
                        text=["★ Óptima"],
                        textposition="top right",
                        marker=dict(color="#F39C12", size=18, symbol="star", line=dict(color="white", width=2)),
                        name="Cartera óptima",
                    ))
                    # Cartera actual
                    _pesos_act_fe = ctx.get("df_ag", pd.DataFrame())
                    if not _pesos_act_fe.empty and "PESO_PCT" in _pesos_act_fe.columns and "TICKER" in _pesos_act_fe.columns:
                        _w_act = {}
                        for t in _cols_ok:
                            if t in _pesos_act_fe["TICKER"].values:
                                _w_act[t] = float(_pesos_act_fe.set_index("TICKER").loc[t, "PESO_PCT"]) / 100.0
                        _tot = sum(_w_act.values())
                        if _tot > 0:
                            _w_act = {t: w / _tot for t, w in _w_act.items()}
                        if _w_act and abs(sum(_w_act.values()) - 1.0) < 0.02:
                            _r_act, _v_act, _ = _risk_ef.calcular_metricas(_w_act)
                            fig_fe.add_trace(go.Scatter(
                                x=[_v_act * 100], y=[_r_act * 100],
                                mode="markers+text", text=["● Actual"], textposition="top right",
                                marker=dict(color="#E74C3C", size=18, symbol="star", line=dict(color="white", width=2)),
                                name="Cartera actual",
                            ))
                    # Libre de riesgo
                    fig_fe.add_trace(go.Scatter(
                        x=[0], y=[RISK_FREE_RATE * 100],
                        mode="markers+text", text=["◆ RF"], textposition="top right",
                        marker=dict(color="#27AE60", size=14, symbol="diamond", line=dict(color="white", width=2)),
                        name=f"Libre de riesgo ({RISK_FREE_RATE:.0%})",
                    ))
                    # Modelos Lab
                    for modelo, r in resultados.items():
                        _wm = {t: r["pesos"].get(t, 0.0) for t in _cols_ok}
                        if any(_wm.values()):
                            _rm, _vm, _ = _risk_ef.calcular_metricas(_wm)
                            fig_fe.add_trace(go.Scatter(
                                x=[_vm * 100], y=[_rm * 100], mode="markers+text",
                                marker=dict(color=_COLORES_LAB.get(modelo, "#fff"), size=12, symbol="star", line=dict(color="white", width=1)),
                                text=[modelo[:8]], textposition="top center", name=modelo,
                            ))
                    fig_fe.update_layout(
                        title=f"Frontera Eficiente — {len(_df_ef)} puntos (Markowitz) | Escala Sharpe",
                        xaxis_title="Volatilidad anual (%)",
                        yaxis_title="Retorno anual (%)",
                        height=500,
                        template="plotly_dark",
                    )
                    st.plotly_chart(fig_fe, use_container_width=True)
        else:
            st.info("Ejecutá el **Lab Quant** primero para cargar histórico y ver la frontera.")
    except Exception as e:
        st.warning(f"No se pudo dibujar la frontera: {e}")

    # Selector de modelo activo
    st.divider()
    st.markdown("### 🎯 Modelo activo para Backtest / Stress Test / Ejecución")

    col_sel1, col_sel2 = st.columns([2, 3])
    with col_sel1:
        modelo_elegido = st.selectbox(
            "Seleccioná el modelo:",
            list(resultados.keys()),
            index=list(resultados.keys()).index(modelo_activo) if modelo_activo in resultados else 0,
            key="lab_modelo_elegido",
        )
        if modelo_elegido != modelo_activo:
            _pw = resultados[modelo_elegido]["pesos"]
            st.session_state["pesos_opt"] = _pw
            st.session_state["modelo_opt"] = modelo_elegido
            _try_registrar_optimization_audit(
                ctx,
                accion="lab_modelo_activo_select",
                modelo=str(modelo_elegido),
                tickers=list(_pw.keys()),
                pesos=_pw,
            )
        r_sel = resultados[modelo_elegido]
        st.info(
            f"**{modelo_elegido}**  \n"
            f"Retorno: {r_sel['ret_a']:.1%} | Vol: {r_sel['vol_a']:.1%}  \n"
            f"Sharpe: {r_sel['sharpe']:.2f} | Max DD: {r_sel['max_dd']:.1%}"
        )

    with col_sel2:
        st.markdown(f"**Pesos — {modelo_elegido}**")
        pesos_disp = resultados[modelo_elegido]["pesos"]
        df_disp = pd.DataFrame(list(pesos_disp.items()), columns=["Activo","Peso %"])
        df_disp["Peso %"] = (df_disp["Peso %"] * 100).round(2)
        df_disp = df_disp.sort_values("Peso %", ascending=False)
        if capital_nuevo > 0:
            df_disp["USD a invertir"] = df_disp["Peso %"].apply(
                lambda p: round(capital_nuevo * p / 100, 2)
            )
        st.dataframe(
            df_disp.style.format({"Peso %": "{:.2f}%"}),
            use_container_width=True,
            hide_index=True,
            height=dataframe_auto_height(df_disp),
        )
        if st.button("💾 Guardar snapshot del modelo activo", key="btn_guardar_snapshot_modelo_activo", disabled=_is_viewer):
            try:
                from services.portfolio_snapshot import guardar_snapshot
                snap_pesos = {}
                if df_disp is not None and not df_disp.empty:
                    for _, rw in df_disp.iterrows():
                        t = str(rw.get("Activo", rw.get("Ticker", rw.get("TICKER", "")))).strip().upper()
                        p = float(rw.get("Peso %", rw.get("peso", 0)) or 0)
                        if t:
                            snap_pesos[t] = round(p / 100.0, 6)
                _snap_met = {
                    k: float(v) for k, v in (r_sel or {}).items()
                    if isinstance(v, (int, float))
                }
                guardar_snapshot(
                    cartera=str(ctx.get("cartera_activa", "")),
                    modelo=str(modelo_elegido),
                    pesos=snap_pesos,
                    metricas=_snap_met,
                    cliente_id=ctx.get("cliente_id"),
                )
                _try_registrar_optimization_audit(
                    ctx,
                    accion="snapshot_guardado",
                    modelo=str(modelo_elegido),
                    pesos=snap_pesos,
                )
                st.success("Snapshot guardado.")
            except Exception as _e_snapshot:
                st.error(f"No se pudo guardar el snapshot: {_e_snapshot}")
        st.caption(f"Modelo activo usado en Backtest y Stress Test: **{modelo_elegido}**")

    # ── TAB: BACKTEST MULTI-MODELO ────────────────────────────────────────────
    with sub_multi:
        st.subheader("📊 Backtest Multi-Modelo — Equity Curves Comparadas")
        st.caption(
            "Ejecutá el Lab Quant primero para cargar histórico. "
            "Luego corré el backtest simultáneo de todos los modelos y compará las equity curves."
        )

        lab_hist   = st.session_state.get("lab_hist")
        lab_res    = st.session_state.get("lab_resultados", {})

        if not lab_res or lab_hist is None:
            st.info("Sin datos. Ejecutá el **Lab Quant** primero para cargar el histórico y los pesos.")
        else:
            import plotly.graph_objects as go
            from services.backtester import run_backtest_multimodelo, MODELOS_DISPONIBLES

            col_mb1, col_mb2 = st.columns([2, 1])
            with col_mb1:
                modelos_con_pesos = {k: v["pesos"] for k, v in lab_res.items() if "pesos" in v}
                modelos_disp_multi = list(modelos_con_pesos.keys())
                modelos_sel = st.multiselect(
                    "Modelos a comparar",
                    modelos_disp_multi,
                    default=modelos_disp_multi[:min(5, len(modelos_disp_multi))],
                    key="multi_bt_sel",
                )
            with col_mb2:
                period_multi = st.selectbox(
                    "Período de backtest",
                    ["1y", "2y", "3y", "5y"],
                    index=1,
                    key="multi_bt_period",
                )

            if st.button("▶ Correr backtest multi-modelo", key="btn_multi_bt",
                         use_container_width=True, type="primary",
                         disabled=not modelos_sel):
                with st.spinner(f"Corriendo backtest para {len(modelos_sel)} modelos…"):
                    pesos_sel = {m: modelos_con_pesos[m] for m in modelos_sel}
                    try:
                        resultados_multi = run_backtest_multimodelo(
                            precios=lab_hist,
                            modelos_pesos=pesos_sel,
                            period=period_multi,
                        )
                        st.session_state["multi_bt_resultados"] = resultados_multi
                    except Exception as e:
                        st.error(f"Error en backtest multi-modelo: {e}")

            # ── Mostrar resultados si existen ──────────────────────────────
            res_multi = st.session_state.get("multi_bt_resultados", {})
            if res_multi:
                import numpy as np
                import pandas as pd

                # ── Equity curves ──────────────────────────────────────────
                st.markdown("##### Equity curves (base 100)")
                fig_eq = go.Figure()
                COLORES = [
                    "#1F4E79","#1A6B3C","#C00000","#D46A00","#5B2D8E",
                    "#0F6E56","#854F0B","#A32D2D",
                ]
                for idx, (modelo, bt) in enumerate(res_multi.items()):
                    eq = np.asarray(bt.equity_strategy, dtype=float)
                    eq_norm = eq / eq[0] * 100 if eq[0] > 0 else eq
                    fig_eq.add_scatter(
                        y=eq_norm, mode="lines", name=modelo,
                        line={"color": COLORES[idx % len(COLORES)], "width": 2},
                    )
                # Benchmark (primera serie disponible)
                first_bt = next(iter(res_multi.values()))
                bm = np.asarray(first_bt.equity_benchmark, dtype=float)
                bm_norm = bm / bm[0] * 100 if bm[0] > 0 else bm
                fig_eq.add_scatter(
                    y=bm_norm, mode="lines", name="SPY (benchmark)",
                    line={"color": "#888780", "width": 1.5, "dash": "dash"},
                )
                fig_eq.update_layout(
                    xaxis_title="Días", yaxis_title="Valor (base 100)",
                    legend={"orientation": "h", "y": -0.2},
                    margin={"l": 0, "r": 0, "t": 30, "b": 0},
                    height=380,
                )
                st.plotly_chart(fig_eq, use_container_width=True)

                # ── Tabla comparativa de métricas ──────────────────────────
                st.markdown("##### Métricas comparadas")
                filas = []
                for modelo, bt in res_multi.items():
                    filas.append({
                        "Modelo":      modelo,
                        "CAGR %":      round(bt.retorno_anual_estrategia * 100, 2),
                        "Sharpe":      round(bt.sharpe_estrategia, 3),
                        "Max DD %":    round(bt.max_dd_estrategia * 100, 2),
                        "Skew":        round(getattr(bt, "skew_retornos_estrategia", 0), 3),
                        "Sharpe SPY":  round(getattr(bt, "sharpe_spy", 0), 3),
                    })
                df_comp = pd.DataFrame(filas).sort_values("Sharpe", ascending=False)

                def _color_sharpe(v):
                    if v >= 1.0:
                        return "color: #1A6B3C; font-weight: 500"
                    if v >= 0.5:
                        return "color: #854F0B"
                    return "color: #A32D2D"

                st.dataframe(
                    df_comp.style
                        .applymap(_color_sharpe, subset=["Sharpe"])
                        .format({
                            "CAGR %":   "{:.2f}%",
                            "Max DD %": "{:.2f}%",
                            "Sharpe":   "{:.3f}",
                            "Skew":     "{:.3f}",
                            "Sharpe SPY": "{:.3f}",
                        }),
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(df_comp),
                )

                # ── Indicadores fundamentales del modelo ganador ───────────
                mejor = df_comp.iloc[0]["Modelo"]
                pesos_mejor = modelos_con_pesos.get(mejor, {})
                if pesos_mejor:
                    st.markdown(f"##### Indicadores fundamentales — modelo **{mejor}**")
                    with st.spinner("Calculando indicadores…"):
                        try:
                            from services.scoring_engine import calcular_indicadores_cartera
                            ind = calcular_indicadores_cartera(pesos_mejor)
                            ci1, ci2, ci3, ci4, ci5 = st.columns(5)
                            ci1.metric("PER pond.",     f"{ind['per_w']:.1f}x")
                            ci2.metric("P/S pond.",     f"{ind['ps_w']:.1f}x")
                            ci3.metric("ROE pond.",     f"{ind['roe_w']*100:.1f}%")
                            ci4.metric("ROA pond.",     f"{ind['roa_w']*100:.1f}%")
                            ci5.metric("Div. Yield",    f"{ind['dividend_yield_w']*100:.2f}%")
                        except Exception as e:
                            st.caption(f"Indicadores no disponibles: {e}")

                # ── Botón para activar el modelo ganador ───────────────────
                st.divider()
                col_act1, col_act2 = st.columns([2, 1])
                with col_act1:
                    modelo_activar = st.selectbox(
                        "Activar modelo para Riesgo & Ejecución",
                        list(res_multi.keys()),
                        index=0,
                        key="multi_bt_activar",
                    )
                with col_act2:
                    st.markdown("<div style='margin-top:28px'/>", unsafe_allow_html=True)
                    if st.button("✅ Activar modelo", key="btn_multi_activar",
                                 use_container_width=True, type="primary"):
                        _pm = modelos_con_pesos[modelo_activar]
                        st.session_state["pesos_opt"] = _pm
                        st.session_state["modelo_opt"] = modelo_activar
                        _try_registrar_optimization_audit(
                            ctx,
                            accion="multi_backtest_activar_modelo",
                            modelo=str(modelo_activar),
                            tickers=list(_pm.keys()),
                            pesos=_pm,
                            extra={"origen": "backtest_multi_modelo"},
                        )
                        st.success(f"Modelo **{modelo_activar}** activado para tabs de Riesgo y Ejecución.")

