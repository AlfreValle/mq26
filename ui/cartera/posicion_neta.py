"""
ui/cartera/posicion_neta.py — sub-tab Posición Neta (P&L + motor de salida + Kelly).

Extraído de ui/tab_cartera.py (Fase 2.1): señales por posición, plan
explicado del asesor (Pilar 3), ficha RF unificada y sizing Kelly.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from core.structured_logging import log_degradacion
from ui.mq26_ux import dataframe_auto_height
from ui.posiciones_broker_table import build_posiciones_broker_html


def _paridad_implicita_pct_on_usd_desde_fila(row: pd.Series, ccl: float) -> float | None:
    """
    Paridad % implícita desde Px actual (ARS) y CCL, alineada a convención monitor/catálogo.
    Si `ESCALA_PRECIO_RF` tiene texto (÷100 vs PPC), el precio en fila es por 1 VN nominal USD.
    """
    try:
        ccl_f = float(ccl or 0.0)
    except (TypeError, ValueError):
        ccl_f = 0.0
    if ccl_f <= 0:
        return None
    tipo = str(row.get("TIPO", "")).upper()
    if tipo not in ("ON_USD", "BONO_USD"):
        return None
    px = pd.to_numeric(row.get("PRECIO_ARS"), errors="coerce")
    if pd.isna(px):
        return None
    px_f = float(px)
    escala = str(row.get("ESCALA_PRECIO_RF", "") or "").strip()
    if escala:
        return round((px_f * 100.0) / ccl_f, 2)
    return round(px_f / ccl_f, 2)

def _render_posicion_neta(ctx, df_ag, tickers_cartera, coverage, sin_precio,
                          precios_dict, ccl, cartera_activa, prop_nombre,
                          df_analisis, metricas, PESO_MAX_CARTERA,
                          cs, m23svc, ab, asignar_sector, _boton_exportar,
                          cliente_perfil):
    """Sub-tab 1: Posicion Neta - P&L en Tiempo Real + Motor Salida + Kelly."""
    import pandas as pd
    st.subheader("Mis activos")
    st.caption(
        "Valor actual, precio de compra, ganancia o pérdida de cada posición.",
    )

    if cartera_activa == "-- Todas las carteras --":
        st.info(
            "Elegí una **cartera concreta** en el sidebar: **📁 Cartera activa** "
            "(debajo del cliente). La opción «-- Todas las carteras --» no carga posiciones en esta vista."
        )
    elif df_ag.empty:
        st.info(
            "Todavía no hay activos en esta cartera.\n\n"
            "1. Si estás en modo **admin/asesor**, revisá que el cliente y la **cartera activa** "
            "del panel lateral coincidan con el libro que querés ver.\n"
            "2. Importá desde tu broker o cargá operaciones en **Cartera → Libro mayor → Importar del broker**."
        )
    else:
        df_pos = df_ag.copy()
        # Vista principal en pesos BYMA: PPC_ARS, PRECIO_ARS y Target en la misma unidad.
        if ccl and float(ccl) > 0 and "PRECIO_ARS" in df_pos.columns:
            df_pos["Equiv USD/ud"] = (
                pd.to_numeric(df_pos["PRECIO_ARS"], errors="coerce").fillna(0.0) / float(ccl)
            )
        df_pos["PNL_%"]       = df_pos.get("PNL_PCT",     0.0)
        df_pos["PNL_%_USD"]   = df_pos.get("PNL_PCT_USD", df_pos["PNL_%"])
        df_pos["PESO_%"]      = df_pos.get("PESO_PCT",    0.0)

        st.caption(
            "**Primera vista en pesos (BYMA):** CEDEARs y acciones se cotizan en ARS; el progreso "
            "compara compra → actual → objetivo en esa misma moneda y unidad. "
            "**Bonos / letras:** el precio suele ir por **lámina** (p. ej. cada 100 o 1.000 VN); "
            "cargá PPC y precio con la **misma convención**. Columna opcional `LAMINA_VN` en el "
            "transaccional para documentar la unidad."
        )

        if sin_precio:
            with st.expander(
                f"⚠ {len(sin_precio)} ticker(s) sin precio en tiempo real", expanded=False
            ):
                st.markdown(
                    "Estos activos usan el **último precio conocido** (fecha de compra u "
                    "otro fallback). El valor total de la cartera puede diferir del real."
                )
                for t in sin_precio:
                    c1, c2 = st.columns([3, 7])
                    c1.code(t)
                    c2.caption(
                        "CEDEAR o activo local sin cotización disponible en yfinance. "
                        "Podés actualizar manualmente el precio desde Tab Cartera → Editar."
                    )
                st.info(
                    "Para precios en tiempo real de activos locales, configurá "
                    "MQ26_BYMA_API_URL en el .env cuando tengas acceso a un "
                    "proveedor de datos BYMA."
                )


        # ── Enriquecer con scores MOD-23 ────────────────────────────────
        score_map  = {}
        estado_map = {}
        rsi_map    = {}
        if not df_analisis.empty:
            score_map  = df_analisis.set_index("TICKER")["PUNTAJE_TECNICO"].to_dict()
            estado_map = df_analisis.set_index("TICKER")["ESTADO"].to_dict()
            if "RSI" in df_analisis.columns:
                rsi_map = df_analisis.set_index("TICKER")["RSI"].to_dict()
        df_pos["SCORE"]  = df_pos["TICKER"].map(score_map).fillna(5.0)
        df_pos["ESTADO"] = df_pos["TICKER"].map(estado_map).fillna("NEUTRO")

        # ── Motor de Salida: calcular target/progreso/señal por posición ──
        from services.motor_salida import estimar_prob_exito, evaluar_salida, kelly_sizing
        targets, progresos, senales = [], [], []
        kelly_rows = []
        senales_full: list[dict] = []  # dicts completos para el plan explicado (Pilar 3)

        for _, row in df_pos.iterrows():
            ticker  = str(row.get("TICKER", ""))
            tipo    = str(row.get("TIPO", ""))
            # Motor: siempre ARS en la unidad del libro (igual que PRECIO_ARS de BYMA).
            ppc_ars = float(pd.to_numeric(row.get("PPC_ARS", 0.0), errors="coerce") or 0.0)
            px_ars  = float(pd.to_numeric(row.get("PRECIO_ARS", 0.0), errors="coerce") or 0.0)
            rsi_val = float(rsi_map.get(ticker, 50.0))
            score_v = float(row.get("SCORE", 5.0))

            # Fecha de primera compra (si disponible en df_ag)
            fecha_c = row.get("FECHA_COMPRA", date(2020, 1, 1))
            if not isinstance(fecha_c, date):
                try:
                    fecha_c = pd.to_datetime(str(fecha_c)).date()
                except Exception as exc:
                    log_degradacion(__name__, "fecha_compra_parse_fallo", exc, ticker=str(ticker))
                    fecha_c = date(2020, 1, 1)

            if ppc_ars > 0 and px_ars > 0:
                res = evaluar_salida(
                    ticker=ticker,
                    ppc_usd=ppc_ars,
                    px_usd_actual=px_ars,
                    rsi=rsi_val,
                    score_actual=score_v,
                    score_semana_anterior=score_v,
                    fecha_compra=fecha_c,
                    perfil=cliente_perfil,
                )
                targets.append(round(res["precio_target"], 2))
                progresos.append(round(res["progreso_pct"], 1))
                senales.append(res["senal"])
                senales_full.append(res)

                # Kelly para esta posición
                prob = estimar_prob_exito(score_v, rsi_val)
                capital_total = float(metricas.get("total_valor", 1_000_000))
                ks = kelly_sizing(
                    prob_exito=prob,
                    target_pct=res["target_pct"],
                    stop_pct=abs(res["stop_pct"]),
                    capital_total=capital_total,
                )
                kelly_rows.append({
                    "Ticker":       ticker,
                    "Prob. éxito":  round(prob * 100, 1),         # numérico para gradiente
                    "Target %":     round(res['target_pct'], 1),   # numérico para gradiente
                    "Stop %":       round(res['stop_pct'], 1),     # numérico para gradiente
                    "Kelly Compl.": round(ks['kelly_completo_pct'], 1),   # numérico
                    "Kelly Aplic.": round(ks['kelly_aplicado_pct'], 1),   # numérico
                    "Capital sug.": ks["capital_sugerido_ars"],
                    "Interpretación": ks["interpretacion"],
                })
            else:
                targets.append(None)
                progresos.append(0.0)
                senales.append("—")

        df_pos["Target ARS"]  = targets
        df_pos["Progreso %"]  = progresos
        df_pos["Señal"]       = senales

        rec_px = ctx.get("precio_records") or {}

        def _label_fuente_precio(tk) -> str:
            from core.price_engine import label_fuente_con_frescura
            return label_fuente_con_frescura(rec_px.get(str(tk).upper().strip()))

        df_pos["FUENTE_PRECIO"] = df_pos["TICKER"].astype(str).map(_label_fuente_precio)

        # ── Banner CCL histórico vs actual ────────────────────────────────
        usa_historico = "INV_ARS_HISTORICO" in df_pos.columns and (df_pos.get("INV_ARS_HISTORICO", 0) > 0).any()
        if usa_historico:
            st.success("✅ INV_ARS calculado con CCL histórico real. **P&L %** incluye CCL. **P&L % USD** = retorno puro en dólares.")
        else:
            st.warning("⚠️ INV_ARS calculado con CCL actual (sin fechas de compra). El costo en pesos puede diferir del valor real pagado.")

        if "ESCALA_PRECIO_RF" in df_pos.columns and (df_pos["ESCALA_PRECIO_RF"].astype(str).str.strip() != "").any():
            st.info(
                "**P2-RF-04:** el precio actual de al menos una posición RF USD se **dividió entre 100** "
                "para alinearlo con el PPC (último en escala distinta). Revisá la columna **Ajuste escala RF**."
            )

        st.markdown(
            "<p class='mq-subsec-label'>Vista resumen (tipo homebroker)</p>",
            unsafe_allow_html=True,
        )
        _bro_html = build_posiciones_broker_html(
            df_pos,
            metricas,
            hint_text=(
                "Valores en pesos — misma grilla que la vista inversor; "
                "si arriba hay tickers sin precio LIVE, algunos importes usan último dato guardado."
            ),
        )
        if _bro_html:
            st.markdown(_bro_html, unsafe_allow_html=True)
        st.markdown(
            "<p class='mq-subsec-label'>Detalle operativo — targets, progreso y señales</p>",
            unsafe_allow_html=True,
        )

        cols_show = [
            "TICKER", "TIPO", "CANTIDAD_TOTAL", "PPC_ARS", "PRECIO_ARS", "FUENTE_PRECIO",
            "ESCALA_PRECIO_RF",
            "Target ARS", "Progreso %", "Señal",
            "VALOR_ARS", "INV_ARS", "PNL_ARS", "PNL_%", "PNL_%_USD", "PESO_%", "SCORE", "ESTADO",
        ]
        if "Equiv USD/ud" in df_pos.columns:
            cols_show.append("Equiv USD/ud")
        cols_show = [c for c in cols_show if c in df_pos.columns]

        def color_pnl(val):
            if isinstance(val, (int, float)):
                return "color:#27AE60;font-weight:bold" if val > 0 else ("color:#E74C3C;font-weight:bold" if val < 0 else "")
            return ""

        def color_senal(val):
            if "SALIR" in str(val):
                return "background-color:#E74C3C;color:white;font-weight:bold"
            if "REVISAR" in str(val):
                return "background-color:#F39C12;color:white"
            if "MANTENER" in str(val):
                return "background-color:#27AE60;color:white"
            return ""

        rename_cols = {
            "TIPO":                 "Tipo",
            "PPC_ARS":              "Precio de compra (ARS)",
            "PRECIO_ARS":           "Px Actual (ARS)",
            "Target ARS":           "Target (ARS)",
            "Equiv USD/ud":         "Equiv. USD",
            "Progreso %":           "Progreso %",
            "Señal":                "Señal",
            "VALOR_ARS":            "Valor ARS",
            "INV_ARS":              "Invertido ARS",
            "PNL_ARS":              "P&L ARS ($)",
            "PNL_%":                "P&L % total",
            "PNL_%_USD":            "P&L % USD",
            "PESO_%":               "Peso %",
            "CANTIDAD_TOTAL":       "Cantidad",
            "FUENTE_PRECIO":         "Fuente px",
            "ESCALA_PRECIO_RF":      "Ajuste escala RF",
        }

        # C1 + C5: Tabla con column_config de Streamlit (ProgressColumn, NumberColumn, etc.)
        df_display = df_pos[cols_show].rename(columns=rename_cols).copy()

        _ESTADO_LABELS = {
            "COMPRAR": "🟢 Acumular",
            "ACUMULAR": "🟡 Mantener / sumar",
            "MANTENER": "⚪ Observar",
            "REDUCIR": "🟠 Reducir",
            "SALIR": "🔴 Evaluar salida",
        }
        if "ESTADO" in df_display.columns:
            def _map_estado(x):
                s = str(x).strip().upper()
                for k, v in _ESTADO_LABELS.items():
                    if k in s or s.endswith(k):
                        return v
                return str(x)

            df_display["ESTADO"] = df_display["ESTADO"].map(_map_estado)

        # Asegurar que "Progreso %" es numérico para ProgressColumn
        if "Progreso %" in df_display.columns:
            df_display["Progreso %"] = pd.to_numeric(df_display["Progreso %"], errors="coerce").fillna(0.0)

        # MQ2-V8: toggle agrupación por sector
        _agrupar_sector = st.checkbox("🏭 Agrupar por sector", key="toggle_agrupar_sector", value=False)
        if _agrupar_sector and "TICKER" in df_pos.columns:
            df_pos["SECTOR"] = df_pos["TICKER"].apply(asignar_sector)
            _sector_group = df_display.copy()
            _sector_group["Sector"] = df_pos["TICKER"].apply(asignar_sector).values
            _sector_group = _sector_group.sort_values("Sector")
            df_display = _sector_group

        col_cfg = {
            "TICKER": st.column_config.TextColumn(
                "Ticker", width="small", help="Ticker del activo en cartera"
            ),
            "Cantidad": st.column_config.NumberColumn(
                "Cant.", format="%d", width="small"
            ),
            "Tipo": st.column_config.TextColumn(
                "Tipo", width="small", help="CEDEAR, acción local, bono, etc."
            ),
            "Fuente px": st.column_config.TextColumn(
                "Fuente px",
                width="small",
                help="Trazabilidad por ticker: LIVE / FALLBACK_BD / FALLBACK_HARD / FALLBACK_PPC / MISSING",
            ),
            "Precio de compra (ARS)": st.column_config.NumberColumn(
                "Precio de compra (ARS)",
                format="$ %.0f",
                width="medium",
                help="Precio promedio al que compraste este activo.",
            ),
            "Px Actual (ARS)": st.column_config.NumberColumn(
                "Px Actual (ARS)", format="$%.2f", width="medium",
                help="Cotización actual en pesos en BYMA",
            ),
            "Target (ARS)": st.column_config.NumberColumn(
                "Target (ARS)", format="$%.2f", width="medium",
                help="Precio objetivo en pesos (perfil + mismo % que el motor)",
            ),
            "Equiv. USD": st.column_config.NumberColumn(
                "Equiv. USD", format="%.4f", width="small",
                help="Precio actual ÷ CCL (referencia; el progreso es en ARS)",
            ),
            "Progreso %": st.column_config.ProgressColumn(
                "Progreso al Target",
                help="Camino del precio en pesos: 0% en tu compra, 100% al target (ARS)",
                format="%.0f%%",
                min_value=-100.0,
                max_value=200.0,
                width="medium",
            ),
            "Señal": st.column_config.TextColumn(
                "Señal", width="medium", help="Señal del motor de salida"
            ),
            "Valor ARS": st.column_config.NumberColumn(
                "Valor ARS", format="$%,.0f", width="medium"
            ),
            "Invertido ARS": st.column_config.NumberColumn(
                "Invertido ARS", format="$%,.0f", width="medium"
            ),
            "P&L ARS ($)": st.column_config.NumberColumn(
                "P&L ARS", format="$%,.0f", width="medium"
            ),
            "P&L % total": st.column_config.NumberColumn(
                "P&L % ARS", format="%.1f%%", width="small",
                help="Retorno total en pesos (incluye apreciación del CCL)"
            ),
            "P&L % USD": st.column_config.NumberColumn(
                "P&L % USD", format="%.1f%%", width="small",
                help="Retorno puro en dólares (cancela efecto CCL)"
            ),
            "Peso %": st.column_config.NumberColumn(
                "Peso %", format="%.1f%%", width="small"
            ),
        }
        # Filtrar solo columnas que existen
        col_cfg_final = {k: v for k, v in col_cfg.items() if k in df_display.columns}

        st.dataframe(
            df_display, use_container_width=True,
            hide_index=True,
            column_config=col_cfg_final,
            height=dataframe_auto_height(df_display, min_px=180, max_px=520),
        )

        # ── Plan explicado (Pilar 3) — posiciones que piden atención ────────
        try:
            from services.recomendador_explicable import construir_plan_accion

            _plan_asesor = construir_plan_accion(
                perfil=str(cliente_perfil or "Moderado"),
                senales=senales_full,
                precio_records=ctx.get("precio_records"),
            )
            if _plan_asesor.vender_revisar:
                with st.expander(
                    f"🧭 Plan explicado — {len(_plan_asesor.vender_revisar)} posición(es) piden atención",
                    expanded=False,
                ):
                    from ui.components.plan_accion_view import render_plan_accion

                    render_plan_accion(_plan_asesor, key_prefix="asesor_plan")
        except Exception as _e_plan:
            log_degradacion(__name__, "plan_explicado_asesor_fallo", _e_plan)

        # ── Ficha RF unificada (P2-RF-01) — posición en cartera ────────────
        try:
            from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR
            from core.renta_fija_ar import es_fila_renta_fija_ar, ficha_rf_minima_bundle
            from ui.components.ficha_rf_minima import render_ficha_rf_minima

            _mask_rf = df_pos.apply(
                lambda r: es_fila_renta_fija_ar(r, UNIVERSO_RENTA_FIJA_AR),
                axis=1,
            )
            _df_rf = df_pos[_mask_rf]
            if not _df_rf.empty:
                _tickers_rf = sorted(
                    {str(t).upper().strip() for t in _df_rf["TICKER"].tolist() if str(t).strip()}
                )
                with st.expander("📋 Ficha RF — detalle por posición (P2-RF-01)", expanded=False):
                    st.caption(
                        "Mismos **Px actual**, **Fuente px** y **Ajuste escala RF** que la tabla. "
                        "TIR al precio (ON/BONO USD): paridad % implícita ≈ Px÷CCL o (Px×100)÷CCL si hubo ÷100."
                    )
                    _pick_rf = st.selectbox(
                        "Ticker RF en cartera",
                        _tickers_rf,
                        key="tab_car_ficha_rf_ticker",
                    )
                    _row_rf = _df_rf[
                        _df_rf["TICKER"].astype(str).str.upper().str.strip() == _pick_rf
                    ].iloc[0]
                    _ccl_num = float(ccl or 0) or 0.0
                    _par_impl = _paridad_implicita_pct_on_usd_desde_fila(_row_rf, _ccl_num)
                    _px_raw = _row_rf.get("PRECIO_ARS")
                    _px_ficha: float | None = None
                    if _px_raw is not None and not pd.isna(_px_raw):
                        try:
                            _px_ficha = float(_px_raw)
                        except (TypeError, ValueError):
                            _px_ficha = None
                    _fu_rf = _row_rf.get("FUENTE_PRECIO")
                    _fu_s = str(_fu_rf).strip() if _fu_rf is not None and str(_fu_rf).strip() else None
                    _esc_rf = str(_row_rf.get("ESCALA_PRECIO_RF", "") or "").strip()
                    _aj_rf = bool(_esc_rf)
                    _nota_rf = (
                        "Precio alineado con **÷100 vs PPC** (guardrail RF USD). Ver **Ajuste escala RF**."
                        if _aj_rf
                        else None
                    )
                    _bundle_rf = ficha_rf_minima_bundle(
                        _pick_rf,
                        None,
                        paridad_pct=_par_impl,
                        precio_mercado_ars=_px_ficha,
                        fuente_precio=_fu_s,
                        escala_div100_aplicada=_aj_rf,
                        nota_escala=_nota_rf,
                    )
                    render_ficha_rf_minima(_bundle_rf, key_prefix=f"car_ficha_{_pick_rf}")
        except Exception as exc:
            log_degradacion(__name__, "ficha_rf_cartera_render", exc)

        with st.expander("ℹ️ Leyenda de columnas"):
            st.markdown("""
