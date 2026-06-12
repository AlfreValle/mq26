"""
ui/cartera/libro_mayor.py — sub-tab Libro Mayor (transaccional + altas/bajas).

Extraído de ui/tab_cartera.py (Fase 2.1).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from ui.mq26_ux import dataframe_auto_height
from ui.rbac import can_action as _can_action_rbac


def _render_libro_mayor(ctx, df_ag, tickers_cartera, precios_dict, ccl,
                        cartera_activa, df_clientes, cs, dbm, lm, bi, gr,
                        engine_data, BASE_DIR, _boton_exportar):
    """Sub-tab 5: Libro Mayor - Importar | Operaciones | Gmail."""
    _viewer_readonly = not _can_action_rbac(ctx, "write")
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
