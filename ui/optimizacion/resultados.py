"""
ui/optimizacion/resultados.py — resultados del Lab Quant (8 modelos de optimización).

Extraído de ui/tab_optimizacion.py (Fase 2.1): métricas por modelo, paneles
comparativos, exportación con guardas de validez (PSD/precios) y auditoría
de optimización. RiskEngine y RISK_FREE_RATE llegan por ctx (sin imports
del motor acá).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.logging_config import get_logger
from ui.mq26_ux import dataframe_auto_height
from ui.rbac import can_action as _can_action_rbac

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
    RiskEngine    = RiskEngineCls
    RISK_FREE_RATE = ctx["RISK_FREE_RATE"]
    _is_viewer    = not _can_action_rbac(ctx, "write")
    sub_multi     = ctx.get("_sub_multi_tab")
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
                for _c, _w in zip(_cols_pdf, _widths, strict=True):
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
            from services.backtester import run_backtest_multimodelo

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

