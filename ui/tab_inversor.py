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
from core.renta_fija_ar import ladder_vencimientos, tir_ponderada_cartera, top_instrumentos_rf
from services.copy_inversor import (
    antes_despues_defensivo,
    patrimonio_dual_line,
)
from ui.mq26_ux import (
    defensive_bar_html,
    fig_torta_ideal,
    hero_alignment_bar_html,
    obs_card_html,
    plotly_chart_layout_base,
    semaforo_html,
)
from services.investor_hub_snapshot import build_investor_hub_snapshot
from services.cartera_service import PRECIOS_FALLBACK_ARS

_OBS_PRIO_MAP = {
    "critica": "critica", "alta": "alta",
    "media": "media", "baja": "baja",
}


def _precios_para_recomendar(ctx: dict) -> dict:
    """
    Precios **ARS por cuotaparte** (BYMA / teórico NY×CCL÷ratio / fallback).
    Sin esto, cartera vacía solo usa fallbacks viejos o valores que parecen USD.
    """
    from services.cartera_service import (
        asegurar_precios_fallback_cargados,
        resolver_precios,
    )

    ccl = float(ctx.get("ccl") or 1150.0)
    universo_df = ctx.get("universo_df")
    asegurar_precios_fallback_cargados()

    need: set[str] = set()
    for _pesos in CARTERA_IDEAL.values():
        for k in _pesos or {}:
            ks = str(k).strip()
            if ks and not ks.startswith("_"):
                need.add(ks.upper())
    df_an = ctx.get("df_analisis")
    if df_an is not None and not df_an.empty and "TICKER" in df_an.columns:
        for t in df_an["TICKER"].astype(str).str.upper().unique():
            tt = str(t).strip()
            if tt:
                need.add(tt)

    tickers_list = sorted(need)
    live: dict[str, float] = {}
    eng = ctx.get("engine_data")
    if eng is not None and tickers_list:
        try:
            live = eng.obtener_precios_cartera(tickers_list, ccl) or {}
        except Exception:
            live = {}

    resolved = resolver_precios(tickers_list, live, ccl, universo_df)
    out: dict[str, float] = {}
    for k, v in resolved.items():
        fv = float(v or 0.0)
        if fv > 0:
            out[str(k).upper()] = fv
    for k, v in (ctx.get("precios_dict") or {}).items():
        fv = float(v or 0.0)
        if fv > 0:
            out[str(k).upper()] = fv
    for k, v in PRECIOS_FALLBACK_ARS.items():
        out.setdefault(str(k).upper(), float(v))
    return out


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
        horizonte_label=_horizonte_ui(ctx),
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


def _horizonte_ui(ctx: dict) -> str:
    return str(
        ctx.get("cliente_horizonte_label")
        or ctx.get("horizonte_label")
        or "1 año",
    )


