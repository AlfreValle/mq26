"""
ui/tab_inversor.py — Vista del inversor individual (tier IN).

Secciones: resumen + lista legible, carga, plata nueva, proyección.
"""
from __future__ import annotations

import html
import hashlib
import time
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.diagnostico_types import (
    CARTERA_IDEAL,
    RENDIMIENTO_MODELO_YTD_REF,
    perfil_diagnostico_valido,
    perfil_motor_salida,
)
from core.renta_fija_ar import descripcion_legible, get_meta, ladder_vencimientos, tir_ponderada_cartera, top_instrumentos_rf
from services.copy_inversor import (
    antes_despues_defensivo,
    patrimonio_dual_line,
    titulo_seccion_resumen,
)
from ui.mq26_ux import defensive_bar_html, fig_torta_ideal, obs_card_html, semaforo_html
from services.cartera_service import PRECIOS_FALLBACK_ARS

_OBS_PRIO_MAP = {
    "critica": "critica", "alta": "alta",
    "media": "media", "baja": "baja",
}


def _nombre_para_lista(ticker: str, ctx: dict) -> str:
    t = (ticker or "").strip().upper()
    if not t:
        return "—"
    try:
        if get_meta(t):
            return descripcion_legible(t)
    except Exception:
        pass
    u = ctx.get("universo_df")
    if u is None or u.empty:
        return t
    col = "TICKER" if "TICKER" in u.columns else ("Ticker" if "Ticker" in u.columns else None)
    if not col:
        return t
    m = u[u[col].astype(str).str.upper() == t]
    if m.empty:
        return t
    for nc in ("NOMBRE", "Nombre", "nombre", "DENOMINACION"):
        if nc in m.columns and pd.notna(m.iloc[0].get(nc)):
            nom = str(m.iloc[0][nc]).strip()
            if nom:
                return nom[:56]
    return t


def _precios_para_recomendar(ctx: dict) -> dict:
    out = {str(k).upper(): float(v) for k, v in (ctx.get("precios_dict") or {}).items()}
    for k, v in PRECIOS_FALLBACK_ARS.items():
        out.setdefault(str(k).upper(), float(v))
    return out


