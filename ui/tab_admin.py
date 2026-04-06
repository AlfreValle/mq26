import streamlit as st

import pandas as pd


def render_tab_admin(ctx: dict) -> None:
    if ctx.get("user_role") != "super_admin":
        st.warning("Acceso restringido al Super Administrador.")
        return
    st.header("Panel de Administracion")
    tab_lat, tab_audit, tab_uso, tab_demo, tab_users = st.tabs(
        ["Latencia", "Auditoria", "Uso", "Demo", "Usuarios BD"]
    )
    with tab_lat:
        st.json({"metricas": ctx.get("metricas", {})})
    with tab_audit:
        st.caption("Auditoria global_param_audit")
    with tab_uso:
        st.metric("N clientes", len(ctx.get("df_clientes", [])))
    with tab_demo:
        st.toggle("DEMO_MODE", key="demo_mode_toggle")
    with tab_users:
        _render_app_usuarios_admin(ctx)


def _render_app_usuarios_admin(ctx: dict) -> None:
    """CRUD mínimo de app_usuarios + vínculo a clientes (carteras)."""
    dbm = ctx["dbm"]
    tid = (ctx.get("tenant_id") or "default").strip() or "default"

    st.markdown(
        "Usuarios con login **usuario + contraseña** guardados en la base. "
        "Si existen, se prueba primero el login contra la BD (`MQ26_TRY_DB_USERS`). "
        "**Rama**: `profesional` = estudio/asesor (tabs amplias); `retail` = inversor."
    )

    try:
        rows = dbm.list_app_usuarios(tenant_id=tid)
    except Exception as e:
        st.error(f"No se pudo leer app_usuarios: {e}")
        return

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No hay usuarios en BD todavía; el login sigue funcionando con variables `.env`.")

    try:
        df_cli = dbm.obtener_clientes_df(tenant_id=tid)
    except Exception:
        df_cli = pd.DataFrame()

    ids = df_cli["ID"].tolist() if not df_cli.empty and "ID" in df_cli.columns else []
    nombres_por_id = (
        dict(zip(df_cli["ID"].astype(int), df_cli["Nombre"])) if not df_cli.empty else {}
    )

    st.divider()
    st.subheader("Alta de usuario")
    with st.form("form_app_usuario_nuevo", clear_on_submit=True):
        nu_user = st.text_input("Usuario (único por tenant)", key="adm_nu_user")
        nu_pass = st.text_input("Contraseña (mín. 8)", type="password", key="adm_nu_pass")
        nu_rol = st.selectbox(
            "Rol",
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
        nu_def = st.selectbox(
            "Cliente predeterminado (opcional)",
            ["— Ninguno —"] + [f"{r['ID']} — {r['Nombre']}" for _, r in df_cli.iterrows()]
            if not df_cli.empty
            else ["— Ninguno —"],
            key="adm_nu_def",
        )
        labels_ms = [f"{i} — {nombres_por_id[i]}" for i in ids]
        nu_links = st.multiselect(
            "Clientes / carteras vinculadas (alcance)",
            options=labels_ms,
            key="adm_nu_links",
            help="Para inversor suele bastar uno; estudio/asesor pueden tener varios.",
        )
        submitted = st.form_submit_button("Crear usuario")

        if submitted:
            cid_def = None
            if nu_def and nu_def != "— Ninguno —":
                try:
                    cid_def = int(str(nu_def).split("—")[0].strip())
                except (TypeError, ValueError):
                    cid_def = None
            link_ids: list[int] = []
            for lbl in nu_links:
                try:
                    link_ids.append(int(str(lbl).split("—")[0].strip()))
                except (TypeError, ValueError):
                    pass
            try:
                dbm.create_app_usuario(
                    tenant_id=tid,
                    username=nu_user,
                    plain_password=nu_pass,
                    rol=nu_rol,
                    rama=nu_rama,
                    cliente_default_id=cid_def,
                    cliente_ids=link_ids,
                )
                st.success("Usuario creado. Podés iniciar sesión con usuario/clave de la BD.")
                st.rerun()
            except ValueError as ve:
                st.error(str(ve))
            except Exception as ex:
                st.exception(ex)

    if rows:
        st.divider()
        st.subheader("Eliminar usuario")
        options = {f"{r['id']} — {r['username']} ({r['rol']})": r["id"] for r in rows}
        pick = st.selectbox("Usuario a eliminar", list(options.keys()), key="adm_del_pick")
        if st.button("Eliminar seleccionado", key="adm_del_btn"):
            try:
                dbm.delete_app_usuario(options[pick])
                st.success("Eliminado.")
                st.rerun()
            except Exception as ex:
                st.exception(ex)