def _render_bienvenida_inversor(ctx: dict) -> None:
    """Bienvenida sin cartera: una pregunta, dos caminos, carga o primera cartera."""
    st.session_state.setdefault("inv_carga_open", False)
    nombre = str(ctx.get("cliente_nombre", "")).split("|")[0].strip() or "inversor"
    perfil = str(ctx.get("cliente_perfil", "Moderado"))

    st.markdown(
        f"""
    <div style="padding:2rem 0 1.5rem 0;">
        <h2 style="font-family:'DM Sans',sans-serif;font-size:1.6rem;
                   font-weight:700;letter-spacing:-0.03em;color:#f1f5f9;
                   margin:0 0 0.4rem 0;">
            Hola, {html.escape(nombre)} 👋
        </h2>
        <p style="font-size:1rem;color:#94a3b8;margin:0;line-height:1.6;">
            ¿Ya tenés activos en el broker o querés empezar desde cero?
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col_si, col_no = st.columns(2, gap="large")

    with col_si:
        st.markdown(
            """
        <div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.2);
                    border-radius:16px;padding:1.75rem 1.5rem;min-height:180px;">
            <div style="font-size:2rem;margin-bottom:0.75rem;">📂</div>
            <div style="font-size:1rem;font-weight:600;color:#f1f5f9;
                        margin-bottom:0.5rem;letter-spacing:-0.01em;">
                Ya tengo activos
            </div>
            <div style="font-size:0.8125rem;color:#94a3b8;line-height:1.5;">
                Importá tu resumen del broker (Balanz, IOL, BMB)
                o cargá tus posiciones una por una.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📥 Importar broker", use_container_width=True, key="bienvenida_importar"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "importar"
                st.rerun()
        with c2:
            if st.button("✏️ Cargar uno por uno", use_container_width=True, key="bienvenida_manual"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "manual"
                st.rerun()

    with col_no:
        st.markdown(
            f"""
        <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.2);
                    border-radius:16px;padding:1.75rem 1.5rem;min-height:180px;">
            <div style="font-size:2rem;margin-bottom:0.75rem;">🚀</div>
            <div style="font-size:1rem;font-weight:600;color:#f1f5f9;
                        margin-bottom:0.5rem;letter-spacing:-0.01em;">
                Empezar de cero
            </div>
            <div style="font-size:0.8125rem;color:#94a3b8;line-height:1.5;">
                La app arma la cartera óptima para tu perfil
                <strong style="color:#10b981;">{html.escape(perfil)}</strong>
                con el capital que tenés disponible.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        if st.button(
            "✨ Armar mi primera cartera",
            use_container_width=True,
            type="primary",
            key="bienvenida_sugerencia",
        ):
            st.session_state["inv_mostrar_sugerencia"] = True
            st.rerun()

    if st.session_state.get("inv_carga_open"):
        st.divider()
        _fn = ctx.get("render_carga_activos_fn")
        if _fn is None:
            from ui.carga_activos import render_carga_activos as _fn
        _fn(ctx)

    if st.session_state.get("inv_mostrar_sugerencia"):
        st.divider()
        _render_primera_cartera_inversor(ctx)


def _render_primera_cartera_inversor(ctx: dict) -> None:
    """Primera cartera: capital en ARS + diagnosticar + recomendar."""
    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte = _horizonte_ui(ctx)
    ccl = float(ctx.get("ccl") or 1150.0)
    perfil_v = perfil_diagnostico_valido(perfil)

    st.markdown(
        """
    <p style="font-size:0.72rem;font-weight:700;color:#10b981;
              text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;">
        Paso 1 de 2 — Tu capital disponible
    </p>
    """,
        unsafe_allow_html=True,
    )
    col_monto, col_info = st.columns([3, 2])
    with col_monto:
        capital_ars = st.number_input(
            "¿Cuánto querés invertir? (ARS)",
            min_value=10_000.0,
            max_value=100_000_000.0,
            value=500_000.0,
            step=50_000.0,
            format="%.0f",
            key="pci_capital_ars",
            help="El motor distribuye este monto según tu perfil.",
        )
    with col_info:
        capital_usd = capital_ars / max(ccl, 1.0)
        st.markdown(
            f"""
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);
                    border-radius:10px;padding:1rem;margin-top:1.5rem;">
            <div style="font-size:0.65rem;color:#4b5563;text-transform:uppercase;
                        letter-spacing:0.06em;margin-bottom:4px;">Tu inversión</div>
            <div style="font-family:'DM Mono',monospace;font-size:1.15rem;
                        font-weight:600;color:#f1f5f9;">$ {capital_ars:,.0f} ARS</div>
            <div style="font-size:0.72rem;color:#64748b;margin-top:6px;line-height:1.35;">
                Referencia ~ USD {capital_usd:,.0f} (CCL {ccl:,.0f})</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
    <p style="font-size:0.72rem;font-weight:700;color:#10b981;
              text-transform:uppercase;letter-spacing:0.08em;
              margin-top:1.25rem;margin-bottom:0.25rem;">
        Paso 2 de 2 — La app calcula por vos
    </p>
    <p style="font-size:0.8125rem;color:#94a3b8;margin:0 0 0.75rem 0;">
        Perfil, mercado y señales técnicas. Solo presioná el botón.
    </p>
    """,
        unsafe_allow_html=True,
    )

    if st.button(
        f"🧠 Calcular cartera óptima para perfil {perfil}",
        type="primary",
        use_container_width=True,
        key="btn_calcular_primera_cartera",
    ):
        with st.spinner("Calculando tu cartera óptima…"):
            try:
                from services.diagnostico_cartera import diagnosticar
                from services.recomendacion_capital import recomendar

                diag = diagnosticar(
                    df_ag=pd.DataFrame(),
                    perfil=perfil_v,
                    horizonte_label=horizonte,
                    metricas={},
                    ccl=ccl,
                    universo_df=ctx.get("universo_df"),
                    senales_salida=None,
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                )
                rr = recomendar(
                    df_ag=pd.DataFrame(),
                    perfil=perfil_v,
                    horizonte_label=horizonte,
                    capital_ars=float(capital_ars),
                    ccl=ccl,
                    precios_dict=_precios_para_recomendar(ctx),
                    diagnostico=diag,
                    universo_df=ctx.get("universo_df"),
                    df_analisis=ctx.get("df_analisis"),
                    market_stress=_market_stress_optional(),
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                )
                st.session_state["pci_resultado"] = {
                    "capital": float(capital_ars),
                    "rr": rr,
                    "perfil": perfil_v,
                    "ideal": CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"]),
                }
                st.rerun()
            except Exception as e:
                st.error(f"Error al calcular: {e}")

    res = st.session_state.get("pci_resultado")
    cap_ui = float(st.session_state.get("pci_capital_ars", 0) or 0)
    if not res or abs(float(res.get("capital", -1)) - cap_ui) >= 1.0:
        return

    rr = res["rr"]
    perfil_res = str(res.get("perfil") or perfil_v)

    if getattr(rr, "alerta_mercado", False):
        st.warning(f"⚠️ {rr.mensaje_alerta}")

    items = list(getattr(rr, "compras_recomendadas", None) or [])
    if not items:
        st.info(
            "No se encontraron compras posibles con el capital disponible. "
            "Probá con otro monto o consultá a tu asesor."
        )
        return

    st.markdown(
        """
    <p style="font-size:0.72rem;font-weight:700;color:#10b981;
              text-transform:uppercase;letter-spacing:0.08em;
              margin:1.25rem 0 0.75rem 0;">Tu cartera sugerida</p>
    """,
        unsafe_allow_html=True,
    )

    monto_total = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)

    for it in items:
        ticker = str(getattr(it, "ticker", ""))
        monto_ars = float(getattr(it, "monto_ars", 0) or 0)
        unidades = int(getattr(it, "unidades", 0) or 0)
        prio_raw = getattr(it, "prioridad", "") or ""
        prio = str(getattr(prio_raw, "value", prio_raw)).lower()
        motivo = str(getattr(it, "justificacion", "") or "")
        nombre_leg = str(getattr(it, "nombre_legible", ticker) or ticker)
        px_u = float(getattr(it, "precio_ars_estimado", 0) or 0)
        color = "#10b981" if "defensa" in prio else ("#3b82f6" if "concentra" in prio else "#f59e0b")
        _px_line = (
            f"~ $ {px_u:,.0f} ARS c/u · "
            if px_u > 0
            else ""
        )
        st.markdown(
            f"""
        <div style="display:flex;align-items:center;gap:1rem;background:rgba(255,255,255,0.02);
                    border:1px solid rgba(255,255,255,0.06);border-left:3px solid {color};
                    border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.5rem;">
            <div style="flex:1;">
                <div style="font-weight:600;font-size:0.9rem;color:#f1f5f9;">
                    {html.escape(ticker)}
                    <span style="font-weight:400;font-size:0.78rem;color:#94a3b8;margin-left:0.5rem;">
                        {html.escape(nombre_leg[:40])}
                    </span>
                </div>
                <div style="font-size:0.72rem;color:#64748b;margin-top:3px;">{_px_line}En el broker pagás en pesos.</div>
                <div style="font-size:0.75rem;color:#4b5563;margin-top:2px;">{html.escape(motivo[:80])}</div>
            </div>
            <div style="text-align:right;min-width:130px;">
                <div style="font-family:'DM Mono',monospace;font-weight:600;font-size:0.925rem;color:#f1f5f9;">
                    × {unidades} ud
                </div>
                <div style="font-family:'DM Mono',monospace;font-size:0.75rem;color:{color};">${monto_ars:,.0f} ARS</div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    ideal_dict = res.get("ideal") or {}
    st.markdown(
        f"""
    <div style="background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.15);
                border-radius:10px;padding:1rem 1.25rem;margin-top:0.75rem;
                display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem;">
        <div><div style="font-size:0.65rem;color:#4b5563;text-transform:uppercase;">Total a invertir</div>
        <div style="font-family:'DM Mono',monospace;font-size:1.1rem;font-weight:600;color:#10b981;">
            ${monto_total:,.0f} ARS</div></div>
        <div><div style="font-size:0.65rem;color:#4b5563;text-transform:uppercase;">Queda en efectivo</div>
        <div style="font-family:'DM Mono',monospace;font-size:1.1rem;color:#94a3b8;">${remanente:,.0f} ARS</div></div>
        <div><div style="font-size:0.65rem;color:#4b5563;text-transform:uppercase;">Perfil</div>
        <div style="font-size:0.875rem;font-weight:600;color:#f1f5f9;">{html.escape(perfil_res)}</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if ideal_dict:
        fig_t = fig_torta_ideal(perfil_res, ideal_dict)
        if fig_t:
            with st.expander("Ver distribución objetivo de la cartera", expanded=False):
                st.plotly_chart(fig_t, use_container_width=True)

    st.info(
        "💡 Sugerencia educativa según tu perfil y el mercado hoy. "
        "Podés cargar posiciones o importar del broker cuando operes."
    )
    col_act, col_reset = st.columns(2)
    with col_act:
        if st.button("✏️ Cargar lo que compré", use_container_width=True, key="pci_ir_a_carga"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "manual"
            st.session_state.pop("pci_resultado", None)
            st.rerun()
    with col_reset:
        if st.button("🔄 Recalcular con otro monto", use_container_width=True, key="pci_reset"):
            st.session_state.pop("pci_resultado", None)
            st.rerun()


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


def _senal_orden_rank(senal: str) -> int:
    s = (senal or "").upper()
    if "SALIR" in s:
        return 0
    if "REVISAR" in s or "ATENCI" in s:
        return 1
    if "CERCA" in s:
        return 2
    return 3


def _render_posiciones_con_targets(ctx: dict, _diag: object) -> None:
    from services.motor_salida import evaluar_salida

    try:
        from core.db_manager import obtener_objetivos_cliente, registrar_objetivo
    except Exception:
        obtener_objetivos_cliente = None  # type: ignore[assignment]
        registrar_objetivo = None  # type: ignore[assignment]

    df_ag = ctx.get("df_ag")
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    cid = ctx.get("cliente_id")
    dbm = ctx.get("dbm")
    precios = ctx.get("precios_dict") or {}
    df_anal = ctx.get("df_analisis")

    if df_ag is None or df_ag.empty:
        return

    obj_df = pd.DataFrame()
    if cid and dbm and obtener_objetivos_cliente:
        try:
            obj_df = obtener_objetivos_cliente(int(cid))
        except Exception:
            pass

    obj_map: dict[str, dict] = {}
    if not obj_df.empty and "Ticker" in obj_df.columns:
        for _, row in obj_df.iterrows():
            tk = str(row.get("Ticker", "")).upper().strip()
            if tk and tk not in obj_map:
                obj_map[tk] = row.to_dict()

    st.markdown(
        "### Mis posiciones",
    )
    st.caption(
        "Cuánto tenés de cada activo, cuánto ganás, y cuándo conviene vender.",
    )

    hoy = date.today()
    filas: list[dict] = []

    for _, pos in df_ag.iterrows():
        ticker = str(pos.get("TICKER", "")).upper().strip()
        if not ticker:
            continue

        ppc_ars = float(pd.to_numeric(pos.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
        px_ars = float(pd.to_numeric(pos.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
        if px_ars <= 0:
            px_ars = float(precios.get(ticker, 0) or 0)

        valor_ars = float(pos.get("VALOR_ARS", 0) or 0)
        pnl_frac = float(pd.to_numeric(pos.get("PNL_PCT_USD", pos.get("PNL_PCT", 0)), errors="coerce") or 0.0)

        fecha_c = pos.get("FECHA_COMPRA")
        dias = 0
        fecha_d: date = hoy
        if fecha_c is not None:
            try:
                if hasattr(fecha_c, "date") and callable(getattr(fecha_c, "date", None)):
                    fecha_d = fecha_c.date()  # type: ignore[union-attr]
                else:
                    _dt = pd.to_datetime(str(fecha_c), errors="coerce")
                    fecha_d = _dt.date() if pd.notna(_dt) else hoy
                dias = max(1, (hoy - fecha_d).days)
            except Exception:
                fecha_d = hoy
                dias = 0

        if dias > 0 and pnl_frac > -1.0:
            cagr = ((1.0 + pnl_frac) ** (365.0 / max(dias, 1)) - 1.0) * 100.0
        else:
            cagr = 0.0

        score_v = 50.0
        rsi_val = 50.0
        if df_anal is not None and not df_anal.empty and "TICKER" in df_anal.columns:
            m = df_anal[df_anal["TICKER"].astype(str).str.upper() == ticker]
            if not m.empty:
                row0 = m.iloc[0]
                if "PUNTAJE_TECNICO" in m.columns:
                    score_v = float(row0.get("PUNTAJE_TECNICO", 50) or 50)
                elif "SCORE" in m.columns:
                    score_v = float(row0.get("SCORE", 50) or 50)
                if "RSI" in m.columns:
                    rsi_val = float(row0.get("RSI", 50) or 50)

        obj_ticker = obj_map.get(ticker, {})
        tgt_o = obj_ticker.get("Target %")
        st_o = obj_ticker.get("Stop %")
        target_override = (
            float(tgt_o) if tgt_o not in (None, "") and pd.notna(tgt_o) else None
        )
        stop_override = (
            float(st_o) if st_o not in (None, "") and pd.notna(st_o) else None
        )

        if ppc_ars <= 0 or px_ars <= 0:
            continue

        try:
            ms = evaluar_salida(
                ticker=ticker,
                ppc_usd=ppc_ars,
                px_usd_actual=px_ars,
                rsi=rsi_val,
                score_actual=score_v,
                score_semana_anterior=score_v,
                fecha_compra=fecha_d,
                perfil=perfil_ms,
                override_target_pct=target_override,
                override_stop_pct=stop_override,
            )
        except Exception:
            ms = {
                "progreso_pct": 0.0,
                "precio_target": 0.0,
                "precio_stop": 0.0,
                "senal": "—",
                "target_pct": 25.0,
                "stop_pct": -15.0,
            }

        filas.append({
            "_ticker": ticker,
            "_dias": dias,
            "_pnl_frac": pnl_frac,
            "_cagr": cagr,
            "_valor_ars": valor_ars,
            "_progreso": float(ms.get("progreso_pct", 0) or 0),
            "_target_pct": float(ms.get("target_pct", 25)),
            "_stop_pct": float(ms.get("stop_pct", -15)),
            "_senal": str(ms.get("senal", "—")),
            "_target_override": target_override,
            "_stop_override": stop_override,
        })

    if not filas:
        return

    filas.sort(key=lambda r: (_senal_orden_rank(r["_senal"]), -r["_progreso"]))

    for f in filas:
        ticker = f["_ticker"]
        dias = f["_dias"]
        pnl_frac = f["_pnl_frac"]
        cagr = f["_cagr"]
        valor_ars = f["_valor_ars"]
        progreso = f["_progreso"]
        target_pct = f["_target_pct"]
        stop_pct = f["_stop_pct"]
        senal = f["_senal"]

        pnl_color = "#10b981" if pnl_frac >= 0 else "#ef4444"
        pnl_sign = "+" if pnl_frac >= 0 else ""
        dias_txt = f"{dias}d" if dias > 0 else "—"
        cagr_txt = f"{cagr:+.1f}%/año" if abs(cagr) > 0.1 else "—"
        prog_color = "#10b981" if progreso >= 80 else ("#3b82f6" if progreso >= 40 else "#f59e0b")
        prog_width = min(100.0, max(0.0, progreso))
        if pnl_frac * 100.0 < stop_pct:
            prog_color = "#ef4444"
            prog_width = 100.0

        with st.container():
            col_main, col_meta, col_senal = st.columns([4, 3, 2])
            with col_main:
                st.markdown(
                    f"""
                <div style="margin-bottom:0.1rem;">
                    <strong style="font-size:0.9rem;color:#f1f5f9;">{html.escape(ticker)}</strong>
                    <span style="font-size:0.75rem;color:{pnl_color};font-family:'DM Mono',monospace;
                                 margin-left:0.5rem;font-weight:600;">{pnl_sign}{pnl_frac:.1%}</span>
                </div>
                <div style="margin-bottom:0.4rem;">
                    <div style="background:rgba(255,255,255,0.07);border-radius:4px;height:5px;overflow:hidden;">
                        <div style="width:{prog_width:.0f}%;height:100%;background:{prog_color};border-radius:4px;"></div>
                    </div>
                </div>
                <div style="font-size:0.65rem;color:#4b5563;">
                    Progreso al objetivo: {progreso:.0f}% (target +{target_pct:.0f}% / stop {stop_pct:.0f}%)
                </div>
                """,
                    unsafe_allow_html=True,
                )
            with col_meta:
                st.markdown(
                    f"""
                <div style="font-size:0.72rem;color:#94a3b8;line-height:1.8;">
                    <span style="color:#4b5563;font-size:0.65rem;">EN CARTERA </span>
                    <strong style="font-family:'DM Mono',monospace;">{dias_txt}</strong><br>
                    <span style="color:#4b5563;font-size:0.65rem;">TASA ANUAL </span>
                    <strong style="font-family:'DM Mono',monospace;color:{'#10b981' if cagr > 0 else '#ef4444'};">
                        {cagr_txt}</strong><br>
                    <span style="color:#4b5563;font-size:0.65rem;">VALOR </span>
                    <strong style="font-family:'DM Mono',monospace;">${valor_ars:,.0f}</strong>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            with col_senal:
                senal_word = senal.split()[-1].upper() if senal else "—"
                senal_colors = {
                    "SALIR": ("#ef4444", "rgba(239,68,68,0.12)"),
                    "REVISAR": ("#f59e0b", "rgba(245,158,11,0.12)"),
                    "ATENCIÓN": ("#f59e0b", "rgba(245,158,11,0.12)"),
                    "CAMINO": ("#6b7280", "rgba(107,114,128,0.08)"),
                    "OBJETIVO": ("#f59e0b", "rgba(245,158,11,0.12)"),
                }
                sc, sb = senal_colors.get(senal_word, ("#6b7280", "rgba(107,114,128,0.08)"))
                st.markdown(
                    f"""
                <div style="text-align:right;padding-top:0.25rem;">
                    <span style="font-size:0.68rem;font-weight:700;color:{sc};background:{sb};
                                 padding:3px 10px;border-radius:999px;border:1px solid {sc}44;">
                        {html.escape(senal_word)}
                    </span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        t_val = float(f["_target_override"] if f["_target_override"] is not None else target_pct)
        s_val = float(abs(f["_stop_override"])) if f["_stop_override"] is not None else abs(stop_pct)

        with st.expander(f"⚙️ Personalizar target/stop de {ticker}", expanded=False):
            col_t, col_s = st.columns(2)
            nuevo_target = col_t.number_input(
                "Target % (ganancia para vender)",
                min_value=5.0,
                max_value=500.0,
                value=min(500.0, max(5.0, t_val)),
                step=5.0,
                key=f"target_{ticker}",
            )
            nuevo_stop = col_s.number_input(
                "Stop % (pérdida máxima)",
                min_value=1.0,
                max_value=80.0,
                value=min(80.0, max(1.0, s_val)),
                step=1.0,
                key=f"stop_{ticker}",
            )
            if st.button(f"Guardar objetivos de {ticker}", key=f"btn_obj_{ticker}"):
                if cid and dbm and registrar_objetivo:
                    try:
                        registrar_objetivo(
                            cliente_id=int(cid),
                            monto_ars=0.0,
                            plazo_label="1 año",
                            motivo=f"Target/stop personalizado para {ticker}",
                            ticker=ticker,
                            target_pct=float(nuevo_target),
                            stop_pct=-float(nuevo_stop),
                            tenant_id=str(ctx.get("tenant_id", "default")),
                        )
                        st.success(
                            f"✓ {ticker}: target +{nuevo_target:.0f}% / stop -{nuevo_stop:.0f}%"
                        )
                        st.session_state.pop("inv_diagnostico", None)
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

        st.markdown(
            "<hr style='border:none;border-top:1px solid rgba(255,255,255,0.05);"
            "margin:0.4rem 0 0.6rem 0;'>",
            unsafe_allow_html=True,
        )


def render_tab_inversor(ctx: dict) -> None:
    with st.expander("⚙️ Mi perfil y configuración", expanded=False):
        _render_config_perfil(ctx)

    df_ag = ctx.get("df_ag")
    metricas = ctx.get("metricas") or {}
    ccl = float(ctx.get("ccl") or 1.0)

    if df_ag is None or df_ag.empty:
        _render_bienvenida_inversor(ctx)
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

    hub = build_investor_hub_snapshot(diag, metricas, ccl, valor_total_ars=valor_total)

    st.markdown(
        """
<h2 style="font-size:1.35rem;font-weight:700;letter-spacing:-0.025em;
           color:var(--c-text);margin:0 0 0.25rem 0;">
    Mi cartera
</h2>
""",
        unsafe_allow_html=True,
    )
    st.caption(patrimonio_dual_line(valor_usd, valor_total, ccl))

    st.markdown(
        "<p class='mq-hub-lead' style='font-size:0.75rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.5rem;'>"
        "Tu salud financiera</p>",
        unsafe_allow_html=True,
    )
    h1, h2, h3 = st.columns([1.1, 1.1, 0.5])
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
    with h2:
        st.markdown(
            hero_alignment_bar_html(hub["alignment_score_pct"]),
            unsafe_allow_html=True,
        )
    with h3:
        if st.button("Actualizar", key="btn_refresh_diag_inversor", use_container_width=True):
            st.session_state.pop("inv_diagnostico", None)
            st.rerun()

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("Cuánto vale tu cartera", f"ARS {valor_total:,.0f}")
    m2.metric("En dólares (aprox.)", f"USD {valor_usd:,.0f}")
    m3.metric(
        "Cómo te fue",
        f"{pnl_pct:+.1f}%",
        help="Rendimiento de referencia en USD (CEDEARs); el valor de mercado es en pesos.",
    )
    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    _res_ej = (hub.get("resumen_ejecutivo") or "").strip()
    if _res_ej:
        st.markdown(
            f"<div style='font-size:0.9rem;color:var(--c-text-2);line-height:1.45;"
            f"margin-bottom:0.75rem;'>{html.escape(_res_ej[:900])}"
            f"{'…' if len(_res_ej) > 900 else ''}</div>",
            unsafe_allow_html=True,
        )

    _def_ok = pct_def_frac >= pct_def_req_frac
    _rv_frac = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - pct_def_frac)) or 0.0)
    _def_label = (
        "✓ Renta fija en rango vs tu plan"
        if _def_ok
        else f"Falta renta fija ({pct_def_req_frac:.0%} sugerido para tu perfil)"
    )
    with st.expander("Comparativa vs tu perfil (renta fija vs renta variable)", expanded=False):
        st.caption(
            "**Renta fija (RF):** bonos, ONs, letras. **Renta variable (RV):** Cedears y acciones. "
            "La barra muestra tu RF frente al objetivo del perfil. "
            f"RV ~{_rv_frac:.0%}. Reglas motor: **{getattr(diag, 'ruleset_version', '') or '—'}**."
        )
        st.markdown(
            defensive_bar_html(pct_def_frac, pct_def_req_frac, _def_label),
            unsafe_allow_html=True,
        )

    with st.expander("Qué hacer hoy (prioridades del diagnóstico)", expanded=True):
        for a in hub.get("acciones_top") or []:
            st.markdown(f"**{a.get('titulo', '—')}** ({a.get('prioridad', '')}) — _{a.get('cifra', '')}_")

    with st.expander("Rebalanceo y plata nueva (sugerencias)", expanded=False):
        _render_bloque_plata_nueva(ctx, df_ag, diag, ccl)

    st.divider()
    _render_posiciones_con_targets(ctx, diag)
    st.divider()

    _ccl_v = float(ctx.get("ccl") or 1150.0)
    with st.expander("💵 ¿Tenés plata para invertir esta semana?", expanded=False):
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
                f"<div style='font-family:DM Mono,monospace;font-size:1.25rem;"
                f"font-weight:500;color:var(--c-text);'>"
                f"ARS {_total_ars:,.0f}</div>"
                f"<div style='font-size:0.7rem;color:var(--c-text-3);margin-top:2px;'>"
                f"Cartera ~ ARS {_val_cartera_ars:,.0f} · "
                f"Efectivo ~ ARS {_efectivo_ars:,.0f} · "
                f"ref. USD {_total_patrimon:,.0f}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


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
    _render_proyeccion_y_pie_inversor(ctx, diag, metricas)


def _render_bloque_plata_nueva(ctx: dict, df_ag, diag, ccl: float) -> None:
    """Bloque extraído: capital nuevo y órdenes sugeridas."""
    st.markdown("### ¿Qué compro ahora?")
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
            horizonte_label=_horizonte_ui(ctx),
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


def _render_proyeccion_y_pie_inversor(ctx: dict, diag, metricas: dict) -> None:
    """Proyección simple, acciones rápidas y descarga de informe (detalle al final del scroll)."""
    st.markdown(
        "<p style='font-size:0.72rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.07em;'>Proyección patrimonial</p>",
        unsafe_allow_html=True,
    )
    from core.retirement_goal import simulate_retirement

    col_a, col_b = st.columns(2)
    aporte_ars = col_a.number_input(
        "Aporte mensual (ARS)",
        min_value=0.0,
        value=float(st.session_state.get("inversor_aporte_ars", 50_000.0)),
        step=10_000.0,
        format="%.0f",
        key="inversor_aporte_ars",
    )
    horizonte_opts = {"1 año": 12, "3 años": 36, "5 años": 60, "10 años": 120}
    horizonte_sel = col_b.selectbox(
        "Horizonte",
        list(horizonte_opts.keys()),
        index=1,
        key="inversor_horiz_label",
    )
    meses = horizonte_opts[horizonte_sel]
    ccl_v = float(ctx.get("ccl") or 1150.0)
    aporte_usd = aporte_ars / max(ccl_v, 1.0)
    val_actual_usd = float(getattr(diag, "valor_cartera_usd", 0) or 0)
    escenarios = {}
    for label, ret_anual in [("Pesimista", 0.04), ("Base", 0.09), ("Optimista", 0.15)]:
        sim = simulate_retirement(
            capital_inicial_usd=val_actual_usd,
            aporte_mensual_usd=aporte_usd,
            retorno_anual=ret_anual,
            meses=meses,
        )
        escenarios[label] = sim.get("capital_final_usd", 0.0)
    COLORS = {"Pesimista": "#ef4444", "Base": "#3b82f6", "Optimista": "#10b981"}
    escenarios_ars = {k: float(v) * ccl_v for k, v in escenarios.items()}
    fig_proy = go.Figure(data=[
        go.Bar(
            x=list(escenarios_ars.keys()),
            y=list(escenarios_ars.values()),
            marker_color=[COLORS[k] for k in escenarios_ars],
            text=[f"{v:,.0f} ARS" for v in escenarios_ars.values()],
            textposition="outside",
        )
    ])
    fig_proy.update_layout(
        **plotly_chart_layout_base(
            height=280,
            showlegend=False,
            yaxis=dict(
                title="Patrimonio estimado (ARS)",
                tickformat=",.0f",
                ticksuffix=" ARS",
                gridcolor="rgba(148,163,184,0.12)",
            ),
            xaxis=dict(tickfont=dict(size=13)),
            margin=dict(t=20, b=20, l=10, r=10),
        ),
    )
    st.plotly_chart(fig_proy, use_container_width=True)
    base_val = escenarios.get("Base", 0)
    base_val_ars = escenarios_ars.get("Base", 0.0)
    delta_pct = ((base_val - val_actual_usd) / max(val_actual_usd, 1)) * 100 if val_actual_usd else 0
    st.markdown(
        f"<p style='font-size:0.78rem;color:var(--c-text-2);text-align:center;'>"
        f"Escenario base: tu patrimonio podría crecer "
        f"<strong style='color:#3b82f6;'>+{delta_pct:.0f}%</strong> en {horizonte_sel}, "
        f"llegando a unos <strong style='color:#3b82f6;'>ARS {base_val_ars:,.0f}</strong> "
        f"(~ USD {base_val:,.0f})</p>",
        unsafe_allow_html=True,
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

