"""
ui/tab_inversor.py — Vista del inversor individual (tier IN).

Secciones: resumen + lista legible, carga, plata nueva, proyección.
"""
from __future__ import annotations

import html
import time
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.diagnostico_types import (
    CARTERA_IDEAL,
    RENDIMIENTO_MODELO_YTD_REF,
    UNIVERSO_RENTA_FIJA_AR,
    perfil_diagnostico_valido,
    perfil_motor_salida,
)
from core.renta_fija_ar import _meta_unificado as _rf_meta_unificado
from core.renta_fija_ar import (
    es_fila_renta_fija_ar,
    es_renta_fija,
    get_meta,
)
from services.copy_inversor import (
    GLOSARIO_INVERSOR,
    antes_despues_defensivo,
    copy_rebalanceo_humano,
    pasos_onboarding_hub,
    patrimonio_dual_line,
)
from services.investor_hub_snapshot import build_investor_hub_snapshot
from services.plan_simulaciones import (
    agrupar_pesos_torta,
    df_ag_tiene_posiciones_reales,
    dias_desde_primera_compra,
    ideal_dict_desde_mix_plan,
)
from ui.inversor._helpers import (
    _TIPOS_EDICION_PRIMERA_CARTERA,
    _cartera_resuelta_primera_cartera,
    _get_diagnostico_cached,
    _horizonte_ui,
    _log_degradacion,
    _market_stress_optional,
    _mix_objetivo_desde_sesion,
    _mix_rf_desde_filas_primera,
    _nombre_universo_para_ticker,
    _precios_para_recomendar,
    _senales_precalculadas,
    _ticker_desde_fila_pos,
    _tipo_universo_ticker,
)
from ui.inversor.proyeccion import _render_proyeccion_y_pie_inversor
from ui.mq26_ux import (
    dataframe_auto_height,
    defensive_bar_html,
    fig_torta_ideal,
    obs_card_html,
    plotly_chart_layout_base,
    semaforo_html,
)
from ui.posiciones_broker_table import build_posiciones_broker_html

_OBS_PRIO_MAP = {
    "critica": "critica", "alta": "alta",
    "media": "media", "baja": "baja",
}


# ── Perfiles para el selector visual ──────────────────────────────────────────
_PERFILES_INFO: dict[str, dict] = {
    "Conservador": {
        "icono": "🛡️",
        "lema": "Priorizo no perder.",
        "rf_rv": "60% RF · 40% RV",
        "color": "#2196F3",
    },
    "Moderado": {
        "icono": "⚖️",
        "lema": "Equilibrio riesgo/retorno.",
        "rf_rv": "50% RF · 50% RV",
        "color": "#4CAF50",
    },
    "Arriesgado": {
        "icono": "📈",
        "lema": "Acepto volatilidad.",
        "rf_rv": "35% RF · 65% RV",
        "color": "#FF9800",
    },
    "Muy arriesgado": {
        "icono": "🚀",
        "lema": "Máximo potencial.",
        "rf_rv": "30% RF · 70% RV",
        "color": "#F44336",
    },
}


