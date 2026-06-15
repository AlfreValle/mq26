"""
ui/tab_cartera.py — Tab 1: Cartera & Libro Mayor
Combina: Posición Neta (P&L + Motor de Salida + Kelly) + Libro Mayor (reemplaza CRM)
"""
from datetime import date, datetime
import html

import pandas as pd
import plotly.express as px
import streamlit as st

from core.structured_logging import log_degradacion
from ui.mq26_ux import dataframe_auto_height
from ui.posiciones_broker_table import build_posiciones_broker_html
from ui.rbac import can_action as _can_action_rbac


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


def _render_resumen_cliente_cartera(ctx: dict, df_ag: pd.DataFrame) -> None:
    """
    Resumen compacto al inicio de Cartera (admin/estudio/super_admin): semáforo, score, patrimonio.
    Inversor: ya lo ve en su suite; acá se omite.
    """
    if str(ctx.get("user_role", "")).lower() == "inversor":
        return
    if df_ag is None or df_ag.empty:
        return

    from services.diagnostico_cartera import diagnosticar

    diag = ctx.get("ultimo_diagnostico")
    nombre = str(ctx.get("cliente_nombre", "") or "").split("|")[0].strip()
    if not nombre:
        nombre = "Cliente"
    ccl = float(ctx.get("ccl") or 1150.0)
    perfil = str(ctx.get("cliente_perfil", "Moderado"))

    if diag is None:
        try:
            diag = diagnosticar(
                df_ag=df_ag,
                perfil=perfil,
                horizonte_label=str(ctx.get("cliente_horizonte_label") or ctx.get("horizonte_label") or "1 año"),
                metricas=dict(ctx.get("metricas") or {}),
                ccl=ccl,
                universo_df=ctx.get("universo_df"),
                senales_salida=None,
                cliente_nombre=str(ctx.get("cliente_nombre", "") or ""),
            )
        except Exception as exc:
            log_degradacion(
                __name__,
                "resumen_cliente_diagnostico_fallo",
                exc,
                cliente=str(ctx.get("cliente_nombre", "")),
            )
            return

    sem_v = str(getattr(getattr(diag, "semaforo", None), "value", "neutro") or "neutro")
    score = float(getattr(diag, "score_total", 0) or 0)
    sem_color = {"verde": "#10b981", "amarillo": "#f59e0b", "rojo": "#ef4444"}.get(sem_v, "#64748b")
    sem_emoji = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(sem_v, "⚪")

    valor_ars = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()) if "VALOR_ARS" in df_ag.columns else 0.0
    valor_usd = valor_ars / max(ccl, 1.0)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)
    pnl = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0)
    pnl_color = "var(--c-green)" if pnl >= 0 else "var(--c-red)"

    obs_list = getattr(diag, "observaciones", []) or []
    obs_txt = ""
    if obs_list:
        o = obs_list[0]
        obs_txt = html.escape(
            f"{getattr(o, 'icono', '')} {getattr(o, 'titulo', '')}".strip()[:55]
        )

    nom_esc = html.escape(nombre)
    perf_esc = html.escape(perfil)
    st.markdown(
        f"""
    <div class="mq-cartera-resumen" style="border-left-color:{sem_color};">
        <div class="mq-cartera-resumen-left">
            <span class="mq-cartera-resumen-emoji">{sem_emoji}</span>
            <div>
                <div class="mq-cartera-resumen-title mq-font-title">{nom_esc}</div>
                <div class="mq-cartera-resumen-sub mq-font-body">
                    {perf_esc} · Score {score:.0f}/100 · {obs_txt}
                </div>
            </div>
        </div>
        <div class="mq-cartera-resumen-right">
            <div class="mq-cartera-resumen-kpi">
                <div class="mq-cartera-resumen-kpi-label">Patrimonio</div>
                <div class="mq-cartera-resumen-kpi-value">
                    USD {valor_usd:,.0f}
                </div>
            </div>
            <div class="mq-cartera-resumen-kpi">
                <div class="mq-cartera-resumen-kpi-label">Resultado ref.</div>
                <div class="mq-cartera-resumen-kpi-value" style="color:{pnl_color};">
                    {'+' if pnl >= 0 else ''}{pnl:.1f}%
                </div>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_tab_cartera(ctx: dict) -> None:
    df_ag           = ctx.get("df_ag")
    if df_ag is None:
        df_ag = pd.DataFrame()
    if df_ag is not None and not df_ag.empty:
        _render_resumen_cliente_cartera(ctx, df_ag)
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
    _can_write      = _can_action_rbac(ctx, "write")
    _is_viewer      = not _can_write

    _is_inversor = str(ctx.get("user_role", "admin")).lower() == "inversor"

    if _is_inversor:
        sub_pos, sub_rendtipo, sub_lm = st.tabs([
            "📊 Posición actual",
            "📈 Rendimiento",
            "📋 Libro mayor",
        ])
        sub_multi = None
    else:
        sub_pos, sub_rendtipo, sub_multi, sub_lm = st.tabs([
            "📊 Posición actual",
            "📈 Rendimiento",
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

    if sub_multi is not None:
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
        st.info(
            "Elegí una **cartera concreta** en el sidebar: **📁 Cartera activa** "
            "(debajo del cliente). La opción «-- Todas las carteras --» no carga posiciones en esta vista."
        )
    elif df_ag.empty:
        st.info(
            "Todavía no hay activos en esta cartera.\n\n"
            "1. Si estás en modo **admin/estudio**, revisá que el cliente y la **cartera activa** "
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
                return "LIVE"
            if src == PriceSource.FALLBACK_BD:
                return "FALLBACK_BD"
            if src == PriceSource.FALLBACK_HARD:
                return "FALLBACK_HARD"
            if src == PriceSource.FALLBACK_PPC:
                return "FALLBACK_PPC"
            if src == PriceSource.MISSING:
                return "MISSING"
            return getattr(src, "label", str(src)) if src else "—"

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


def _render_rendimiento_tipo(ctx, df_ag, cartera_activa, ccl, cs, _boton_exportar):
    """Sub-tab 2: Rendimiento por Tipo de Activo BYMA."""
    st.subheader("Cómo rindió cada parte de la cartera")
    st.caption(
        "Comparativa por tipo de activo: acciones, bonos, fondos, etc.",
    )

    if cartera_activa == "-- Todas las carteras --":
        st.info(
            "Elegí una **cartera concreta** en el sidebar: **📁 Cartera activa** "
            "(debajo del cliente). La opción «-- Todas las carteras --» no carga posiciones en esta vista."
        )
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
            # Mapeo interno → etiqueta legible
            _LABEL_TIPO = {
                "CEDEAR":       "CEDEARs",
                "ACCION_LOCAL": "Acciones Arg.",
                "BONO":         "Bonos ARS",
                "BONO_USD":     "Bonos USD",
                "LETRA":        "Letras",
                "ON":           "Oblig. Neg.",
                "ON_USD":       "Oblig. Neg. USD",
                "FCI":          "Fondos (FCI)",
            }
            # Agrupación Renta Fija / Variable
            _RF = {"BONO", "BONO_USD", "LETRA", "ON", "ON_USD"}
            _RV = {"CEDEAR", "ACCION_LOCAL", "FCI"}

            _wf_col1, _wf_col2, _wf_col3 = st.columns([2, 2, 2])
            with _wf_col1:
                _wf_moneda = st.radio(
                    "Moneda del gráfico", ["ARS", "USD"],
                    horizontal=True, key="wf_moneda"
                )
            with _wf_col2:
                _wf_grupo = st.radio(
                    "Agrupación", ["Por tipo", "Renta Fija / Variable"],
                    horizontal=True, key="wf_grupo"
                )

            _pnl_col = "P&L ARS" if _wf_moneda == "ARS" else "P&L USD aprox"
            _moneda_sym = "$" if _wf_moneda == "ARS" else "U$S"

            _df_wf_base = df_rend.copy()

            if _wf_grupo == "Renta Fija / Variable":
                _df_wf_base["_GRUPO"] = _df_wf_base["Tipo"].apply(
                    lambda t: "Renta Fija" if t in _RF else "Renta Variable"
                )
                _df_wf_base = (
                    _df_wf_base.groupby("_GRUPO", as_index=False)
                    .agg({_pnl_col: "sum"})
                    .rename(columns={"_GRUPO": "Tipo"})
                )
            else:
                _df_wf_base["Tipo"] = _df_wf_base["Tipo"].map(
                    lambda t: _LABEL_TIPO.get(t, t)
                )
                _df_wf_base = _df_wf_base[["Tipo", _pnl_col]]

            _df_wf_base = _df_wf_base.sort_values(_pnl_col, ascending=False)
            _pnl_total = _df_wf_base[_pnl_col].sum()
            _medidas_wf = ["relative"] * len(_df_wf_base) + ["total"]
            _valores_wf = _df_wf_base[_pnl_col].tolist() + [_pnl_total]
            _labels_wf  = _df_wf_base["Tipo"].tolist() + ["TOTAL"]

            fig_wf = go.Figure(go.Waterfall(
                orientation="v",
                measure=_medidas_wf,
                x=_labels_wf,
                y=_valores_wf,
                connector={"line": {"color": "#424242"}},
                increasing={"marker": {"color": "#4CAF50"}},
                decreasing={"marker": {"color": "#F44336"}},
                totals={"marker": {"color": "#2196F3"}},
                text=[f"{_moneda_sym}{abs(v):,.0f}" for v in _valores_wf],
                textposition="outside",
            ))
            fig_wf.update_layout(
                title=f"Contribución al P&L Total ({_wf_moneda})",
                height=380,
                margin=dict(t=50, b=30, l=20, r=20),
                yaxis_title=_wf_moneda,
            )
            st.plotly_chart(fig_wf, use_container_width=True, key="waterfall_pnl")



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
                        _df_res_rows = pd.DataFrame(resumen_rows)
                        st.dataframe(
                            _df_res_rows,
                            use_container_width=True,
                            hide_index=True,
                            height=dataframe_auto_height(_df_res_rows, min_px=120, max_px=280),
                        )
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
    _viewer_readonly = not _can_action_rbac(ctx, "write")
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
                                from core.cache_manager import (
                                    invalidar_cache_tras_cambio_transaccional,
                                )

                                invalidar_cache_tras_cambio_transaccional()
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
            # Compactar si hay pocos registros y limitar crecimiento en históricos largos.
            st.dataframe(
                _df_hist_cached,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(_df_hist_cached, min_px=140, max_px=420),
            )
            st.info(f"📋 {len(_df_hist_cached)} operaciones listas para aplicar al Libro Mayor.")

            if st.button("💾 Aplicar al Libro Mayor y guardar", type="primary", key="btn_guardar_gmail",
                         disabled=_viewer_readonly):
                prop_map = {
                    "Balanz":      {"propietario": prop_balanz, "cartera": cart_balanz},
                    "Bull Market": {"propietario": prop_bull,   "cartera": cart_bull},
                }
                df_maestra = gr.construir_maestra_desde_historial(_df_hist_cached, prop_map)
                # Persistencia segura: merge al transaccional (no sobrescribir libro completo).
                df_new = pd.DataFrame({
                    "CARTERA": df_maestra["Propietario"].astype(str).str.strip() + " | " + df_maestra["Cartera"].astype(str).str.strip(),
                    "FECHA_COMPRA": pd.to_datetime(df_maestra["FECHA_INICIAL"], errors="coerce").dt.date,
                    "TICKER": df_maestra["Ticker"].astype(str).str.strip().str.upper(),
                    "CANTIDAD": pd.to_numeric(df_maestra["Cantidad"], errors="coerce").fillna(0.0),
                    "PPC_USD": pd.to_numeric(df_maestra["PPC_USD"], errors="coerce").fillna(0.0),
                    "PPC_ARS": 0.0,
                    "TIPO": df_maestra["Tipo"].astype(str).str.strip().str.upper(),
                    "LAMINA_VN": float("nan"),
                    "MONEDA_PRECIO": "USD_MEP",
                })
                df_new = df_new[df_new["CANTIDAD"] != 0].copy()
                df_new = df_new.dropna(subset=["FECHA_COMPRA"])
                from core.import_fingerprint import merge_idempotent
                df_all = engine_data.cargar_transaccional()
                df_merge, n_insertadas, n_duplicadas = merge_idempotent(df_all, df_new)
                engine_data.guardar_transaccional(df_merge)
                st.session_state.pop("libro_mayor_data", None)
                st.session_state.pop("gmail_df_hist", None)   # limpiar cola tras guardar
                st.session_state["gmail_mensajes_balanz"] = []
                st.session_state["gmail_mensajes_bull"]   = []
                st.success(
                    f"✅ {n_insertadas} operaciones nuevas agregadas."
                    + (f" ({n_duplicadas} duplicadas omitidas por idempotencia)." if n_duplicadas else "")
                )
                st.rerun()

            if st.button("🗑️ Descartar resultados", key="btn_descartar_gmail"):
                st.session_state.pop("gmail_df_hist", None)
                st.rerun()
