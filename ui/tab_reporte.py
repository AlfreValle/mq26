"""
ui/tab_reporte.py — Tab 6: Reporte (Client Reporting)
Informe HTML profesional con objetivos del cliente, recomendaciones condicionales
(qué comprar / qué vender según la acción ejecutada) y gestión de objetivos vencidos.
"""
from datetime import datetime

import pandas as pd
import streamlit as st
from core.auth import has_feature


def render_tab_reporte(ctx: dict) -> None:
    df_ag            = ctx["df_ag"]
    metricas         = ctx.get("metricas", {})
    ccl              = ctx["ccl"]
    prop_nombre      = ctx["prop_nombre"]
    tickers_cartera  = ctx["tickers_cartera"]
    horizonte_dias   = ctx["horizonte_dias"]
    RISK_FREE_RATE   = ctx["RISK_FREE_RATE"]
    engine_data      = ctx["engine_data"]
    ejsvc            = ctx["ejsvc"]
    rpt              = ctx["rpt"]
    cached_historico = ctx["cached_historico"]
    dbm              = ctx["dbm"]
    cliente_id       = ctx.get("cliente_id")
    cliente_nombre   = ctx.get("cliente_nombre", prop_nombre)
    horizonte_label  = ctx.get("horizonte_label", "1 año")
    cliente_perfil   = ctx.get("cliente_perfil", "Moderado")

    # ── MODO PRESENTACIÓN (H12) ───────────────────────────────────────────────
    modo_pres = st.session_state.get("modo_presentacion", False)
    col_hdr1, col_hdr2 = st.columns([4, 1])
    with col_hdr1:
        st.subheader("📄 Reporte Profesional para el Cliente")
    with col_hdr2:
        if st.button("🎭 Modo Presentación" if not modo_pres else "✕ Cerrar Presentación",
                     key="btn_modo_pres", use_container_width=True):
            st.session_state["modo_presentacion"] = not modo_pres
            st.rerun()

    if modo_pres:
        # Modo presentación: solo datos relevantes para el cliente
        st.markdown("""
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        </style>
        """, unsafe_allow_html=True)
        st.markdown(f"## 📊 Cartera — {prop_nombre}")
        st.markdown(f"*{horizonte_label}  |  Perfil: {cliente_perfil}*")
        if not df_ag.empty:
            cols_pres = ["TICKER","CANTIDAD_TOTAL","VALOR_ARS","PNL_%_USD"]
            cols_pres = [c for c in cols_pres if c in df_ag.columns]
            rename_pres = {"TICKER": "Activo","CANTIDAD_TOTAL": "Cantidad",
                           "VALOR_ARS": "Valor ARS","PNL_%_USD": "P&L %"}
            st.dataframe(
                df_ag[cols_pres].rename(columns=rename_pres)
                .style.format({"Valor ARS": "${:,.0f}", "P&L %": "{:.1%}"}), use_container_width=True, hide_index=True,
            )
        st.stop()

    st.info(
        "Genera un informe HTML descargable con la situación actual de la cartera, "
        "objetivos de inversión, diagnóstico de riesgo, resultados cuantitativos y plan de acción. "
        "Usá **Ctrl+P → Guardar como PDF** para imprimir."
    )

    # ── SECCIÓN: OBJETIVOS DEL CLIENTE ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎯 Objetivos de Inversión del Cliente")

    df_obj = pd.DataFrame()
    if cliente_id:
        df_obj = dbm.obtener_objetivos_cliente(cliente_id)

    if df_obj.empty:
        st.info("No hay objetivos registrados para este cliente. "
                "Podés crear uno en la **Tab 5 → Rebalanceo / Capital**.")
    else:
        # Resumen de objetivos
        n_activos    = (df_obj["Estado"] == "ACTIVO").sum()
        n_vencidos   = (df_obj["Estado"] == "VENCIDO").sum()
        n_completados = (df_obj["Estado"] == "COMPLETADO").sum()
        total_ars     = df_obj[df_obj["Estado"] == "ACTIVO"]["Monto ARS"].sum()

        oc1, oc2, oc3, oc4 = st.columns(4)
        oc1.metric("Objetivos activos", n_activos)
        oc2.metric("Vencidos", n_vencidos)
        oc3.metric("Completados", n_completados)
        oc4.metric("Capital total activo", f"${total_ars:,.0f} ARS")

        def _color_est(val):
            if val == "ACTIVO":     return "background-color:#D4EDDA"
            if val == "VENCIDO":    return "background-color:#FADBD8"
            if val == "COMPLETADO": return "background-color:#D1ECF1"
            return ""

        st.dataframe(
            df_obj.style
            .format({"Monto ARS": "${:,.0f}"}, na_rep="—")
            .map(_color_est, subset=["Estado"]), use_container_width=True, hide_index=True,
        )

        # Acciones sobre objetivos
        col_obj_act1, col_obj_act2 = st.columns(2)
        with col_obj_act1:
            obj_ids = df_obj[df_obj["Estado"].isin(["ACTIVO","VENCIDO"])]["ID"].tolist()
            if obj_ids:
                sel_obj = st.selectbox(
                    "Seleccioná un objetivo para marcar como completado:",
                    obj_ids,
                    format_func=lambda oid: f"#{oid} — {df_obj[df_obj['ID']==oid]['Motivo'].iloc[0][:40]}",
                    key="rpt_sel_objetivo",
                )
                if st.button("✅ Marcar como completado", key="btn_rpt_completar"):
                    dbm.marcar_objetivo_completado(int(sel_obj))
                    st.success(f"✅ Objetivo #{sel_obj} marcado como completado.")
                    st.rerun()

        with col_obj_act2:
            obj_venc = df_obj[df_obj["Estado"] == "VENCIDO"]
            if not obj_venc.empty:
                st.warning(f"⚠️ {len(obj_venc)} objetivo(s) vencidos requieren acción.")
                for _, ov in obj_venc.iterrows():
                    with st.expander(f"Editar objetivo vencido #{ov['ID']} — {ov['Motivo'][:40]}"):
                        with st.form(f"form_rpt_editar_{ov['ID']}", clear_on_submit=True):
                            nuevo_plazo_r = st.selectbox(
                                "Nuevo horizonte:",
                                ["1 mes","3 meses","6 meses","1 año","3 años","+5 años"],
                                key=f"rpt_plazo_{ov['ID']}")
                            nuevo_motivo_r = st.text_input("Motivo:", value=str(ov["Motivo"]),
                                                            key=f"rpt_motivo_{ov['ID']}")
                            if st.form_submit_button("🔄 Renovar"):
                                dbm.actualizar_objetivo(
                                    int(ov["ID"]), plazo_label=nuevo_plazo_r,
                                    motivo=nuevo_motivo_r, estado="ACTIVO")
                                st.success("✅ Objetivo renovado.")
                                st.rerun()

    # ── SECCIÓN: RECOMENDACIONES CONDICIONALES ───────────────────────────────
    st.markdown("---")
    st.markdown("### 💡 Recomendaciones de la Sesión")

    tiene_inyeccion = "df_compras_inyeccion" in st.session_state
    tiene_rebalanceo = ("df_compras_rebalanceo" in st.session_state or
                        "df_ventas_rebalanceo"  in st.session_state)

    if not tiene_inyeccion and not tiene_rebalanceo:
        st.info("No hay acciones de inversión en esta sesión. "
                "Podés ejecutar un rebalanceo o inyección de capital en la **Tab 5**.")
    else:
        if tiene_inyeccion:
            st.markdown("#### 🛒 Órdenes de Compra — Inyección de Capital")
            df_c = st.session_state["df_compras_inyeccion"]
            monto_total = st.session_state.get("ultima_inyeccion_ars", 0)
            plazo_inj   = st.session_state.get("ultima_inyeccion_plazo", "—")
            motivo_inj  = st.session_state.get("ultima_inyeccion_mot", "—")
            st.caption(f"Capital: **${monto_total:,.0f} ARS** | Plazo: **{plazo_inj}** | Motivo: *{motivo_inj}*")
            st.dataframe(
                df_c.style.format({
                    "Precio ARS": "${:,.2f}", "Total ARS": "${:,.0f}", "Comisión": "${:,.0f}",
                }), use_container_width=True, hide_index=True,
            )

        if tiene_rebalanceo:
            df_compras_reb = st.session_state.get("df_compras_rebalanceo", pd.DataFrame())
            df_ventas_reb  = st.session_state.get("df_ventas_rebalanceo",  pd.DataFrame())

            if not df_ventas_reb.empty:
                st.markdown("#### 🔴 Ventas — Rebalanceo")
                st.dataframe(df_ventas_reb.style.format({
                    "precio_ars": "${:,.2f}", "valor_nocional": "${:,.0f}",
                    "alpha_neto": "${:,.0f}",
                }), use_container_width=True, hide_index=True)

            if not df_compras_reb.empty:
                st.markdown("#### 🟢 Compras — Rebalanceo")
                st.dataframe(df_compras_reb.style.format({
                    "precio_ars": "${:,.2f}", "valor_nocional": "${:,.0f}",
                    "alpha_neto": "${:,.0f}",
                }), use_container_width=True, hide_index=True)

        if tiene_inyeccion and tiene_rebalanceo:
            st.success("✅ Sesión combinada: Rebalanceo + Inyección de capital. Ambas recomendaciones incluidas en el reporte.")

    # ── CONFIGURACIÓN Y GENERACIÓN DEL REPORTE HTML ──────────────────────────
    st.markdown("---")
    st.markdown("### 📄 Configurar y Generar Reporte HTML")

    if df_ag.empty:
        st.warning("Seleccioná una cartera con posiciones para generar el reporte.")
        return

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        rpt_cliente = st.text_input("Nombre del cliente", value=cliente_nombre or prop_nombre,
                                     key="rpt_nombre_cliente")
    with col_r2:
        rpt_asesor  = st.text_input("Nombre del asesor",  value="Alfredo Vallejos",
                                     key="rpt_nombre_asesor")

    rpt_notas = st.text_area(
        "Notas del asesor (opcional)",
        placeholder="Comentarios adicionales para el cliente, contexto de mercado...",
        height=90, key="rpt_notas_asesor",
    )

    st.markdown("**Secciones a incluir:**")
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    with col_s1:
        inc_lab = st.checkbox("Lab Quant", value="lab_resultados" in st.session_state,
                              key="rpt_inc_lab")
    with col_s2:
        inc_bt  = st.checkbox("Backtest vs Benchmark", value="bt_result" in st.session_state,
                              key="rpt_inc_bt")
    with col_s3:
        inc_ord = st.checkbox("Órdenes de ejecución", value=False, key="rpt_inc_ord")
    with col_s4:
        inc_obj = st.checkbox("Objetivos del cliente", value=not df_obj.empty, key="rpt_inc_obj")

    st.divider()

    if st.button("📄 Generar Reporte", type="primary", key="btn_generar_reporte"):
        with st.spinner("Preparando informe..."):
            lab_res  = st.session_state.get("lab_resultados") if inc_lab else None
            modelo_r = st.session_state.get("modelo_opt")
            bt_res   = st.session_state.get("bt_result") if inc_bt else None

            ejecutables_rpt = None
            if inc_ord:
                try:
                    _hist_rpt = cached_historico(tuple(tickers_cartera), "1y")
                    _plan_rpt = ejsvc.generar_plan_rebalanceo(
                        tickers_cartera=tickers_cartera,
                        df_ag=df_ag,
                        hist_precios=_hist_rpt,
                        precios_ars=ctx["precios_dict"],
                        modelo=modelo_r or "Sharpe",
                        capital_nuevo_ars=0,
                        umbral_churning=0.05,
                        comision_pct=0.006,
                        horizonte_dias=horizonte_dias,
                        risk_free_rate=RISK_FREE_RATE,
                    )
                    if not _plan_rpt.get("error") and not _plan_rpt["ejecutables"].empty:
                        ejecutables_rpt = _plan_rpt["ejecutables"]
                except Exception:
                    pass

            # Armar sección de objetivos como texto para el HTML
            notas_extendidas = rpt_notas
            if inc_obj and not df_obj.empty:
                notas_extendidas += "\n\n### OBJETIVOS DE INVERSIÓN\n"
                for _, obj_row in df_obj.iterrows():
                    notas_extendidas += (
                        f"• {obj_row['Motivo']} | {obj_row['Horizonte']} | "
                        f"${obj_row['Monto ARS']:,.0f} ARS | "
                        f"Estado: {obj_row['Estado']} | "
                        f"Vence: {obj_row['Vencimiento']} ({obj_row['Días restantes']} días restantes)\n"
                    )

            # Agregar recomendaciones de compra/venta
            if tiene_inyeccion:
                notas_extendidas += "\n\n### ÓRDENES DE COMPRA — INYECCIÓN DE CAPITAL\n"
                df_c_rpt = st.session_state.get("df_compras_inyeccion", pd.DataFrame())
                if not df_c_rpt.empty:
                    for _, cr in df_c_rpt.iterrows():
                        notas_extendidas += (
                            f"COMPRAR {int(cr.get('Nominales',0)):>5} x {cr.get('Ticker',''):<8} "
                            f"= ${cr.get('Total ARS',0):,.0f} ARS\n"
                        )

            if tiene_rebalanceo:
                df_v_rpt = st.session_state.get("df_ventas_rebalanceo",  pd.DataFrame())
                df_c2_rpt = st.session_state.get("df_compras_rebalanceo", pd.DataFrame())
                if not df_v_rpt.empty:
                    notas_extendidas += "\n\n### VENTAS — REBALANCEO\n"
                    for _, vr in df_v_rpt.iterrows():
                        notas_extendidas += f"VENDER {vr.get('nominales',0):>5} x {vr.get('ticker',''):<8}\n"
                if not df_c2_rpt.empty:
                    notas_extendidas += "\n### COMPRAS — REBALANCEO\n"
                    for _, cr2 in df_c2_rpt.iterrows():
                        notas_extendidas += f"COMPRAR {cr2.get('nominales',0):>5} x {cr2.get('ticker',''):<8}\n"

            # S4: Attribution BHB + Stress test para el PDF
            attr_data = {}
            stress_data = None
            try:
                from services.attribution_engine import AttributionEngine
                from services.stress_test import StressTestEngine
                attr_eng = AttributionEngine()
                attr_data = attr_eng.reporte_attribution(
                    df_pos=df_ag.copy(), df_trans=ctx.get("df_trans"), ccl=ccl
                )
                ste = StressTestEngine()
                stress_data = ste.todos_los_escenarios(df_ag.copy(), ccl)
            except Exception:
                pass

            html_str = rpt.generar_reporte_html(
                nombre_cliente = rpt_cliente,
                nombre_asesor  = rpt_asesor,
                df_pos         = df_ag.copy(),
                metricas       = metricas,
                ccl            = ccl,
                df_analisis    = engine_data.cargar_analisis(),
                lab_resultados = lab_res,
                modelo_opt     = modelo_r,
                backtest       = bt_res,
                ejecutables    = ejecutables_rpt,
                notas_asesor   = notas_extendidas,
                horizonte_dias = horizonte_dias,
                attribution    = attr_data if attr_data else None,
                stress         = stress_data,
            )

            st.session_state["rpt_html"]    = html_str
            st.session_state["rpt_cliente"] = rpt_cliente
            st.session_state["rpt_fecha"]   = datetime.now().strftime("%Y%m%d_%H%M")

    if "rpt_html" in st.session_state:
        _html_bytes     = st.session_state["rpt_html"].encode("utf-8")
        _nombre_archivo = (
            f"reporte_{st.session_state['rpt_cliente'].replace(' ','_')}"
            f"_{st.session_state['rpt_fecha']}.html"
        )
        st.success("✅ Reporte generado. Descargalo y abrilo en el navegador para imprimirlo como PDF.")

        _col_dl1, _col_dl2 = st.columns(2)
        with _col_dl1:
            st.download_button(
                label     = "⬇️ Descargar Reporte HTML",
                data      = _html_bytes,
                file_name = _nombre_archivo,
                mime      = "text/html",
                key       = "dl_reporte",
            )

        # H8: Exportación PDF nativa con fpdf2
        with _col_dl2:
            if st.button("📄 Exportar PDF (fpdf2)", key="btn_pdf_fpdf2"):
                with st.spinner("Generando PDF..."):
                    try:
                        import io as _io_pdf

                        from fpdf import FPDF

                        _cli_pdf   = st.session_state.get("rpt_cliente", "cliente")
                        _fecha_pdf = st.session_state.get("rpt_fecha", "")

                        class _PDFReporte(FPDF):
                            def header(self):
                                self.set_fill_color(10, 10, 20)
                                self.rect(0, 0, self.w, 20, "F")
                                self.set_font("Helvetica", "B", 14)
                                self.set_text_color(46, 134, 171)
                                self.set_xy(0, 4)
                                self.cell(self.w, 12, "MQ26-DSS — Reporte de Cartera", align="C")
                                self.set_text_color(200, 200, 200)
                                self.ln(20)

                            def footer(self):
                                self.set_y(-12)
                                self.set_font("Helvetica", "I", 8)
                                self.set_text_color(140, 140, 140)
                                self.cell(0, 8, f"MQ26-DSS | Pág. {self.page_no()} | {_fecha_pdf}", align="C")

                        _pdf = _PDFReporte()
                        _pdf.set_auto_page_break(auto=True, margin=15)
                        _pdf.add_page()

                        # Título
                        _pdf.set_font("Helvetica", "B", 18)
                        _pdf.set_text_color(46, 134, 171)
                        _pdf.cell(0, 12, f"Reporte de Cartera — {_cli_pdf}", ln=True)
                        _pdf.set_font("Helvetica", "", 10)
                        _pdf.set_text_color(100, 100, 100)
                        _pdf.cell(0, 8, f"Generado: {_fecha_pdf}", ln=True)
                        _pdf.ln(4)

                        # Métricas
                        _pdf.set_font("Helvetica", "B", 13)
                        _pdf.set_text_color(46, 134, 171)
                        _pdf.cell(0, 10, "Metricas Clave", ln=True)
                        _pdf.set_draw_color(46, 134, 171)
                        _pdf.line(10, _pdf.get_y(), _pdf.w - 10, _pdf.get_y())
                        _pdf.ln(3)
                        _pdf.set_font("Helvetica", "", 10)
                        _pdf.set_text_color(30, 30, 30)
                        _met_pdf = [
                            ("Valor Cartera ARS", f"${metricas.get('valor_total', 0):,.0f}"),
                            ("P&L Total",         f"${metricas.get('pnl_total', 0):,.0f} ({metricas.get('pnl_pct', 0):.1%})"),
                            ("CCL / MEP",         f"${ccl:,.0f}"),
                            ("Activos en cartera",str(len(tickers_cartera))),
                        ]
                        for _lbl_m, _val_m in _met_pdf:
                            _pdf.set_font("Helvetica", "B", 10)
                            _pdf.cell(70, 8, _lbl_m + ":", border=0)
                            _pdf.set_font("Helvetica", "", 10)
                            _pdf.cell(0, 8, _val_m, ln=True, border=0)

                        # Tabla posiciones
                        if not df_ag.empty:
                            _pdf.ln(5)
                            _pdf.set_font("Helvetica", "B", 13)
                            _pdf.set_text_color(46, 134, 171)
                            _pdf.cell(0, 10, "Posicion Actual", ln=True)
                            _pdf.line(10, _pdf.get_y(), _pdf.w - 10, _pdf.get_y())
                            _pdf.ln(3)
                            _cols_pdf = ["TICKER", "CANTIDAD", "VALOR_ARS", "PNL"]
                            _cols_ok  = [c for c in _cols_pdf if c in df_ag.columns]
                            if _cols_ok:
                                _header_pdf = {"TICKER": "Ticker", "CANTIDAD": "Cant.",
                                               "VALOR_ARS": "Valor ARS", "PNL": "P&L ARS"}
                                _pdf.set_fill_color(46, 134, 171)
                                _pdf.set_text_color(255, 255, 255)
                                _pdf.set_font("Helvetica", "B", 9)
                                _col_w_pdf = 45
                                for _c in _cols_ok:
                                    _pdf.cell(_col_w_pdf, 7, _header_pdf.get(_c, _c), border=1, fill=True)
                                _pdf.ln()
                                _pdf.set_font("Helvetica", "", 9)
                                _even = False
                                for _, _row in df_ag[_cols_ok].iterrows():
                                    _pdf.set_fill_color(245, 245, 252) if _even else _pdf.set_fill_color(255, 255, 255)
                                    _pdf.set_text_color(30, 30, 30)
                                    for _c in _cols_ok:
                                        _v = _row[_c]
                                        if isinstance(_v, float):
                                            _txt = f"{_v:,.2f}"
                                        else:
                                            _txt = str(_v)
                                        _pdf.cell(_col_w_pdf, 6, _txt[:18], border="LR", fill=True)
                                    _pdf.ln()
                                    _even = not _even
                                _pdf.set_draw_color(150, 150, 150)
                                _pdf.line(10, _pdf.get_y(), _pdf.w - 10, _pdf.get_y())

                        _pdf_output = _io_pdf.BytesIO(_pdf.output())
                        st.download_button(
                            label     = "⬇️ Descargar PDF",
                            data      = _pdf_output,
                            file_name = _nombre_archivo.replace(".html", ".pdf"),
                            mime      = "application/pdf",
                            key       = "dl_reporte_pdf",
                        )
                        st.toast("✅ PDF generado con fpdf2", icon="📄")
                    except ImportError:
                        st.warning(
                            "fpdf2 no está instalado. Ejecutá: `pip install fpdf2` "
                            "para habilitar la exportación PDF nativa."
                        )
                    except Exception as _ex_pdf:
                        st.error(f"Error generando PDF: {_ex_pdf}")
        with st.expander("👁️ Vista previa del reporte", expanded=False):
            st.components.v1.html(
                st.session_state["rpt_html"],
                height=700,
                scrolling=True,
            )

    # ── SECCIÓN: REPORTE MENSUAL (H6) ────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📅 Reporte Mensual Automático")
    st.caption("Genera un resumen del mes: retorno del período, operaciones, objetivos alcanzados, comparación vs inflación y Merval.")

    col_rm1, col_rm2 = st.columns([2, 1])
    with col_rm1:
        mes_rpt = st.selectbox(
            "Período del reporte:",
            ["Mes actual", "Mes anterior", "Últimos 3 meses", "Últimos 6 meses"],
            key="rm_periodo",
        )
    with col_rm2:
        if st.button("📅 Generar Reporte Mensual", type="primary", key="btn_reporte_mensual"):
            with st.spinner("Generando reporte mensual..."):
                try:
                    import sys
                    from pathlib import Path as _Path
                    _svc = str(_Path(__file__).resolve().parent.parent / "services")
                    if _svc not in sys.path:
                        sys.path.insert(0, _svc)
                    from reporte_mensual import generar_reporte_mensual
                    html_mensual = generar_reporte_mensual(
                        df_ag=df_ag,
                        metricas=metricas,
                        prop_nombre=prop_nombre,
                        horizonte_label=horizonte_label,
                        cliente_perfil=cliente_perfil,
                        periodo=mes_rpt,
                    )
                    if html_mensual:
                        st.download_button(
                            "📥 Descargar Reporte Mensual HTML",
                            data=html_mensual.encode("utf-8"),
                            file_name=f"reporte_mensual_{prop_nombre}_{datetime.now().strftime('%Y%m')}.html",
                            mime="text/html",
                            key="dl_mensual",
                        )
                        st.toast("✅ Reporte mensual generado", icon="📅")
                except ImportError:
                    # Generar reporte básico si no existe el módulo
                    html_mensual = f"""
                    <html><body style="font-family:Inter,sans-serif;background:#0A0A14;color:#E8E8F0;padding:2rem">
                    <h1 style="color:#2E86AB">Reporte Mensual — {prop_nombre}</h1>
                    <p>Período: {mes_rpt}</p>
                    <h2>Métricas del período</h2>
                    <ul>
                        <li>P&L total: {metricas.get('pnl_total', 0):,.0f} ARS</li>
                        <li>Retorno %: {metricas.get('pnl_pct', 0):.1%}</li>
                        <li>CCL actual: {ccl:,.0f}</li>
                        <li>Activos: {len(tickers_cartera)}</li>
                    </ul>
                    <p style="color:#888;font-size:0.8rem">Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    </body></html>
                    """
                    st.download_button(
                        "📥 Descargar Reporte Mensual",
                        data=html_mensual.encode("utf-8"),
                        file_name=f"reporte_mensual_{datetime.now().strftime('%Y%m')}.html",
                        mime="text/html",
                        key="dl_mensual_basic",
                    )
                except Exception as e:
                    st.error(f"Error generando reporte mensual: {e}")


    # ── SECCIONES AVANZADAS (feature-gated) ──────────────────────────────────
    _role = ctx.get("user_role", "inversor")
    _extra_tabs = []
    _extra_names = []
    if has_feature(_role, "analisis_empresa"):
        _extra_names.append("🔍 Ficha Empresa")
        _extra_tabs.append("ficha_empresa")
    if has_feature(_role, "analisis_empresa"):
        _extra_names.append("🎯 Planificador de Retiro")
        _extra_tabs.append("retiro")
    if has_feature(_role, "analisis_empresa"):
        _extra_names.append("📊 Benchmark histórico")
        _extra_tabs.append("comparador")

    if _extra_names:
        st.markdown("---")
        _subtabs = st.tabs(_extra_names)
        _tab_map = dict(zip(_extra_tabs, _subtabs))

        if "ficha_empresa" in _tab_map:
            with _tab_map["ficha_empresa"]:
                st.subheader("Análisis de Empresa")
                ticker_input = st.text_input(
                    "Ticker", placeholder="AAPL, MSFT, GOOGL...",
                    key="rpt_ficha_ticker"
                )
                if ticker_input and st.button("Analizar", key="rpt_btn_ficha",
                                               use_container_width=True):
                    with st.spinner(f"Analizando {ticker_input.upper()}..."):
                        try:
                            from services.empresa_ficha import generar_ficha_activo
                            ficha = generar_ficha_activo(ticker_input.upper())
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Score Técnico",     f"{ficha['score_tecnico']:.0f}/100")
                            c2.metric("Score Fundamental", f"{ficha['score_fundamental']:.0f}/100")
                            c3.metric("Score Total",       f"{ficha['score_total']:.0f}/100")
                            st.success(f"Recomendación: {ficha['recomendacion']}")
                            if ficha.get("figura_velas") is not None:
                                st.plotly_chart(ficha["figura_velas"],
                                                use_container_width=True)
                                fmt_rrss = st.selectbox(
                                    "Formato para exportar",
                                    ["instagram", "linkedin", "twitter"],
                                    key="rpt_rrss_fmt"
                                )
                                if st.button("Exportar para redes sociales",
                                             key="rpt_btn_rrss",
                                             use_container_width=True):
                                    try:
                                        from services.market_stress_map import exportar_para_rrss
                                        png = exportar_para_rrss(ficha["figura_velas"], fmt_rrss)
                                        st.download_button(
                                            label=f"Descargar PNG ({fmt_rrss})",
                                            data=png,
                                            file_name=f"{ticker_input.upper()}_{fmt_rrss}.png",
                                            mime="image/png",
                                            key="rpt_dl_rrss",
                                            use_container_width=True,
                                        )
                                    except RuntimeError as e:
                                        st.warning(str(e))
                        except Exception as exc:
                            st.error(f"No se pudo analizar {ticker_input}: {exc}")

        if "retiro" in _tab_map:
            with _tab_map["retiro"]:
                import numpy as np
                import plotly.graph_objects as go
                from core.retirement_goal import (
                    calcular_aporte_necesario,
                    simulate_retirement,
                )
                st.subheader("Planificador de Retiro")
                col_r1, col_r2 = st.columns(2)
                capital_actual = col_r1.number_input(
                    "Capital actual (USD)", min_value=0.0, value=10_000.0,
                    step=1_000.0, key="rpt_ret_cap"
                )
                objetivo_usd = col_r1.number_input(
                    "Objetivo patrimonial (USD)", min_value=0.0, value=200_000.0,
                    step=10_000.0, key="rpt_ret_obj"
                )
                n_años = col_r2.slider(
                    "Años hasta el retiro", min_value=5, max_value=40,
                    value=20, key="rpt_ret_años"
                )
                perfil_ret = col_r2.selectbox(
                    "Perfil de inversión",
                    ["conservador", "moderado", "arriesgado"],
                    key="rpt_ret_perfil"
                )
                RENDIMIENTOS = {"conservador": 0.06, "moderado": 0.09, "arriesgado": 0.12}
                rend = RENDIMIENTOS[perfil_ret]

                if st.button("Calcular plan de retiro", key="rpt_btn_retiro",
                             use_container_width=True):
                    aporte = calcular_aporte_necesario(capital_actual, objetivo_usd, n_años, rend)
                    st.metric("Aporte mensual necesario", f"USD {aporte:,.0f}")
                    rng_ret = np.random.default_rng(42)
                    vol_m   = {"conservador": 0.025, "moderado": 0.04, "arriesgado": 0.06}
                    r_d     = rng_ret.normal(rend / 252, vol_m[perfil_ret] / 15, 252 * n_años)
                    sim = simulate_retirement(
                        aporte_mensual=aporte,
                        n_meses_acum=n_años * 12,
                        retiro_mensual=objetivo_usd * 0.004,
                        n_meses_desacum=20 * 12,
                        retornos_diarios=r_d,
                        n_sim=2000,
                    )
                    años_eje = list(range(n_años + 1))
                    cap_evol = [capital_actual]
                    cap = capital_actual
                    rm  = (1 + rend) ** (1 / 12) - 1
                    for k in range(n_años * 12):
                        cap = (cap + aporte) * (1 + rm)
                        if (k + 1) % 12 == 0:
                            cap_evol.append(cap)
                    fig_ret = go.Figure()
                    fig_ret.add_scatter(
                        x=años_eje, y=cap_evol, mode="lines",
                        name="Proyección P50",
                        line={"color": "#1A6B3C", "width": 2}
                    )
                    fig_ret.add_hline(
                        y=objetivo_usd, line_dash="dash",
                        annotation_text=f"Objetivo: USD {objetivo_usd:,.0f}"
                    )
                    fig_ret.update_layout(
                        xaxis_title="Años", yaxis_title="Patrimonio (USD)",
                        margin={"l": 0, "r": 0, "t": 30, "b": 0}
                    )
                    st.plotly_chart(fig_ret, use_container_width=True)
                    cp1, cp2, cp3 = st.columns(3)
                    cp1.metric("Escenario pesimista (P10)", f"USD {sim['p10']:,.0f}")
                    cp2.metric("Escenario base (P50)",      f"USD {sim['p50']:,.0f}")
                    cp3.metric("Escenario optimista (P90)", f"USD {sim['p90']:,.0f}")
                    st.info(
                        f"Probabilidad de no agotar el capital: "
                        f"**{sim['prob_no_agotar']:.1%}**"
                    )

        if "comparador" in _tab_map:
            with _tab_map["comparador"]:
                st.subheader("📊 ¿Dónde conviene invertir?")
                st.caption(
                    "USD invertidos en diferentes instrumentos — SPY vs dólar vs plazo fijo vs "
                    "cartera conservadora. Escala logarítmica."
                )
                col_c1, col_c2 = st.columns([1, 2])
                with col_c1:
                    capital_comp = st.number_input(
                        "Capital inicial (USD)",
                        min_value=100,
                        max_value=100_000,
                        value=1_000,
                        step=500,
                        key="comp_capital",
                    )
                    start_comp = st.selectbox(
                        "Desde el año",
                        ["2005-01-01", "2010-01-01", "2015-01-01", "2020-01-01"],
                        key="comp_start",
                    )
                with col_c2:
                    with st.spinner("Cargando datos históricos..."):
                        try:
                            from services.comparador_instrumentos import generar_comparador_instrumentos
                            fig_comp = generar_comparador_instrumentos(
                                start=start_comp,
                                capital=float(capital_comp),
                            )
                            st.plotly_chart(fig_comp, use_container_width=True)
                        except Exception as e_comp:
                            st.error(f"No se pudo generar el comparador: {e_comp}")
                st.info(
                    "💡 **El argumento en números:** en 20 años, USD 1.000 en SPY se convirtieron "
                    "en más de USD 7.000. El plazo fijo en pesos perdió valor real frente al dólar. "
                    "La cartera conservadora de MQ26 supera al dólar billete con menor volatilidad."
                )
                if has_feature(_role, "exportar_rrss") and st.button(
                    "Exportar para redes sociales",
                    key="btn_comp_rrss",
                    use_container_width=True,
                ):
                    try:
                        from services.market_stress_map import exportar_para_rrss
                        st.download_button(
                            "⬇️ Descargar PNG (Instagram)",
                            data=exportar_para_rrss(fig_comp, "instagram"),
                            file_name="comparador_instrumentos.png",
                            mime="image/png",
                            key="dl_comp_rrss",
                            use_container_width=True,
                        )
                    except RuntimeError as e_rrss:
                        st.warning(str(e_rrss))
