"""
Panel Admin (solo super_admin): métricas, auditoría, uso, demo, usuarios BD, Primera Cartera, Telegram.

P0-RBAC-01: mutaciones del panel usan `_require_panel_admin_write` → `can_action(ctx, "panel_admin_write")`
(inventario docs/product/PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md §4a).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from core import db_manager as dbm
from services.precio_cache_service import estado_circuit_breaker
from ui.rbac import can_action
from ui.mq26_ux import dataframe_auto_height


def _require_panel_admin_write(ctx: dict) -> bool:
    """Defensa en profundidad: mutaciones del panel (rol UI ya limitado a super_admin)."""
    if can_action(ctx, "panel_admin_write"):
        return True
    st.warning("No tenés permiso para esta acción de administración.")
    return False


def _actor_panel(ctx: dict) -> str:
    """Usuario para auditoría P1-ADM-01 (MQ26 o app según ctx)."""
    return str(ctx.get("login_user") or st.session_state.get("mq26_login_user") or "").strip()[:200]


def _collect_degradaciones(ctx: dict) -> list[dict]:
    """
    Construye eventos de degradación visibles para operación.
    """
    eventos: list[dict] = []
    ss = st.session_state

    # Estado de cobertura de precios inferida/live.
    cov = float(ctx.get("price_coverage_pct") or 0.0)
    tickers_sin = ctx.get("tickers_sin_precio") or []
    if cov < 95.0 or tickers_sin:
        sev = "ALTA" if cov < 85.0 else "MEDIA"
        eventos.append(
            {
                "severidad": sev,
                "evento": "cobertura_precios_baja",
                "detalle": f"Cobertura {cov:.1f}% | sin precio: {len(tickers_sin)}",
                "accion": "Revisar feed/live, fallback BD y universo habilitado.",
            }
        )

    # Circuit breaker de yfinance.
    cb = estado_circuit_breaker()
    if bool(cb.get("degradado")):
        eventos.append(
            {
                "severidad": "MEDIA",
                "evento": "circuit_breaker_yfinance_activo",
                "detalle": (
                    f"fallos_recientes={int(cb.get('fallos_recientes') or 0)} | "
                    f"cooldown={int(cb.get('segundos_restantes') or 0)}s"
                ),
                "accion": "Esperar cooldown o usar fuentes alternas hasta recuperación.",
            }
        )

    # Login BD degradado (fallback local).
    auth_flags = [k for k in ss.keys() if str(k).endswith("_degraded_auth") and bool(ss.get(k))]
    if auth_flags:
        eventos.append(
            {
                "severidad": "ALTA",
                "evento": "auth_bd_degradado",
                "detalle": f"flags={', '.join(auth_flags)}",
                "accion": "Verificar DB de usuarios, credenciales y conectividad.",
            }
        )

    # Degradación UI inversor reportada por tab.
    if bool(ss.get("inv_degradado_ui")):
        eventos.append(
            {
                "severidad": "MEDIA",
                "evento": "tab_inversor_modo_degradado",
                "detalle": "Se ejecutaron bloques con fallback por excepción no fatal.",
                "accion": "Validar datos antes de confirmar operaciones y revisar logs.",
            }
        )

    if not eventos:
        eventos.append(
            {
                "severidad": "OK",
                "evento": "sin_degradaciones_activas",
                "detalle": "No se detectaron banderas activas de degradación.",
                "accion": "Mantener monitoreo.",
            }
        )
    return eventos


def _render_tablero_degradaciones(ctx: dict) -> None:
    st.markdown("#### Tablero de degradaciones")
    st.caption(
        "Vista operativa en tiempo real (sesión actual): cobertura de precios, "
        "circuit breaker, auth degradado y banderas UI."
    )
    eventos = _collect_degradaciones(ctx)
    df = pd.DataFrame(eventos)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=dataframe_auto_height(df),
    )

    crit = sum(1 for e in eventos if e.get("severidad") == "ALTA")
    med = sum(1 for e in eventos if e.get("severidad") == "MEDIA")
    ok = sum(1 for e in eventos if e.get("severidad") == "OK")
    c1, c2, c3 = st.columns(3)
    c1.metric("ALTA", crit)
    c2.metric("MEDIA", med)
    c3.metric("OK", ok)

    st.info(
        "Runbook: `docs/RUNBOOK_INCIDENTES_DEGRADACIONES.md`",
        icon="🧭",
    )


def _render_primera_cartera_admin(ctx: dict) -> None:
    """Generador semanal Mi Primera Cartera (Super Admin)."""
    from services.primera_cartera import (
        cargar_recomendacion_activa,
        construir_payload_completo,
        generar_narrativa_semana,
        guardar_recomendacion,
        historial_recomendaciones,
        numero_semana_del_año,
        presupuesto_semana,
    )
    from services.reporte_primera_cartera import generar_html_semana

    st.subheader("Mi Primera Cartera de Inversiones")
    st.caption(
        "Recomendaciones semanales educativas en ARS (2–3 activos). "
        "La generación puede tardar por datos de mercado y el motor de scoring."
    )

    ccl_def = float(ctx.get("ccl") or 0) or 1400.0
    ccl_in = st.number_input("CCL referencia (ARS/USD)", min_value=1.0, value=ccl_def, step=10.0, key="pci_ccl")
    n_rec = st.slider("Cantidad de recomendaciones", min_value=2, max_value=3, value=3, key="pci_n")
    min_sc = st.number_input("Score mínimo", min_value=0.0, max_value=100.0, value=45.0, step=1.0, key="pci_min")
    nota = st.text_area("Nota opcional (aparece en resumen e informe)", key="pci_nota", height=68)

    col_g, col_sv = st.columns(2)
    with col_g:
        gen = st.button("Generar recomendación semanal", type="primary", key="pci_gen")
    with col_sv:
        save_only = st.button("Editar nota y re-guardar activa", key="pci_resave")

    if gen:
        if _require_panel_admin_write(ctx):
            with st.spinner("Calculando scores y precios…"):
                try:
                    payload = construir_payload_completo(
                        ccl_in,
                        n=int(n_rec),
                        min_score=float(min_sc),
                        nota_admin=nota,
                    )
                    if not payload:
                        st.warning("No hubo activos que cumplan el score mínimo. Bajá el umbral o revisá el universo.")
                        st.session_state.pop("pci_payload", None)
                    else:
                        st.session_state["pci_payload"] = payload
                        st.session_state["pci_narrativa_preview"] = payload.get("resumen_ejecutivo", "")
                        dbm.registrar_admin_audit_event(
                            "primera_cartera.generar_preview",
                            actor=_actor_panel(ctx),
                            tenant_id=str(ctx.get("tenant_id") or "default"),
                            detail={
                                "semana": payload.get("semana"),
                                "anio": payload.get("anio"),
                                "n_items": len(payload.get("items") or []),
                            },
                        )
                        st.success("Listo. Revisá el resumen y guardá si corresponde.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al generar: {e}")

    active = cargar_recomendacion_activa()
    payload_live = st.session_state.get("pci_payload") or active

    if save_only and payload_live:
        if _require_panel_admin_write(ctx):
            merged = dict(payload_live)
            narr_upd = generar_narrativa_semana(
                merged.get("items") or [],
                float(merged.get("presupuesto_ars") or presupuesto_semana()),
                float(merged.get("ccl") or ccl_in),
                nota_admin=nota,
            )
            merged["nota"] = narr_upd["nota"]
            merged["resumen_ejecutivo"] = narr_upd["resumen_ejecutivo"]
            merged["items"] = narr_upd["items"]
            try:
                guardar_recomendacion(merged, audit_user=str(st.session_state.get("mq26_login_user") or ""))
                dbm.registrar_admin_audit_event(
                    "primera_cartera.nota_reguardada",
                    actor=_actor_panel(ctx),
                    tenant_id=str(ctx.get("tenant_id") or "default"),
                    detail={
                        "semana": merged.get("semana"),
                        "anio": merged.get("anio"),
                    },
                )
                st.session_state["pci_payload"] = merged
                st.session_state["pci_narrativa_preview"] = merged.get("resumen_ejecutivo", "")
                st.success("Recomendación activa actualizada (nota).")
                st.rerun()
            except Exception as e:
                st.warning(f"No se pudo guardar: {e}")

    prev = st.session_state.get("pci_narrativa_preview")
    if prev:
        st.text_area("Vista previa del resumen", value=prev, height=220, disabled=True, key="pci_preview_txt")

    if payload_live:
        sem_r = payload_live.get("semana")
        anio_r = payload_live.get("anio")
        try:
            sem_int = int(sem_r)
        except (TypeError, ValueError):
            sem_int = numero_semana_del_año()
        try:
            anio_int = int(anio_r)
        except (TypeError, ValueError):
            from datetime import date

            anio_int = date.today().year
        html_doc = generar_html_semana(payload_live)
        st.download_button(
            label="Descargar HTML (imprimible/PDF)",
            data=html_doc.encode("utf-8"),
            file_name=f"primera_cartera_s{sem_int}_{anio_int}.html",
            mime="text/html",
            use_container_width=True,
            key="pci_dl_html",
        )
        st.checkbox(
            "Confirmo persistir en base esta semana como activa + histórico (clave `primera_cartera_*`).",
            key="pci_save_db_ack",
        )
        if st.button(
            "Guardar en base como semana activa + histórico",
            key="pci_save_db",
            disabled=not st.session_state.get("pci_save_db_ack"),
        ):
            if _require_panel_admin_write(ctx):
                try:
                    guardar_recomendacion(
                        payload_live,
                        audit_user=str(st.session_state.get("mq26_login_user") or ""),
                    )
                    dbm.registrar_admin_audit_event(
                        "primera_cartera.persist_db",
                        actor=_actor_panel(ctx),
                        tenant_id=str(ctx.get("tenant_id") or "default"),
                        detail={
                            "semana": payload_live.get("semana"),
                            "anio": payload_live.get("anio"),
                            "n_items": len(payload_live.get("items") or []),
                        },
                    )
                    st.session_state["pci_save_db_ack"] = False
                    st.success("Persistido en tabla configuracion.")
                except Exception as e:
                    st.warning(f"No se pudo guardar: {e}")

    st.divider()
    st.caption("Histórico por año (clave `primera_cartera_<año>_sNN`)")
    from datetime import date

    y_hist = st.number_input("Año", min_value=2020, max_value=2035, value=date.today().year, key="pci_hist_y")
    rows = historial_recomendaciones(int(y_hist))
    if rows:
        _df_pci_hist = pd.DataFrame(
            [{"clave": r.get("_clave_config"), "semana": r.get("semana"), "presupuesto": r.get("presupuesto_ars")} for r in rows]
        )
        st.dataframe(
            _df_pci_hist,
            use_container_width=True,
            hide_index=True,
            height=dataframe_auto_height(_df_pci_hist),
        )
    else:
        st.info("Sin registros para ese año.")


def _render_app_usuarios_admin(ctx: dict, tenant_id: str, df_clientes: pd.DataFrame) -> None:
    """Alta / baja / vínculos de app_usuarios."""
    st.caption("Login MQ26 con usuarios persistidos en BD (si MQ26_TRY_DB_USERS esta activo).")

    rows = dbm.list_app_usuarios(tenant_id)
    if rows:
        _df_app_u = pd.DataFrame(rows)
        st.dataframe(
            _df_app_u,
            use_container_width=True,
            hide_index=True,
            height=dataframe_auto_height(_df_app_u),
        )
    else:
        st.info("No hay usuarios en BD para este tenant.")

    opts_ids: list[int] = []
    opts_labels: list[str] = []
    if df_clientes is not None and not df_clientes.empty and "ID" in df_clientes.columns:
        for _, r in df_clientes.iterrows():
            cid = int(r["ID"])
            nom = str(r.get("Nombre", cid))
            opts_ids.append(cid)
            opts_labels.append(f"{cid} — {nom}")

    id_map = dict(zip(opts_labels, opts_ids, strict=True))

    with st.expander("Alta de usuario", expanded=False):
        with st.form("adm_nuevo_usuario"):
            nu_user = st.text_input("Usuario (unico por tenant)", key="adm_nu_user")
            nu_pwd = st.text_input("Contraseña (min. 8)", type="password", key="adm_nu_pwd")
            nu_rol = st.selectbox(
                "Rol en BD",
                ["inversor", "estudio", "super_admin"],
                index=0,
                key="adm_nu_rol",
            )
            nu_rama = st.selectbox(
                "Rama UI",
                ["retail", "profesional"],
                index=1,
                key="adm_nu_rama",
                help="Inversor: retail. Estudio: profesional.",
            )
            sel_lbl = st.multiselect(
                "Clientes vinculados",
                options=opts_labels,
                default=[],
                key="adm_nu_cli",
            )
            st.checkbox(
                "Confirmo crear este usuario en el tenant con el rol indicado.",
                key="adm_nu_ack",
            )
            submitted = st.form_submit_button(
                "Crear usuario",
                disabled=not st.session_state.get("adm_nu_ack"),
            )
            if submitted:
                if not _require_panel_admin_write(ctx):
                    pass
                else:
                    cids = [id_map[x] for x in sel_lbl if x in id_map]
                    def_cid = cids[0] if len(cids) == 1 else (cids[0] if cids else None)
                    try:
                        uid = dbm.create_app_usuario(
                            tenant_id,
                            nu_user,
                            nu_pwd,
                            nu_rol,
                            nu_rama,
                            def_cid,
                            cids,
                        )
                        dbm.registrar_admin_audit_event(
                            "app_usuario.create",
                            actor=_actor_panel(ctx),
                            tenant_id=tenant_id,
                            detail={
                                "usuario_id": int(uid),
                                "username": nu_user,
                                "rol": nu_rol,
                                "rama": nu_rama,
                                "cliente_ids": cids,
                            },
                        )
                        st.session_state["adm_nu_ack"] = False
                        st.success(f"Usuario creado (id={uid}).")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    with st.expander("Eliminar usuario", expanded=False):
        if not rows:
            st.caption("Nada que eliminar.")
        else:
            pick = st.selectbox(
                "Usuario",
                options=rows,
                format_func=lambda r: f"{r['username']} (id={r['id']}, {r['rol']})",
                key="adm_del_pick",
            )
            st.checkbox(
                "Confirmo la eliminación permanente del usuario seleccionado (irreversible).",
                key="adm_del_ack",
            )
            if st.button(
                "Eliminar seleccionado",
                type="primary",
                key="adm_del_btn",
                disabled=not st.session_state.get("adm_del_ack"),
            ):
                if _require_panel_admin_write(ctx):
                    try:
                        dbm.delete_app_usuario(int(pick["id"]), tenant_id=tenant_id)
                        dbm.registrar_admin_audit_event(
                            "app_usuario.delete",
                            actor=_actor_panel(ctx),
                            tenant_id=tenant_id,
                            detail={
                                "usuario_id": int(pick["id"]),
                                "username": str(pick.get("username") or ""),
                            },
                        )
                        st.session_state["adm_del_ack"] = False
                        st.success("Usuario eliminado.")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

    with st.expander("Actualizar clientes vinculados", expanded=False):
        if not rows:
            st.caption("Nada que editar.")
        else:
            u = st.selectbox(
                "Usuario",
                options=rows,
                format_func=lambda r: f"{r['username']} (id={r['id']})",
                key="adm_lnk_user",
            )
            default_lbls = []
            for cid in u.get("cliente_ids", []):
                match = next((l for l in opts_labels if l.startswith(f"{cid} — ")), None)
                if match:
                    default_lbls.append(match)
            sel2 = st.multiselect(
                "Nuevos clientes",
                options=opts_labels,
                default=default_lbls,
                key="adm_lnk_cli",
            )
            cids2 = [id_map[x] for x in sel2 if x in id_map]
            def2 = st.number_input(
                "cliente_default_id (0 = ninguno)",
                min_value=0,
                value=int(u.get("cliente_default_id") or 0),
                key="adm_lnk_def",
            )
            st.checkbox(
                "Confirmo actualizar los clientes vinculados para este usuario.",
                key="adm_lnk_ack",
            )
            if st.button(
                "Guardar vínculos",
                key="adm_lnk_save",
                disabled=not st.session_state.get("adm_lnk_ack"),
            ):
                if _require_panel_admin_write(ctx):
                    dbm.set_app_usuario_clientes(
                        int(u["id"]),
                        cids2,
                        int(def2) if def2 else None,
                    )
                    dbm.registrar_admin_audit_event(
                        "app_usuario.vinculos",
                        actor=_actor_panel(ctx),
                        tenant_id=tenant_id,
                        detail={
                            "usuario_id": int(u["id"]),
                            "username": str(u.get("username") or ""),
                            "cliente_ids": cids2,
                            "cliente_default_id": int(def2) if def2 else None,
                        },
                    )
                    st.session_state["adm_lnk_ack"] = False
                    st.success("Vinculos actualizados.")
                    st.rerun()


def render_tab_admin(ctx: dict) -> None:
    if ctx.get("user_role") != "super_admin":
        st.warning("Acceso restringido al Super Administrador.")
        return

    st.markdown(
        """
