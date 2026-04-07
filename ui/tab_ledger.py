"""
ui/tab_ledger.py — Tab 2: Libro Mayor (IBOR)
Equivalente institucional: Investment Book of Record / Ledger
Combina: Libro Mayor + Importador de broker + Sincronización Gmail
"""
from datetime import datetime

import streamlit as st


def render_tab_ledger(ctx: dict) -> None:
    df_ag           = ctx["df_ag"]
    tickers_cartera = ctx["tickers_cartera"]
    precios_dict    = ctx["precios_dict"]
    ccl             = ctx["ccl"]
    cartera_activa  = ctx["cartera_activa"]
    cs              = ctx["cs"]
    lm              = ctx["lm"]
    bi              = ctx["bi"]
    gr              = ctx["gr"]
    engine_data     = ctx["engine_data"]
    BASE_DIR        = ctx["BASE_DIR"]
    _boton_exportar = ctx["_boton_exportar"]

    sub_lm, sub_gmail = st.tabs(["📒 Libro Mayor", "📧 Gmail / Importar correos"])

    # ── SUB-TAB: LIBRO MAYOR ────────────────────────────────────────────────────
    with sub_lm:
        precios_usd_subs, ratios_cartera = cs.precios_usd_subyacente(
            tickers_cartera, precios_dict, ccl,
            universo_df=engine_data.universo_df,
        ) if tickers_cartera else ({}, {})

        ruta_maestra = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"

        st.markdown("#### 📥 Importar comprobante de broker (Balanz / Bull Market)")
        with st.expander("➕ Importar nuevo comprobante Excel", expanded=False):
            col_bi1, col_bi2, col_bi3 = st.columns(3)
            with col_bi1:
                archivo_broker = st.file_uploader(
                    "Subí el Excel del broker:", type=["xlsx"], key="uploader_broker"
                )
            with col_bi2:
                prop_broker = st.selectbox(
                    "Propietario:", ["Alfredo y Andrea", "Alfredo", "Santi"], key="prop_broker"
                )
            with col_bi3:
                cart_broker = st.selectbox(
                    "Cartera:", ["Retiro", "Reto 2026", "Cartera Agresiva"], key="cart_broker"
                )
            ccl_broker = st.number_input(
                f"CCL del día de las operaciones (actual: ${ccl:,.0f}):",
                min_value=100.0, value=float(ccl), step=10.0, key="ccl_broker"
            )
            if archivo_broker is not None:
                try:
                    df_preview = bi.importar_comprobante(
                        archivo_broker,
                        propietario=prop_broker,
                        cartera=cart_broker,
                        ccl=ccl_broker,
                    )
                    if df_preview.empty:
                        st.warning("No se encontraron operaciones en el archivo.")
                    else:
                        st.markdown(f"**Preview — {len(df_preview)} operaciones detectadas:**")
                        st.caption(f"Brokers detectados: {', '.join(df_preview['Broker'].unique().tolist())}")
                        st.dataframe(
                            df_preview.style.format({
                                "Precio_ARS": "${:,.2f}",
                                "Neto_ARS":   "${:,.2f}",
                                "PPC_USD":    "${:.4f}",
                            }).apply(
                                lambda r: ["background-color:#D4EDDA" if v == "COMPRA"
                                           else "background-color:#FADBD8" if v == "VENTA"
                                           else "" for v in r],
                                subset=["Tipo_Op"], axis=0
                            ), use_container_width=True, hide_index=True
                        )
                        if st.button("💾 Aplicar al Libro Mayor", type="primary", key="btn_aplicar_broker"):
                            bi.aplicar_operaciones_a_maestra(df_preview, ruta_maestra)
                            st.session_state.pop("libro_mayor_data", None)
                            st.success(f"✅ {len(df_preview)} operaciones aplicadas al Libro Mayor.")
                            st.rerun()
                except Exception as e:
                    st.error(f"Error procesando el archivo: {e}")

        df_libro_resultado = lm.render_libro_mayor(
            ruta_excel=ruta_maestra,
            ratios=ratios_cartera,
            precios_usd=precios_usd_subs,
            ccl=ccl,
            cartera_filtro=cartera_activa,
        )
        if df_libro_resultado is not None and not df_libro_resultado.empty:
            _nombre_archivo = (
                f"libro_mayor_{cartera_activa.replace(' ','_').replace('|','')[:30]}"
                f"_{datetime.now().strftime('%Y%m%d')}"
            )
            _boton_exportar(df_libro_resultado, _nombre_archivo, "📥 Exportar Libro Mayor a Excel")

    # ── SUB-TAB: GMAIL ──────────────────────────────────────────────────────────
    with sub_gmail:
        st.markdown("### 📧 Lector automático de correos de brokers")
        st.info(
            "Lee automáticamente los correos de **Balanz** y **Bull Market** "
            "desde tu Gmail y genera el historial completo de operaciones."
        )

        col_gm1, col_gm2 = st.columns(2)
        with col_gm1:
            st.markdown("**Balanz** → boletos@balanz.com")
            prop_balanz = st.selectbox("Propietario Balanz:", ["Alfredo y Andrea","Alfredo","Santi"], key="prop_balanz")
            cart_balanz = st.selectbox("Cartera Balanz:", ["Retiro","Reto 2026","Cartera Agresiva"], key="cart_balanz")
        with col_gm2:
            st.markdown("**Bull Market** → accountactivity@bullmarketbrokers.com")
            prop_bull = st.selectbox("Propietario Bull Market:", ["Alfredo","Alfredo y Andrea","Santi"], key="prop_bull")
            cart_bull = st.selectbox("Cartera Bull Market:", ["Reto 2026","Retiro","Cartera Agresiva"], key="cart_bull")

        if "gmail_mensajes_balanz" not in st.session_state:
            st.session_state["gmail_mensajes_balanz"] = []
        if "gmail_mensajes_bull" not in st.session_state:
            st.session_state["gmail_mensajes_bull"] = []

        st.divider()
        st.markdown("#### 📋 O pegá el cuerpo de un correo manualmente")
        col_paste1, col_paste2 = st.columns(2)
        with col_paste1:
            texto_balanz = st.text_area("Texto correo Balanz:", height=120,
                                         placeholder="Pegá el cuerpo del email de Balanz aquí...",
                                         key="texto_balanz_manual")
            if st.button("➕ Agregar correo Balanz", key="btn_add_balanz"):
                if texto_balanz.strip():
                    st.session_state["gmail_mensajes_balanz"].append({"body": texto_balanz, "fecha": ""})
                    st.success(f"✅ Agregado. Total Balanz: {len(st.session_state['gmail_mensajes_balanz'])}")
        with col_paste2:
            texto_bull = st.text_area("Texto correo Bull Market:", height=120,
                                       placeholder="Pegá el cuerpo del email de Bull Market aquí...",
                                       key="texto_bull_manual")
            if st.button("➕ Agregar correo Bull Market", key="btn_add_bull"):
                if texto_bull.strip():
                    st.session_state["gmail_mensajes_bull"].append({"body": texto_bull, "fecha": ""})
                    st.success(f"✅ Agregado. Total Bull Market: {len(st.session_state['gmail_mensajes_bull'])}")

        st.caption(
            f"Correos en cola: Balanz={len(st.session_state['gmail_mensajes_balanz'])} | "
            f"Bull Market={len(st.session_state['gmail_mensajes_bull'])}"
        )

        if st.button("⚡ Procesar todos los correos en cola", type="primary", key="btn_procesar_gmail"):
            total_msgs = (
                len(st.session_state["gmail_mensajes_balanz"]) +
                len(st.session_state["gmail_mensajes_bull"])
            )
            if total_msgs == 0:
                st.warning("No hay correos en cola. Agregá correos arriba.")
            else:
                with st.spinner(f"Procesando {total_msgs} correos..."):
                    df_hist = gr.leer_todos_los_correos(
                        st.session_state["gmail_mensajes_balanz"],
                        st.session_state["gmail_mensajes_bull"],
                    )
                    if df_hist.empty:
                        st.error("No se encontraron operaciones en los correos.")
                    else:
                        st.success(f"✅ {len(df_hist)} operaciones extraídas de {total_msgs} correos.")
                        st.dataframe(
                            df_hist.style.format({
                                "Precio_ARS": "${:,.2f}",
                                "Neto_ARS":   "${:,.2f}",
                                "PPC_USD":    "${:.4f}",
                                "CCL_dia":    "${:,.0f}",
                            }).apply(
                                lambda r: ["background-color:#D4EDDA" if v == "COMPRA"
                                           else "background-color:#FADBD8" if v == "VENTA"
                                           else "" for v in r],
                                subset=["Tipo_Op"], axis=0
                            ), use_container_width=True, hide_index=True
                        )

                        ruta_hist = BASE_DIR / "0_Data_Maestra" / "Historial_Operaciones_Gmail.xlsx"
                        gr.exportar_a_excel(df_hist, ruta_hist)

                        if st.button("💾 Aplicar al Libro Mayor y guardar", key="btn_guardar_gmail"):
                            prop_map = {
                                "Balanz":      {"propietario": prop_balanz, "cartera": cart_balanz},
                                "Bull Market": {"propietario": prop_bull,   "cartera": cart_bull},
                            }
                            df_maestra = gr.construir_maestra_desde_historial(df_hist, prop_map)
                            ruta_m = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
                            df_maestra.to_excel(ruta_m, index=False)
                            st.session_state.pop("libro_mayor_data", None)
                            st.success(f"✅ {len(df_maestra)} filas guardadas en Maestra_Inversiones.xlsx")
                            st.rerun()
