"""
ui/tab_ejecucion.py — Tab 5: Mesa de Ejecución
Combina: Rebalanceo + Inyección de Capital con Objetivos + Recomendador Semanal
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core.logging_config import get_logger

_log = get_logger(__name__)


def render_tab_ejecucion(ctx: dict) -> None:
    df_ag            = ctx["df_ag"]
    tickers_cartera  = ctx["tickers_cartera"]
    precios_dict     = ctx["precios_dict"]
    ccl              = ctx["ccl"]
    cartera_activa   = ctx["cartera_activa"]
    prop_nombre      = ctx["prop_nombre"]
    df_clientes      = ctx["df_clientes"]
    RISK_FREE_RATE   = ctx["RISK_FREE_RATE"]
    horizonte_dias   = ctx["horizonte_dias"]
    ejsvc            = ctx["ejsvc"]
    cached_historico = ctx["cached_historico"]
    _boton_exportar  = ctx["_boton_exportar"]
    RiskEngine       = ctx["RiskEngine"]
    dbm              = ctx["dbm"]
    cliente_id       = ctx.get("cliente_id")
    cliente_perfil   = ctx.get("cliente_perfil", "Moderado")
    horizonte_label  = ctx.get("horizonte_label", "1 año")
    _is_viewer       = str(ctx.get("user_role", "admin")).lower() == "viewer"
    sub_reb, sub_rec, sub_export = st.tabs([
        "🛒 Rebalanceo / Capital",
        "🎯 Recomendador Semanal",
        "📤 Exportar Órdenes",
    ])

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 1: REBALANCEO / CAPITAL CON OBJETIVOS
    # ══════════════════════════════════════════════════════════════════
    with sub_reb:
        st.subheader("🛒 Rebalanceo & Inyección de Capital")

        # ── Checkboxes de acción ──────────────────────────────────────────────
        col_chk1, col_chk2, _ = st.columns([2, 2, 2])
        with col_chk1:
            hacer_rebalanceo = st.checkbox("⚖️ Rebalancear cartera existente",
                                            value=False, key="chk_rebalanceo")
        with col_chk2:
            inyectar_capital = st.checkbox("💰 Inyectar capital nuevo (con objetivo)",
                                            value=False, key="chk_inyeccion")

        if not hacer_rebalanceo and not inyectar_capital:
            st.info("Seleccioná al menos una acción: rebalancear, inyectar capital, o ambas.")

        # ── SECCIÓN: INYECCIÓN DE CAPITAL CON OBJETIVO ───────────────────────
        if inyectar_capital:
            st.markdown("---")
            st.markdown("### 💰 Nuevo Objetivo de Inversión")
            st.caption(
                "Cada inyección de capital queda asociada a un objetivo con horizonte y motivo. "
                "Esto permite gestionar distintas estrategias de salida según cada objetivo."
            )

            with st.form("form_objetivo_inversion", clear_on_submit=False):
                col_obj1, col_obj2 = st.columns(2)
                with col_obj1:
                    moneda_obj = st.radio("Moneda:", ["ARS ($)", "USD (u$s)"],
                                          horizontal=True, key="obj_moneda")
                    if moneda_obj == "ARS ($)":
                        monto_obj = st.number_input("Monto (ARS):", min_value=0,
                                                     value=500_000, step=50_000, key="obj_monto_ars")
                        monto_ars = float(monto_obj)
                    else:
                        monto_obj_usd = st.number_input("Monto (USD):", min_value=0,
                                                          value=1_000, step=100, key="obj_monto_usd")
                        monto_ars = float(monto_obj_usd) * ccl

                    st.caption(f"Equivalente: **${monto_ars:,.0f} ARS** | **USD {monto_ars/ccl:,.0f}**" if ccl > 0 else "")

                with col_obj2:
                    plazo_obj = st.selectbox("Horizonte:",
                                              ["1 mes","3 meses","6 meses","1 año","3 años","+5 años"],
                                              key="obj_plazo")
                    _ticker_raw = st.text_input("Activo principal (opcional):",
                                                placeholder="AAPL, MELI, SPY...",
                                                key="obj_ticker")
                    # D8: Sanitización de ticker input
                    ticker_obj = _ticker_raw.upper().strip().replace(" ", "")[:10]
                motivo_obj = st.text_area(
                    "Motivo / Descripción del objetivo:",
                    placeholder='Ej: "Retiro parcial en 1 año", "Fondo universitario hija", "Cartera agresiva 5 años"',
                    height=80, key="obj_motivo"
                )

                col_adv1, col_adv2 = st.columns(2)
                with col_adv1:
                    target_override = st.number_input("Target % override (dejar en 0 = usar perfil):",
                                                       min_value=0.0, max_value=200.0, value=0.0,
                                                       step=5.0, key="obj_target")
                with col_adv2:
                    stop_override = st.number_input("Stop % override (dejar en 0 = usar perfil):",
                                                     min_value=0.0, max_value=50.0, value=0.0,
                                                     step=1.0, key="obj_stop")

                submitted_obj = st.form_submit_button(
                    "💾 Guardar objetivo e inyectar capital",
                    type="primary",
                    use_container_width=True,
                    disabled=_is_viewer,
                )
                if submitted_obj:
                    if not cliente_id:
                        st.error("Seleccioná un cliente antes de registrar objetivos.")
                    elif monto_ars <= 0:
                        st.error("El monto debe ser mayor a cero.")
                    elif not motivo_obj.strip():
                        st.error("Describí el motivo del objetivo.")
                    else:
                        nuevo_id = dbm.registrar_objetivo(
                            cliente_id=cliente_id,
                            monto_ars=monto_ars,
                            plazo_label=plazo_obj,
                            motivo=motivo_obj.strip(),
                            ticker=ticker_obj,
                            target_pct=target_override if target_override > 0 else None,
                            stop_pct=stop_override   if stop_override > 0   else None,
                        )
                        # Guardar para uso en reporte
                        st.session_state["ultimo_objetivo_id"]    = nuevo_id
                        st.session_state["ultima_inyeccion_ars"]  = monto_ars
                        st.session_state["ultima_inyeccion_plazo"]= plazo_obj
                        st.session_state["ultima_inyeccion_mot"]  = motivo_obj.strip()
                        st.success(
                            f"✅ Objetivo registrado | Monto: **${monto_ars:,.0f} ARS** | "
                            f"Horizonte: **{plazo_obj}** | Motivo: *{motivo_obj[:60]}*"
                        )
                        st.rerun()

            # Calcular órdenes de compra si hay pesos óptimos disponibles
            pesos_iny = st.session_state.get("pesos_opt", {})
            if pesos_iny and st.session_state.get("ultima_inyeccion_ars", 0) > 0:
                capital_ars_iny = st.session_state["ultima_inyeccion_ars"]
                comision_iny = 0.006
                st.markdown(f"#### 🛒 ¿Qué comprar con ${capital_ars_iny:,.0f} ARS?")
                st.caption(f"Basado en modelo: **{st.session_state.get('modelo_opt','Óptimo')}**")
                filas_iny = []
                for ticker_i, peso_i in sorted(pesos_iny.items(), key=lambda x: x[1], reverse=True):
                    if peso_i < 0.001:
                        continue
                    px_ars_i = float(precios_dict.get(ticker_i, 0.0))
                    if px_ars_i <= 0:
                        continue
                    monto_i     = capital_ars_iny * peso_i
                    nominales_i = int(monto_i / px_ars_i)
                    if nominales_i <= 0:
                        continue
                    total_i = nominales_i * px_ars_i
                    filas_iny.append({
                        "Ticker": ticker_i, "Peso %": f"{peso_i*100:.1f}%",
                        "Nominales": nominales_i, "Precio ARS": px_ars_i,
                        "Total ARS": total_i, "Comisión": total_i * comision_iny,
                    })
                if filas_iny:
                    df_iny = pd.DataFrame(filas_iny)

                    # MQ2-V10: calcular preview de impacto de cada orden
                    _val_total_actual = df_ag["VALOR_ARS"].sum() if not df_ag.empty and "VALOR_ARS" in df_ag.columns else 0.0
                    _val_nuevo = _val_total_actual + capital_ars_iny
                    _notas_impacto = []
                    for _fila in filas_iny:
                        _t_imp  = _fila["Ticker"]
                        _tot_imp= _fila["Total ARS"]
                        _nom_imp= _fila["Nominales"]
                        _pesos_nuevos = (_tot_imp + (df_ag.set_index("TICKER").get("VALOR_ARS", pd.Series()).get(_t_imp, 0.0) if not df_ag.empty else 0.0)) / _val_nuevo * 100 if _val_nuevo > 0 else 0.0
                        _com_imp = _fila["Comisión"]
                        _nota = f"Peso→{_pesos_nuevos:.1f}% | Com.${_com_imp:,.0f}"
                        _notas_impacto.append(_nota)
                    df_iny["Impacto"] = _notas_impacto

                    st.dataframe(
                        df_iny, use_container_width=True, hide_index=True,
                        column_config={
                            "Peso %":     st.column_config.TextColumn("Peso %"),
                            "Nominales":  st.column_config.NumberColumn("Nominales", format="%d"),
                            "Precio ARS": st.column_config.NumberColumn("Precio ARS", format="$%.2f"),
                            "Total ARS":  st.column_config.NumberColumn("Total ARS",  format="$%.0f"),
                            "Comisión":   st.column_config.NumberColumn("Comisión",   format="$%.0f"),
                            "Impacto":    st.column_config.TextColumn("Preview Impacto", help="Nuevo peso % + costo comisión"),
                        },
                    )
                    # MQ2-S9: registrar órdenes calculadas en audit_trail
                    if not _is_viewer:
                        try:
                            from services.audit_trail import registrar_orden as _reg_ord
                            for _f in filas_iny:
                                _reg_ord(
                                    tipo="COMPRA", ticker=_f["Ticker"], cantidad=_f["Nominales"],
                                    precio_ars=_f["Precio ARS"], cliente_id=cliente_id,
                                    cartera=cartera_activa,
                                    modelo=st.session_state.get("modelo_opt", "inyeccion"),
                                )
                        except Exception:
                            pass

                    st.session_state["df_compras_inyeccion"] = df_iny
                    _boton_exportar(df_iny, f"compras_inyeccion_{datetime.now().strftime('%Y%m%d')}", "📥 Exportar órdenes")
                else:
                    st.warning("No hay precios disponibles para calcular las órdenes. Verificá los precios en el panel lateral.")

        # ── TABLA DE OBJETIVOS ACTIVOS ────────────────────────────────────────
        if cliente_id:
            st.markdown("---")
            st.markdown("### 📋 Objetivos de Inversión Activos")
            df_obj = dbm.obtener_objetivos_cliente(cliente_id)
            if df_obj.empty:
                st.info("No hay objetivos registrados para este cliente.")
            else:
                def _color_estado(val):
                    if val == "ACTIVO":    return "background-color:#D4EDDA;color:#155724"
                    if val == "VENCIDO":   return "background-color:#FADBD8;color:#721C24"
                    if val == "COMPLETADO": return "background-color:#D1ECF1;color:#0C5460"
                    return ""

                st.dataframe(
                    df_obj.style
                    .format({
                        "Monto ARS": "${:,.0f}",
                        "Target %":  lambda x: f"{x:.0f}%" if pd.notna(x) else "—",
                        "Stop %":    lambda x: f"{x:.0f}%" if pd.notna(x) else "—",
                    }, na_rep="—")
                    .map(_color_estado, subset=["Estado"]), use_container_width=True, hide_index=True,
                )

                # Editar objetivos vencidos
                obj_vencidos = df_obj[df_obj["Estado"] == "VENCIDO"]
                if not obj_vencidos.empty:
                    st.markdown("---")
                    st.markdown("#### ✏️ Editar / Renovar objetivos vencidos")
                    for _, ov in obj_vencidos.iterrows():
                        with st.expander(f"Objetivo #{ov['ID']} — {ov['Motivo'][:50]} | Venció: {ov['Vencimiento']}"):
                            with st.form(f"form_editar_obj_{ov['ID']}", clear_on_submit=True):
                                col_e1, col_e2 = st.columns(2)
                                with col_e1:
                                    nuevo_monto = st.number_input(
                                        "Nuevo monto ARS:", value=float(ov["Monto ARS"]),
                                        step=50_000.0, key=f"e_monto_{ov['ID']}")
                                    nuevo_plazo = st.selectbox(
                                        "Nuevo horizonte:",
                                        ["1 mes","3 meses","6 meses","1 año","3 años","+5 años"],
                                        key=f"e_plazo_{ov['ID']}")
                                with col_e2:
                                    nuevo_motivo = st.text_input("Motivo:", value=str(ov["Motivo"]),
                                                                  key=f"e_motivo_{ov['ID']}")
                                col_sb1, col_sb2 = st.columns(2)
                                with col_sb1:
                                    if st.form_submit_button("🔄 Renovar objetivo", type="primary", disabled=_is_viewer):
                                        dbm.actualizar_objetivo(
                                            int(ov["ID"]),
                                            monto_ars=nuevo_monto,
                                            plazo_label=nuevo_plazo,
                                            motivo=nuevo_motivo,
                                            estado="ACTIVO",
                                        )
                                        st.success("✅ Objetivo renovado.")
                                        st.rerun()
                                with col_sb2:
                                    if st.form_submit_button("✅ Marcar como completado", disabled=_is_viewer):
                                        dbm.marcar_objetivo_completado(int(ov["ID"]))
                                        st.success("✅ Marcado como completado.")
                                        st.rerun()

        # ── SECCIÓN: REBALANCEO CON ÁRBOL DE DECISIÓN ────────────────────────
        if hacer_rebalanceo:
            st.markdown("---")
            st.markdown("### ⚖️ Rebalanceo — Árbol de Decisión")
            st.info("Genera órdenes si: (1) desviación ≥ 5% del peso ideal, "
                    "(2) alpha neto > 0 (ganancia esperada > costos de broker).")

            col_ej1, col_ej2, col_ej3 = st.columns(3)
            with col_ej1:
                liq_nueva = st.number_input("Capital adicional a inyectar (ARS):", value=0, step=10_000,
                                             key="reb_liq")
            with col_ej2:
                mod_ejec = st.selectbox("Modelo objetivo:",
                                         ["Sharpe","Sortino","CVaR","Paridad de Riesgo"],
                                         key="reb_modelo")
            with col_ej3:
                comision_pct    = st.slider("Comisión broker (%):", 0.1, 1.5, 0.6, 0.1,
                                             key="reb_comision") / 100.0
                umbral_churning = st.slider("Umbral anti-churning (%):", 1, 10, 5,
                                             key="reb_churning") / 100.0

            if df_ag.empty:
                st.warning("Seleccioná una cartera con posiciones.")
            elif st.button(
                "⚡ Generar Órdenes con Árbol de Decisión",
                type="primary",
                key="btn_arbol_decision",
                disabled=_is_viewer,
            ):
                with st.spinner("Calculando órdenes óptimas..."):
                    hist_ej = cached_historico(tuple(tickers_cartera), "1y")
                    plan = ejsvc.generar_plan_rebalanceo(
                        tickers_cartera=tickers_cartera,
                        df_ag=df_ag,
                        hist_precios=hist_ej,
                        precios_ars=precios_dict,
                        modelo=mod_ejec,
                        capital_nuevo_ars=liq_nueva,
                        umbral_churning=umbral_churning,
                        comision_pct=comision_pct,
                        horizonte_dias=horizonte_dias,
                        risk_free_rate=RISK_FREE_RATE,
                    )

                    if plan["error"]:
                        st.error(plan["error"])
                    elif not plan["ejecutables"].empty or plan["reporte"]:
                        st.text(plan["reporte"])
                        ejecutables = plan["ejecutables"]
                        bloqueadas  = plan["bloqueadas"]

                        if not ejecutables.empty:
                            total_compras = ejecutables[ejecutables["tipo_op"]=="COMPRA"]["valor_nocional"].sum()
                            total_ventas  = ejecutables[ejecutables["tipo_op"]=="VENTA"]["valor_nocional"].sum()
                            total_costos  = ejecutables["costo_total"].sum()

                            tc1, tc2, tc3 = st.columns(3)
                            tc1.metric("Total a comprar", f"${total_compras:,.0f} ARS")
                            tc2.metric("Total a vender",  f"${total_ventas:,.0f} ARS")
                            tc3.metric("Costo broker est.", f"${total_costos:,.0f} ARS")

                            st.dataframe(
                                ejecutables.style.format({
                                    "precio_ars":     "${:,.2f}",
                                    "valor_nocional": "${:,.0f}",
                                    "costo_total":    "${:,.0f}",
                                    "alpha_esperado": "${:,.0f}",
                                    "alpha_neto":     "${:,.0f}",
                                }).apply(
                                    lambda r: ["background-color:#D4EDDA" if v == "COMPRA"
                                               else "background-color:#FADBD8" if v == "VENTA"
                                               else "" for v in r],
                                    subset=["tipo_op"], axis=0
                                ), use_container_width=True, hide_index=True,
                            )
                            ejsvc.enviar_alerta_rebalanceo(ejecutables, prop_nombre)
                            try:
                                _usr_ej = str(st.session_state.get("mq26_login_user", "") or "")
                                _tk_ej = (
                                    ejecutables["ticker"].astype(str).tolist()
                                    if "ticker" in ejecutables.columns
                                    else []
                                )
                                dbm.registrar_optimization_audit(
                                    cliente_id=cliente_id,
                                    usuario=_usr_ej[:100],
                                    accion="plan_rebalanceo_generado",
                                    modelo=str(mod_ejec),
                                    ccl=float(ccl) if ccl else None,
                                    tickers=_tk_ej,
                                    pesos=None,
                                    run_id=datetime.now().strftime("%Y%m%d%H%M%S"),
                                    extra={
                                        "n_filas": int(len(ejecutables)),
                                        "total_compras_ars": float(total_compras),
                                        "total_ventas_ars": float(total_ventas),
                                        "total_costos_ars": float(total_costos),
                                        "capital_nuevo_ars": float(liq_nueva),
                                        "comision_pct": float(comision_pct),
                                        "umbral_churning": float(umbral_churning),
                                        "prop_nombre": str(prop_nombre or ""),
                                    },
                                )
                            except Exception as _aud_e:
                                _log.warning("OPTIMIZATION_AUDIT plan rebalanceo: %s", _aud_e)
                            st.session_state["df_ventas_rebalanceo"] = ejecutables[
                                ejecutables["tipo_op"] == "VENTA"]
                            st.session_state["df_compras_rebalanceo"] = ejecutables[
                                ejecutables["tipo_op"] == "COMPRA"]
                            _boton_exportar(
                                ejecutables,
                                f"ordenes_{prop_nombre.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}",
                                "📥 Exportar órdenes a Excel",
                            )

                        if not bloqueadas.empty:
                            with st.expander(f"🚫 {len(bloqueadas)} órdenes bloqueadas por alpha negativo"):
                                st.dataframe(
                                    bloqueadas[["ticker","tipo_op","valor_nocional","costo_total",
                                                "alpha_neto","motivo"]].style.format({
                                        "valor_nocional": "${:,.0f}",
                                        "costo_total":    "${:,.0f}",
                                        "alpha_neto":     "${:,.0f}",
                                    }), use_container_width=True, hide_index=True
                                )

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 2: RECOMENDADOR SEMANAL
    # ══════════════════════════════════════════════════════════════════
    with sub_rec:
        cartera_actual_dict = {}
        if not df_ag.empty:
            for _, _row_rec in df_ag.iterrows():
                _t_key = str(_row_rec.get("TICKER", "")).strip()
                _cant  = int(_row_rec.get("CANTIDAD_TOTAL", 0))
                if _t_key and _cant > 0:
                    cartera_actual_dict[_t_key] = _cant

        _prop_rec   = cartera_activa.split("|")[0].strip() if "|" in cartera_activa else cartera_activa
        _df_cli_rec = (df_clientes[df_clientes["Nombre"] == _prop_rec]
                       if not df_clientes.empty else pd.DataFrame())
        perfil_activo = cliente_perfil or (
            _df_cli_rec["Perfil"].iloc[0] if not _df_cli_rec.empty else "Moderado")

        try:
            from services.tab_recomendador import render_tab_recomendador
            # MQ2-D10: email y presupuesto desde BD, con fallback a valores hardcoded
            _email_bd = ""
            _presup_bd = 500_000.0
            try:
                _email_bd  = dbm.obtener_config("recomendador_email_destino") or ""
                _presup_bd = float(dbm.obtener_config("recomendador_presupuesto_semanal") or 500_000)
                if not _email_bd and not _df_cli_rec.empty and "Email" in _df_cli_rec.columns:
                    _email_bd = str(_df_cli_rec["Email"].iloc[0] or "")
            except Exception:
                pass
            render_tab_recomendador(
                cartera_actual      = cartera_actual_dict,
                perfil_cliente      = perfil_activo,
                presupuesto_semanal = _presup_bd,
                ccl                 = ccl,
                email_destino       = _email_bd or "comercial@tudominio.com",
            )
        except Exception as e:
            st.error(f"Error en Recomendador Semanal: {e}")

        # El envío de email está integrado directamente en render_tab_recomendador

    # ══════════════════════════════════════════════════════════════════
    # SUB-TAB 3: EXPORTAR ÓRDENES (H10)
    # ══════════════════════════════════════════════════════════════════
    with sub_export:
        st.subheader("📤 Exportar Órdenes de Ejecución")
        st.markdown(
            "Genera un CSV o Excel con las órdenes calculadas, "
            "compatible con el formato de importación de brokers argentinos (IOL/Bull Market/Balanz)."
        )

        # Recuperar órdenes previamente calculadas desde sub_reb
        _df_ventas   = st.session_state.get("df_ventas_rebalanceo",  pd.DataFrame())
        _df_compras  = st.session_state.get("df_compras_rebalanceo", pd.DataFrame())
        _df_exp = pd.concat([_df_ventas, _df_compras], ignore_index=True)

        if _df_exp.empty:
            st.info("ℹ️ Primero genera las órdenes en la pestaña **Rebalanceo / Capital** para exportarlas aquí.")
        else:
            # Columnas broker-compatible
            _COLS_BROKER = {
                "ticker":          "Instrumento",
                "tipo_op":         "Tipo Orden",
                "cantidad":        "Cantidad",
                "valor_nocional":  "Monto Estimado (ARS)",
                "costo_total":     "Comision Estimada (ARS)",
                "motivo":          "Observaciones",
            }
            _df_broker = pd.DataFrame()
            for _src, _dst in _COLS_BROKER.items():
                if _src in _df_exp.columns:
                    _df_broker[_dst] = _df_exp[_src]
            _df_broker["Mercado"] = "BCBA / NYSE"
            _df_broker["Moneda"]  = "ARS"
            _df_broker["Fecha"]   = pd.Timestamp.today().strftime("%Y-%m-%d")

            st.dataframe(_df_broker, use_container_width=True, hide_index=True)

            _col_csv, _col_xl = st.columns(2)
            with _col_csv:
                _csv_bytes = _df_broker.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="⬇️ Descargar CSV (broker)",
                    data=_csv_bytes,
                    file_name=f"ordenes_MQ26_{pd.Timestamp.today().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv", use_container_width=True,
                )
            with _col_xl:
                try:
                    import io as _io
                    _buf = _io.BytesIO()
                    with pd.ExcelWriter(_buf, engine="openpyxl") as _wr:
                        _df_broker.to_excel(_wr, sheet_name="Ordenes", index=False)
                    _buf.seek(0)
                    st.download_button(
                        label="⬇️ Descargar Excel",
                        data=_buf.read(),
                        file_name=f"ordenes_MQ26_{pd.Timestamp.today().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True,
                    )
                except ImportError:
                    st.warning("Instala `openpyxl` para exportar a Excel.")
