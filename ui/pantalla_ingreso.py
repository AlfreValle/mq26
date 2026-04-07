"""
ui/pantalla_ingreso.py — Selección y creación de cliente.
Rediseño v9: hero minimalista, cards limpias, feedback inmediato.
"""
from __future__ import annotations

import html as html_module
from datetime import datetime

import streamlit as st


def render_pantalla_ingreso(dbm, app_title: str = "MQ26",
                             app_icon: str = "📈") -> None:
    """
    Pantalla de selección/creación de cliente.
    Llama a st.stop() si no se selecciona cliente.
    """
    _icon = html_module.escape(app_icon)
    _title = html_module.escape(app_title)

    # ── MEJORA 41: Hero section limpio ────────────────────────────────────────
    st.markdown(f"""
    <div style="
        text-align:center;
        padding: 3rem 0 2rem 0;
    ">
        <div style="
            display:inline-flex;
            align-items:center;
            justify-content:center;
            width:52px; height:52px;
            background:rgba(59,130,246,0.12);
            border:1px solid rgba(59,130,246,0.25);
            border-radius:14px;
            font-size:1.5rem;
            margin-bottom:1.25rem;
        ">{_icon}</div>
        <h1 style="
            font-family:'DM Sans',sans-serif;
            font-size:1.5rem;
            font-weight:600;
            letter-spacing:-0.03em;
            color:#f1f5f9;
            margin:0 0 0.4rem 0;
        ">Master Quant</h1>
        <p style="
            font-size:0.8125rem;
            color:#4b5563;
            margin:0;
            letter-spacing:0.01em;
        ">¿Con qué cartera trabajamos hoy?</p>
    </div>
    """, unsafe_allow_html=True)

    col_sel, col_sep, col_nuevo = st.columns([5, 1, 5])

    # ── MEJORA 42: Selector de cliente existente ──────────────────────────────
    with col_sel:
        st.markdown("""
        <p style="font-size:0.72rem;font-weight:600;color:#4b5563;
                  text-transform:uppercase;letter-spacing:0.07em;
                  margin-bottom:0.75rem;">
            Cliente existente
        </p>""", unsafe_allow_html=True)

        df_cli = dbm.obtener_clientes_df()

        if df_cli.empty:
            st.markdown("""
            <div style="
                background:#0f1117;
                border:1px dashed rgba(255,255,255,0.08);
                border-radius:12px;
                padding:2rem;
                text-align:center;
            ">
                <p style="color:#4b5563;font-size:0.8125rem;margin:0;">
                    Sin clientes aún.<br>Creá el primero al lado →
                </p>
            </div>""", unsafe_allow_html=True)
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

                st.markdown(f"""
                <div style="
                    background:#161b27;
                    border:1px solid rgba(255,255,255,0.08);
                    border-radius:12px;
                    padding:1.25rem 1.5rem;
                    margin-top:0.75rem;
                ">
                    <div style="display:flex;justify-content:space-between;
                                align-items:flex-start;margin-bottom:0.75rem;">
                        <div>
                            <div style="font-weight:600;font-size:0.9375rem;
                                        color:#f1f5f9;letter-spacing:-0.01em;">
                                {sel_esc}
                            </div>
                        </div>
                        <span style="
                            background:rgba({rgb},0.15);
                            color:{perfil_color};
                            font-size:0.65rem;font-weight:600;
                            padding:2px 8px;border-radius:999px;
                            text-transform:uppercase;letter-spacing:0.05em;
                        ">{perfil_esc}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                        <div>
                            <div style="font-size:0.65rem;color:#4b5563;
                                        text-transform:uppercase;letter-spacing:0.06em;">
                                Horizonte
                            </div>
                            <div style="font-size:0.8125rem;color:#94a3b8;margin-top:2px;">
                                {horiz_esc}
                            </div>
                        </div>
                        <div>
                            <div style="font-size:0.65rem;color:#4b5563;
                                        text-transform:uppercase;letter-spacing:0.06em;">
                                Capital inicial
                            </div>
                            <div style="font-family:'DM Mono',monospace;
                                        font-size:0.8125rem;color:#94a3b8;margin-top:2px;">
                                USD {cap_usd:,.0f}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ── MEJORA 44: Botón de ingreso prominente ────────────────────
                st.markdown("<div style='height:0.75rem'></div>",
                            unsafe_allow_html=True)
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
        st.markdown("""
        <div style="
            display:flex;
            flex-direction:column;
            align-items:center;
            height:100%;
            padding-top:2rem;
        ">
            <div style="flex:1;width:1px;background:rgba(255,255,255,0.06);"></div>
            <span style="
                font-size:0.65rem;color:#4b5563;
                padding:0.5rem 0;letter-spacing:0.05em;
            ">o</span>
            <div style="flex:1;width:1px;background:rgba(255,255,255,0.06);"></div>
        </div>
        """, unsafe_allow_html=True)

    # ── MEJORA 46: Formulario nuevo cliente rediseñado ─────────────────────────
    with col_nuevo:
        st.markdown("""
        <p style="font-size:0.72rem;font-weight:600;color:#4b5563;
                  text-transform:uppercase;letter-spacing:0.07em;
                  margin-bottom:0.75rem;">
            Nuevo cliente
        </p>""", unsafe_allow_html=True)

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
    st.markdown(f"""
    <div style="
        text-align:center;
        padding-top:3rem;
        padding-bottom:1rem;
    ">
        <span style="font-size:0.65rem;color:#1f2937;letter-spacing:0.08em;">
            Master Quant · {_y}
        </span>
    </div>
    """, unsafe_allow_html=True)

    st.stop()