<h2 class="mq-admin-panel-h2">
    🛠 Panel de administración
</h2>
""",
        unsafe_allow_html=True,
    )
    tab_lat, tab_audit, tab_uso, tab_inc, tab_demo, tab_users, tab_cartera_ini, tab_growth = st.tabs(
        [
            "Latencia",
            "Auditoria",
            "Uso",
            "Incidentes",
            "Demo",
            "Usuarios BD",
            "Primera Cartera",
            "Growth Top 3",
        ]
    )

    with tab_lat:
        st.json({"metricas": ctx.get("metricas", {})})

    with tab_audit:
        st.caption(
            "Historial **global_param_audit** (solo lectura): parámetros globales "
            "(`RISK_FREE_RATE`, etc.) y eventos de panel **ADMIN.*** (P1-ADM-01: usuarios, "
            "primera cartera, demo, Telegram, favoritos del mes)."
        )
        keys = sorted(dbm.GLOBAL_PARAM_AUDIT_KEYS | {"(solo ADMIN.*)"})
        pk = st.selectbox("Filtrar param_key", ["(todos)"] + keys, key="adm_audit_key")
        lim = st.number_input("Limite filas", min_value=20, max_value=2000, value=200, step=20)
        if pk == "(todos)":
            audits = dbm.list_global_param_audit(None, limit=int(lim))
        elif pk == "(solo ADMIN.*)":
            audits = dbm.list_global_param_audit(
                None, limit=int(lim), param_prefix=dbm.ADMIN_AUDIT_KEY_PREFIX
            )
        else:
            audits = dbm.list_global_param_audit(pk, limit=int(lim))
        if audits:
            df_a = pd.DataFrame(audits)
            if "changed_at" in df_a.columns:
                df_a["changed_at"] = df_a["changed_at"].astype(str)
            st.dataframe(
                df_a,
                use_container_width=True,
                hide_index=True,
                height=dataframe_auto_height(df_a),
            )
        else:
            st.info("Sin registros.")

    with tab_uso:
        st.markdown("#### Estado del sistema")

        dbm_a = ctx.get("dbm")
        tid_a = (str(ctx.get("tenant_id") or "default")).strip() or "default"
        try:
            df_cli_a = dbm_a.obtener_clientes_df(tenant_id=tid_a) if dbm_a else None
            n_cli = len(df_cli_a) if df_cli_a is not None and not df_cli_a.empty else 0
        except Exception:
            n_cli = 0

        try:
            from sqlalchemy import text as _text

            from core.db_manager import get_engine as _ge

            with _ge().connect() as _c:
                n_scores = _c.execute(_text("SELECT COUNT(*) FROM scores_historicos")).scalar() or 0
                ultima_fecha = _c.execute(_text("SELECT MAX(fecha) FROM scores_historicos")).scalar() or "—"
        except Exception:
            n_scores = 0
            ultima_fecha = "—"

        _df_ctx = ctx.get("df_clientes")
        n_ctx = len(_df_ctx) if _df_ctx is not None and not getattr(_df_ctx, "empty", True) else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Clientes en BD", n_cli)
        m2.metric("Scores históricos", f"{int(n_scores):,}")
        m3.metric("Última actualización scores", str(ultima_fecha))
        m4.metric("Clientes visibles (ctx)", n_ctx)

        st.divider()

        st.markdown("#### Semáforo del estudio")
        n_rojos = int(st.session_state.get("dashboard_n_rojos", 0) or 0)
        n_amarillos = int(st.session_state.get("dashboard_n_amarillos", 0) or 0)
        n_verdes = int(st.session_state.get("dashboard_n_verdes", 0) or 0)
        if n_rojos + n_amarillos + n_verdes > 0:
            col_r, col_a, col_v = st.columns(3)
            col_r.metric("🔴 Urgentes", n_rojos, help="Semáforo rojo en torre Estudio (prioridad máxima)")
            col_a.metric("🟡 Para revisar", n_amarillos, help="Semáforo amarillo en torre Estudio")
            col_v.metric("🟢 OK", n_verdes, help="Semáforo verde en torre Estudio")
        else:
            st.info("Abrí primero el tab Mis Clientes (Estudio) para que los semáforos se calculen.")

        st.divider()
        st.subheader("Alertas automaticas (Telegram)")
        st.caption(
            "Requiere credenciales en el entorno o en `configuracion` (no se muestran ni se guardan en esta vista)."
        )
        prueba = st.text_input(
            "Mensaje de prueba",
            value="MQ26: prueba de alerta automatica",
            key="adm_tg_msg",
        )
        st.checkbox(
            "Confirmo enviar un mensaje de prueba al chat de Telegram configurado.",
            key="adm_tg_ack",
        )
        if st.button(
            "Enviar prueba Telegram",
            key="adm_tg_send",
            disabled=not st.session_state.get("adm_tg_ack"),
        ):
            if _require_panel_admin_write(ctx):
                from services.alert_bot import enviar_telegram

                ok = enviar_telegram(prueba)
                if ok:
                    dbm.registrar_admin_audit_event(
                        "telegram.prueba_enviada",
                        actor=_actor_panel(ctx),
                        tenant_id=str(ctx.get("tenant_id") or "default"),
                        detail={"mensaje_chars": len(prueba or "")},
                    )
                    st.session_state["adm_tg_ack"] = False
                    st.success("Mensaje enviado (revisa el chat configurado).")
                else:
                    st.warning(
                        "No se pudo enviar. Verifica token, chat_id y que el bot tenga acceso al chat."
                    )

    with tab_inc:
        _render_tablero_degradaciones(ctx)

    with tab_demo:
        st.markdown("#### Modo demo")
        st.caption(
            "El modo demo usa una base SQLite con **10 clientes** sintéticos "
            "(conservador a muy arriesgado) y transacciones desde 2022. "
            "Útil para demostraciones sin datos reales; no modifica la BD productiva."
        )

        try:
            import config as _cfg_demo

            demo_activo = bool(getattr(_cfg_demo, "DEMO_MODE", False))
        except Exception:
            demo_activo = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

        if demo_activo:
            st.success("✓ Modo demo ACTIVO — mostrando datos sintéticos")
        else:
            st.info("Modo demo INACTIVO — mostrando datos reales")

        st.divider()
        st.markdown("**Para activar el modo demo:**")
        st.code("DEMO_MODE=true streamlit run run_mq26.py", language="bash")
        st.caption(
            "Al activarse, el sistema genera automáticamente la BD demo si no existe. "
            "Para regenerar datos: botón inferior o `python scripts/generate_demo_data.py`."
        )

        _def_demo = os.environ.get("DEMO_DB_PATH") or str(
            Path(os.environ.get("TEMP", os.path.expanduser("~"))) / "mq26_demo.db"
        )

        st.checkbox(
            "Confirmo sobrescribir el archivo de BD demo en esta ruta (solo entorno actual).",
            key="adm_demo_regen_ack",
        )
        if st.button(
            "🔄 Regenerar datos de demo (no afecta BD real)",
            key="btn_regen_demo",
            disabled=not st.session_state.get("adm_demo_regen_ack"),
        ):
            if _require_panel_admin_write(ctx):
                with st.spinner("Generando datos demo..."):
                    try:
                        import sys
                        from pathlib import Path as _Path

                        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
                        from scripts.generate_demo_data import run as _run_demo

                        demo_path = os.environ.get("DEMO_DB_PATH") or _def_demo
                        _run_demo(demo_path)
                        dbm.registrar_admin_audit_event(
                            "demo.regenerada",
                            actor=_actor_panel(ctx),
                            tenant_id=str(ctx.get("tenant_id") or "default"),
                            detail={"demo_path": str(demo_path)[:400]},
                        )
                        st.session_state["adm_demo_regen_ack"] = False
                        st.success(f"✓ BD demo generada en {demo_path}")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.toggle(
            "DEMO_MODE activo (solo informativo)",
            key="demo_mode_toggle",
            value=demo_activo,
            disabled=True,
        )

    with tab_users:
        tid = str(ctx.get("tenant_id") or "default")
        dfx = ctx.get("df_clientes")
        _render_app_usuarios_admin(ctx, tid, dfx if isinstance(dfx, pd.DataFrame) else pd.DataFrame())

    with tab_cartera_ini:
        _render_primera_cartera_admin(ctx)

    with tab_growth:
        _render_growth_top3_admin(ctx)


def _render_growth_top3_admin(ctx: dict) -> None:
    """Top 3 educativo para redes desde universo_df (sin recomendación personalizada)."""
    from services.contenido_mercado import DISCLAIMER_REDES, generar_top3_redes
    from services.favoritos_mes import load_favoritos_mes, save_favoritos_mes

    st.subheader("Growth — Favoritos del mes (recomendador)")
    st.caption(
        "Convicción del estudio publicada una sola vez: prioriza esos tickers en el motor de capital nuevo "
        "(tras el orden por déficit RF y momentum). Queda registro de fecha y usuario."
    )
    doc = load_favoritos_mes()
    c1, c2 = st.columns(2)
    with c1:
        rf_txt = st.text_area(
            "Tickers RF (uno por línea o separados por coma)",
            value=", ".join(doc.get("rf") or []),
            height=90,
            key="adm_fav_rf",
        )
    with c2:
        rv_txt = st.text_area(
            "Tickers RV (uno por línea o separados por coma)",
            value=", ".join(doc.get("rv") or []),
            height=90,
            key="adm_fav_rv",
        )
    disc = st.text_input(
        "Disclaimer (opcional, se guarda en JSON)",
        value=str(doc.get("disclaimer") or ""),
        key="adm_fav_disc",
    )
    pub_by = st.text_input(
        "Publicado por (auditoría)",
        value=str(st.session_state.get("mq26_login_user") or doc.get("published_by") or ""),
        key="adm_fav_pubby",
    )
    st.checkbox(
        "Confirmo publicar favoritos del mes (archivo JSON operativo).",
        key="adm_fav_save_ack",
    )
    if st.button(
        "Guardar favoritos del mes",
        type="primary",
        key="adm_fav_save",
        disabled=not st.session_state.get("adm_fav_save_ack"),
    ):
        if not _require_panel_admin_write(ctx):
            pass
        else:
            def _parse_tickers(s: str) -> list[str]:
                parts: list[str] = []
                for chunk in (s or "").replace("\n", ",").split(","):
                    u = chunk.strip().upper()
                    if u:
                        parts.append(u)
                return parts

            try:
                _rf = _parse_tickers(rf_txt)
                _rv = _parse_tickers(rv_txt)
                p = save_favoritos_mes(
                    _rf,
                    _rv,
                    published_by=pub_by,
                    disclaimer=disc,
                )
                dbm.registrar_admin_audit_event(
                    "growth.favoritos_mes_guardados",
                    actor=_actor_panel(ctx),
                    tenant_id=str(ctx.get("tenant_id") or "default"),
                    detail={
                        "rf_tickers": len(_rf),
                        "rv_tickers": len(_rv),
                        "published_by": (pub_by or "")[:120],
                    },
                )
                st.session_state["adm_fav_save_ack"] = False
                st.success(f"Guardado en {p.name}. Publicado: {load_favoritos_mes().get('published_at', '')}")
                st.rerun()
            except OSError as e:
                st.error(f"No se pudo guardar: {e}")

    if doc.get("published_at"):
        st.caption(
            f"Última publicación: {doc.get('published_at')} — por {doc.get('published_by') or '(sin usuario)'}"
        )

    st.divider()
    st.subheader("Growth — Top 3 de la semana (redes)")
    st.caption(
        "Genera texto listo para copiar. Uso educativo; cada salida incluye disclaimer legal."
    )
    udf = ctx.get("universo_df")
    if udf is None or (hasattr(udf, "empty") and udf.empty):
        st.info("Cargá el universo en la app (motor de datos) para generar contenido.")
        return

    tit = st.text_input("Título / hook", value="Tres ideas para mirar esta semana", key="adm_growth_tit")
    n_top = st.slider("Cantidad de bullets", 2, 5, 3, key="adm_growth_n")

    if st.button("Generar texto", type="primary", key="adm_growth_gen"):
        out = generar_top3_redes(udf, n=int(n_top), titulo_semana=tit or "Ideas de la semana")
        st.session_state["adm_growth_last"] = out

    last = st.session_state.get("adm_growth_last")
    if last:
        st.text_area(
            "Vista previa",
            value=last.get("texto_plano", ""),
            height=260,
            key="adm_growth_preview",
        )
        st.caption(DISCLAIMER_REDES)
