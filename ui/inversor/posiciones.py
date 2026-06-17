"""
ui/inversor/posiciones.py — posiciones con targets, tabla resumen y salud de referencias.

Extraído de ui/tab_inversor.py (Fase 2.1, quinto slice): lista legible de
posiciones con señales del motor de salida, tabla tipo homebroker, ficha por
posición (Pilar 2) y los DataFrames de salud/alineación que consume el
orquestador.
"""
from __future__ import annotations

import html
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from core.diagnostico_types import (
    UNIVERSO_RENTA_FIJA_AR,
    perfil_motor_salida,
)
from core.renta_fija_ar import _meta_unificado as _rf_meta_unificado
from core.renta_fija_ar import es_fila_renta_fija_ar, get_meta
from ui.inversor._helpers import (
    _nombre_universo_para_ticker,
    _ticker_desde_fila_pos,
)
from ui.mq26_ux import dataframe_auto_height
from ui.posiciones_broker_table import build_posiciones_broker_html


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


