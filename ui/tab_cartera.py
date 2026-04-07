"""
ui/tab_cartera.py — Tab 1: Cartera & Libro Mayor
Combina: Posición Neta (P&L + Motor de Salida + Kelly) + Libro Mayor (reemplaza CRM)
"""
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st


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


def render_tab_cartera(ctx: dict) -> None:
    df_ag           = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
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
    _is_viewer      = str(ctx.get("user_role", "admin")).lower() == "viewer"

    sub_pos, sub_rendtipo, sub_historial, sub_multi, sub_lm = st.tabs([
        "📊 Posición actual",
        "📈 Rendimiento",
        "📅 Historial",
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

    with sub_historial:
        _render_historial_timeline(ctx, df_ag, ccl)

    with sub_multi:
        _render_vista_consolidada(ctx, df_ag, df_analisis, engine_data, ccl)

    with sub_lm:
        _render_libro_mayor(
            ctx, df_ag, tickers_cartera, precios_dict, ccl,
            cartera_activa, df_clientes, cs, dbm, lm, bi, gr,
            engine_data, BASE_DIR, _boton_exportar)



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
        st.info("Seleccioná una cartera en el panel lateral.")
    elif df_ag.empty:
        st.info(
            "Todavía no hay activos en esta cartera. "
            "Importá desde tu broker o cargá tus posiciones en **Libro mayor → Importar del broker**."
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
                except Exception:
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
            from core.price_engine import PriceSource
            r = rec_px.get(str(tk).upper().strip())
            if r is None:
                return "—"
            src = getattr(r, "source", None)
            if src in (PriceSource.LIVE_YFINANCE, PriceSource.LIVE_BYMA):
                return "Live"
            if src in (PriceSource.FALLBACK_PPC, PriceSource.FALLBACK_HARD, PriceSource.FALLBACK_BD):
                return "Guardado"
            if src == PriceSource.MISSING:
                return "Sin dato"
            return getattr(src, "label", str(src)) if src else "—"

        df_pos["FUENTE_PRECIO"] = df_pos["TICKER"].astype(str).map(_label_fuente_precio)

        # ── Banner CCL histórico vs actual ────────────────────────────────
        usa_historico = "INV_ARS_HISTORICO" in df_pos.columns and (df_pos.get("INV_ARS_HISTORICO", 0) > 0).any()
        if usa_historico:
            st.success("✅ INV_ARS calculado con CCL histórico real. **P&L %** incluye CCL. **P&L % USD** = retorno puro en dólares.")
        else:
            st.warning("⚠️ INV_ARS calculado con CCL actual (sin fechas de compra). El costo en pesos puede diferir del valor real pagado.")

        cols_show = [
            "TICKER", "TIPO", "CANTIDAD_TOTAL", "PPC_ARS", "PRECIO_ARS", "FUENTE_PRECIO",
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
        )

        with st.expander("ℹ️ Leyenda de columnas"):
            st.markdown("""
| Columna | Significado |
|---|---|
| **Tipo** | Clase de activo (CEDEAR, acción local, bono…) |
| **PPC (ARS)** | Precio pagado en pesos, **misma unidad** que la cotización BYMA |
| **Px Actual (ARS)** | Precio de mercado hoy en pesos (BYMA) |
| **Target (ARS)** | Objetivo en pesos (+X% sobre PPC según tu perfil) |
| **Equiv. USD** | Solo referencia (÷ CCL); la barra usa **ARS** |
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
        except Exception:
            pass

        # ── Alertas de concentración avanzadas (H13) ────────────────────────
        from config import (
            CONCENTRACION_ACTIVO_ALERTA,
            CONCENTRACION_SECTOR_ALERTA,
            SECTORES,
        )
        valor_total_pos = float(df_pos.get("VALOR_ARS", pd.Series(dtype=float)).sum())
        alertas_conc = []

        # 1. Concentración por activo
        pos_sobreweight = df_pos[df_pos["PESO_%"] > CONCENTRACION_ACTIVO_ALERTA]
        if not pos_sobreweight.empty:
            for _, r in pos_sobreweight.iterrows():
                alertas_conc.append(
                    f"🔴 **{r['TICKER']}** ocupa {r['PESO_%']:.0%} del portafolio "
                    f"(límite {CONCENTRACION_ACTIVO_ALERTA:.0%})"
                )

        # 2. Concentración por sector
        df_pos_s = df_pos.copy()
        df_pos_s["SECTOR"] = df_pos_s["TICKER"].apply(lambda t: SECTORES.get(str(t).upper(), "Otros"))
        if valor_total_pos > 0:
            sector_pesos = df_pos_s.groupby("SECTOR")["VALOR_ARS"].sum() / valor_total_pos
            for sector, peso in sector_pesos.items():
                if peso > CONCENTRACION_SECTOR_ALERTA:
                    alertas_conc.append(
                        f"🟠 Sector **{sector}** representa el {peso:.0%} "
                        f"(límite {CONCENTRACION_SECTOR_ALERTA:.0%})"
                    )

        if alertas_conc:
            st.markdown("#### ⚠️ Activos con mucho peso en tu cartera")
            st.caption("Si un solo activo representa demasiado, aumentás el riesgo.")
            for alerta in alertas_conc:
                st.warning(alerta)
        else:
            st.success("✅ Diversificación adecuada — sin alertas de concentración")

        pos_sobreweight = df_pos[df_pos["PESO_%"] > PESO_MAX_CARTERA / 100]
        if not pos_sobreweight.empty:
            st.warning(f"⚠️ Concentración excesiva (>{PESO_MAX_CARTERA}%): "
                       f"{', '.join(pos_sobreweight['TICKER'].tolist())}")

        alertas_venta = m23svc.detectar_alertas_venta(df_analisis, tickers_cartera)
        for alerta in alertas_venta:
            st.warning(
                f"📉 Alerta en **{alerta['ticker']}**: el análisis técnico sugiere revisar "
                f"esta posición. Score actual: {alerta['score']:.0f}/100."
            )
            ab.alerta_senal_venta(alerta["ticker"], alerta["score"], alerta["estado"], prop_nombre)

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


def _render_rendimiento_tipo(ctx, df_ag, cartera_activa, ccl, cs, _boton_exportar):
    """Sub-tab 2: Rendimiento por Tipo de Activo BYMA."""
    st.subheader("Cómo rindió cada parte de la cartera")
    st.caption(
        "Comparativa por tipo de activo: acciones, bonos, fondos, etc.",
    )

    if cartera_activa == "-- Todas las carteras --":
        st.info("Seleccioná una cartera en el panel lateral.")
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
            df_wf = df_rend.sort_values("P&L ARS", ascending=False)
            pnl_total_wf = df_wf["P&L ARS"].sum()
            medidas = ["relative"] * len(df_wf) + ["total"]
            valores_wf = df_wf["P&L ARS"].tolist() + [pnl_total_wf]
            labels_wf  = df_wf["Tipo"].tolist() + ["TOTAL"]

            fig_wf = go.Figure(go.Waterfall(
                orientation="v",
                measure=medidas,
                x=labels_wf,
                y=valores_wf,
                connector={"line": {"color": "#424242"}},
                increasing={"marker": {"color": "#4CAF50"}},
                decreasing={"marker": {"color": "#F44336"}},
                totals={"marker": {"color": "#2196F3"}},
                text=[f"${abs(v):,.0f}" for v in valores_wf],
                textposition="outside",
            ))
            fig_wf.update_layout(
                title="Contribución de cada Clase de Activo al P&L Total (ARS)",
                height=340,
                margin=dict(t=50, b=30, l=20, r=20),
                yaxis_title="ARS",
            )
            st.plotly_chart(fig_wf, use_container_width=True, key="waterfall_pnl")

            # ── Tabla resumen ──────────────────────────────────────────────────
            st.markdown("##### Métricas detalladas por tipo")
            cols_tabla = ["Tipo","Inv. ARS","Valor ARS","P&L ARS",
                          "Rend. ARS %","Rend. USD %","CAGR ARS %","CAGR USD %",
                          "Contribución %","N posiciones"]
            st.dataframe(
                df_rend[cols_tabla].reset_index(drop=True),
                hide_index=True, use_container_width=True,
                column_config={
                    "Tipo":           st.column_config.TextColumn("Tipo"),
                    "Inv. ARS":       st.column_config.NumberColumn("Inv. ARS", format="$%.0f"),
                    "Valor ARS":      st.column_config.NumberColumn("Valor ARS", format="$%.0f"),
                    "P&L ARS":        st.column_config.NumberColumn("P&L ARS", format="$%.0f"),
                    "Rend. ARS %":    st.column_config.NumberColumn("Rend. ARS %", format="+%.1f%%"),
                    "Rend. USD %":    st.column_config.NumberColumn("Rend. USD %", format="+%.1f%%"),
                    "CAGR ARS %":     st.column_config.NumberColumn("CAGR ARS %", format="+%.1f%%",
                                        help="Tasa anual compuesta en ARS desde la primera compra"),
                    "CAGR USD %":     st.column_config.NumberColumn("CAGR USD %", format="+%.1f%%",
                                        help="Tasa anual compuesta en USD"),
                    "Contribución %": st.column_config.ProgressColumn(
                                        "Contribución %", min_value=-100, max_value=100, format="+%.1f%%"
                                      ),
                    "N posiciones":   st.column_config.NumberColumn("Pos.", format="%d"),
                },
            )
            st.caption(
                f"Rendimiento global anual: **{resumen_global['cagr_global_ars']:+.1f}% ARS** | "
                f"**{resumen_global['cagr_global_usd']:+.1f}% USD** | "
                f"Promedio en cartera: **{resumen_global['dias_hold_promedio']} días**"
            )

            _boton_exportar(df_rend, "rendimiento_por_tipo")

            # ── MQ2-D1: TWRR anualizado ───────────────────────────────────
            st.divider()
            st.markdown("##### ⏱ TWRR (Time-Weighted Rate of Return)")
            try:
                _df_trans_twrr = ctx.get("df_trans", pd.DataFrame())
                _hist_twrr = ctx.get("df_historico", pd.DataFrame())
                if not _df_trans_twrr.empty:
                    _twrr = cs.calcular_twrr(_df_trans_twrr, _hist_twrr, ccl)
                    _t1, _t2, _t3 = st.columns(3)
                    _t1.metric("TWRR Anualizado ARS", f"{_twrr.get('twrr_ars_anual', 0):+.2f}%",
                               help="Eliminates capital flow effects — standard CFA metric")
                    _t2.metric("TWRR Anualizado USD", f"{_twrr.get('twrr_usd_anual', 0):+.2f}%")
                    _t3.metric("Sub-períodos", str(_twrr.get("n_periodos", "—")))
            except Exception as _e_twrr:
                st.caption(f"TWRR no disponible: {_e_twrr}")

            # ── MQ2-D2: Máquina de Dividendos ─────────────────────────────
            st.divider()
            st.markdown("##### 💰 Máquina de Dividendos")
            st.caption("Proyección de flujo de ingresos pasivos a 1, 3 y 5 años")
            try:
                _div = cs.calcular_dividendos_proyectados(df_pos_neta if "df_pos_neta" in dir() else df_ag, ccl)
                if _div and _div.get("flujo_anual_usd", 0) > 0:
                    _d1, _d2, _d3 = st.columns(3)
                    _d1.metric("Flujo Mensual USD", f"${_div.get('flujo_mensual_usd', 0):,.0f}")
                    _d2.metric("Flujo Anual USD", f"${_div.get('flujo_anual_usd', 0):,.0f}")
                    _d3.metric("Flujo Anual ARS", f"${_div.get('flujo_anual_ars', 0):,.0f}")
                    if _div.get("detalle"):
                        import plotly.graph_objects as go
                        _df_div = pd.DataFrame(_div["detalle"])
                        _fig_div = go.Figure(go.Bar(
                            x=_df_div.get("ticker", []).tolist() if "ticker" in _df_div.columns else [],
                            y=_df_div.get("div_anual_usd", []).tolist() if "div_anual_usd" in _df_div.columns else [],
                            marker_color="#4CAF50",
                            text=[f"${v:,.0f}" for v in (_df_div.get("div_anual_usd", pd.Series()).tolist())],
                            textposition="outside",
                        ))
                        _fig_div.update_layout(title="Dividendos anuales por activo (USD)",
                                               height=280, margin=dict(t=40,b=20,l=10,r=10))
                        st.plotly_chart(_fig_div, use_container_width=True, key="fig_dividendos")
                    _e1, _e2, _e3 = st.columns(3)
                    _e1.metric("Proyección 1 año", f"${_div.get('flujo_anual_usd', 0):,.0f}")
                    _e2.metric("Proyección 3 años", f"${_div.get('flujo_anual_usd', 0)*3:,.0f}")
                    _e3.metric("Proyección 5 años", f"${_div.get('flujo_anual_usd', 0)*5:,.0f}")
                else:
                    st.info("No se encontraron dividendos proyectados para esta cartera.")
            except Exception as _e_div:
                st.caption(f"Dividendos no disponibles: {_e_div}")


def _render_historial_timeline(ctx, df_ag, ccl):
    """Sub-tab 3: Historial Timeline + Heatmap mensual."""
    from datetime import datetime
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
                        st.dataframe(pd.DataFrame(resumen_rows), use_container_width=True, hide_index=True)
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


def _render_libro_mayor(ctx, df_ag, tickers_cartera, precios_dict, ccl,
                        cartera_activa, df_clientes, cs, dbm, lm, bi, gr,
                        engine_data, BASE_DIR, _boton_exportar):
    """Sub-tab 5: Libro Mayor - Importar | Operaciones | Gmail."""
    _viewer_readonly = str(ctx.get("user_role", "admin")).lower() == "viewer"
    from datetime import datetime
    sub_lm_imp, sub_lm_op, sub_lm_gmail = st.tabs([
        "📥 Importar del broker",
        "📋 Mis operaciones",
        "📧 Importar desde email",
    ])

    ruta_maestra = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
    precios_usd_subs, ratios_cartera = cs.precios_usd_subyacente(
        tickers_cartera, precios_dict, ccl,
        universo_df=engine_data.universo_df,
    ) if tickers_cartera else ({}, {})

    # ── c.1: Importar comprobante broker ─────────────────────────────────
    with sub_lm_imp:
        st.markdown("#### 📥 Importar comprobante de broker (Balanz / Bull Market)")
        col_bi1, col_bi2, col_bi3 = st.columns(3)
        with col_bi1:
            archivo_broker = st.file_uploader(
                "Subí el Excel del broker:", type=["xlsx"], key="uploader_broker"
            )
        with col_bi2:
            # MQ2-A8: propietarios dinámicos desde tabla clientes
            _nombres_cli = sorted(df_clientes["Nombre"].dropna().tolist()) if not df_clientes.empty else []
            _prop_opts = _nombres_cli if _nombres_cli else ["Alfredo y Andrea", "Alfredo", "Santi"]
            prop_broker = st.selectbox(
                "Propietario:", _prop_opts, key="prop_broker"
            )
        with col_bi3:
            _cart_opts_b = sorted({c.split("|")[1].strip() for c in (ctx.get("carteras_csv") or []) if "|" in c}) or ["Retiro", "Reto 2026", "Cartera Agresiva"]
            cart_broker = st.selectbox(
                "Cartera:", _cart_opts_b, key="cart_broker"
            )
        ccl_broker = st.number_input(
            f"CCL del día de las operaciones (actual: ${ccl:,.0f}):",
            min_value=100.0, value=float(ccl), step=10.0, key="ccl_broker"
        )
        if archivo_broker is not None:
            try:
                df_preview = bi.importar_comprobante(
                    archivo_broker, propietario=prop_broker,
                    cartera=cart_broker, ccl=ccl_broker,
                )
                if df_preview.empty:
                    st.warning("No se encontraron operaciones en el archivo.")
                else:
                    st.markdown(f"**Preview — {len(df_preview)} operaciones detectadas:**")
                    st.dataframe(
                        df_preview.style.format({
                            "Precio_ARS": "${:,.2f}", "Neto_ARS": "${:,.2f}", "PPC_USD": "${:.4f}",
                        }).apply(
                            lambda r: ["background-color:#D4EDDA" if v == "COMPRA"
                                       else "background-color:#FADBD8" if v == "VENTA"
                                       else "" for v in r],
                            subset=["Tipo_Op"], axis=0
                        ), use_container_width=True, hide_index=True
                    )
                    if st.button("💾 Aplicar al Libro Mayor", type="primary", key="btn_aplicar_broker",
                                 disabled=_viewer_readonly):
                        bi.aplicar_operaciones_a_maestra(df_preview, ruta_maestra)
                        st.session_state.pop("libro_mayor_data", None)
                        st.success(f"✅ {len(df_preview)} operaciones aplicadas.")
                        st.rerun()
            except Exception as e:
                st.error(f"Error procesando el archivo: {e}")

        st.divider()
        # Vista del libro mayor filtrado por cartera activa
        df_libro = lm.render_libro_mayor(
            ruta_excel=ruta_maestra,
            ratios=ratios_cartera,
            precios_usd=precios_usd_subs,
            ccl=ccl,
            cartera_filtro=cartera_activa,
        )
        if df_libro is not None and not df_libro.empty:
            _nombre_lm = f"libro_mayor_{cartera_activa.replace(' ','_').replace('|','')[:30]}_{datetime.now().strftime('%Y%m%d')}"
            _boton_exportar(df_libro, _nombre_lm, "📥 Exportar Libro Mayor a Excel")

    # ── c.1 alternativo: Tabla editable de operaciones ────────────────────
    with sub_lm_op:
        st.markdown("#### 📋 Libro Mayor de Operaciones")
        st.caption(
            "Planilla de operaciones con columnas exactas para importar/exportar. "
            "Podés editar directamente y guardar cambios. "
            "El precio va **por defecto en pesos (ARS)**; si pagaste en **USD MEP**, elegí esa moneda "
            "(se usa el **CCL** de la barra lateral para convertir)."
        )

        # MQ2-S10: validación de unicidad de cartera al agregar nueva
        with st.expander("➕ Agregar nueva cartera", expanded=False):
            _nc_prop = st.text_input("Propietario:", key="nc_prop_lm")
            _nc_cart = st.text_input("Nombre cartera:", key="nc_cart_lm")
            if st.button("✅ Verificar unicidad", key="btn_verificar_unicidad"):
                _nombre_cartera_nuevo = f"{_nc_prop.strip()} | {_nc_cart.strip()}"
                _trans_all = engine_data.cargar_transaccional()
                if not _trans_all.empty and "CARTERA" in _trans_all.columns:
                    _carteras_existentes = _trans_all["CARTERA"].dropna().str.strip().str.upper().tolist()
                    if _nombre_cartera_nuevo.upper() in _carteras_existentes:
                        st.warning(
                            f"⚠️ **Cartera duplicada** — Ya existe '{_nombre_cartera_nuevo}'. "
                            "Verificá el nombre antes de crear operaciones."
                        )
                    else:
                        st.success(f"✅ '{_nombre_cartera_nuevo}' está disponible.")

        # Cargar operaciones existentes desde CSV/Excel
        _trans = engine_data.cargar_transaccional()
        if not _trans.empty and cartera_activa != "-- Todas las carteras --":
            _trans_filtrado = _trans[_trans["CARTERA"] == cartera_activa].copy()
        else:
            _trans_filtrado = _trans.copy() if not _trans.empty else pd.DataFrame()

        # Normalizar a las columnas exactas del plan
        _cols_op = [
            "Propietario", "Cartera", "Ticker", "Tipo", "Tipo_Instrumento", "Cantidad",
            "Moneda_Precio", "Precio_ARS_Compra", "Fecha", "Gastos_Operacion",
        ]
        if not _trans_filtrado.empty:
            # Mapear columnas del CSV interno a las del libro mayor
            _df_op = pd.DataFrame()
            _cart_raw = _trans_filtrado.get("CARTERA", pd.Series([""] * len(_trans_filtrado))).astype(str)
            _df_op["Propietario"] = _trans_filtrado.get(
                "PROPIETARIO",
                _cart_raw.str.split("|").str[0].str.strip(),
            )
            _df_op["Cartera"] = _cart_raw.apply(
                lambda s: s.split("|", 1)[1].strip() if "|" in s else s.strip()
            )
            _df_op["Ticker"]           = _trans_filtrado.get("TICKER", "")
            _cant_raw = pd.to_numeric(_trans_filtrado["CANTIDAD"], errors="coerce").fillna(0.0)
            _raw_tip = _trans_filtrado.get(
                "TIPO", pd.Series(["CEDEAR"] * len(_trans_filtrado))
            ).astype(str).str.strip().str.upper()
            _tipo_op_list = []
            _tipo_inst_list = []
            for _i in range(len(_trans_filtrado)):
                _t = str(_raw_tip.iloc[_i]).strip().upper()
                _c = float(_cant_raw.iloc[_i])
                if _t in ("COMPRA", "VENTA"):
                    _tipo_op_list.append(_t)
                    _tipo_inst_list.append("CEDEAR")
                else:
                    _tipo_inst_list.append(_t if _t else "CEDEAR")
                    _tipo_op_list.append("COMPRA" if _c > 0 else "VENTA")
            _df_op["Tipo"] = _tipo_op_list
            _df_op["Tipo_Instrumento"] = _tipo_inst_list
            _df_op["Cantidad"] = _cant_raw.abs().astype(int)
            _mp_csv = _trans_filtrado.get(
                "MONEDA_PRECIO",
                pd.Series([""] * len(_trans_filtrado)),
            ).astype(str).str.strip().str.upper()
            _ppc_a = pd.to_numeric(
                _trans_filtrado.get("PPC_ARS", 0), errors="coerce"
            ).fillna(0.0)
            _ppc_u = pd.to_numeric(
                _trans_filtrado.get("PPC_USD", 0), errors="coerce"
            ).fillna(0.0)
            _monedas: list[str] = []
            _precios: list[float] = []
            for _i in range(len(_trans_filtrado)):
                _m = str(_mp_csv.iloc[_i]).strip().upper()
                if _m in ("USD_MEP", "USD MEP", "MEP"):
                    _monedas.append("USD MEP")
                    _precios.append(float(_ppc_u.iloc[_i]))
                else:
                    _monedas.append("ARS")
                    _precios.append(float(_ppc_a.iloc[_i]))
            _df_op["Moneda_Precio"] = _monedas
            _df_op["Precio_ARS_Compra"] = _precios
            # Fecha: convertir a datetime.date para compatibilidad con DateColumn
            _fecha_col = "FECHA_COMPRA" if "FECHA_COMPRA" in _trans_filtrado.columns else "FECHA"
            _df_op["Fecha"] = pd.to_datetime(
                _trans_filtrado.get(_fecha_col, ""), errors="coerce"
            ).dt.date
            _df_op["Gastos_Operacion"] = _trans_filtrado.get("GASTOS", 0.0)
        else:
            _df_op = pd.DataFrame(columns=_cols_op)
            # Asegurar que Fecha sea datetime.date en DataFrame vacío
            _df_op["Fecha"] = pd.Series(dtype="object")

        # Versión en la key del editor: si no cambia, Streamlit puede seguir mostrando
        # el estado viejo del widget tras guardar aunque el CSV ya esté actualizado.
        if "_libro_op_editor_gen" not in st.session_state:
            st.session_state["_libro_op_editor_gen"] = 0
        _editor_lm_key = f"editor_libro_op_{st.session_state['_libro_op_editor_gen']}"

        _df_op_edit = st.data_editor(
            _df_op.reset_index(drop=True),
            num_rows="dynamic", use_container_width=True,
            hide_index=True,
            key=_editor_lm_key,
            column_config={
                "Propietario":       st.column_config.TextColumn("Propietario", width="medium"),
                "Cartera":           st.column_config.TextColumn("Cartera", width="medium"),
                "Ticker":            st.column_config.TextColumn("Ticker", width="small"),
                "Tipo":              st.column_config.SelectboxColumn("Tipo",
                                        options=["COMPRA","VENTA"], width="small"),
                "Tipo_Instrumento":  st.column_config.SelectboxColumn("Tipo Instrumento",
                                        options=[
                                            "CEDEAR","ACCION_LOCAL","BONO","LETRA",
                                            "FCI","ON","ON_USD","BONO_USD","OTRO"
                                        ], width="medium"),
                "Cantidad":          st.column_config.NumberColumn("Cantidad",
                                        min_value=1, step=1, width="small"),
                "Moneda_Precio":     st.column_config.SelectboxColumn(
                                        "Moneda precio",
                                        options=["ARS", "USD MEP"],
                                        width="small",
                                        help="ARS = pesos por cuotaparte (BYMA). USD MEP = dólares contado con liqui.",
                                    ),
                "Precio_ARS_Compra": st.column_config.NumberColumn(
                                        "Precio unitario",
                                        format="$%.2f", min_value=0.0,
                                        help="En ARS o en USD MEP según la columna Moneda.",
                                    ),
                "Fecha":             st.column_config.DateColumn("Fecha",
                                        format="YYYY-MM-DD", width="medium"),
                "Gastos_Operacion":  st.column_config.NumberColumn("Gastos Operación",
                                        format="$%.2f", min_value=0.0),
            },
        )

        # MQ2-S5: sanitizar inputs del Libro Mayor antes de guardar
        import re as _re_lm
        def _sanitizar_campo(valor: str) -> str:
            return _re_lm.sub(r"[^A-Z0-9\s|\-\._/]", "", str(valor).upper().strip())

        col_exp1, col_exp2, col_exp3 = st.columns(3)
        with col_exp1:
            _boton_exportar(
                _df_op_edit,
                f"operaciones_{cartera_activa.replace(' ','_')[:20]}_{datetime.now().strftime('%Y%m%d')}",
                "📥 Exportar operaciones a Excel",
            )
        with col_exp2:
            st.caption("💡 Formato compatible con importación directa al sistema")
        with col_exp3:
            if st.button("🧹 Sanitizar & Guardar", key="btn_sanitizar_lm", disabled=_viewer_readonly):
                # Sanitizar y persistir en Maestra_Transaccional.csv (antes solo se mostraba éxito).
                _df_sanitizado = _df_op_edit.copy()
                for _col_s in ["Ticker", "Propietario", "Cartera"]:
                    if _col_s in _df_sanitizado.columns:
                        _df_sanitizado[_col_s] = _df_sanitizado[_col_s].apply(
                            lambda v: _sanitizar_campo(str(v)) if pd.notna(v) else ""
                        )
                if "Ticker" in _df_sanitizado.columns:
                    _df_sanitizado = _df_sanitizado[
                        _df_sanitizado["Ticker"].astype(str).str.len() > 0
                    ].copy()
                if str(cartera_activa).strip().endswith("| (sin datos)"):
                    st.error("Seleccioná una cartera válida en la barra lateral (no “(sin datos)”).")
                elif _df_sanitizado.empty:
                    st.warning("No hay filas con Ticker válido para guardar.")
                else:
                    _ccl_lm = float(ccl) if ccl else 0.0
                    if _ccl_lm <= 0:
                        st.error("El CCL no es válido: no se puede derivar PPC_USD desde el precio en ARS.")
                    else:
                        _rows_lm = []
                        for _, _r in _df_sanitizado.iterrows():
                            _tick = str(_r.get("Ticker", "")).strip().upper()
                            if not _tick:
                                continue
                            _prop = str(_r.get("Propietario", "")).strip()
                            _cart = str(_r.get("Cartera", "")).strip()
                            _cartera_full = (
                                _cart if "|" in _cart else f"{_prop} | {_cart}".strip()
                            ).strip()
                            if not _cartera_full or _cartera_full == "|":
                                continue
                            _tipo_op = str(_r.get("Tipo", "COMPRA")).strip().upper()
                            _q = int(
                                pd.to_numeric(_r.get("Cantidad", 0), errors="coerce") or 0
                            )
                            if _q == 0:
                                continue
                            _q = -abs(_q) if _tipo_op == "VENTA" else abs(_q)
                            _px_raw = float(
                                pd.to_numeric(
                                    _r.get("Precio_ARS_Compra", 0), errors="coerce"
                                )
                                or 0.0
                            )
                            _moneda_r = str(_r.get("Moneda_Precio", "ARS") or "ARS").strip().upper()
                            _es_mep = _moneda_r in ("USD MEP", "USD_MEP", "MEP")
                            if _px_raw <= 0:
                                st.warning(
                                    f"{_tick}: precio unitario debe ser > 0 — fila omitida."
                                )
                                continue
                            if _es_mep:
                                _ppc_usd = round(_px_raw, 6)
                                _ppc_ars = round(_ppc_usd * _ccl_lm, 4)
                            else:
                                _ppc_ars = round(_px_raw, 4)
                                _ppc_usd = round(_ppc_ars / _ccl_lm, 6)
                            _fecha_v = _r.get("Fecha")
                            if pd.isna(_fecha_v):
                                st.warning(f"{_tick}: fecha inválida — fila omitida.")
                                continue
                            _fecha_out = (
                                _fecha_v
                                if hasattr(_fecha_v, "strftime")
                                else pd.to_datetime(_fecha_v).date()
                            )
                            _ti = (
                                str(_r.get("Tipo_Instrumento", "CEDEAR")).strip().upper()
                                or "CEDEAR"
                            )
                            if _ti in ("COMPRA", "VENTA"):
                                _ti = "CEDEAR"
                            _g = float(
                                pd.to_numeric(
                                    _r.get("Gastos_Operacion", 0), errors="coerce"
                                )
                                or 0.0
                            )
                            _rows_lm.append({
                                "CARTERA": _cartera_full,
                                "FECHA_COMPRA": _fecha_out,
                                "TICKER": _tick,
                                "CANTIDAD": _q,
                                "PPC_USD": _ppc_usd,
                                "PPC_ARS": round(_ppc_ars, 4),
                                "TIPO": _ti,
                                "GASTOS": _g,
                                "MONEDA_PRECIO": "USD_MEP" if _es_mep else "ARS",
                            })
                        if not _rows_lm:
                            st.error("No quedaron filas válidas para persistir.")
                        else:
                            _df_new = pd.DataFrame(_rows_lm)
                            try:
                                _all_t = engine_data.cargar_transaccional().copy()
                            except Exception as _e_ld:
                                st.error(f"No se pudo leer el transaccional: {_e_ld}")
                                _all_t = pd.DataFrame()
                            _es_todas = cartera_activa == "-- Todas las carteras --"
                            if _es_todas:
                                _kept = (
                                    _all_t.iloc[0:0].copy()
                                    if not _all_t.empty
                                    else pd.DataFrame(columns=_df_new.columns)
                                )
                            else:
                                if _all_t.empty or "CARTERA" not in _all_t.columns:
                                    _kept = pd.DataFrame(columns=_df_new.columns)
                                else:
                                    _kept = _all_t[
                                        _all_t["CARTERA"] != cartera_activa
                                    ].copy()
                            _cols_lm = (
                                list(_all_t.columns)
                                if not _all_t.empty
                                else list(_df_new.columns)
                            )
                            for _c in _df_new.columns:
                                if _c not in _cols_lm:
                                    _cols_lm.append(_c)
                            _kept = _kept.reindex(columns=_cols_lm)
                            _df_new = _df_new.reindex(columns=_cols_lm)
                            _out_lm = pd.concat([_kept, _df_new], ignore_index=True)
                            try:
                                engine_data.guardar_transaccional(_out_lm)
                                st.session_state.pop("libro_mayor_data", None)
                                _old_ed = (
                                    f"editor_libro_op_"
                                    f"{st.session_state.get('_libro_op_editor_gen', 0)}"
                                )
                                st.session_state["_libro_op_editor_gen"] = (
                                    st.session_state.get("_libro_op_editor_gen", 0) + 1
                                )
                                st.session_state.pop(_old_ed, None)
                                st.success(
                                    f"✅ {len(_df_new)} operaciones guardadas en "
                                    f"Maestra_Transaccional.csv "
                                    f"({'reemplazo total' if _es_todas else cartera_activa})."
                                )
                                st.rerun()
                            except Exception as _e_g:
                                st.error(
                                    "No se pudo escribir Maestra_Transaccional.csv "
                                    f"(en Railway el disco del contenedor puede ser efímero): {_e_g}"
                                )

    # ── c.2: Gmail ────────────────────────────────────────────────────────
    with sub_lm_gmail:
        st.markdown("### 📧 Lector automático de correos de brokers")
        st.info("Lee correos de Balanz y Bull Market desde tu Gmail y genera el historial de operaciones.")

        col_gm1, col_gm2 = st.columns(2)
        with col_gm1:
            st.markdown("**Balanz** → boletos@balanz.com")
            # MQ2-A8: propietarios dinámicos
            _prop_opts2 = sorted(df_clientes["Nombre"].dropna().tolist()) if not df_clientes.empty else ["Alfredo y Andrea","Alfredo","Santi"]
            _cart_opts2 = sorted({c.split("|")[1].strip() for c in (ctx.get("carteras_csv") or []) if "|" in c}) or ["Retiro","Reto 2026","Cartera Agresiva"]
            prop_balanz = st.selectbox("Propietario Balanz:", _prop_opts2, key="prop_balanz")
            cart_balanz = st.selectbox("Cartera Balanz:", _cart_opts2, key="cart_balanz")
        with col_gm2:
            st.markdown("**Bull Market** → accountactivity@bullmarketbrokers.com")
            prop_bull = st.selectbox("Propietario Bull Market:", _prop_opts2, key="prop_bull")
            cart_bull = st.selectbox("Cartera Bull Market:", _cart_opts2, key="cart_bull")

        if "gmail_mensajes_balanz" not in st.session_state:
            st.session_state["gmail_mensajes_balanz"] = []
        if "gmail_mensajes_bull" not in st.session_state:
            st.session_state["gmail_mensajes_bull"] = []

        st.divider()
        st.markdown("#### 📋 Pegá el cuerpo de un correo manualmente")
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            texto_balanz = st.text_area("Texto correo Balanz:", height=120,
                                         placeholder="Pegá el cuerpo del email de Balanz aquí...",
                                         key="texto_balanz_manual")
            if st.button("➕ Agregar correo Balanz", key="btn_add_balanz", disabled=_viewer_readonly):
                if texto_balanz.strip():
                    st.session_state["gmail_mensajes_balanz"].append({"body": texto_balanz, "fecha": ""})
                    st.success(f"✅ Agregado. Total Balanz: {len(st.session_state['gmail_mensajes_balanz'])}")
        with col_p2:
            texto_bull = st.text_area("Texto correo Bull Market:", height=120,
                                       placeholder="Pegá el cuerpo del email de Bull Market aquí...",
                                       key="texto_bull_manual")
            if st.button("➕ Agregar correo Bull Market", key="btn_add_bull", disabled=_viewer_readonly):
                if texto_bull.strip():
                    st.session_state["gmail_mensajes_bull"].append({"body": texto_bull, "fecha": ""})
                    st.success(f"✅ Agregado. Total Bull Market: {len(st.session_state['gmail_mensajes_bull'])}")

        st.caption(
            f"Correos en cola: Balanz={len(st.session_state['gmail_mensajes_balanz'])} | "
            f"Bull Market={len(st.session_state['gmail_mensajes_bull'])}"
        )

        # ── CORRECCIÓN BUG: botón guardar no puede estar anidado en el botón procesar ──
        # Solución: guardar df_hist en session_state al procesar,
        # y mostrar el botón guardar FUERA del bloque if-botón-procesar.

        if st.button("⚡ Procesar todos los correos en cola", type="primary", key="btn_procesar_gmail",
                     disabled=_viewer_readonly):
            total_msgs = (len(st.session_state["gmail_mensajes_balanz"]) +
                          len(st.session_state["gmail_mensajes_bull"]))
            if total_msgs == 0:
                st.warning("No hay correos en cola. Agregá correos arriba.")
            else:
                with st.spinner(f"Procesando {total_msgs} correos..."):
                    _df_hist_proc = gr.leer_todos_los_correos(
                        st.session_state["gmail_mensajes_balanz"],
                        st.session_state["gmail_mensajes_bull"],
                    )
                if _df_hist_proc.empty:
                    st.error("No se encontraron operaciones en los correos.")
                    st.session_state.pop("gmail_df_hist", None)
                else:
                    # Persistir en session_state para que el botón guardar lo use
                    st.session_state["gmail_df_hist"] = _df_hist_proc
                    ruta_hist = BASE_DIR / "0_Data_Maestra" / "Historial_Operaciones_Gmail.xlsx"
                    gr.exportar_a_excel(_df_hist_proc, ruta_hist)
                    st.success(f"✅ {len(_df_hist_proc)} operaciones extraídas. Revisá abajo y guardá.")

        # Mostrar resultado y botón guardar FUERA del bloque del botón procesar
        if "gmail_df_hist" in st.session_state:
            _df_hist_cached = st.session_state["gmail_df_hist"]
            st.dataframe(_df_hist_cached, use_container_width=True, hide_index=True)
            st.info(f"📋 {len(_df_hist_cached)} operaciones listas para aplicar al Libro Mayor.")

            if st.button("💾 Aplicar al Libro Mayor y guardar", type="primary", key="btn_guardar_gmail",
                         disabled=_viewer_readonly):
                prop_map = {
                    "Balanz":      {"propietario": prop_balanz, "cartera": cart_balanz},
                    "Bull Market": {"propietario": prop_bull,   "cartera": cart_bull},
                }
                df_maestra = gr.construir_maestra_desde_historial(_df_hist_cached, prop_map)
                ruta_m = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
                df_maestra.to_excel(ruta_m, index=False)
                st.session_state.pop("libro_mayor_data", None)
                st.session_state.pop("gmail_df_hist", None)   # limpiar cola tras guardar
                st.session_state["gmail_mensajes_balanz"] = []
                st.session_state["gmail_mensajes_bull"]   = []
                st.success(f"✅ {len(df_maestra)} filas guardadas en el Libro Mayor.")
                st.rerun()

            if st.button("🗑️ Descartar resultados", key="btn_descartar_gmail"):
                st.session_state.pop("gmail_df_hist", None)
                st.rerun()