# ── Selector de perfil minimalista (visual, una sola decisión del inversor) ──
def _render_selector_perfil_cards(ctx: dict) -> None:
    """
    4 tarjetas visuales para elegir perfil de riesgo.
    El inversor solo presiona una — es la única decisión requerida.
    """
    from core.db_manager import actualizar_cliente

    cid = ctx.get("cliente_id")
    dbm = ctx.get("dbm")
    perfil_actual = str(ctx.get("cliente_perfil", "Moderado"))

    st.markdown(
        "<p style='font-size:0.7rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.08em;margin:0 0 0.4rem 0;'>"
        "Mi perfil de riesgo</p>",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    for col, (nombre, info) in zip(cols, _PERFILES_INFO.items(), strict=False):
        activo = nombre == perfil_actual
        borde = f"2px solid {info['color']}" if activo else "1px solid #424242"
        bg = f"{info['color']}18" if activo else "transparent"
        with col:
            st.markdown(
                f"<div style='border:{borde};border-radius:8px;padding:0.55rem 0.6rem;"
                f"background:{bg};text-align:center;'>"
                f"<div style='font-size:1.4rem;'>{info['icono']}</div>"
                f"<div style='font-size:0.78rem;font-weight:700;color:{info['color']};'>{nombre}</div>"
                f"<div style='font-size:0.68rem;color:var(--c-text-3);'>{info['rf_rv']}</div>"
                f"<div style='font-size:0.63rem;color:var(--c-text-3);margin-top:0.15rem;'>{info['lema']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if not activo and cid and dbm:
                if st.button(
                    "Elegir",
                    key=f"btn_perfil_{nombre.replace(' ', '_')}",
                    use_container_width=True,
                ):
                    try:
                        horizonte_act = str(ctx.get("cliente_horizonte_label", "1 año"))
                        capital_act = float(ctx.get("cliente_capital_usd", 0) or 0)
                        nombre_act = str(ctx.get("cliente_nombre", "")).split("|")[0].strip()
                        actualizar_cliente(
                            int(cid), nombre_act or "—", nombre,
                            capital_act, "Persona", horizonte_act,
                            tenant_id=str(ctx.get("tenant_id") or "default"),
                        )
                        st.session_state["cliente_perfil"] = nombre
                        st.session_state.pop("inv_diagnostico", None)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"No se pudo cambiar el perfil: {_e}")
            elif activo:
                st.markdown(
                    f"<div style='text-align:center;font-size:0.65rem;"
                    f"color:{info['color']};font-weight:600;margin-top:0.15rem;'>Activo</div>",
                    unsafe_allow_html=True,
                )


# ── Panel de KPIs Renta Fija ──────────────────────────────────────────────────
def _render_panel_rf_kpis(ctx: dict, df_ag: pd.DataFrame, ccl: float, diag) -> None:
    """
    Panel dedicado de Renta Fija con KPIs propios:
    TIR ponderada, paridad BYMA live, % RF vs objetivo,
    próximo vencimiento y ladder de vencimientos.
    """
    from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
    from core.perfil_allocation import target_rf_efectivo
    from core.renta_fija_ar import (
        INSTRUMENTOS_RF,
        es_fila_renta_fija_ar,
        ficha_rf_minima_bundle,
        get_meta,
        ladder_vencimientos,
        tir_ponderada_cartera,
    )
    from ui.components.ficha_rf_minima import render_ficha_rf_minima
    from ui.tab_cartera import _paridad_implicita_pct_on_usd_desde_fila

    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte = str(ctx.get("cliente_horizonte_label", "1 año"))
    target_rf = target_rf_efectivo(perfil, horizonte)
    pct_rf_actual = float(getattr(diag, "pct_defensivo_actual", 0) or 0)

    st.markdown(
        "<p style='font-size:0.7rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.08em;margin:0.75rem 0 0.4rem 0;'>"
        "Renta Fija</p>",
        unsafe_allow_html=True,
    )

    # KPIs fila 1
    k1, k2, k3, k4 = st.columns(4)

    # TIR ponderada
    tir = tir_ponderada_cartera(df_ag)
    k1.metric(
        "TIR ponderada",
        f"{tir:.2f}%" if tir is not None else "—",
        help="TIR de referencia promedio ponderada por peso en cartera de los instrumentos RF.",
    )

    # % RF actual vs objetivo
    delta_rf = pct_rf_actual - target_rf
    k2.metric(
        "RF en cartera",
        f"{pct_rf_actual:.1%}",
        delta=f"{delta_rf:+.1%} vs objetivo {target_rf:.0%}",
        delta_color="normal" if abs(delta_rf) < 0.05 else ("inverse" if delta_rf < 0 else "normal"),
        help=f"Objetivo RF para perfil {perfil}: {target_rf:.0%}.",
    )

    # Paridad promedio (BYMA live si disponible, sino catálogo)
    _byma_enrich: dict = {}
    try:
        import sys as _sys
        from pathlib import Path as _BPath
        _r = str(_BPath(__file__).resolve().parent.parent)
        if _r not in _sys.path:
            _sys.path.insert(0, _r)
        from services.byma_market_data import cached_on_byma
        _byma_enrich = cached_on_byma(ccl) or {}
    except Exception as exc:
        _log_degradacion(ctx, "rf_byma_enrich_fallo", exc)

    paridades: list[float] = []
    for _, row in df_ag.iterrows():
        if not es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
            continue
        tk = str(row.get("TICKER", "")).upper()
        live = _byma_enrich.get(tk, {})
        par = live.get("paridad_ref") if live else None
        if par is None:
            meta = INSTRUMENTOS_RF.get(tk) or {}
            par = meta.get("paridad_ref")
        if par is not None:
            try:
                paridades.append(float(par))
            except (TypeError, ValueError):
                pass
    paridad_prom = sum(paridades) / len(paridades) if paridades else None
    fuente_par = "BYMA" if _byma_enrich else "catálogo"
    k3.metric(
        "Paridad prom.",
        f"{paridad_prom:.1f}%" if paridad_prom is not None else "—",
        help=f"Paridad promedio de instrumentos RF en cartera (fuente: {fuente_par}).",
    )

    # Próximo vencimiento RF
    ladder = ladder_vencimientos(df_ag)
    from datetime import date as _date
    anio_hoy = _date.today().year
    proximos = [(y, w) for y, w in ladder if y >= anio_hoy]
    if proximos:
        proximo_año, proximo_w = proximos[0]
        k4.metric(
            "Próximo vto.",
            str(proximo_año),
            delta=f"{proximo_w:.1%} de cartera",
            delta_color="off",
            help="Año del próximo vencimiento RF y su peso en cartera.",
        )
    else:
        k4.metric("Próximo vto.", "—")

    # Variación del día (BYMA) si disponible
    if _byma_enrich:
        vars_dia: list[float] = []
        for _, row in df_ag.iterrows():
            if not es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
                continue
            tk = str(row.get("TICKER", "")).upper()
            live = _byma_enrich.get(tk, {})
            v = live.get("var_diaria_pct")
            if v is not None:
                try:
                    vars_dia.append(float(v))
                except (TypeError, ValueError):
                    pass
        if vars_dia:
            var_prom_dia = sum(vars_dia) / len(vars_dia)
            signo = "+" if var_prom_dia >= 0 else ""
            st.caption(
                f"Variación promedio del día (BYMA live): "
                f"**{signo}{var_prom_dia:.2f}%** sobre {len(vars_dia)} ticker(s) RF"
            )

    # Ladder de vencimientos como gráfico
    if ladder:
        import plotly.graph_objects as _go
        años = [str(y) for y, _ in ladder]
        pesos = [round(w * 100, 1) for _, w in ladder]
        fig_l = _go.Figure(_go.Bar(
            x=años, y=pesos,
            marker_color="#2196F3",
            text=[f"{p:.1f}%" for p in pesos],
            textposition="outside",
        ))
        fig_l.update_layout(
            title="Ladder de vencimientos RF (% de cartera)",
            height=240, margin=dict(t=36, b=20, l=10, r=10),
            yaxis_title="%", xaxis_title="Año vto.",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_l, use_container_width=True, key="ladder_vtos_rf")
    else:
        st.info("No hay posiciones de renta fija con vencimiento cargado en el catálogo.")

    # P2-RF-01: ficha unificada (antes tabla plana P2-RF-05: ISIN / denom / forma)
    _seen_rf: set[str] = set()
    _tickers_rf_inv: list[str] = []
    for _, _row_rf in df_ag.iterrows():
        if not es_fila_renta_fija_ar(_row_rf, UNIVERSO_RENTA_FIJA_AR):
            continue
        _tkf = str(_row_rf.get("TICKER", "")).upper().strip()
        if not _tkf or _tkf in _seen_rf:
            continue
        _seen_rf.add(_tkf)
        if get_meta(_tkf):
            _tickers_rf_inv.append(_tkf)
    if _tickers_rf_inv:
        st.caption(
            "Ficha RF (P2-RF-01) — alineada a monitor y cartera; referencia educativa "
            "(validar con prospecto / custodio)."
        )
        _pick_inv = st.selectbox(
            "Instrumento RF en tu cartera",
            sorted(_tickers_rf_inv),
            key="inv_ficha_rf_ticker",
        )
        _row_sel = df_ag[
            df_ag["TICKER"].astype(str).str.upper().str.strip() == _pick_inv
        ].iloc[0]
        _live_sel = _byma_enrich.get(_pick_inv, {}) or {}
        _par_b: float | None = None
        if _live_sel.get("paridad_ref") is not None:
            try:
                _par_b = float(_live_sel["paridad_ref"])
            except (TypeError, ValueError):
                _par_b = None
        if _par_b is None:
            _par_b = _paridad_implicita_pct_on_usd_desde_fila(
                _row_sel,
                float(ccl or 0) or 0.0,
            )

        _px_raw = _live_sel.get("precio_ars")
        _px_b: float | None = None
        if _px_raw is not None:
            try:
                _px_b = float(_px_raw)
            except (TypeError, ValueError):
                _px_b = None
        if _px_b is None:
            _px_num = pd.to_numeric(_row_sel.get("PRECIO_ARS"), errors="coerce")
            if not pd.isna(_px_num):
                _px_b = float(_px_num)

        _aj_b = bool(_live_sel.get("escala_div100")) or bool(
            str(_row_sel.get("ESCALA_PRECIO_RF", "") or "").strip()
        )
        _nota_b = None
        if _live_sel.get("escala_div100"):
            _nota_b = (
                "Último BYMA en escala ×100; se aplicó ÷100 al precio. "
                "Ver `docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md`."
            )
        elif str(_row_sel.get("ESCALA_PRECIO_RF", "") or "").strip():
            _nota_b = "Precio alineado con **÷100 vs PPC** (guardrail RF USD) en cartera."

        _fu_b = "BYMA live" if _live_sel else "Catálogo / último en cartera"

        _bundle_inv = ficha_rf_minima_bundle(
            _pick_inv,
            None,
            paridad_pct=_par_b,
            precio_mercado_ars=_px_b,
            fuente_precio=_fu_b,
            escala_div100_aplicada=_aj_b,
            nota_escala=_nota_b,
        )
        render_ficha_rf_minima(_bundle_inv, key_prefix=f"inv_ficha_{_pick_inv}")


# ── Panel de KPIs Renta Variable ──────────────────────────────────────────────
def _render_panel_rv_kpis(ctx: dict, df_ag: pd.DataFrame, metricas: dict, ccl: float, diag) -> None:
    """
    Panel dedicado de Renta Variable con KPIs propios:
    P&L%, CAGR, Sharpe estimado, % RV vs objetivo y top posiciones.
    """
    from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
    from core.perfil_allocation import target_rv_efectivo
    from core.renta_fija_ar import es_fila_renta_fija_ar

    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte = str(ctx.get("cliente_horizonte_label", "1 año"))
    target_rv = target_rv_efectivo(perfil, horizonte)
    pct_rv_actual = float(getattr(diag, "pct_rv_actual",
                          max(0.0, 1.0 - float(getattr(diag, "pct_defensivo_actual", 0) or 0))) or 0.0)

    st.markdown(
        "<p style='font-size:0.7rem;font-weight:600;color:var(--c-text-3);"
        "text-transform:uppercase;letter-spacing:0.08em;margin:0.75rem 0 0.4rem 0;'>"
        "Renta Variable</p>",
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)

    # P&L %
    pnl_pct = float(metricas.get("pnl_pct_total", 0) or 0) * 100
    k1.metric(
        "P&L acumulado",
        f"{pnl_pct:+.1f}%",
        help="Ganancia/pérdida sobre el capital histórico cargado en ARS.",
    )

    # Rendimiento USD
    pnl_usd_pct = float(metricas.get("pnl_pct_total_usd", 0) or 0) * 100
    k2.metric(
        "Rendimiento USD",
        f"{pnl_usd_pct:+.1f}%",
        help="Rendimiento sobre base USD × CCL.",
    )

    # % RV actual vs objetivo
    delta_rv = pct_rv_actual - target_rv
    k3.metric(
        "RV en cartera",
        f"{pct_rv_actual:.1%}",
        delta=f"{delta_rv:+.1%} vs objetivo {target_rv:.0%}",
        delta_color="normal" if abs(delta_rv) < 0.05 else "inverse",
        help=f"Objetivo RV para perfil {perfil}: {target_rv:.0%}.",
    )

    # CAGR si disponible en métricas
    cagr_ars = metricas.get("cagr_ars") or metricas.get("cagr_global_ars")
    cagr_usd = metricas.get("cagr_usd") or metricas.get("cagr_global_usd")
    if cagr_ars is not None:
        k4.metric(
            "CAGR ARS",
            f"{float(cagr_ars) * 100:+.1f}%",
            help="Tasa anualizada de crecimiento en pesos.",
        )
    elif cagr_usd is not None:
        k4.metric(
            "CAGR USD",
            f"{float(cagr_usd) * 100:+.1f}%",
            help="Tasa anualizada de crecimiento en USD.",
        )
    else:
        k4.metric("CAGR", "—", help="Sin datos de período suficiente.")

    # Top 3 posiciones RV por peso
    try:
        rv_rows = []
        for _, row in df_ag.iterrows():
            if es_fila_renta_fija_ar(row, UNIVERSO_RENTA_FIJA_AR):
                continue
            tk = str(row.get("TICKER", ""))
            peso = float(row.get("PESO_PCT", row.get("PESO", 0)) or 0)
            pnl_row = float(row.get("PNL_PCT", row.get("P_L_PCT", 0)) or 0)
            rv_rows.append({"Ticker": tk, "Peso %": round(peso * 100, 1) if peso < 1.5 else round(peso, 1), "P&L %": round(pnl_row * 100 if pnl_row < 5 else pnl_row, 1)})
        rv_rows.sort(key=lambda x: x["Peso %"], reverse=True)
        if rv_rows:
            import pandas as _pd
            top_rv = _pd.DataFrame(rv_rows[:8])
            st.caption("Top posiciones RV")
            st.dataframe(
                top_rv,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(top_rv, min_px=140, max_px=280),
            )
    except Exception:
        pass


@st.cache_data(ttl=1800)
def _benchmark_ytd_pct(symbol: str) -> float | None:
    """Retorno YTD aproximado (%) vía yfinance; None si no hay datos."""
    try:
        import yfinance as yf

        h = yf.Ticker(symbol).history(period="ytd")
        if h is None or len(h) < 2:
            return None
        c = h["Close"].dropna()
        if len(c) < 2:
            return None
        return float(c.iloc[-1] / c.iloc[0] - 1.0) * 100.0
    except Exception:
        return None


def _ideal_rf_rv_fracciones(ideal_d: dict) -> tuple[float, float]:
    """Suma pesos renta fija vs variable del dict CARTERA_IDEAL."""
    rf = rv = 0.0
    for k, v in (ideal_d or {}).items():
        try:
            w = float(v)
        except (TypeError, ValueError):
            continue
        ks = str(k).strip()
        if not ks:
            continue
        if ks.startswith("_") or es_renta_fija(ks.upper()):
            rf += max(0.0, w)
        else:
            rv += max(0.0, w)
    return rf, rv


def _inversor_sin_posiciones_cargadas(df_ag: pd.DataFrame | None) -> bool:
    """True si no hay activos reales: bienvenida + primera cartera / sugerencia."""
    if df_ag is None or df_ag.empty:
        return True
    if "TICKER" not in df_ag.columns:
        return True
    s = df_ag["TICKER"].astype(str).str.strip().str.upper()
    s = s[s.ne("") & s.ne("NAN") & s.ne("NONE")]
    return s.empty


def _render_bienvenida_inversor(ctx: dict) -> None:
    """Bienvenida sin cartera: una pregunta, dos caminos, carga o primera cartera."""
    st.session_state.setdefault("inv_carga_open", False)
    nombre = str(ctx.get("cliente_nombre", "")).split("|")[0].strip() or "inversor"
    perfil = str(ctx.get("cliente_perfil", "Moderado"))

    st.markdown(
        f"""
    <div class="mq-motion-page-fade mq-inv-hero-wrap">
        <h2 class="mq-inv-h2-hero">
            Hola, {html.escape(nombre)} 👋
        </h2>
        <p class="mq-inv-lead">
            ¿Ya tenés activos en el broker o querés armar tu primera cartera con una sugerencia?
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact" style="margin-top:0.5rem;">
        Mi primera cartera
    </h3>
    """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Todavía no hay posiciones cargadas. Podés importar lo que ya tenés en el broker, "
        "cargar a mano, o pedir una **cartera sugerida** según tu perfil de arriba "
        "(simulación; no es promesa de resultado)."
    )

    col_si, col_no = st.columns(2, gap="large")

    with col_si:
        st.markdown(
            """
        <div class="mq-inv-card mq-inv-card--accent">
            <div class="mq-inv-card-emoji">📂</div>
            <div class="mq-inv-card-title">
                Ya tengo activos
            </div>
            <div class="mq-inv-card-body">
                Importá tu resumen del broker (Balanz, IOL, BMB)
                o cargá tus posiciones una por una.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mq-inv-spacer-sm"></div>', unsafe_allow_html=True)
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
        <div class="mq-inv-card mq-inv-card--green">
            <div class="mq-inv-card-emoji">🚀</div>
            <div class="mq-inv-card-title">
                Cartera sugerida (desde cero)
            </div>
            <div class="mq-inv-card-body">
                El motor propone una primera cartera para tu perfil
                <strong class="mq-inv-strong-green">{html.escape(perfil)}</strong>
                con el monto en pesos que indiques. La operación real la hacés en tu broker.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mq-inv-spacer-sm"></div>', unsafe_allow_html=True)
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


def _render_wizard_objetivos(ctx: dict) -> None:
    """
    Paso 0 del wizard de primera cartera: ¿Qué querés lograr?

    Presenta 9 objetivos CP/MP/LP en 3 columnas. El inversor elige
    los que aplican y continúa. Los seleccionados se guardan en
    session_state["pci_objetivos"] para que el motor los use.
    """
    from services.portfolio_optimizer import CATALOGO_OBJETIVOS

    st.markdown(
        """
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact">
        ¿Qué querés lograr con esta inversión?
    </h3>
    <p class="mq-inv-muted-p" style="margin-bottom:1rem;">
        Elegí uno o más objetivos. La cartera se va a armar en función de lo que necesitás.
        Podés seleccionar objetivos de distintos horizontes — el motor distribuye el capital entre ellos.
    </p>
    """,
        unsafe_allow_html=True,
    )

    # Definición visual de cada objetivo (ícono, color de borde, descripción corta)
    _OBJ_UI: dict[str, dict] = {
        "CP1": {"icono": "🛡️", "color": "#2ECC71",
                "titulo": "Fondo de emergencia",
                "corto": "3–6 meses de gastos, liquidez inmediata."},
        "CP2": {"icono": "⚡", "color": "#27AE60",
                "titulo": "Capital de trabajo",
                "corto": "Plata operativa a 30–90 días."},
        "CP3": {"icono": "🎯", "color": "#F39C12",
                "titulo": "Reserva de oportunidad",
                "corto": "Dry powder para aprovechar bajas de mercado."},
        "MP1": {"icono": "💵", "color": "#3498DB",
                "titulo": "Renta en dólares",
                "corto": "Flujo semestral en USD vía ONs 7–9% TIR."},
        "MP2": {"icono": "📊", "color": "#9B59B6",
                "titulo": "Cobertura inflación",
                "corto": "BONCER/LECAP — preservar poder adquisitivo ARS."},
        "MP3": {"icono": "🌐", "color": "#1ABC9C",
                "titulo": "Diversificación internacional",
                "corto": "S&P 500 / Nasdaq vía CEDEARs."},
        "LP1": {"icono": "🏦", "color": "#E67E22",
                "titulo": "Acumulación patrimonial",
                "corto": "ONs largas 2030+, TIR ≥ 7%, capital en USD."},
        "LP2": {"icono": "🌅", "color": "#E74C3C",
                "titulo": "Jubilación / FIRE",
                "corto": "Construir independencia financiera a 10–20 años."},
        "LP3": {"icono": "🚀", "color": "#2980B9",
                "titulo": "Crecimiento USD",
                "corto": "Acciones growth/value, retorno esperado 12–15%/año."},
    }

    # Agrupar por horizonte
    grupos = {
        "⚡ Corto Plazo  ≤ 12 meses": ["CP1", "CP2", "CP3"],
        "📈 Mediano Plazo  1–3 años":  ["MP1", "MP2", "MP3"],
        "🏦 Largo Plazo  3–15 años":   ["LP1", "LP2", "LP3"],
    }

    # Recuperar selección previa (si el usuario vuelve)
    seleccionados: set[str] = set(st.session_state.get("pci_objetivos") or [])

    for grupo_label, codigos in grupos.items():
        st.markdown(
            f"<p style='font-size:0.72rem;font-weight:700;color:var(--c-text-3);"
            f"text-transform:uppercase;letter-spacing:0.08em;margin:0.8rem 0 0.3rem 0;'>"
            f"{grupo_label}</p>",
            unsafe_allow_html=True,
        )
        cols = st.columns(3, gap="small")
        for col, cod in zip(cols, codigos, strict=False):
            ui = _OBJ_UI[cod]
            cfg = CATALOGO_OBJETIVOS[cod]
            activo = cod in seleccionados
            borde = f"2px solid {ui['color']}" if activo else "1px solid #3a3a3a"
            bg = f"{ui['color']}1A" if activo else "transparent"
            with col:
                # Tarjeta visual
                st.markdown(
                    f"""<div style="border:{borde};border-radius:8px;padding:0.65rem 0.75rem;
                    background:{bg};margin-bottom:0.2rem;min-height:90px;">
                    <span style="font-size:1.3rem;">{ui['icono']}</span>
                    <span style="font-weight:600;font-size:0.82rem;"> {ui['titulo']}</span><br>
                    <span style="font-size:0.72rem;color:var(--c-text-3);">{ui['corto']}</span><br>
                    <span style="font-size:0.68rem;color:{ui['color']};">
                        ~{cfg.retorno_esperado_usd_anual:.0f}% USD/año · {cfg.liquidez} liquidez
                    </span></div>""",
                    unsafe_allow_html=True,
                )
                checked = st.checkbox(
                    "Seleccionar" if not activo else "✔ Elegido",
                    value=activo,
                    key=f"pci_obj_{cod}",
                    label_visibility="collapsed",
                )
                if checked:
                    seleccionados.add(cod)
                else:
                    seleccionados.discard(cod)

    st.session_state["pci_objetivos"] = list(seleccionados)

    st.divider()

    if not seleccionados:
        st.info("👆 Elegí al menos un objetivo para continuar.")
        return

    # Resumen de lo seleccionado
    obj_labels = " · ".join(
        f"{_OBJ_UI[c]['icono']} **{_OBJ_UI[c]['titulo']}**"
        for c in sorted(seleccionados)
        if c in _OBJ_UI
    )
    st.success(f"Objetivos elegidos: {obj_labels}")

    if st.button(
        "Continuar — ingresar capital →",
        type="primary",
        use_container_width=True,
        key="btn_pci_objetivos_ok",
    ):
        st.session_state["pci_wizard_paso"] = 1
        st.rerun()


def _render_primera_cartera_inversor(ctx: dict) -> None:
    """Primera cartera: wizard objetivos → capital → cálculo."""
    # ── Paso 0: objetivos (wizard) ────────────────────────────────────────────
    wizard_paso = st.session_state.get("pci_wizard_paso", 0)
    objetivos_elegidos: list[str] = st.session_state.get("pci_objetivos") or []

    if wizard_paso == 0:
        _render_wizard_objetivos(ctx)
        return

    # ── Pasó el wizard — mostrar resumen de objetivos + link para volver ──────
    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte = _horizonte_ui(ctx)
    ccl = float(ctx.get("ccl") or 1150.0)
    perfil_v = perfil_diagnostico_valido(perfil)

    # Encabezado con breadcrumb de objetivos
    from services.portfolio_optimizer import CATALOGO_OBJETIVOS as _CAT_OBJ
    obj_resumen = ", ".join(
        f"{cod} {_CAT_OBJ[cod].nombre}" for cod in objetivos_elegidos if cod in _CAT_OBJ
    ) or "sin objetivos"

    st.markdown(
        f"""
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact">
        Cartera sugerida — armá tu primera cartera
    </h3>
    <p class="mq-inv-muted-p" style="margin-bottom:0.5rem;">
        <strong>Objetivos:</strong> {obj_resumen}
    </p>
    <p class="mq-inv-muted-p" style="margin-bottom:0.75rem;">
        La cartera se construye en función de esos objetivos, tu perfil
        <strong>{html.escape(perfil)}</strong> y el monto disponible.
    </p>
    <p class="mq-inv-step-label">
        Paso 2 de 3 — Tu capital disponible
    </p>
    """,
        unsafe_allow_html=True,
    )

    if st.button("← Cambiar objetivos", key="btn_pci_volver_obj"):
        st.session_state["pci_wizard_paso"] = 0
        st.session_state.pop("pci_resultado", None)
        st.rerun()

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
            help="El motor distribuye este monto según tus objetivos y perfil.",
        )
        flujo_mensual_ars = st.number_input(
            "Aporte mensual recurrente (ARS, opcional)",
            min_value=0.0,
            max_value=10_000_000.0,
            value=0.0,
            step=10_000.0,
            format="%.0f",
            key="pci_flujo_mensual_ars",
            help="¿Pensás sumar plata todos los meses? Mejora la proyección a futuro.",
        )
    with col_info:
        capital_usd = capital_ars / max(ccl, 1.0)
        flujo_usd = flujo_mensual_ars / max(ccl, 1.0)
        st.markdown(
            f"""
        <div class="mq-inv-kpi-box">
            <div class="mq-inv-kpi-label">Tu inversión</div>
            <div class="mq-inv-kpi-value">$ {capital_ars:,.0f} ARS</div>
            <div class="mq-inv-kpi-hint">
                ~ USD {capital_usd:,.0f} (CCL {ccl:,.0f})</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if flujo_mensual_ars > 0:
            st.markdown(
                f"""
            <div class="mq-inv-kpi-box" style="margin-top:0.5rem;">
                <div class="mq-inv-kpi-label">Aporte mensual</div>
                <div class="mq-inv-kpi-value">$ {flujo_mensual_ars:,.0f} ARS</div>
                <div class="mq-inv-kpi-hint">~ USD {flujo_usd:,.0f}/mes</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--tight">
        Paso 3 de 3 — La app calcula por vos
    </p>
    <p class="mq-inv-muted-p">
        Perfil, objetivos, mercado y señales técnicas. Solo presioná el botón.
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
                from services.recomendacion_capital import generar_primera_cartera

                # Guardar flujo mensual en session_state para mostrarlo en resultados
                st.session_state["pci_flujo_mensual_ars_calc"] = float(flujo_mensual_ars)

                # df_scores (scanner 60/20/20) mejora selección de CEDEARs;
                # si no está disponible, el motor usa scoring estático por sector.
                _df_scores_pci = st.session_state.get("df_scores")
                if not isinstance(_df_scores_pci, pd.DataFrame) or _df_scores_pci.empty:
                    _df_scores_pci = None

                rr = generar_primera_cartera(
                    capital_ars=float(capital_ars),
                    perfil=perfil_v,
                    ccl=ccl,
                    precios_dict=_precios_para_recomendar(ctx),
                    universo_df=ctx.get("universo_df"),
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                    df_analisis=ctx.get("df_analisis"),
                    df_scores=_df_scores_pci,
                )
                from services.recomendacion_capital import _expandir_ideal
                st.session_state["pci_resultado"] = {
                    "capital": float(capital_ars),
                    "rr": rr,
                    "perfil": perfil_v,
                    "ideal": _expandir_ideal(
                        CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"]),
                        perfil_v,
                        df_scores=_df_scores_pci,
                    ),
                }

                # ── Plan multi-objetivo (sidebar del resultado) ───────────────
                # Si el usuario eligió objetivos, calculamos el plan CP/MP/LP en
                # paralelo y lo guardamos para mostrarlo como contexto de la cartera.
                if objetivos_elegidos:
                    try:
                        from services.portfolio_optimizer import calcular_plan_multifuncional
                        _flujo_usd = float(flujo_mensual_ars) / max(ccl, 1.0)
                        _capital_usd = float(capital_ars) / max(ccl, 1.0)
                        plan = calcular_plan_multifuncional(
                            objetivos_elegidos,
                            capital_inicial_usd=_capital_usd,
                            flujo_mensual_usd=_flujo_usd,
                            ccl=ccl,
                        )
                        st.session_state["pci_plan_objetivos"] = plan
                    except Exception as _ep:
                        _log_degradacion(ctx, "pci_plan_objetivos_error", _ep)
                        st.session_state.pop("pci_plan_objetivos", None)

                try:
                    from services.audit_trail import registrar_recomendacion_evento

                    registrar_recomendacion_evento(
                        evento="SIMULACION_RECOMENDACION",
                        origen="primera_cartera",
                        cliente_id=ctx.get("cliente_id"),
                        cliente_nombre=str(ctx.get("cliente_nombre", "")),
                        tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                        actor=str(ctx.get("login_user", "") or ""),
                        correlation_id=str(st.session_state.get("session_correlation_id", "")),
                        cartera=str(_cartera_resuelta_primera_cartera(ctx)),
                        perfil=perfil_v,
                        capital_ars=float(capital_ars),
                        filas=len(list(getattr(rr, "compras_recomendadas", None) or [])),
                        payload={
                            "alerta_mercado": bool(getattr(rr, "alerta_mercado", False)),
                            "capital_remanente_ars": float(getattr(rr, "capital_remanente_ars", 0) or 0),
                            "objetivos": objetivos_elegidos,
                            "flujo_mensual_ars": float(flujo_mensual_ars),
                        },
                    )
                except Exception as exc:
                    _log_degradacion(ctx, "audit_evento_simulacion_fallo", exc)
                # Pilar 3: plan explicado de la primera cartera al audit trail
                try:
                    from services.recomendador_explicable import (
                        auditar_plan,
                        construir_plan_accion,
                    )

                    _plan_pci = construir_plan_accion(
                        perfil=perfil_v,
                        rr=rr,
                        capital_ars=float(capital_ars),
                        precio_records=ctx.get("precio_records"),
                    )
                    st.session_state["pci_plan_explicado"] = _plan_pci
                    auditar_plan(
                        _plan_pci,
                        ctx={
                            "cliente_id": ctx.get("cliente_id"),
                            "cliente_nombre": str(ctx.get("cliente_nombre", "")),
                            "tenant_id": str(ctx.get("tenant_id", "default") or "default"),
                            "login_user": str(ctx.get("login_user", "") or ""),
                            "correlation_id": str(st.session_state.get("session_correlation_id", "")),
                            "cartera_activa": str(_cartera_resuelta_primera_cartera(ctx)),
                        },
                    )
                except Exception:
                    st.session_state.pop("pci_plan_explicado", None)
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

    # Pilar 3: cada sugerencia con su porqué, confianza de datos y link a ficha
    _plan_pci_exp = st.session_state.get("pci_plan_explicado")
    if _plan_pci_exp is not None and _flag_plan_explicado(ctx):
        with st.expander("🧭 Por qué esta cartera — plan explicado", expanded=False):
            from ui.components.plan_accion_view import render_plan_accion

            render_plan_accion(_plan_pci_exp, key_prefix="pci_plan")

    # ── Panel de objetivos — plan multi-objetivo (si está disponible) ──────────
    plan_obj = st.session_state.get("pci_plan_objetivos")
    if plan_obj is not None and objetivos_elegidos:
        try:
            import plotly.express as px
            import plotly.graph_objects as go

            from services.portfolio_optimizer import (
                proyeccion_consolidada_df as _proy_df,
            )

            _colores_obj = {
                "CP1": "#2ECC71", "CP2": "#27AE60", "CP3": "#F39C12",
                "MP1": "#3498DB", "MP2": "#9B59B6", "MP3": "#1ABC9C",
                "LP1": "#E67E22", "LP2": "#E74C3C", "LP3": "#2980B9",
            }

            with st.expander("📊 Plan por objetivos — proyección y distribución", expanded=True):
                st.markdown(
                    f"Capital **USD {plan_obj.capital_total_usd:,.0f}** distribuido entre "
                    f"**{len(plan_obj.tramos)} objetivo(s)**: "
                    + " · ".join(
                        f"`{t.objetivo}` {t.nombre} ({t.horizonte_meses}m)"
                        for t in plan_obj.tramos
                    )
                )

                col_pie, col_proy = st.columns([1, 2], gap="medium")

                with col_pie:
                    from services.portfolio_optimizer import asignacion_pie_df as _pie_df
                    df_pie = _pie_df(plan_obj)
                    if not df_pie.empty:
                        df_pie["label"] = df_pie["objetivo"] + "<br>" + df_pie["nombre"].str[:18]
                        fig_pie = px.pie(
                            df_pie,
                            names="label",
                            values="capital_usd",
                            color="objetivo",
                            color_discrete_map=_colores_obj,
                            hole=0.42,
                            title="Capital por objetivo",
                        )
                        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        fig_pie.update_layout(
                            height=260, margin=dict(l=5, r=5, t=35, b=5), showlegend=False
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)

                with col_proy:
                    df_proy = _proy_df(plan_obj)
                    if not df_proy.empty:
                        fig_l = go.Figure()
                        for t in plan_obj.tramos:
                            sub = df_proy[df_proy["objetivo"] == t.objetivo]
                            color = _colores_obj.get(t.objetivo, "#888")
                            fig_l.add_trace(go.Scatter(
                                x=sub["fecha"], y=sub["valor_usd"],
                                mode="lines",
                                name=f"{t.objetivo} — {t.nombre}",
                                line=dict(color=color, width=2),
                                hovertemplate=f"<b>{t.objetivo}</b><br>USD %{{y:,.0f}}<extra></extra>",
                            ))
                        fig_l.update_layout(
                            title="Proyección FV USD por objetivo",
                            xaxis_title="Fecha", yaxis_title="USD",
                            height=260,
                            margin=dict(l=10, r=10, t=35, b=10),
                            legend=dict(orientation="h", y=-0.25),
                            hovermode="x unified",
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                        )
                        fig_l.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
                        fig_l.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
                        st.plotly_chart(fig_l, use_container_width=True)

                # KPIs de valor final por tramo
                _tcols = st.columns(min(len(plan_obj.tramos), 4))
                for _i, _t in enumerate(plan_obj.tramos):
                    _ret = _t.valor_final_usd - _t.capital_inicial_usd
                    _pct = (_ret / _t.capital_inicial_usd * 100) if _t.capital_inicial_usd > 0 else 0
                    _tcols[_i % len(_tcols)].metric(
                        f"{_t.objetivo} ({_t.horizonte_meses}m)",
                        f"USD {_t.valor_final_usd:,.0f}",
                        f"+USD {_ret:,.0f} ({_pct:.1f}%)" if _ret >= 0 else f"USD {_ret:,.0f}",
                    )

                if plan_obj.advertencias_globales:
                    for _adv in plan_obj.advertencias_globales:
                        st.warning(_adv)
        except Exception as _ep:
            _log_degradacion(ctx, "pci_plan_objetivos_render", _ep)

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--step3">Paso 3 — Tu cartera sugerida (editable)</p>
    <p class="mq-inv-muted-p">
        Ajustá cantidades, precio por cuotaparte (ARS) o el instrumento. Podés agregar o quitar filas.
        Cuando esté bien, confirmá para guardarla como punto de partida y seguir en la app.
    </p>
    """,
        unsafe_allow_html=True,
    )

    monto_total = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)
    _udf_pc = ctx.get("universo_df")
    _rows_ed: list[dict] = []
    for it in items:
        _tk = str(getattr(it, "ticker", "") or "").strip().upper()
        if not _tk:
            continue
        _rows_ed.append(
            {
                "Ticker": _tk,
                "Unidades": int(getattr(it, "unidades", 0) or 0),
                "Precio_ARS": float(getattr(it, "precio_ars_estimado", 0) or 0),
                "TIPO": _tipo_universo_ticker(_tk, _udf_pc),
                "Notas": str(getattr(it, "justificacion", "") or "")[:120],
            }
        )
    df_ed_base = pd.DataFrame(_rows_ed)
    edited = st.data_editor(
        df_ed_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="pci_data_editor_cartera",
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", help="Código BYMA", width="small"),
            "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1, width="small"),
            "Precio_ARS": st.column_config.NumberColumn(
                "Precio ARS c/u",
                min_value=0.0,
                format="%.2f",
                help="Pesos por cuotaparte en BYMA.",
            ),
            "TIPO": st.column_config.SelectboxColumn(
                "Tipo",
                options=_TIPOS_EDICION_PRIMERA_CARTERA,
                width="small",
            ),
            "Notas": st.column_config.TextColumn("Notas (solo guía)", width="large"),
        },
    )

    ideal_dict = res.get("ideal") or {}
    try:
        _nu = pd.to_numeric(edited["Unidades"], errors="coerce").fillna(0)
        _npx = pd.to_numeric(edited["Precio_ARS"], errors="coerce").fillna(0)
        monto_editado = float((_nu * _npx).sum())
    except Exception as exc:
        _log_degradacion(ctx, "monto_editado_calculo_fallo", exc)
        monto_editado = monto_total

    st.markdown(
        f"""
    <div class="mq-inv-totals-bar">
        <div><div class="mq-inv-totals-kpi-label">Total tabla (estim.)</div>
        <div class="mq-inv-totals-kpi-num">
            ${monto_editado:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Motor (referencia)</div>
        <div class="mq-inv-totals-kpi-num mq-inv-totals-kpi-num--muted">
            ${monto_total:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Queda en efectivo (ref.)</div>
        <div class="mq-inv-totals-kpi-num--plain">${remanente:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Perfil</div>
        <div class="mq-inv-perfil-name">{html.escape(perfil_res)}</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if ideal_dict:
        fig_t = fig_torta_ideal(perfil_res, ideal_dict)
        if fig_t:
            with st.expander("Ver distribución objetivo de la cartera", expanded=False):
                st.plotly_chart(fig_t, use_container_width=True)

    _cart_guardar = _cartera_resuelta_primera_cartera(ctx)
    st.caption(f"Al confirmar, las compras se guardan en: **`{_cart_guardar}`**")

    st.info(
        "💡 Es una sugerencia según tu perfil y el mercado. "
        "La confirmación registra **COMPRAS** en tu libro (como si ya hubieras operado), para poder ver métricas y el resto de la app."
    )
    _confirm_exec_real = st.checkbox(
        "Confirmo que ya ejecuté estas operaciones en mi broker",
        key="pci_confirm_exec_real",
    )

    col_ok, col_act, col_reset = st.columns(3)
    with col_ok:
        if st.button(
            "✅ Confirmar como mi cartera",
            type="primary",
            use_container_width=True,
            key="pci_confirmar_cartera",
            disabled=not _confirm_exec_real,
        ):
            from ui.carga_activos import _persist_filas

            _ccl_ok = float(ctx.get("ccl") or 0.0)
            if _ccl_ok <= 0:
                st.error("CCL inválido: no se puede derivar PPC USD.")
            elif edited.empty:
                st.warning("La tabla está vacía.")
            else:
                _filas: list[dict] = []
                for _, row in edited.iterrows():
                    _tick = str(row.get("Ticker", "")).strip().upper()
                    _u = int(pd.to_numeric(row.get("Unidades", 0), errors="coerce") or 0)
                    _px = float(pd.to_numeric(row.get("Precio_ARS", 0), errors="coerce") or 0.0)
                    _ti = str(row.get("TIPO", "CEDEAR") or "CEDEAR").strip().upper()
                    if _ti in ("NAN", "NONE", ""):
                        _ti = "CEDEAR"
                    if _ti in ("COMPRA", "VENTA"):
                        _ti = "CEDEAR"
                    if not _tick or _u <= 0 or _px <= 0:
                        continue
                    _ppc_ars = round(_px, 4)
                    _ppc_usd = round(_ppc_ars / max(_ccl_ok, 1e-9), 6)
                    _filas.append(
                        {
                            "FECHA_COMPRA": date.today(),
                            "TICKER": _tick,
                            "CANTIDAD": _u,
                            "PPC_USD": _ppc_usd,
                            "PPC_ARS": _ppc_ars,
                            "TIPO": _ti,
                            "LAMINA_VN": float("nan"),
                        }
                    )
                if not _filas:
                    st.error(
                        "No hay filas válidas: cada una necesita **Ticker**, **Unidades** > 0 y **Precio ARS** > 0."
                    )
                else:
                    _mix_rf = _mix_rf_desde_filas_primera(_filas)
                    st.session_state["inv_mix_plan"] = {
                        "rf": round(_mix_rf, 5),
                        "ts": time.time(),
                    }
                    st.session_state.pop("inv_diagnostico", None)
                    try:
                        from services.audit_trail import registrar_recomendacion_evento

                        registrar_recomendacion_evento(
                            evento="EJECUCION_CONFIRMADA",
                            origen="primera_cartera",
                            cliente_id=ctx.get("cliente_id"),
                            cliente_nombre=str(ctx.get("cliente_nombre", "")),
                            tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                            actor=str(ctx.get("login_user", "") or ""),
                            correlation_id=str(st.session_state.get("session_correlation_id", "")),
                            cartera=str(_cart_guardar),
                            perfil=perfil_res,
                            capital_ars=float(cap_ui),
                            filas=len(_filas),
                            payload={"confirmacion_broker": True},
                        )
                    except Exception:
                        pass
                    _persist_filas(
                        ctx,
                        _filas,
                        "agregar",
                        cartera_override=_cart_guardar,
                        session_keys_clear=["pci_resultado", "inv_mostrar_sugerencia"],
                    )

    with col_act:
        if st.button("✏️ Cargar lo que compré", use_container_width=True, key="pci_ir_a_carga"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "manual"
            st.session_state.pop("pci_resultado", None)
            st.rerun()
    with col_reset:
        if st.button("🔄 Recalcular con otro monto", use_container_width=True, key="pci_reset"):
            st.session_state.pop("pci_resultado", None)
            st.session_state.pop("inv_mix_plan", None)
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
                tenant_id=str(ctx.get("tenant_id") or "default"),
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

    df_ag = ctx.get("df_ag")
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    precios = ctx.get("precios_dict") or {}
    df_anal = ctx.get("df_analisis")
    uinv = ctx.get("universo_df")

    if df_ag is None or df_ag.empty:
        return

    st.markdown(
        "### Mis posiciones",
    )
    st.caption(
        "Cuánto tenés de cada activo, cuánto ganás, y cuándo conviene vender.",
    )

    hoy = date.today()
    filas: list[dict] = []

    for _, pos in df_ag.iterrows():
        ticker = _ticker_desde_fila_pos(pos)
        if not ticker:
            continue

        ppc_ars = float(pd.to_numeric(pos.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
        px_ars = float(pd.to_numeric(pos.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
        if px_ars <= 0:
            px_ars = float(precios.get(ticker, precios.get(ticker.upper(), 0)) or 0)

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

        if ppc_ars <= 0:
            continue

        _sin_cotiz = False
        _px_motor = px_ars
        if _px_motor <= 0:
            _sin_cotiz = True
            _px_motor = max(ppc_ars, 1e-6)

        try:
            ms = evaluar_salida(
                ticker=ticker,
                ppc_usd=ppc_ars,
                px_usd_actual=_px_motor,
                rsi=rsi_val,
                score_actual=score_v,
                score_semana_anterior=score_v,
                fecha_compra=fecha_d,
                perfil=perfil_ms,
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

        nombre_u = _nombre_universo_para_ticker(ticker, uinv)

        filas.append({
            "_ticker": ticker,
            "_nombre": nombre_u,
            "_sin_cotiz": _sin_cotiz,
            "_dias": dias,
            "_pnl_frac": pnl_frac,
            "_cagr": cagr,
            "_valor_ars": valor_ars,
            "_progreso": float(ms.get("progreso_pct", 0) or 0),
            "_target_pct": float(ms.get("target_pct", 25)),
            "_stop_pct": float(ms.get("stop_pct", -15)),
            "_senal": str(ms.get("senal", "—")),
        })

    if not filas:
        return

    filas.sort(key=lambda r: (_senal_orden_rank(r["_senal"]), -r["_progreso"]))

    for f in filas:
        ticker = f["_ticker"]
        nombre_u = str(f.get("_nombre") or "").strip()
        sin_cotiz = bool(f.get("_sin_cotiz"))
        dias = f["_dias"]
        pnl_frac = f["_pnl_frac"]
        cagr = f["_cagr"]
        valor_ars = f["_valor_ars"]
        progreso = f["_progreso"]
        target_pct = f["_target_pct"]
        stop_pct = f["_stop_pct"]
        senal = f["_senal"]

        pnl_color = "var(--c-green)" if pnl_frac >= 0 else "var(--c-red)"
        pnl_sign = "+" if pnl_frac >= 0 else ""
        dias_txt = f"{dias}d" if dias > 0 else "—"
        cagr_txt = f"{cagr:+.1f}%/año" if abs(cagr) > 0.1 else "—"
        prog_color = "var(--c-green)" if progreso >= 80 else (
            "var(--c-accent)" if progreso >= 40 else "var(--c-yellow)"
        )
        prog_width = min(100.0, max(0.0, progreso))
        if pnl_frac * 100.0 < stop_pct:
            prog_color = "var(--c-red)"
            prog_width = 100.0

        _sub = ""
        if nombre_u:
            _sub = (
                f"<span style=\"font-size:0.72rem;color:var(--c-text-2);display:block;"
                f"font-weight:500;margin-top:2px;\">{html.escape(nombre_u)}</span>"
            )
        _cot = ""
        if sin_cotiz:
            _cot = (
                "<span style=\"font-size:0.62rem;color:var(--c-yellow);display:block;margin-top:3px;\">"
                "Sin cotización live: señal aproximada usando PPC.</span>"
            )

        with st.container():
            col_main, col_meta, col_senal = st.columns([4, 3, 2])
            with col_main:
                st.markdown(
                    f"""
                <div style="margin-bottom:0.1rem;">
                    <strong style="font-size:0.95rem;color:var(--c-text);font-family:var(--font-mono),monospace;"
                            >{html.escape(ticker)}</strong>
                    <span style="font-size:0.75rem;color:{pnl_color};font-family:var(--font-mono),monospace;
                                 margin-left:0.5rem;font-weight:600;">{pnl_sign}{pnl_frac:.1%}</span>
                    {_sub}
                    {_cot}
                </div>
                <div style="margin-bottom:0.4rem;">
                    <div style="background:var(--c-surface-3);border-radius:4px;height:5px;overflow:hidden;">
                        <div style="width:{prog_width:.0f}%;height:100%;background:{prog_color};border-radius:4px;"></div>
                    </div>
                </div>
                <div style="font-size:0.65rem;color:var(--c-text-3);">
                    Progreso al objetivo: {progreso:.0f}% (target +{target_pct:.0f}% / stop {stop_pct:.0f}%)
                </div>
                """,
                    unsafe_allow_html=True,
                )
            with col_meta:
                _cagr_css = "var(--c-green)" if cagr > 0 else "var(--c-red)"
                st.markdown(
                    f"""
                <div style="font-size:0.72rem;color:var(--c-text-2);line-height:1.8;">
                    <span style="color:var(--c-text-3);font-size:0.65rem;">EN CARTERA </span>
                    <strong style="font-family:var(--font-mono),monospace;color:var(--c-text);">{dias_txt}</strong><br>
                    <span style="color:var(--c-text-3);font-size:0.65rem;">TASA ANUAL </span>
                    <strong style="font-family:var(--font-mono),monospace;color:{_cagr_css};">
                        {cagr_txt}</strong><br>
                    <span style="color:var(--c-text-3);font-size:0.65rem;">VALOR </span>
                    <strong style="font-family:var(--font-mono),monospace;color:var(--c-text);">${valor_ars:,.0f}</strong>
                </div>
                """,
                    unsafe_allow_html=True,
                )
            with col_senal:
                senal_word = senal.split()[-1].upper() if senal else "—"
                senal_colors = {
                    "SALIR": ("var(--c-red)", "var(--c-red-muted)"),
                    "REVISAR": ("var(--c-yellow)", "var(--c-yellow-muted)"),
                    "ATENCIÓN": ("var(--c-yellow)", "var(--c-yellow-muted)"),
                    "CAMINO": ("var(--c-text-3)", "var(--c-surface-3)"),
                    "OBJETIVO": ("var(--c-yellow)", "var(--c-yellow-muted)"),
                }
                sc, sb = senal_colors.get(
                    senal_word, ("var(--c-text-3)", "var(--c-surface-3)")
                )
                st.markdown(
                    f"""
                <div style="text-align:right;padding-top:0.25rem;">
                    <span style="font-size:0.68rem;font-weight:700;color:{sc};background:{sb};
                                 padding:3px 10px;border-radius:999px;border:1px solid var(--c-border);">
                        {html.escape(senal_word)}
                    </span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

        st.markdown(
            "<hr style='border:none;border-top:1px solid var(--c-border);"
            "margin:0.4rem 0 0.6rem 0;'>",
            unsafe_allow_html=True,
        )


def _flag_plan_explicado(ctx: dict) -> bool:
    """Feature flag A08: plan explicado activable por tenant sin deploy."""
    try:
        from core.feature_flags import get_flag

        return get_flag("plan_explicado", ctx.get("tenant_id"))
    except Exception:
        return True


def _render_ficha_posicion(ctx: dict, df_ag) -> None:
    """Ficha integral de un activo de la cartera (Pilar 2) — lazy, solo RV."""
    from core.instrument_master import get_master

    master = get_master(ctx.get("universo_df"))
    tickers_rv = sorted(
        {
            t
            for t in df_ag["TICKER"].astype(str).str.strip().str.upper()
            if t and (master.get(t) is None or not master.get(t).es_renta_fija)
        }
    )
    if not tickers_rv:
        return
    with st.expander("📑 Ficha integral de un activo de tu cartera", expanded=False):
        sel = st.selectbox(
            "Elegí el activo",
            tickers_rv,
            index=None,
            placeholder="Seleccioná un ticker…",
            key="inv_ficha_pos_sel",
        )
        if sel:
            from ui.components.ficha_ticker_view import render_ficha_ticker

            render_ficha_ticker(sel, key_prefix="inv_pos")


def _render_tabla_posiciones_resumen(ctx: dict) -> None:
    """
    Tabla tipo homebroker (Balanz / Bull Market): columnas claras, totales,
    resultado resaltado y sin scroll interno forzado.
    """
    df = ctx.get("df_ag")
    if df is None or df.empty:
        st.info("No hay posiciones cargadas.")
        return
    _html = build_posiciones_broker_html(
        df,
        ctx.get("metricas"),
        hint_text=f"Valores en pesos (ARS) — último precio cargado en MQ26 · CCL {float(ctx.get('ccl') or 0):,.0f}. Pasá el mouse sobre cada cifra para ver el equivalente en USD.",
        ccl=ctx.get("ccl"),
        precio_records=ctx.get("precio_records"),
    )
    if _html:
        st.markdown(_html, unsafe_allow_html=True)
        st.caption(
            "**Resultado / % resultado:** sobre costo en pesos histórico. "
            "**% rend. USD:** igual que la tarjeta «Rendimiento USD» arriba. "
            "**1ª compra, días y tasa anual posición** solo aparecen si el CSV de operaciones trae "
            "**FECHA_COMPRA** (o primera compra agregada); sin eso MQ26 no puede estimar días en cartera. "
            "La tasa anual **no** es la proyección de jubilación (está en Plan). "
            "La columna **Resultado** está resaltada como en tu broker."
        )
        _render_ficha_posicion(ctx, df)
        return
    cols_map = [
        ("TICKER", "Activo"),
        ("CANTIDAD_TOTAL", "Cantidad"),
        ("PRECIO_ARS", "Precio ARS"),
        ("VALOR_ARS", "Valor ARS"),
        ("INV_ARS", "Costo ARS"),
        ("PNL_PCT", "P&L % cartera"),
        ("PNL_PCT_USD", "P&L % rend. USD"),
        ("PESO_PCT", "Peso %"),
    ]
    pick = [c for c, _ in cols_map if c in df.columns]
    if not pick:
        return
    disp = df[pick].copy()
    if "PESO_PCT" in disp.columns:
        disp["PESO_PCT"] = (pd.to_numeric(disp["PESO_PCT"], errors="coerce").fillna(0) * 100).round(1)
    for c in ("PNL_PCT", "PNL_PCT_USD"):
        if c in disp.columns:
            disp[c] = (pd.to_numeric(disp[c], errors="coerce").fillna(0) * 100).round(1)
    rename = {c: lab for c, lab in cols_map if c in disp.columns}
    disp = disp.rename(columns=rename)
    st.dataframe(
        disp,
        use_container_width=True,
        hide_index=True,
        height=dataframe_auto_height(disp, min_px=140, max_px=360),
    )


def _df_salud_referencias_posicion(ctx: dict, df_ag: pd.DataFrame) -> pd.DataFrame:
    """Target ARS (motor de salida) para RV; TIR ref. y vencimiento para renta fija."""
    from services.motor_salida import evaluar_salida

    if df_ag is None or df_ag.empty:
        return pd.DataFrame()
    perfil_ms = perfil_motor_salida(str(ctx.get("cliente_perfil", "Moderado")))
    hoy = date.today()
    df_anal = ctx.get("df_analisis")
    precios = ctx.get("precios_dict") or {}
    udf = ctx.get("universo_df")
    rows: list[dict] = []
    for _, pos in df_ag.iterrows():
        row_s = pd.Series(pos)
        ticker = _ticker_desde_fila_pos(row_s)
        if not ticker:
            continue
        _nm = _nombre_universo_para_ticker(ticker, udf)
        _act_lbl = f"{ticker} — {_nm}" if _nm else ticker
        px_ars = float(pd.to_numeric(pos.get("PRECIO_ARS", 0), errors="coerce") or 0.0)
        if px_ars <= 0:
            px_ars = float(precios.get(ticker, 0) or 0)
        if es_fila_renta_fija_ar(row_s, UNIVERSO_RENTA_FIJA_AR):
            meta = get_meta(ticker) or _rf_meta_unificado(ticker, UNIVERSO_RENTA_FIJA_AR) or {}
            tir = meta.get("tir_ref")
            vto = str(meta.get("vencimiento", "") or "").strip()
            tir_txt = f"{float(tir):.1f} %" if tir is not None else "—"
            rows.append({
                "Activo": _act_lbl,
                "Clase": "Renta fija",
                "Precio ARS": round(px_ars, 2) if px_ars else None,
                "Referencia": f"TIR ref. {tir_txt}",
                "Detalle": f"Venc. {vto}" if vto else "—",
            })
            continue
        ppc_ars = float(pd.to_numeric(pos.get("PPC_ARS", 0), errors="coerce") or 0.0)
        fecha_c = pos.get("FECHA_COMPRA") or pos.get("FECHA_PRIMERA_COMPRA")
        fecha_d = hoy
        if fecha_c is not None:
            try:
                if hasattr(fecha_c, "date") and callable(getattr(fecha_c, "date", None)):
                    fecha_d = fecha_c.date()  # type: ignore[union-attr]
                else:
                    _dt = pd.to_datetime(str(fecha_c), errors="coerce")
                    fecha_d = _dt.date() if pd.notna(_dt) else hoy
            except Exception:
                fecha_d = hoy
        score_v, rsi_val = 50.0, 50.0
        if df_anal is not None and not df_anal.empty and "TICKER" in df_anal.columns:
            m = df_anal[df_anal["TICKER"].astype(str).str.upper().str.strip() == ticker]
            if not m.empty:
                row0 = m.iloc[0]
                if "PUNTAJE_TECNICO" in m.columns:
                    score_v = float(row0.get("PUNTAJE_TECNICO", 50) or 50)
                if "RSI" in m.columns:
                    rsi_val = float(row0.get("RSI", 50) or 50)
        ref = "—"
        det = "Motor de salida (perfil + señales)"
        if ppc_ars > 0 and px_ars > 0:
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
                )
                pt = float(ms.get("precio_target", 0) or 0)
                if pt > 0:
                    ref = f"Target ARS {round(pt, 2)}"
            except Exception:
                ref = "—"
        rows.append({
            "Activo": _act_lbl,
            "Clase": "Renta variable",
            "Precio ARS": round(px_ars, 2) if px_ars else None,
            "Referencia": ref,
            "Detalle": det,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("Clase", ascending=False).reset_index(drop=True)


def _df_alineacion_activos(
    df_ag: pd.DataFrame,
    diag: object,
    df_analisis: pd.DataFrame | None = None,
    universo_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    max_t = str(getattr(diag, "activo_mas_concentrado", "") or "").strip().upper()
    max_w = float(getattr(diag, "pct_concentracion_max", 0) or 0)
    score_map: dict[str, float] = {}
    estado_map: dict[str, str] = {}
    if df_analisis is not None and not df_analisis.empty and "TICKER" in df_analisis.columns:
        da = df_analisis.copy()
        da["TICKER"] = da["TICKER"].astype(str).str.strip().str.upper()
        if "PUNTAJE_TECNICO" in da.columns:
            for _, sr in da.iterrows():
                tk = str(sr["TICKER"] or "").strip().upper()
                if tk:
                    try:
                        score_map[tk] = float(sr.get("PUNTAJE_TECNICO", 0) or 0.0)
                    except (TypeError, ValueError):
                        score_map[tk] = float("nan")
        if "ESTADO" in da.columns:
            for _, sr in da.iterrows():
                tk = str(sr["TICKER"] or "").strip().upper()
                if tk:
                    estado_map[tk] = str(sr.get("ESTADO", "") or "").strip()

    pct_rf_act = float(getattr(diag, "pct_defensivo_actual", 0) or 0) * 100.0
    pct_rf_req_u = float(getattr(diag, "pct_defensivo_requerido", 0) or 0) * 100.0
    pct_rv_act = float(getattr(diag, "pct_rv_actual", 0) or 0) * 100.0
    pct_rv_req_u = max(0.0, min(100.0, 100.0 - pct_rf_req_u))

    rows: list[dict] = []
    for _, r in df_ag.iterrows():
        row_s = pd.Series(r)
        t = _ticker_desde_fila_pos(row_s)
        if not t:
            continue
        es_rf = es_fila_renta_fija_ar(row_s, UNIVERSO_RENTA_FIJA_AR)
        try:
            peso = float(r.get("PESO_PCT", 0) or 0) * 100.0
        except (TypeError, ValueError):
            peso = 0.0
        adv = ""
        if t == max_t and max_w > 30:
            adv = "Concentración alta"
        elif t == max_t and max_w > 20:
            adv = "Monitorear peso"
        else:
            adv = "En rango"
        sc = score_map.get(t)
        if sc is None or (isinstance(sc, float) and np.isnan(sc)):
            motor_txt = "n/d"
        else:
            motor_txt = f"{float(sc):.1f}"
            est = estado_map.get(t, "")
            if est:
                motor_txt = f"{motor_txt} · {est}"
        _nom = _nombre_universo_para_ticker(t, universo_df)
        _act_lbl = f"{t} — {_nom}" if _nom else t
        rows.append({
            "Activo": _act_lbl,
            "Peso %": round(peso, 1),
            "Clase": "Renta fija" if es_rf else "Renta variable",
            "RF % cartera": round(pct_rf_act, 1),
            "RF % objet.": round(pct_rf_req_u, 1),
            "RV % cartera": round(pct_rv_act, 1),
            "RV % objet.": round(pct_rv_req_u, 1),
            "Motor (score)": motor_txt,
            "Chequeo": adv,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("Peso %", ascending=False).reset_index(drop=True)


def _render_inv_onboarding_hub() -> None:
    """Onboarding ligero (3 pasos); el inversor puede ocultar la guía."""
    if st.session_state.get("inv_hub_onboarding_done"):
        return
    with st.expander("Tu recorrido sugerido (3 pasos)", expanded=True):
        for tit, txt in pasos_onboarding_hub():
            st.markdown(f"**{tit}** — {txt}")
        if st.button("Listo, ocultar esta guía", key="inv_hub_onboarding_btn"):
            st.session_state["inv_hub_onboarding_done"] = True
            st.rerun()


@st.cache_data(ttl=300, show_spinner=False)
def _estado_universo_inversor_cached() -> tuple[dict, pd.DataFrame]:
    from services.estado_universo_mq26 import (
        dataframe_estado_universo,
        resumen_estado_universo_mq26,
    )

    r = resumen_estado_universo_mq26(
        max_scan_cedears=80,
        max_scan_merval=40,
        max_scan_on=60,
        max_scan_bonos=30,
    )
    return r, dataframe_estado_universo(r)


def render_tab_inversor(ctx: dict) -> None:
    if st.session_state.pop("inv_degradado_ui", False):
        st.warning("Algunas funciones se ejecutaron en modo degradado. Revisá datos antes de confirmar operaciones.")
    # ── Selector de perfil — primera y única decisión del inversor ─────────────
    _render_selector_perfil_cards(ctx)
    st.divider()

    df_ag = ctx.get("df_ag")
    metricas = ctx.get("metricas") or {}
    ccl = float(ctx.get("ccl") or 1.0)

    if _inversor_sin_posiciones_cargadas(df_ag):
        _render_bienvenida_inversor(ctx)
        return

    diag = _get_diagnostico_cached(ctx)

    uxb = st.session_state.pop("inv_ux_before_load", None)
    if isinstance(uxb, dict) and "pct" in uxb:
        nuevo_pct = float(getattr(diag, "pct_defensivo_actual", 0.0) or 0.0) * 100.0
        st.success(antes_despues_defensivo(float(uxb["pct"]), nuevo_pct))

    pnl_ars_frac = float(metricas.get("pnl_pct_total", 0) or 0.0)
    pnl_papel_frac = float(metricas.get("pnl_pct_total_usd", 0) or 0.0)
    valor_total = float(metricas.get("total_valor", 0) or 0)
    valor_usd = valor_total / max(ccl, 1e-9)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)
    pct_def_frac = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
    pct_def_req_frac = float(getattr(diag, "pct_defensivo_requerido", 0) or 0) or 0.4

    hub = build_investor_hub_snapshot(diag, metricas, ccl, valor_total_ars=valor_total)

    _render_inv_onboarding_hub()

    st.markdown(
        '<h2 class="mq-inv-h2-hero mq-inv-h2-hero--compact">Mi cartera</h2>',
        unsafe_allow_html=True,
    )
    st.caption(patrimonio_dual_line(valor_usd, valor_total, ccl))

    # Ancla CSS (M484–M486): tabs internos estilo “capítulo” sin afectar otras vistas.
    st.markdown(
        '<div class="mq-inv-inner-tabs-anchor" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    tab_res, tab_rfv, tab_salud, tab_plan, tab_reb = st.tabs([
        "📋 Resumen",
        "📊 RF · RV",
        "❤️ Salud y alineación",
        "🎯 Plan y simulaciones",
        "⚖️ Rebalanceo y oportunidades",
    ])

    _def_ok = pct_def_frac >= pct_def_req_frac
    _rv_frac = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - pct_def_frac)) or 0.0)
    _def_label = (
        "✓ Renta fija en rango vs tu plan"
        if _def_ok
        else f"Falta renta fija ({pct_def_req_frac:.0%} sugerido para tu perfil)"
    )

    with tab_res:
        # Ancla M471–M473: primera fila de KPIs (grid + tabular nums vía CSS scoped).
        st.markdown(
            '<div class="mq-inv-resumen-kpi-hook" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Valor cartera", f"ARS {valor_total:,.0f}")
        m2.metric("Equivalente USD", f"USD {valor_usd:,.0f}")
        m3.metric(
            "P&L sobre costo (ARS)",
            f"{pnl_ars_frac * 100:+.1f}%",
            help="Ganancia o pérdida en pesos respecto del capital histórico cargado "
            "(en CEDEARs incluye el efecto del tipo de cambio implícito).",
        )
        m4.metric(
            "Rendimiento USD (%)",
            f"{pnl_papel_frac * 100:+.1f}%",
            help="Rendimiento sobre la base en USD × CCL vigente (costo del certificado) o, en locales, "
            "el costo en ARS comparable a esa pata dólar. Complementa el P&L en pesos histórico de la tarjeta anterior.",
        )
        st.caption(
            "Patrimonio en **ARS** y equivalente **USD**; P&L y rendimiento USD según costos "
            "y reglas del diagnóstico (ver ayuda en cada tarjeta)."
        )
        st.markdown(
            '<h4 class="mq-inv-resumen-positions-head">Tus posiciones</h4>',
            unsafe_allow_html=True,
        )
        _render_tabla_posiciones_resumen(ctx)

    # ── Tab RF · RV: paneles separados con KPIs distintos ─────────────────────
    with tab_rfv:
        st.caption(
            "Renta Fija y Renta Variable tienen KPIs distintos. "
            "El objetivo RF/RV está definido por tu perfil de riesgo."
        )
        with st.expander("Estado de situacion - universo analizado", expanded=False):
            try:
                _, df_est = _estado_universo_inversor_cached()
                st.dataframe(df_est, hide_index=True, use_container_width=True)
            except Exception as exc:
                st.warning(f"No se pudo cargar el resumen del universo: {exc}")
        _render_panel_rf_kpis(ctx, df_ag, ccl, diag)
        st.divider()
        _render_panel_rv_kpis(ctx, df_ag, metricas, ccl, diag)
        # Barra de alineación general
        st.divider()
        st.markdown(
            defensive_bar_html(pct_def_frac, pct_def_req_frac, _def_label),
            unsafe_allow_html=True,
        )
        from ui.monitor_on_usd import render_monitor_on_usd
        render_monitor_on_usd(expanded=False)

    with tab_salud:
        st.markdown(
            "<p class='mq-hub-lead'>Salud financiera</p>",
            unsafe_allow_html=True,
        )
        _score_hub = float(hub.get("alignment_score_pct") or 0.0)
        st.metric(
            "Salud de la cartera (puntaje único 0–100)",
            f"{_score_hub:.0f}",
            help=GLOSARIO_INVERSOR["salud_score"],
        )
        st.progress(min(1.0, max(0.0, _score_hub / 100.0)))
        st.caption(
            "Un solo número resume el diagnóstico; el semáforo y el texto de abajo amplían el mismo resultado."
        )
        h1, h2, h3 = st.columns([1.1, 1.1, 0.45])
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
            st.caption(GLOSARIO_INVERSOR["semaforo"])
        with h2:
            _tit_sem = str(getattr(diag, "titulo_semaforo", "") or "").strip()
            if _tit_sem:
                st.markdown(f"**{_tit_sem}**")
            st.caption(
                "Progreso visual alineado al mismo puntaje; no es un segundo score distinto."
            )
        with h3:
            if st.button("Actualizar", key="btn_refresh_diag_inversor", use_container_width=True):
                st.session_state.pop("inv_diagnostico", None)
                st.rerun()
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Renta fija en cartera",
            f"{pct_def_frac * 100:.1f}%",
            help="Porcentaje del patrimonio en renta fija (bonos, ON, letras).",
        )
        k2.metric(
            "Objetivo RF (perfil)",
            f"{pct_def_req_frac * 100:.1f}%",
            help="Renta fija objetivo según tu perfil de riesgo.",
        )
        k3.metric(
            "Renta variable",
            f"{_rv_frac * 100:.1f}%",
            help="Porcentaje del patrimonio en CEDEARs y acciones (precio fluctúa más).",
        )
        with st.expander("Glosario rápido", expanded=False):
            st.markdown(
                f"**Renta fija vs variable**  \n{GLOSARIO_INVERSOR['rf_rv']}\n\n"
                f"**CCL**  \n{GLOSARIO_INVERSOR['ccl']}\n\n"
                f"**Target y stop**  \n{GLOSARIO_INVERSOR['target_stop']}\n\n"
                f"**Rebalanceo**  \n{GLOSARIO_INVERSOR['rebalanceo']}"
            )
        st.markdown("##### Objetivos por activo (target RV · TIR renta fija)")
        _ref_df = _df_salud_referencias_posicion(ctx, df_ag)
        if not _ref_df.empty:
            st.dataframe(
                _ref_df,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(_ref_df, min_px=140, max_px=320),
            )
        st.caption(
            "**CEDEARs / acciones:** precio objetivo en ARS según el motor de salida (perfil y señales). "
            "**Renta fija:** TIR de referencia del catálogo MQ26 y vencimiento; no aplica un ‘target’ tipo acción."
        )
        st.markdown("##### ¿Cada activo está razonablemente alineado?")
        _al = _df_alineacion_activos(
            df_ag, diag, ctx.get("df_analisis"), ctx.get("universo_df"),
        )
        if not _al.empty:
            st.dataframe(
                _al,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(_al, min_px=160, max_px=360),
            )
        st.caption(
            "**RF/RV en columnas:** porcentajes del **total de la cartera** frente al **objetivo del perfil** (mismos valores en cada fila; sirve para leer cartera vs plan junto a cada activo). "
            "**Motor (score):** señal técnica 0–10 del análisis del universo (y **ESTADO** si viene cargado). "
            f"Ruleset del mix: **{getattr(diag, 'ruleset_version', '') or '—'}**. "
            "**Chequeo:** concentración fuerte en un ticker (según el diagnóstico). "
            "No reemplaza asesoramiento personalizado."
        )

        with st.expander("RF vs RV: comparativa con tu perfil", expanded=True):
            st.caption(
                "**Renta fija:** bonos, ONs, letras. **Renta variable:** CEDEARs y acciones. "
                f"RV ~{_rv_frac:.0%}. Reglas: **{getattr(diag, 'ruleset_version', '') or '—'}**."
            )
            st.markdown(
                defensive_bar_html(pct_def_frac, pct_def_req_frac, _def_label),
                unsafe_allow_html=True,
            )

        _res_ej = (hub.get("resumen_ejecutivo") or "").strip()
        if _res_ej:
            st.markdown("##### Qué resume el motor")
            st.markdown(
                f"<div style='font-size:0.9rem;color:var(--c-text-2);line-height:1.45;"
                f"margin-bottom:0.75rem;'>{html.escape(_res_ej[:1200])}"
                f"{'…' if len(_res_ej) > 1200 else ''}</div>",
                unsafe_allow_html=True,
            )

        with st.expander("Observaciones del diagnóstico", expanded=False):
            for o in getattr(diag, "observaciones", [])[:6]:
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

    with tab_plan:
        perfil_ui = perfil_diagnostico_valido(str(ctx.get("cliente_perfil", "Moderado")))
        ideal_d_base = CARTERA_IDEAL.get(perfil_ui, CARTERA_IDEAL["Moderado"])
        _mix_st = st.session_state.get("inv_mix_plan")
        ideal_dict, ideal_src = ideal_dict_desde_mix_plan(
            perfil_ui, ideal_d_base, _mix_st if isinstance(_mix_st, dict) else None
        )
        _d_plan_days = dias_desde_primera_compra(df_ag)
        _ccl_plan = float(ctx.get("ccl") or 1150.0)
        _tiene_pos = df_ag_tiene_posiciones_reales(df_ag)

        st.caption(
            "Proyecciones y benchmarks **ilustrativos**: no son promesa de resultado ni asesoramiento personalizado."
        )
        st.markdown(
            "<p style='font-size:0.85rem;color:var(--c-text-2);margin:0 0 0.75rem 0;'>"
            "En esta pestaña: <strong>prioridades</strong>, <strong>mix</strong> vs referencia, "
            "<strong>comparativas de rendimiento</strong> (con matices de período) y una "
            "<strong>proyección</strong> con escenarios.</p>",
            unsafe_allow_html=True,
        )
        with st.expander("Qué asumimos en los números de abajo", expanded=False):
            st.markdown(
                "- **Referencia ideal:** cartera modelo del perfil, o —si guardaste un armado— "
                "esa fracción de renta fija combinada con la RV del modelo.\n"
                "- **Tu cartera:** P&amp;L acumulado en USD de referencia usa la misma base que el diagnóstico "
                "(no es necesariamente año calendario).\n"
                "- **SPY / QQQ:** retorno **YTD calendario** USA desde yfinance (precios ajustados).\n"
                "- **Proyección:** escenarios fijos y opcional Montecarlo con historia SPY (semilla fija 42)."
            )

        st.markdown(
            "<p style='font-size:0.65rem;font-weight:600;color:var(--c-text-3);"
            "text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.35rem;'>Estado de datos</p>",
            unsafe_allow_html=True,
        )
        _ed1, _ed2, _ed3 = st.columns(3)
        _ed1.metric("CCL (referencia)", f"{_ccl_plan:,.2f}")
        _ed2.metric("Posiciones", str(int(hub.get("n_posiciones") or 0)))
        if _d_plan_days is not None:
            _ed3.metric("Días desde 1ª compra", str(int(_d_plan_days)))
        else:
            _ed3.metric("Días desde 1ª compra", "—")
        if not _tiene_pos:
            st.warning(
                "No hay pesos de cartera cargados o la cartera está vacía. Importá posiciones "
                "para ver el mix real y comparativas con sentido."
            )
            if st.button(
                "Abrir importación del broker",
                key="inv_plan_cta_import",
                use_container_width=True,
            ):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "importar"
                st.rerun()

        st.markdown(
            '<div class="mq-inv-plan-subtabs-anchor" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        plan_s1, plan_s2, plan_s3 = st.tabs(
            ["1 · Prioridades y mix", "2 · Rendimiento (orientativo)", "3 · Proyección y descarga"],
        )

        with plan_s1:
            st.markdown("##### Prioridades (primeras acciones)")
            for a in hub.get("acciones_top") or []:
                st.markdown(
                    f"**{a.get('titulo', '—')}** ({a.get('prioridad', '')}) — _{a.get('cifra', '')}_"
                )
            st.divider()
            st.markdown("##### Cartera ideal vs tu mix actual")
            _ideal_lbl = (
                "Incluye el **mix RF que guardaste** al armar en la app (resto según modelo del perfil)."
                if ideal_src == "armado_app"
                else f"Referencia **CARTERA_IDEAL** del perfil **{html.escape(perfil_ui)}**."
            )
            st.caption(_ideal_lbl)
            _cmp: list[dict] = []
            try:
                for k, v in (ideal_dict or {}).items():
                    ks = str(k).strip()
                    if not ks:
                        continue
                    if ks.startswith("_") and ks != "_RENTA_AR":
                        continue
                    lbl = "Renta fija AR (otros)" if ks == "_RENTA_AR" else ks
                    _cmp.append({"Bucket": lbl, "Peso objetivo %": round(float(v) * 100.0, 1)})
            except Exception:
                _cmp = []
            if _cmp:
                _df_cmp_responsive = pd.DataFrame(_cmp)
                st.dataframe(
                    _df_cmp_responsive,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(_df_cmp_responsive, min_px=120, max_px=260),
                )
            _c1, _c2 = st.columns(2)
            with _c1:
                cap_ideal = "**Ideal** (tu armado + modelo)" if ideal_src == "armado_app" else "**Ideal** del modelo (perfil)"
                st.caption(cap_ideal)
                fig_t_ideal = fig_torta_ideal(perfil_ui, ideal_dict or {})
                if fig_t_ideal:
                    st.plotly_chart(fig_t_ideal, use_container_width=True, key="inv_pie_ideal")
            with _c2:
                st.caption("**Tu mix** actual (pesos en cartera)")
                fig_t_actual = None
                if df_ag is not None and not df_ag.empty and "PESO_PCT" in df_ag.columns:
                    wmap: dict[str, float] = {}
                    for _, rw in df_ag.iterrows():
                        tk = _ticker_desde_fila_pos(rw)
                        if not tk:
                            continue
                        try:
                            w = float(rw.get("PESO_PCT", 0) or 0)
                        except (TypeError, ValueError):
                            w = 0.0
                        if w <= 0:
                            continue
                        wmap[tk] = wmap.get(tk, 0.0) + w
                    wmap = agrupar_pesos_torta(wmap, min_frac=0.03)
                    if wmap:
                        fig_t_actual = go.Figure(
                            data=[
                                go.Pie(
                                    labels=list(wmap.keys()),
                                    values=[max(0.0, v) for v in wmap.values()],
                                    hole=0.45,
                                    textinfo="label+percent",
                                    hoverinfo="label+percent",
                                    marker=dict(line=dict(color="rgba(15,23,42,0.35)", width=1)),
                                )
                            ]
                        )
                        fig_t_actual.update_layout(
                            **plotly_chart_layout_base(
                                title=dict(
                                    text=f"Tu cartera — {len(wmap)} segmento(s)",
                                    font=dict(size=14),
                                ),
                                margin=dict(t=40, b=10, l=10, r=10),
                                height=280,
                                showlegend=False,
                            ),
                        )
                if fig_t_actual:
                    st.plotly_chart(fig_t_actual, use_container_width=True, key="inv_pie_actual")
                else:
                    st.info("Sin posiciones para armar la torta de tu mix.")

            st.markdown("##### RF / RV: tu cartera vs referencia ideal")
            rf_i, rv_i = _ideal_rf_rv_fracciones(ideal_dict)
            rf_tu = float(getattr(diag, "pct_defensivo_actual", 0) or 0)
            rv_tu = float(getattr(diag, "pct_rv_actual", max(0.0, 1.0 - rf_tu)) or 0)
            _xl = ["Tu cartera", "Referencia ideal"]
            fig_stack = go.Figure(
                data=[
                    go.Bar(
                        name="Renta fija",
                        x=_xl,
                        y=[rf_tu * 100.0, rf_i * 100.0],
                        marker_color="#3b82f6",
                    ),
                    go.Bar(
                        name="Renta variable",
                        x=_xl,
                        y=[rv_tu * 100.0, rv_i * 100.0],
                        marker_color="#10b981",
                    ),
                ]
            )
            fig_stack.update_layout(
                **plotly_chart_layout_base(
                    barmode="stack",
                    height=320,
                    yaxis=dict(title="% del patrimonio", rangemode="tozero"),
                    xaxis=dict(title=""),
                    margin=dict(t=24, b=40, l=50, r=16),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                ),
            )
            st.plotly_chart(fig_stack, use_container_width=True, key="inv_bar_rf_rv")
            st.caption(
                "Referencia ideal: pesos anteriores (modelo o armado). "
                "Tu cartera: mix del diagnóstico. "
                "El detalle de alineación por activo está en **Salud y alineación**."
            )

        with plan_s2:
            st.markdown("##### Rendimiento: referencias orientativas")
            ytd_tu = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0)
            ytd_mod = float(RENDIMIENTO_MODELO_YTD_REF.get(perfil_ui, 0.0869)) * 100.0
            ytd_bench_diag = float(getattr(diag, "benchmark_ytd_pct", 0.0) or 0.0)
            ytd_spy = _benchmark_ytd_pct("SPY")
            ytd_qqq = _benchmark_ytd_pct("QQQ")
            _bench_rows: list[tuple[str, float, str]] = [
                ("Tu cartera — acumulado ref. USD", ytd_tu, "desde primera compra (diagnóstico); no es YTD calendario."),
                ("Objetivo rendimiento motor (prorrateado)", ytd_bench_diag, "benchmark interno del diagnóstico; coherente con observaciones."),
                ("Referencia estática perfil MQ26", ytd_mod, "número de estilo; no es un fondo cotizable."),
            ]
            if ytd_spy is not None:
                _bench_rows.append(("SPY (USA, YTD calendario)", ytd_spy, "yfinance, precios ajustados."))
            if ytd_qqq is not None:
                _bench_rows.append(("QQQ (USA, YTD calendario)", ytd_qqq, "yfinance, precios ajustados."))
            _bx = [a for a, _, _ in _bench_rows]
            _by = [b for _, b, _ in _bench_rows]
            _colors = ["#6366f1", "#94a3b8", "#f59e0b", "#22c55e", "#0ea5e9", "#a78bfa"]
            fig_ytd = go.Figure(
                data=[
                    go.Bar(
                        x=_bx,
                        y=_by,
                        marker_color=_colors[: len(_bx)],
                        text=[f"{v:+.1f}%" for v in _by],
                        textposition="outside",
                    )
                ]
            )
            _perd_txt = (
                f"Desde la **primera fecha de compra** registrada: **{_d_plan_days}** días (~{(_d_plan_days or 0) / 365.25:.2f} años)."
                if _d_plan_days is not None
                else "Sin fechas de compra: el % de tu cartera sigue al diagnóstico, pero no mostramos un largo de período."
            )
            fig_ytd.update_layout(
                **plotly_chart_layout_base(
                    height=360,
                    yaxis=dict(title="Porcentaje (%)"),
                    xaxis=dict(tickangle=-22),
                    margin=dict(t=40, b=120, l=50, r=24),
                    annotations=[
                        dict(
                            text=_perd_txt[:220],
                            xref="paper",
                            yref="paper",
                            x=0,
                            y=-0.42,
                            showarrow=False,
                            xanchor="left",
                            font=dict(size=11, color="rgb(148, 163, 184)"),
                        ),
                    ],
                ),
            )
            st.plotly_chart(fig_ytd, use_container_width=True, key="inv_bar_ytd_bench")
            st.caption(
                "Las barras **no comparten el mismo período**: tu cartera y el objetivo del motor usan tu historial; "
                "SPY/QQQ usan **año calendario** en USA. No las interpretés como ranking de fondos."
            )
            try:
                _df_bench = pd.DataFrame(
                    [{"Serie": a, "%": round(b, 2), "Nota": c} for a, b, c in _bench_rows]
                )
                st.dataframe(
                    _df_bench,
                    use_container_width=True,
                    hide_index=True,
                    height=dataframe_auto_height(_df_bench, min_px=120, max_px=260),
                )
            except Exception:
                pass

        with plan_s3:
            _render_proyeccion_y_pie_inversor(ctx, diag, metricas, hub)

        st.caption(
            "Para **RF vs objetivo por activo**, abrí la pestaña **Salud y alineación**."
        )

    with tab_reb:
        st.markdown(copy_rebalanceo_humano())
        _render_bloque_plata_nueva(ctx, df_ag, diag, ccl)
        st.markdown("##### Objetivos por posición (target / stop / señal)")
        _render_posiciones_con_targets(ctx, diag)

        _ccl_v = float(ctx.get("ccl") or 1150.0)
        with st.expander("💵 Efectivo para sumar al patrimonio", expanded=False):
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
                    f"<div style='font-family:var(--font-mono),monospace;font-size:1.25rem;"
                    f"font-weight:500;color:var(--c-text);'>"
                    f"ARS {_total_ars:,.0f}</div>"
                    f"<div style='font-size:0.7rem;color:var(--c-text-3);margin-top:2px;'>"
                    f"Cartera ~ ARS {_val_cartera_ars:,.0f} · "
                    f"Efectivo ~ ARS {_efectivo_ars:,.0f} · "
                    f"ref. USD {_total_patrimon:,.0f}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("### Agregar o importar")
        st.session_state.setdefault("inv_carga_open", False)
        if st.button(
            "📝 Registrar venta",
            key="inv_open_venta_manual",
            use_container_width=True,
            help="Abre el asistente para registrar una venta manualmente o importar el extracto del broker.",
        ):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "venta"
            st.rerun()
        st.caption("Para vaciar toda la cartera y empezar de cero, usá el panel **🧹 Vaciar cartera** en la columna izquierda.")
        st.checkbox(
            "Mostrar asistente para sumar compras o importar archivo del broker",
            key="inv_carga_open",
        )
        if st.session_state.get("inv_carga_open"):
            _fn = ctx.get("render_carga_activos_fn")
            if _fn is None:
                from ui.carga_activos import render_carga_activos as _fn
            _fn(ctx)


