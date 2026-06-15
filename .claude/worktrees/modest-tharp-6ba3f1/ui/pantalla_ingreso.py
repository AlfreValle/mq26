"""
ui/pantalla_ingreso.py — Selección y creación de cliente.
Rediseño v9: hero minimalista, cards limpias, feedback inmediato.
"""
from __future__ import annotations

import html as html_module
import os
from datetime import datetime

import streamlit as st


def render_pantalla_ingreso(
    dbm,
    app_title: str = "MQ26",
    app_icon: str = "📈",
    *,
    tenant_id: str | None = None,
) -> None:
    """
    Pantalla de selección/creación de cliente.
    Llama a st.stop() si no se selecciona cliente.
    """
    _icon = html_module.escape(app_icon)
    _title = html_module.escape(app_title)

    # ── Hero: mismas clases que run_mq26._pantalla_ingreso (design system) ─────
    st.markdown(
        f"""
    <div class="mq-motion-page-fade mq-login-hero">
        <div class="mq-login-hero-icon" aria-hidden="true">{_icon}</div>
        <h1>Master Quant</h1>
        <p>¿Con qué cartera trabajamos hoy?</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col_sel, col_sep, col_nuevo = st.columns([5, 1, 5])

    # ── MEJORA 42: Selector de cliente existente ──────────────────────────────
    with col_sel:
        st.markdown(
            '<p class="mq-login-col-label">Cliente existente</p>',
            unsafe_allow_html=True,
        )

        _tid = (tenant_id or os.environ.get("MQ26_DB_TENANT_ID") or "default").strip() or "default"
        df_cli = dbm.obtener_clientes_df(tenant_id=_tid)

        if df_cli.empty:
            st.markdown(
                """
            <div class="mq-login-empty">
                <p>Sin clientes aún.<br>Creá el primero al lado →</p>
            </div>""",
                unsafe_allow_html=True,
            )
        else:
            opciones = ["— Elegir —"] + df_cli["Nombre"].tolist()
            sel = st.selectbox(
                "Cliente",
                opciones,
                key="ing_sel_cliente",
                label_visibility="collapsed",
            )
            if sel != "— Elegir —":
                row = df_cli[df_cli["Nombre"] == sel].iloc[0]
                sel_esc = html_module.escape(sel)
                perfil_raw = str(row.get("Perfil", ""))
                perfil_esc = html_module.escape(perfil_raw)

                # ── MEJORA 43: Card de resumen del cliente seleccionado ────────
                perfil_color = {
                    "Conservador": "#10b981",
                    "Moderado": "#f59e0b",
                    "Agresivo": "#ef4444",
                    "Arriesgado": "#ef4444",
                    "Muy arriesgado": "#dc2626",
                }.get(perfil_raw, "#3b82f6")

                rgb = ",".join(
                    str(int(perfil_color.lstrip("#")[i : i + 2], 16)) for i in (0, 2, 4)
                )
                horiz_esc = html_module.escape(str(row.get("Horizonte", "1 año")))
                cap_usd = float(row.get("Capital_USD", 0) or 0)

                st.markdown(
                    f"""
                <div class="mq-login-client-card">
                    <div class="mq-login-client-head">
                        <div>
                            <div class="mq-login-client-title">{sel_esc}</div>
                        </div>
                        <span class="mq-login-badge-perfil"
                            style="background:rgba({rgb},0.15);color:{perfil_color};">{perfil_esc}</span>
                    </div>
                    <div class="mq-login-grid-2">
                        <div>
                            <div class="mq-inv-kpi-label">Horizonte</div>
                            <div class="mq-login-kpi-val">{horiz_esc}</div>
                        </div>
                        <div>
                            <div class="mq-inv-kpi-label">Capital inicial</div>
                            <div class="mq-login-kpi-val-mono">USD {cap_usd:,.0f}</div>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                # ── MEJORA 44: Botón de ingreso prominente ────────────────────
                st.markdown(
                    '<div class="mq-login-spacer-md"></div>',
                    unsafe_allow_html=True,
                )
                if st.button(
                    "Ingresar →",
                    type="primary",
                    use_container_width=True,
                    key="btn_ingresar",
                ):
                    st.session_state.update({
                        "cliente_id":               int(row["ID"]),
                        "cliente_nombre":           sel,
                        "cliente_perfil":           row["Perfil"],
                        "cliente_horizonte_label":  row.get("Horizonte", "1 año"),
                    })
                    st.rerun()

    # ── MEJORA 45: Separador vertical ─────────────────────────────────────────
    with col_sep:
        st.markdown(
            """
        <div class="mq-login-vsep">
            <div class="mq-login-vsep-line"></div>
            <span class="mq-login-vsep-mid">o</span>
            <div class="mq-login-vsep-line"></div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # ── MEJORA 46: Formulario nuevo cliente rediseñado ─────────────────────────
    with col_nuevo:
        st.markdown(
            '<p class="mq-login-col-label">Nuevo cliente</p>',
            unsafe_allow_html=True,
        )

        # ── MEJORA 47: Form sin borde por defecto (aplicado via CSS) ──────────
        with st.form("form_nuevo_cliente_ingreso", clear_on_submit=True):
            nc_nombre = st.text_input(
                "Nombre completo",
                placeholder="Ej: María Fernández",
                key="nc_nombre",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                nc_perfil = st.selectbox(
                    "Perfil de riesgo",
                    ["Conservador", "Moderado", "Arriesgado", "Muy arriesgado"],
                    help="Conservador: preserva capital. Moderado: balance. "
                         "Arriesgado/Muy arriesgado: maximiza retorno.",
                )
            with col_b:
                nc_horiz = st.selectbox(
                    "Horizonte",
                    ["1 mes", "3 meses", "6 meses",
                     "1 año", "3 años", "+5 años"],
                    index=3,
                )

            col_c, col_d = st.columns(2)
            with col_c:
                nc_tipo = st.selectbox("Tipo", ["Persona", "Empresa"])
            with col_d:
                nc_capital = st.number_input(
                    "Capital inicial (USD)",
                    min_value=0.0,
                    value=10_000.0,
                    step=1_000.0,
                    format="%.0f",
                )

            # ── MEJORA 48: Submit con estado de carga ──────────────────────────
            submitted = st.form_submit_button(
                "Crear cliente",
                type="primary",
                use_container_width=True,
            )
            if submitted:
                if not nc_nombre.strip():
                    st.error("El nombre es obligatorio.")
                else:
                    nuevo_id = dbm.registrar_cliente(
                        nc_nombre.strip(), nc_perfil,
                        nc_capital, nc_tipo, nc_horiz,
                    )
                    st.session_state.update({
                        "cliente_id":              nuevo_id,
                        "cliente_nombre":          nc_nombre.strip(),
                        "cliente_perfil":          nc_perfil,
                        "cliente_horizonte_label": nc_horiz,
                    })
                    st.success(f"✓ {nc_nombre.strip()} creado")
                    st.rerun()

    # ── MEJORA 49: Footer de versión ──────────────────────────────────────────
    _y = datetime.now().year
    st.markdown(
        f"""
    <div class="mq-login-footer">
        <span>Master Quant · {_y}</span>
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.stop()
