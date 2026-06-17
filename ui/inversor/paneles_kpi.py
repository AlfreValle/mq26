"""
ui/inversor/paneles_kpi.py — paneles de KPIs de renta fija y renta variable.

Extraído de ui/tab_inversor.py (Fase 2.1, sexto slice): los dos paneles
superiores del hub del inversor — RF (TIR ponderada, ladder de vencimientos,
top instrumentos) y RV (rendimiento, concentración, benchmark).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
from core.renta_fija_ar import (
    es_fila_renta_fija_ar,
    get_meta,
    ladder_vencimientos,
    tir_ponderada_cartera,
)
from ui.inversor._helpers import _log_degradacion
from ui.mq26_ux import dataframe_auto_height


def _render_panel_rf_kpis(ctx: dict, df_ag: pd.DataFrame, ccl: float, diag) -> None:
    """
    Panel dedicado de Renta Fija con KPIs propios:
    TIR ponderada, paridad BYMA live, % RF vs objetivo,
    próximo vencimiento y ladder de vencimientos.
    """
    from core.perfil_allocation import target_rf_efectivo
    from core.renta_fija_ar import (
        INSTRUMENTOS_RF,
        ficha_rf_minima_bundle,
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
    from core.perfil_allocation import target_rv_efectivo

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