| Columna | Significado |
|---|---|
| **Tipo** | Clase de activo (CEDEAR, acción local, bono…) |
| **PPC (ARS)** | Precio pagado en pesos, **misma unidad** que la cotización BYMA |
| **Px Actual (ARS)** | Precio de mercado hoy en pesos (BYMA) |
| **Target (ARS)** | Objetivo en pesos (+X% sobre PPC según tu perfil) |
| **Equiv. USD** | Solo referencia (÷ CCL); la barra usa **ARS** |
| **Fuente px** | `LIVE`, `FALLBACK_BD`, `FALLBACK_HARD`, `FALLBACK_PPC` o `MISSING` por ticker |
| **Progreso %** | Cuánto del camino compra → objetivo ya recorriste (en pesos) |
| **Señal** | SALIR (objetivo/stop alcanzado) · REVISAR (señal media) · MANTENER |
| **Invertido ARS** | Total de pesos realmente invertidos (usando CCL histórico del mes de compra) |
| **P&L % total** | Retorno total en pesos — incluye apreciación del CCL |
| **P&L % USD** | Retorno puro en dólares — para comparar con benchmarks globales |
""")

        # ── Gráficos ──────────────────────────────────────────────────────
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_pie = px.pie(df_pos, names="TICKER", values="VALOR_ARS",
                             title="Exposición por Activo", hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_g2:
            df_sector = df_pos.copy()
            df_sector["SECTOR"] = df_sector["TICKER"].apply(asignar_sector)
            df_sec_agg = df_sector.groupby("SECTOR")["VALOR_ARS"].sum().reset_index()
            fig_sec = px.bar(df_sec_agg, x="SECTOR", y="VALOR_ARS",
                             title="Exposición por Sector (ARS)",
                             color="VALOR_ARS", color_continuous_scale="Blues")
            st.plotly_chart(fig_sec, use_container_width=True)

        # ── Retorno real vs inflación (H7) ───────────────────────────────
        try:
            import sys
            from pathlib import Path as _Path
            sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
            from config import INFLACION_MENSUAL_ARG
            pnl_pct_total = float(metricas.get("pnl_pct", 0.0))
            inflacion_periodo = (1 + INFLACION_MENSUAL_ARG) ** 12 - 1
            retorno_real = (1 + pnl_pct_total) / (1 + inflacion_periodo) - 1
            col_inf1, col_inf2, col_inf3 = st.columns(3)
            with col_inf1:
                st.metric("Retorno nominal (ARS)", f"{pnl_pct_total:.1%}",
                          help="P&L total de la cartera en pesos")
            with col_inf2:
                st.metric("Inflación anual estimada", f"{inflacion_periodo:.1%}",
                          help="Inflación mensual configurada en config.py × 12")
            with col_inf3:
                st.metric("Retorno real (ajustado)", f"{retorno_real:.1%}",
                          delta=f"{'▲' if retorno_real > 0 else '▼'} vs inflación",
                          delta_color="normal" if retorno_real >= 0 else "inverse",
                          help="(1 + nominal) / (1 + inflacion) - 1 | Indicador clave para inversores argentinos")
        except Exception as exc:
            log_degradacion(__name__, "retorno_real_calculo_fallo", exc)

        # ── Alertas de concentración avanzadas (H13) ────────────────────────

        # ── Exportar ──────────────────────────────────────────────────────
        _boton_exportar(
            df_pos[cols_show].rename(columns=rename_cols),
            f"posicion_neta_{datetime.now().strftime('%Y%m%d')}",
            "📥 Exportar Posición Neta a Excel",
        )

        # ── Kelly Criterion — Sizing Óptimo (solo perfil profesional) ────
        if str(ctx.get("user_role", "")).lower() != "inversor":
            st.divider()
            st.markdown("### 🎯 Kelly Criterion — Sizing Óptimo por Posición")
            st.caption(
                f"Perfil: **{cliente_perfil}** | "
                f"Fracción Kelly: 25% (conservador) | Capital total: "
                f"${metricas.get('total_valor', 0):,.0f} ARS"
            )
        if str(ctx.get("user_role", "")).lower() != "inversor" and kelly_rows:
            df_kelly = pd.DataFrame(kelly_rows)
            st.dataframe(
                df_kelly, use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(df_kelly, min_px=140, max_px=360),
                column_config={
                    "Prob. éxito":  st.column_config.NumberColumn("Prob. éxito",  format="%.1f%%"),
                    "Target %":     st.column_config.NumberColumn("Target %",     format="+%.1f%%"),
                    "Stop %":       st.column_config.NumberColumn("Stop %",       format="%.1f%%"),
                    "Kelly Compl.": st.column_config.NumberColumn("Kelly Compl.", format="%.1f%%",
                                        help="Kelly completo (teórico)"),
                    "Kelly Aplic.": st.column_config.ProgressColumn(
                                        "Kelly Aplic.", format="%.1f%%",
                                        min_value=0, max_value=25,
                                        help="25% del Kelly completo — fracción conservadora"),
                    "Capital sug.": st.column_config.NumberColumn("Capital sug.", format="$%.0f"),
                },
            )
            with st.expander("ℹ️ ¿Cómo interpretar el Kelly Criterion?"):
                st.markdown(r"""
El **Kelly Criterion** calcula el tamaño óptimo de posición que maximiza el crecimiento del capital a largo plazo.

**Fórmula:** `Kelly = (p × b − q) / b` donde:
- `p` = probabilidad de alcanzar el target (estimada por score + RSI)
- `b` = ratio ganancia/pérdida (target% / stop%)
- `q` = 1 - p (probabilidad de stop)

Se usa el **25% del Kelly completo** para mayor seguridad. Un Kelly > 10% por posición indica una oportunidad de alta convicción.
""")


