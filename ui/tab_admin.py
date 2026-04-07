"""
Panel Admin (solo super_admin): métricas, auditoría, uso, demo, usuarios BD, Primera Cartera, Telegram.
"""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from core import db_manager as dbm


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
                    st.success("Listo. Revisá el resumen y guardá si corresponde.")
                    st.rerun()
            except Exception as e:
                st.error(f"Error al generar: {e}")

    active = cargar_recomendacion_activa()
    payload_live = st.session_state.get("pci_payload") or active

    if save_only and payload_live:
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
        if st.button("Guardar en base como semana activa + histórico", key="pci_save_db"):
            try:
                guardar_recomendacion(
                    payload_live,
                    audit_user=str(st.session_state.get("mq26_login_user") or ""),
                )
                st.success("Persistido en tabla configuracion.")
            except Exception as e:
                st.warning(f"No se pudo guardar: {e}")

    st.divider()
    st.caption("Histórico por año (clave `primera_cartera_<año>_sNN`)")
    from datetime import date

    y_hist = st.number_input("Año", min_value=2020, max_value=2035, value=date.today().year, key="pci_hist_y")
    rows = historial_recomendaciones(int(y_hist))
    if rows:
        st.dataframe(
            pd.DataFrame(
                [{"clave": r.get("_clave_config"), "semana": r.get("semana"), "presupuesto": r.get("presupuesto_ars")} for r in rows]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin registros para ese año.")


def _render_app_usuarios_admin(tenant_id: str, df_clientes: pd.DataFrame) -> None:
    """Alta / baja / vínculos de app_usuarios."""
    st.caption("Login MQ26 con usuarios persistidos en BD (si MQ26_TRY_DB_USERS esta activo).")

    rows = dbm.list_app_usuarios(tenant_id)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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
                ["inversor", "estudio", "asesor", "super_admin"],
                index=0,
                key="adm_nu_rol",
            )
            nu_rama = st.selectbox(
                "Rama UI",
                ["retail", "profesional"],
                index=1,
                key="adm_nu_rama",
                help="Inversor: retail. Estudio/asesor: profesional.",
            )
            sel_lbl = st.multiselect(
                "Clientes vinculados",
                options=opts_labels,
                default=[],
                key="adm_nu_cli",
            )
            submitted = st.form_submit_button("Crear usuario")
            if submitted:
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
            if st.button("Eliminar seleccionado", type="primary", key="adm_del_btn"):
                dbm.delete_app_usuario(int(pick["id"]))
                st.success("Usuario eliminado.")
                st.rerun()

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
            if st.button("Guardar vínculos", key="adm_lnk_save"):
                dbm.set_app_usuario_clientes(
                    int(u["id"]),
                    cids2,
                    int(def2) if def2 else None,
                )
                st.success("Vinculos actualizados.")
                st.rerun()


def render_tab_admin(ctx: dict) -> None:
    if ctx.get("user_role") != "super_admin":
        st.warning("Acceso restringido al Super Administrador.")
        return

    st.markdown(
        """
<h2 style="font-size:1.1rem;font-weight:700;color:var(--c-text);margin:0 0 1rem 0;">
    🛠 Panel de administración
</h2>
""",
        unsafe_allow_html=True,
    )
    tab_lat, tab_audit, tab_uso, tab_demo, tab_users, tab_cartera_ini, tab_growth = st.tabs(
        ["Latencia", "Auditoria", "Uso", "Demo", "Usuarios BD", "Primera Cartera", "Growth Top 3"]
    )

    with tab_lat:
        st.json({"metricas": ctx.get("metricas", {})})

    with tab_audit:
        st.caption("Historial global_param_audit (solo lectura).")
        keys = sorted(dbm.GLOBAL_PARAM_AUDIT_KEYS)
        pk = st.selectbox("Filtrar param_key", ["(todos)"] + keys, key="adm_audit_key")
        lim = st.number_input("Limite filas", min_value=20, max_value=2000, value=200, step=20)
        audits = dbm.list_global_param_audit(
            None if pk == "(todos)" else pk,
            limit=int(lim),
        )
        if audits:
            df_a = pd.DataFrame(audits)
            if "changed_at" in df_a.columns:
                df_a["changed_at"] = df_a["changed_at"].astype(str)
            st.dataframe(df_a, use_container_width=True, hide_index=True)
        else:
            st.info("Sin registros.")

    with tab_uso:
        dfc = ctx.get("df_clientes")
        n_cli = len(dfc) if dfc is not None and not getattr(dfc, "empty", True) else 0
        st.metric("Clientes visibles (tenant)", n_cli)
        st.metric("Tenant", str(ctx.get("tenant_id") or "default"))

        st.subheader("Alertas automaticas (Telegram)")
        st.caption("Requiere TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en el entorno o en configuracion.")
        prueba = st.text_input(
            "Mensaje de prueba",
            value="MQ26: prueba de alerta automatica",
            key="adm_tg_msg",
        )
        if st.button("Enviar prueba Telegram", key="adm_tg_send"):
            from services.alert_bot import enviar_telegram

            ok = enviar_telegram(prueba)
            if ok:
                st.success("Mensaje enviado (revisa el chat configurado).")
            else:
                st.warning(
                    "No se pudo enviar. Verifica token, chat_id y que el bot tenga acceso al chat."
                )

    with tab_demo:
        try:
            import config as _cfg

            demo = bool(getattr(_cfg, "DEMO_MODE", False))
        except Exception:
            demo = os.environ.get("DEMO_MODE", "").strip().lower() in ("1", "true", "yes")
        st.metric("DEMO_MODE activo (posible en esta sesion)", "Si" if demo else "No")
        st.caption(
            "El modo demo se define en variable de entorno DEMO_MODE al iniciar Streamlit; "
            "cambiarla requiere reiniciar la app."
        )

    with tab_users:
        tid = str(ctx.get("tenant_id") or "default")
        dfx = ctx.get("df_clientes")
        _render_app_usuarios_admin(tid, dfx if isinstance(dfx, pd.DataFrame) else pd.DataFrame())

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
    if st.button("Guardar favoritos del mes", type="primary", key="adm_fav_save"):
        def _parse_tickers(s: str) -> list[str]:
            parts: list[str] = []
            for chunk in (s or "").replace("\n", ",").split(","):
                u = chunk.strip().upper()
                if u:
                    parts.append(u)
            return parts

        try:
            p = save_favoritos_mes(
                _parse_tickers(rf_txt),
                _parse_tickers(rv_txt),
                published_by=pub_by,
                disclaimer=disc,
            )
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