def _render_lista_cartera_legible(ctx: dict, df_ag: pd.DataFrame) -> None:
    st.markdown("##### Posiciones")
    if df_ag is None or df_ag.empty:
        st.caption("Todavía no hay activos cargados.")
        return
    rows = []
    for _, row in df_ag.iterrows():
        tk = str(row.get("TICKER", "")).strip().upper()
        nom = _nombre_para_lista(tk, ctx)
        peso = float(pd.to_numeric(row.get("PESO_PCT", 0), errors="coerce") or 0.0) * 100.0
        pnl_u = float(pd.to_numeric(row.get("PNL_PCT_USD", 0), errors="coerce") or 0.0) * 100.0
        if "PNL_PCT_USD" not in df_ag.columns:
            pnl_u = float(pd.to_numeric(row.get("PNL_PCT", 0), errors="coerce") or 0.0) * 100.0
        rows.append(
            {
                "Activos": f"{tk} — {nom}" if nom != tk else tk,
                "Participación": f"{peso:.1f}%",
                "Resultado (USD)": f"{pnl_u:+.1f}%",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(320, 44 + len(rows) * 38))
    st.caption(
        "Participación: cuánto representa cada uno en tu cartera hoy. "
        "Resultado (USD): respecto del dinero que pusiste, en dólares de compra."
    )


def _ctx_hash_inversor(ctx: dict) -> str:
    df_ag = ctx.get("df_ag")
    ccl = round(float(ctx.get("ccl") or 0), 4)
    cartera = str(ctx.get("cartera_activa", ""))
    if df_ag is None or df_ag.empty:
        return hashlib.md5(f"empty|{ccl}|{cartera}".encode()).hexdigest()
    try:
        h = str(pd.util.hash_pandas_object(df_ag, index=False).sum())
    except Exception:
        h = str(len(df_ag)) + str(df_ag["TICKER"].tolist())
    return hashlib.md5(f"{h}|{ccl}|{cartera}".encode()).hexdigest()


def _senales_precalculadas(ctx: dict) -> list[dict] | None:
    df_ag = ctx.get("df_ag")
    if df_ag is None or df_ag.empty:
        return None
    df_analisis = ctx.get("df_analisis")
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    score_map: dict = {}
    rsi_map: dict = {}
    if df_analisis is not None and not df_analisis.empty:
        if "TICKER" in df_analisis.columns and "PUNTAJE_TECNICO" in df_analisis.columns:
            score_map = df_analisis.set_index("TICKER")["PUNTAJE_TECNICO"].to_dict()
        if "RSI" in df_analisis.columns:
            rsi_map = df_analisis.set_index("TICKER")["RSI"].to_dict()
    from services.motor_salida import evaluar_salida

    out: list[dict] = []
    for _, row in df_ag.iterrows():
        ticker = str(row.get("TICKER", ""))
        ppc_ars = float(pd.to_numeric(row.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
        px_ars = float(pd.to_numeric(row.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
        rsi_val = float(rsi_map.get(ticker, 50.0) or 50.0)
        score_v = float(score_map.get(ticker, 5.0) or 5.0)
        fecha_c = row.get("FECHA_COMPRA", date(2020, 1, 1))
        if not isinstance(fecha_c, date):
            try:
                fecha_c = pd.to_datetime(str(fecha_c)).date()
            except Exception:
                fecha_c = date(2020, 1, 1)
        if ppc_ars <= 0 or px_ars <= 0:
            continue
        out.append(
            evaluar_salida(
                ticker=ticker,
                ppc_usd=ppc_ars,
                px_usd_actual=px_ars,
                rsi=rsi_val,
                score_actual=score_v,
                score_semana_anterior=score_v,
                fecha_compra=fecha_c,
                perfil=perfil_ms,
            )
        )
    return out if out else None


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


def _get_diagnostico_cached(ctx: dict) -> object:
    h = _ctx_hash_inversor(ctx)
    now = time.monotonic()
    cache = st.session_state.get("inv_diagnostico") or {}
    ttl = 300.0
    if (
        cache.get("hash") == h
        and cache.get("result") is not None
        and (now - float(cache.get("ts", 0))) < ttl
    ):
        return cache["result"]
    from services.diagnostico_cartera import diagnosticar

    df_ag = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
    metricas = ctx.get("metricas") or {}
    senales = _senales_precalculadas(ctx)
    res = diagnosticar(
        df_ag=df_ag,
        perfil=str(ctx.get("cliente_perfil", "Moderado")),
        horizonte_label=str(ctx.get("horizonte_label", "1 año")),
        metricas=metricas,
        ccl=float(ctx.get("ccl") or 0.0),
        universo_df=ctx.get("universo_df"),
        senales_salida=senales,
        cliente_nombre=str(ctx.get("cliente_nombre", "")),
    )
    st.session_state["inv_diagnostico"] = {"hash": h, "ts": now, "result": res}
    st.session_state.pop("diagnostico_cache", None)
    return res


def _market_stress_optional() -> dict | None:
    try:
        import yfinance as yf

        vix_h = yf.Ticker("^VIX").history(period="5d")
        vix = float(vix_h["Close"].iloc[-1]) if len(vix_h) > 0 else None
        spy = yf.Ticker("SPY").history(period="30d")["Close"].dropna()
        dd = None
        if len(spy) >= 2:
            dd = float(spy.iloc[-1] / spy.iloc[0] - 1.0)
        return {"vix": vix, "spy_drawdown_30d": dd}
    except Exception:
        return None


_MESES_HORIZONTE = {"1 año": 12, "3 años": 36, "5 años": 60, "10 años": 120}


def _render_empezar_cero(ctx: dict) -> None:
    st.markdown("##### Empezar de cero con una sugerencia")
    st.caption(
        "Todavía no cargaste posiciones. Si querés, ingresá cuánto tenés para invertir "
        "y te proponemos una distribución de referencia para tu perfil."
    )
    cap0 = st.number_input(
        "Cuánto querés invertir (ARS)",
        min_value=0.0,
        value=200_000.0,
        step=25_000.0,
        key="inv_sugerencia_capital",
        format="%.0f",
    )
    ccl = float(ctx.get("ccl") or 1.0)
    if st.button("Ver sugerencia", key="inv_sugerencia_btn", use_container_width=True):
        from services.diagnostico_cartera import diagnosticar
        from services.recomendacion_capital import recomendar

        d_empty = diagnosticar(
            df_ag=pd.DataFrame(),
            perfil=str(ctx.get("cliente_perfil", "Moderado")),
            horizonte_label=str(ctx.get("horizonte_label", "1 año")),
            metricas={},
            ccl=ccl,
            universo_df=ctx.get("universo_df"),
            senales_salida=None,
            cliente_nombre=str(ctx.get("cliente_nombre", "")),
        )
        rr = recomendar(
            df_ag=pd.DataFrame(),
            perfil=str(ctx.get("cliente_perfil", "Moderado")),
            horizonte_label=str(ctx.get("horizonte_label", "1 año")),
            capital_ars=float(cap0),
            ccl=ccl,
            precios_dict=_precios_para_recomendar(ctx),
            diagnostico=d_empty,
            universo_df=ctx.get("universo_df"),
            df_analisis=ctx.get("df_analisis"),
            market_stress=_market_stress_optional(),
            cliente_nombre=str(ctx.get("cliente_nombre", "")),
        )
        st.session_state["inv_recomendacion"] = {"capital": float(cap0), "rr": rr}
    rec = st.session_state.get("inv_recomendacion") or {}
    rr = rec.get("rr")
    if rr is not None and abs(float(rec.get("capital", -1)) - float(cap0)) < 0.5:
        perfil_v = perfil_diagnostico_valido(str(ctx.get("cliente_perfil", "Moderado")))
        ideal_dict = CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"])
        if getattr(rr, "alerta_mercado", False):
            st.warning(rr.mensaje_alerta)
        else:
            st.success("¡Tu portafolio semilla está listo para revisar y ejecutar con tu asesor!")
        st.plotly_chart(
            fig_torta_ideal(perfil_v, ideal_dict),
            use_container_width=True,
        )
        st.caption(getattr(rr, "resumen_recomendacion", "") or "Sugerencias según tu perfil y el capital ingresado.")
        for it in getattr(rr, "compras_recomendadas", []) or []:
            st.markdown(
                f"**{it.ticker}** ({it.nombre_legible}) — {it.unidades} unidades — "
                f"aprox. ARS {it.monto_ars:,.0f} — _{it.justificacion}_"
            )
        pend = getattr(rr, "pendientes_proxima_inyeccion", []) or []
        if pend:
            st.markdown("**Para después o con tu asesor**")
            for p in pend[:8]:
                st.caption(f"{p.get('ticker', '')}: {p.get('motivo', '')}")


def render_tab_inversor(ctx: dict) -> None:
    df_ag = ctx.get("df_ag")
    nombre = str(ctx.get("cliente_nombre", "inversor"))
    metricas = ctx.get("metricas") or {}
    ccl = float(ctx.get("ccl") or 1.0)

    if df_ag is None or df_ag.empty:
        st.session_state.setdefault("inv_carga_open", False)
        st.markdown(f"### Hola, **{nombre}**")
        st.markdown(
            "Para ver cómo está tu cartera, cargá lo que tenés en el broker "
            "o pedile a tu asesor que te ayude con la primera carga."
        )
        c1, c2, c3 = st.columns(3, gap="medium")
        with c1:
            if st.button("Importar desde mi broker", use_container_width=True, key="inv_welcome_imp"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "importar"
                st.rerun()
        with c2:
            if st.button("Cargar uno por uno", use_container_width=True, key="inv_welcome_manual"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "manual"
                st.rerun()
        with c3:
            if st.button("Empezar de cero con sugerencia", use_container_width=True, key="inv_welcome_sug"):
                st.session_state["inv_mostrar_sugerencia"] = True
                st.rerun()
        if st.session_state.get("inv_mostrar_sugerencia"):
            _render_empezar_cero(ctx)
        st.checkbox(
            "Mostrar asistente para sumar compras o importar archivo del broker",
            key="inv_carga_open",
        )
        if st.session_state.get("inv_carga_open"):
            _fn = ctx.get("render_carga_activos_fn")
            if _fn is None:
                from ui.carga_activos import render_carga_activos as _fn
            _fn(ctx)
        return

    diag = _get_diagnostico_cached(ctx)

    uxb = st.session_state.pop("inv_ux_before_load", None)
    if isinstance(uxb, dict) and "pct" in uxb:
        nuevo_pct = float(getattr(diag, "pct_defensivo_actual", 0.0) or 0.0) * 100.0
        st.success(antes_despues_defensivo(float(uxb["pct"]), nuevo_pct))

    pnl_pct = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0.0)
    valor_total = float(metricas.get("total_valor", 0) or 0)
    valor_usd = valor_total / max(ccl, 1e-9)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)
    pct_def_frac = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
    pct_def_req_frac = float(getattr(diag, "pct_defensivo_requerido", 0) or 0) or 0.4

    st.markdown(f"## {titulo_seccion_resumen(nombre)}")
    st.caption(patrimonio_dual_line(valor_usd, valor_total, ccl))

    col_top1, col_top2 = st.columns([2, 1])
    with col_top1:
        _sem = getattr(diag, "semaforo", None)
        sem_val = (
            str(getattr(_sem, "value", "")) if _sem is not None else ""
        ) or "amarillo"
        st.markdown(
            semaforo_html(
                valor=sem_val,
                score=diag.score_total,
                titulo=str(getattr(diag, "titulo_semaforo", "") or ""),
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            defensive_bar_html(pct_def_frac, pct_def_req_frac, "Cobertura defensiva"),
            unsafe_allow_html=True,
        )
    with col_top2:
        if st.button("Actualizar diagnóstico", key="btn_refresh_diag_inversor", use_container_width=True):
            st.session_state.pop("inv_diagnostico", None)
            st.rerun()

    m1, m2, m3 = st.columns(3)
    m1.metric("Patrimonio (USD)", f"USD {valor_usd:,.0f}")
    m2.metric("Patrimonio (ARS)", f"ARS {valor_total:,.0f}")
    m3.metric("Resultado acum. (USD)", f"{pnl_pct:+.1f}%", help="Respecto de tu costo, en marco dólar compra.")

    with st.expander("Observaciones", expanded=False):
        for o in getattr(diag, "observaciones", [])[:3]:
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

    st.divider()
    _render_lista_cartera_legible(ctx, df_ag)

    st.divider()
    st.markdown("### Agregar o importar")
    st.session_state.setdefault("inv_carga_open", False)
    st.checkbox(
        "Mostrar asistente para sumar compras o importar archivo del broker",
        key="inv_carga_open",
    )
    if st.session_state.get("inv_carga_open"):
        _fn = ctx.get("render_carga_activos_fn")
        if _fn is None:
            from ui.carga_activos import render_carga_activos as _fn
        _fn(ctx)

    st.divider()
    st.markdown("### Qué hacer con plata nueva")
    cap_default = float(ctx.get("capital_nuevo", 0.0) or 0.0)
    cap_side = float(st.session_state.get("capital_disponible_mq", 0.0) or 0.0)
    if cap_side > 0:
        cap_default = cap_side
    cap_in = st.number_input(
        "Cuánto tenés para invertir (ARS)",
        min_value=0.0,
        value=max(0.0, cap_default),
        step=10_000.0,
        key="inversor_capital_ars",
        format="%.0f",
    )
    stress = _market_stress_optional()
    if st.button("Calcular sugerencias", key="btn_recomendar_inversor", use_container_width=True):
        from services.recomendacion_capital import recomendar

        _rr_new = recomendar(
            df_ag=df_ag,
            perfil=str(ctx.get("cliente_perfil", "Moderado")),
            horizonte_label=str(ctx.get("horizonte_label", "1 año")),
            capital_ars=float(cap_in),
            ccl=ccl,
            precios_dict=ctx.get("precios_dict") or {},
            diagnostico=diag,
            universo_df=ctx.get("universo_df"),
            df_analisis=ctx.get("df_analisis"),
            market_stress=stress,
            cliente_nombre=str(ctx.get("cliente_nombre", "")),
        )
        st.session_state["inv_recomendacion"] = {"capital": float(cap_in), "rr": _rr_new}

    _rec = st.session_state.get("inv_recomendacion") or {}
    rr = _rec.get("rr") if abs(float(_rec.get("capital", -1.0)) - float(cap_in)) < 0.5 else None

    if rr is not None:
        if getattr(rr, "alerta_mercado", False):
            st.warning(rr.mensaje_alerta)
        st.caption(getattr(rr, "resumen_recomendacion", ""))
        for it in getattr(rr, "compras_recomendadas", []) or []:
            st.markdown(
                f"**{it.ticker}** × {it.unidades} u. — "
                f"ARS {it.monto_ars:,.0f} — _{it.justificacion}_"
            )
            orden_txt = (
                f"COMPRA {it.ticker} — {it.unidades} unidades — "
                f"aprox. ARS {it.monto_ars:,.0f} — {it.justificacion}"
            )
            st.code(orden_txt, language=None)
        pend = getattr(rr, "pendientes_proxima_inyeccion", []) or []
        if pend:
            st.markdown("**Para la próxima vez**")
            for p in pend[:6]:
                st.caption(f"{p.get('ticker', '')}: {p.get('motivo', '')}")

    st.divider()
    st.markdown("### Mirá adelante")
    aporte_ars = st.slider(
        "Aporte mensual (ARS)",
        min_value=10_000.0,
        max_value=500_000.0,
        value=100_000.0,
        step=10_000.0,
        key="inversor_aporte_ars",
    )
    horiz_lab = st.selectbox(
        "Horizonte",
        ["1 año", "3 años", "5 años", "10 años"],
        index=1,
        key="inversor_horiz_label",
    )
    horiz_meses = _MESES_HORIZONTE[horiz_lab]
    aporte_usd = float(aporte_ars) / max(ccl, 1e-9)
    rng = np.random.default_rng(seed=42)
    pk = str(ctx.get("cliente_perfil", "moderado")).lower()
    vol_m = {"conservador": 0.025, "moderado": 0.04, "arriesgado": 0.06}
    rend = {"conservador": 0.06, "moderado": 0.09, "arriesgado": 0.12}
    rkey = "moderado"
    if "conserv" in pk:
        rkey = "conservador"
    elif "arries" in pk or "riesg" in pk:
        rkey = "arriesgado"
    r_d = rng.normal(rend[rkey] / 252, vol_m[rkey] / 15, max(252, horiz_meses * 21))
    from core.retirement_goal import simulate_retirement

    sim = simulate_retirement(
        aporte_mensual=aporte_usd,
        n_meses_acum=horiz_meses,
        retiro_mensual=0.0,
        n_meses_desacum=0,
        retornos_diarios=r_d,
        n_sim=1200,
    )
    fig = go.Figure(
        data=[
            go.Bar(
                name="Escenarios",
                x=["Pesimista (p10)", "Base (p50)", "Optimista (p90)"],
                y=[sim["p10"], sim["p50"], sim["p90"]],
                marker_color=["#64748b", "#3b82f6", "#22c55e"],
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        yaxis_title="USD estimados",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Proyección ilustrativa en USD con aporte mensual ~USD {aporte_usd:,.0f} "
        f"(CCL actual {ccl:,.0f}). No es promesa de retorno."
    )

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
        horiz_rep = _MESES_HORIZONTE.get(
            str(st.session_state.get("inversor_horiz_label", "3 años")), 36
        )
        html_rep = generar_reporte_inversor(
            diag,
            rr_dl,
            metricas,
            aporte_mensual_usd=aporte_usd_rep,
            horizon_meses=int(horiz_rep),
            bloque_competitivo=_bloque_competitivo(ctx, diag),
        )
        st.download_button(
            "Descargar informe",
            data=html_rep,
            file_name="mq26_informe.html",
            mime="text/html",
            use_container_width=True,
        )