def _render_bloque_plata_nueva(ctx: dict, df_ag, _diag, ccl: float) -> None:
    """
    Capital nuevo + sugerencias: mismo flujo que «Armar mi primera cartera», pero
    el motor recibe tu cartera actual (df_ag) y un diagnóstico alineado al perfil.
    """
    st.markdown("### ¿Qué compro ahora?")
    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    perfil_v = perfil_diagnostico_valido(perfil)
    horizonte = _horizonte_ui(ctx)
    ccl_f = float(ccl or 1150.0)
    df_ag_use = df_ag if df_ag is not None else pd.DataFrame()

    cap_default = float(ctx.get("capital_nuevo", 0.0) or 0.0)
    cap_side = float(st.session_state.get("capital_disponible_mq", 0.0) or 0.0)
    if cap_side > 0:
        cap_default = cap_side

    st.markdown(
        """
    <p class="mq-inv-step-label">
        Paso 1 de 2 — Capital que querés sumar
    </p>
    """,
        unsafe_allow_html=True,
    )
    col_monto, col_info = st.columns([3, 2])
    with col_monto:
        cap_in = st.number_input(
            "¿Cuánto querés invertir ahora? (ARS)",
            min_value=10_000.0,
            max_value=100_000_000.0,
            value=float(max(10_000.0, cap_default)) if cap_default > 0 else 500_000.0,
            step=50_000.0,
            format="%.0f",
            key="inversor_capital_ars",
            help="El motor reparte este monto respetando tu cartera actual y tu perfil.",
        )
    with col_info:
        cap_usd = float(cap_in) / max(ccl_f, 1.0)
        st.markdown(
            f"""
        <div class="mq-inv-kpi-box mq-inv-kpi-box--offset">
            <div class="mq-inv-kpi-label">Plata nueva</div>
            <div class="mq-inv-kpi-value">$ {float(cap_in):,.0f} ARS</div>
            <div class="mq-inv-kpi-hint">
                Referencia ~ USD {cap_usd:,.0f} (CCL {ccl_f:,.0f}) · ya tenés cartera cargada</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--tight">
        Paso 2 de 2 — La app calcula por vos
    </p>
    <p class="mq-inv-muted-p">
        Misma lógica que «mi primera cartera»: perfil, mercado y señales. Incluye lo que ya tenés para no duplicar el espíritu del plan.
    </p>
    """,
        unsafe_allow_html=True,
    )

    stress = _market_stress_optional()
    if st.button(
        f"🧠 Calcular sugerencias (perfil {perfil})",
        type="primary",
        use_container_width=True,
        key="btn_recomendar_inversor",
    ):
        with st.spinner("Calculando sugerencias sobre tu cartera actual…"):
            try:
                from services.diagnostico_cartera import diagnosticar
                from services.recomendacion_capital import recomendar

                metricas = ctx.get("metricas") or {}
                senales = _senales_precalculadas(ctx)
                mix_o = _mix_objetivo_desde_sesion(df_ag_use, ctx.get("universo_df"))
                diag_fresh = diagnosticar(
                    df_ag=df_ag_use,
                    perfil=perfil,
                    horizonte_label=horizonte,
                    metricas=metricas,
                    ccl=ccl_f,
                    universo_df=ctx.get("universo_df"),
                    senales_salida=senales,
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                    mix_objetivo_rf=mix_o,
                )
                rr = recomendar(
                    df_ag=df_ag_use,
                    perfil=perfil_v,
                    horizonte_label=horizonte,
                    capital_ars=float(cap_in),
                    ccl=ccl_f,
                    precios_dict=_precios_para_recomendar(ctx),
                    diagnostico=diag_fresh,
                    universo_df=ctx.get("universo_df"),
                    df_analisis=ctx.get("df_analisis"),
                    market_stress=stress,
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                )
                st.session_state["inv_plata_resultado"] = {
                    "capital": float(cap_in),
                    "rr": rr,
                    "perfil": perfil_v,
                    "ideal": CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"]),
                }
                st.session_state["inv_recomendacion"] = {"capital": float(cap_in), "rr": rr}
                try:
                    from services.audit_trail import registrar_recomendacion_evento

                    registrar_recomendacion_evento(
                        evento="SIMULACION_RECOMENDACION",
                        origen="capital_incremental",
                        cliente_id=ctx.get("cliente_id"),
                        cliente_nombre=str(ctx.get("cliente_nombre", "")),
                        tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                        actor=str(ctx.get("login_user", "") or ""),
                        correlation_id=str(st.session_state.get("session_correlation_id", "")),
                        cartera=str(_cartera_resuelta_primera_cartera(ctx)),
                        perfil=perfil_v,
                        capital_ars=float(cap_in),
                        filas=len(list(getattr(rr, "compras_recomendadas", None) or [])),
                        payload={
                            "alerta_mercado": bool(getattr(rr, "alerta_mercado", False)),
                            "capital_remanente_ars": float(getattr(rr, "capital_remanente_ars", 0) or 0),
                        },
                    )
                except Exception:
                    pass
                # Pilar 3: plan explicado con motivos + trazabilidad al audit trail
                try:
                    from services.recomendador_explicable import (
                        auditar_plan,
                        construir_plan_accion,
                    )

                    plan = construir_plan_accion(
                        perfil=perfil_v,
                        rr=rr,
                        senales=senales,
                        capital_ars=float(cap_in),
                        precio_records=ctx.get("precio_records"),
                    )
                    st.session_state["inv_plan_explicado"] = plan
                    auditar_plan(
                        plan,
                        ctx={
                            "cliente_id": ctx.get("cliente_id"),
                            "cliente_nombre": str(ctx.get("cliente_nombre", "")),
                            "tenant_id": str(ctx.get("tenant_id", "default") or "default"),
                            "login_user": str(ctx.get("login_user", "") or ""),
                            "correlation_id": str(st.session_state.get("session_correlation_id", "")),
                            "cartera_activa": str(_cartera_resuelta_primera_cartera(ctx)),
                        },
                    )
                except Exception:
                    st.session_state.pop("inv_plan_explicado", None)
                st.rerun()
            except Exception as e:
                st.error(f"Error al calcular: {e}")

    res = st.session_state.get("inv_plata_resultado") or {}
    cap_ui = float(st.session_state.get("inversor_capital_ars", 0) or 0)
    if not res or abs(float(res.get("capital", -1)) - cap_ui) >= 1.0:
        return

    rr = res.get("rr")
    perfil_res = str(res.get("perfil") or perfil_v)
    if rr is None:
        return

    if getattr(rr, "alerta_mercado", False):
        st.warning(f"⚠️ {rr.mensaje_alerta}")

    if getattr(rr, "resumen_recomendacion", ""):
        st.caption(str(rr.resumen_recomendacion))

    # Pilar 3: cada sugerencia con su porqué, confianza de datos y link a ficha
    _plan_exp = st.session_state.get("inv_plan_explicado")
    if _plan_exp is not None and _flag_plan_explicado(ctx):
        with st.expander("🧭 Por qué estas sugerencias — plan explicado", expanded=False):
            from ui.components.plan_accion_view import render_plan_accion

            render_plan_accion(_plan_exp, key_prefix="inv_plan")

    items = list(getattr(rr, "compras_recomendadas", None) or [])
    if not items:
        st.info(
            "No se encontraron compras posibles con este capital y tu cartera actual. "
            "Probá con otro monto o consultá a tu asesor."
        )
        pend0 = getattr(rr, "pendientes_proxima_inyeccion", []) or []
        if pend0:
            st.markdown("**Para la próxima vez**")
            for p in pend0[:6]:
                tk_raw = str(p.get("ticker", "") or "")
                tk_lbl = (
                    "Renta fija AR (soberanos / cupo no cubierto por ON del modelo)"
                    if tk_raw == "_RENTA_AR"
                    else tk_raw
                )
                st.caption(
                    f"**{html.escape(tk_lbl)}:** {html.escape(str(p.get('motivo', '') or ''))}"
                )
        return

    st.markdown(
        """
    <p style="font-size:0.72rem;font-weight:700;color:var(--c-green);
              text-transform:uppercase;letter-spacing:0.08em;
              margin:1.25rem 0 0.35rem 0;">Paso 3 — Sugerencias (editables)</p>
    <p style="font-size:0.8125rem;color:var(--c-text-2);margin:0 0 0.75rem 0;">
        Ajustá cantidades, precio por cuotaparte (ARS) o el instrumento. Podés agregar o quitar filas.
        Confirmá para registrar <strong>COMPRAS</strong> en tu libro (se suman a lo que ya tenés).
    </p>
    """,
        unsafe_allow_html=True,
    )

    monto_total = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)
    _udf_pln = ctx.get("universo_df")
    _rows_ed: list[dict] = []
    for it in items:
        _tk = str(getattr(it, "ticker", "") or "").strip().upper()
        if not _tk:
            continue
        _rows_ed.append(
            {
                "Ticker": _tk,
                "Unidades": int(getattr(it, "unidades", 0) or 0),
                "Precio_ARS": float(getattr(it, "precio_ars_estimado", 0) or 0),
                "TIPO": _tipo_universo_ticker(_tk, _udf_pln),
                "Notas": str(getattr(it, "justificacion", "") or "")[:120],
            }
        )
    df_ed_base = pd.DataFrame(_rows_ed)
    edited = st.data_editor(
        df_ed_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="pln_data_editor_cartera",
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", help="Código BYMA", width="small"),
            "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1, width="small"),
            "Precio_ARS": st.column_config.NumberColumn(
                "Precio ARS c/u",
                min_value=0.0,
                format="%.2f",
                help="Pesos por cuotaparte en BYMA.",
            ),
            "TIPO": st.column_config.SelectboxColumn(
                "Tipo",
                options=_TIPOS_EDICION_PRIMERA_CARTERA,
                width="small",
            ),
            "Notas": st.column_config.TextColumn("Notas (solo guía)", width="large"),
        },
    )

    ideal_dict = res.get("ideal") or {}
    try:
        _nu = pd.to_numeric(edited["Unidades"], errors="coerce").fillna(0)
        _npx = pd.to_numeric(edited["Precio_ARS"], errors="coerce").fillna(0)
        monto_editado = float((_nu * _npx).sum())
    except Exception:
        monto_editado = monto_total

    st.markdown(
        f"""
    <div class="mq-inv-totals-bar">
        <div><div class="mq-inv-totals-kpi-label">Total tabla (estim.)</div>
        <div class="mq-inv-totals-kpi-num">
            ${monto_editado:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Motor (referencia)</div>
        <div class="mq-inv-totals-kpi-num mq-inv-totals-kpi-num--muted">
            ${monto_total:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Queda en efectivo (ref.)</div>
        <div class="mq-inv-totals-kpi-num--plain">${remanente:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Perfil</div>
        <div class="mq-inv-perfil-name">{html.escape(perfil_res)}</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if ideal_dict:
        fig_t = fig_torta_ideal(perfil_res, ideal_dict)
        if fig_t:
            with st.expander("Ver distribución objetivo del perfil", expanded=False):
                st.plotly_chart(fig_t, use_container_width=True)

    _cart_guardar = _cartera_resuelta_primera_cartera(ctx)
    st.caption(f"Al confirmar, las compras se agregan a: **`{_cart_guardar}`**")

    st.info(
        "💡 Es una sugerencia según tu perfil, tu cartera actual y el mercado. "
        "La confirmación registra **COMPRAS** en tu libro, sumadas a posiciones existentes."
    )
    _confirm_exec_real = st.checkbox(
        "Confirmo que ya ejecuté estas operaciones en mi broker",
        key="pln_confirm_exec_real",
    )

    col_ok, col_act, col_reset = st.columns(3)
    with col_ok:
        if st.button(
            "✅ Confirmar compras sugeridas",
            type="primary",
            use_container_width=True,
            key="pln_confirmar_cartera",
            disabled=not _confirm_exec_real,
        ):
            from ui.carga_activos import _persist_filas

            _ccl_ok = float(ctx.get("ccl") or 0.0)
            if _ccl_ok <= 0:
                st.error("CCL inválido: no se puede derivar PPC USD.")
            elif edited.empty:
                st.warning("La tabla está vacía.")
            else:
                _filas: list[dict] = []
                for _, row in edited.iterrows():
                    _tick = str(row.get("Ticker", "")).strip().upper()
                    _u = int(pd.to_numeric(row.get("Unidades", 0), errors="coerce") or 0)
                    _px = float(pd.to_numeric(row.get("Precio_ARS", 0), errors="coerce") or 0.0)
                    _ti = str(row.get("TIPO", "CEDEAR") or "CEDEAR").strip().upper()
                    if _ti in ("NAN", "NONE", ""):
                        _ti = "CEDEAR"
                    if _ti in ("COMPRA", "VENTA"):
                        _ti = "CEDEAR"
                    if not _tick or _u <= 0 or _px <= 0:
                        continue
                    _ppc_ars = round(_px, 4)
                    _ppc_usd = round(_ppc_ars / max(_ccl_ok, 1e-9), 6)
                    _filas.append(
                        {
                            "FECHA_COMPRA": date.today(),
                            "TICKER": _tick,
                            "CANTIDAD": _u,
                            "PPC_USD": _ppc_usd,
                            "PPC_ARS": _ppc_ars,
                            "TIPO": _ti,
                            "LAMINA_VN": float("nan"),
                        }
                    )
                if not _filas:
                    st.error(
                        "No hay filas válidas: cada una necesita **Ticker**, **Unidades** > 0 y **Precio ARS** > 0."
                    )
                else:
                    _mix_rf = _mix_rf_desde_filas_primera(_filas)
                    st.session_state["inv_mix_plan"] = {
                        "rf": round(_mix_rf, 5),
                        "ts": time.time(),
                    }
                    st.session_state.pop("inv_diagnostico", None)
                    try:
                        from services.audit_trail import registrar_recomendacion_evento

                        registrar_recomendacion_evento(
                            evento="EJECUCION_CONFIRMADA",
                            origen="capital_incremental",
                            cliente_id=ctx.get("cliente_id"),
                            cliente_nombre=str(ctx.get("cliente_nombre", "")),
                            tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                            actor=str(ctx.get("login_user", "") or ""),
                            correlation_id=str(st.session_state.get("session_correlation_id", "")),
                            cartera=str(_cart_guardar),
                            perfil=perfil_res,
                            capital_ars=float(cap_ui),
                            filas=len(_filas),
                            payload={"confirmacion_broker": True},
                        )
                    except Exception:
                        pass
                    _persist_filas(
                        ctx,
                        _filas,
                        "agregar",
                        cartera_override=_cart_guardar,
                        session_keys_clear=["inv_plata_resultado", "inv_recomendacion"],
                    )

    with col_act:
        if st.button("✏️ Cargar lo que compré", use_container_width=True, key="pln_ir_a_carga"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "manual"
            st.session_state.pop("inv_plata_resultado", None)
            st.session_state.pop("inv_recomendacion", None)
            st.rerun()
    with col_reset:
        if st.button("🔄 Recalcular con otro monto", use_container_width=True, key="pln_reset"):
            st.session_state.pop("inv_plata_resultado", None)
            st.session_state.pop("inv_recomendacion", None)
            st.rerun()

    pend = getattr(rr, "pendientes_proxima_inyeccion", []) or []
    if pend:
        st.markdown("**Para la próxima vez**")
        for p in pend[:6]:
            tk_raw = str(p.get("ticker", "") or "")
            if tk_raw == "_RENTA_AR":
                tk_lbl = "Renta fija AR (soberanos / cupo no cubierto por ON del modelo)"
            else:
                tk_lbl = tk_raw
            st.caption(
                f"**{html.escape(tk_lbl)}:** {html.escape(str(p.get('motivo', '') or ''))}"
            )

