"""
tab_recomendador.py — Tab de Recomendación Semanal 60/20/20
Master Quant 26 | DSS Unificado

Renderiza en Streamlit:
  - Cartera óptima a largo plazo (ranking 60/20/20)
  - Recomendación semanal personalizada por cliente
  - Contexto macro editable
  - Botón para generar email de reporte
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from services.scoring_engine import (
    actualizar_contexto_macro,
    calcular_cartera_optima,
    escanear_universo_completo,
    obtener_contexto_macro,
)

# ─── CACHÉ SEMANAL DEL SCAN ───────────────────────────────────────────────────

@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)  # 12 horas
def _scan_cacheado(incluir_cedears, incluir_merval, incluir_bonos,
                   incluir_intl, incluir_fci, max_activos):
    return escanear_universo_completo(
        incluir_cedears=incluir_cedears,
        incluir_merval=incluir_merval,
        incluir_bonos=incluir_bonos,
        incluir_internacional=incluir_intl,
        incluir_fci=incluir_fci,
        max_activos=max_activos,
    )


# ─── RENDER PRINCIPAL ─────────────────────────────────────────────────────────

def render_tab_recomendador(
    cartera_actual: dict,   # {ticker: cantidad} de la cartera activa
    perfil_cliente: str,    # "Conservador" / "Moderado" / "Agresivo"
    presupuesto_semanal: float,  # en ARS
    ccl: float,
    email_destino: str = "comercial@tudominio.com",
):
    st.markdown("## 🎯 Recomendador Semanal — Modelo 60/20/20")
    st.caption(
        "**Fundamental 60%** · Técnico 20% (MOD-23) · Sector/Contexto 20%  |  "
        f"Score 0–100 · Actualización cada 12 hs · Perfil: **{perfil_cliente}**"
    )

    # ── Sidebar de configuración ───────────────────────────────────────────────
    with st.expander("⚙️ Configurar universo y parámetros", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            incl_cedears = st.checkbox("CEDEARs BYMA", value=True)
            incl_merval  = st.checkbox("Acciones Merval", value=True)
        with col2:
            incl_bonos   = st.checkbox("Bonos USD", value=False)
            incl_fci     = st.checkbox("FCI argentinos", value=False)
        with col3:
            incl_intl    = st.checkbox("Internacional", value=False)
        with col3:
            max_activos  = st.slider("Máx activos a escanear", 20, 120, 60)
            presupuesto  = st.number_input(
                "Presupuesto semanal (ARS)", min_value=10_000,
                value=int(presupuesto_semanal), step=10_000, format="%d"
            )

    # ── Contexto macro editable ────────────────────────────────────────────────
    with st.expander("🌍 Contexto Macro (editar para ajustar scores)", expanded=False):
        ctx = obtener_contexto_macro()
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🇺🇸 EEUU**")
            fed     = st.selectbox("Fed ciclo",    ["PAUSA","BAJA","SUBA"],
                                   index=["PAUSA","BAJA","SUBA"].index(ctx["fed_ciclo"]))
            recesion= st.selectbox("Riesgo recesión", ["BAJO","MEDIO","ALTO"],
                                   index=["BAJO","MEDIO","ALTO"].index(ctx["recesion_riesgo"]))
            sp500   = st.selectbox("S&P500",       ["ALCISTA","LATERAL","BAJISTA"],
                                   index=["ALCISTA","LATERAL","BAJISTA"].index(ctx["sp500_tendencia"]))
        with c2:
            st.markdown("**🇦🇷 Argentina**")
            riesgo  = st.selectbox("Riesgo país",  ["BAJO","MEDIO","ALTO"],
                                   index=["BAJO","MEDIO","ALTO"].index(ctx["riesgo_pais"]))
            ccl_tend= st.selectbox("CCL tendencia",["ESTABLE","SUBE","BAJA"],
                                   index=["ESTABLE","SUBE","BAJA"].index(ctx["ccl_tendencia"]))
            cepo    = st.selectbox("Cepo cambiario",["PARCIAL","PLENO","SIN"],
                                   index=["PARCIAL","PLENO","SIN"].index(ctx["cepo_status"]))
        with c3:
            st.markdown("**🛢️ Commodities**")
            petro   = st.selectbox("Petróleo",     ["LATERAL","ALCISTA","BAJISTA"],
                                   index=["LATERAL","ALCISTA","BAJISTA"].index(ctx["petroleo"]))
            oro_t   = st.selectbox("Oro",          ["ALCISTA","LATERAL","BAJISTA"],
                                   index=["ALCISTA","LATERAL","BAJISTA"].index(ctx["oro"]))

        if st.button("💾 Actualizar contexto macro"):
            actualizar_contexto_macro({
                "fed_ciclo": fed, "recesion_riesgo": recesion,
                "sp500_tendencia": sp500, "riesgo_pais": riesgo,
                "ccl_tendencia": ccl_tend, "cepo_status": cepo,
                "petroleo": petro, "oro": oro_t,
            })
            st.success("✅ Contexto actualizado — re-escaneá el universo para aplicar cambios")
            st.cache_data.clear()

    st.divider()

    # ── Botón de escaneo ──────────────────────────────────────────────────────
    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
    with col_btn1:
        escanear = st.button("🔍 Escanear universo ahora", type="primary", use_container_width=True)
    with col_btn2:
        limpiar  = st.button("🗑️ Limpiar caché", use_container_width=True)
    with col_btn3:
        st.caption(f"Último scan: {st.session_state.get('ultimo_scan', 'Nunca')}")

    if limpiar:
        st.cache_data.clear()
        st.session_state.pop("df_scores", None)
        st.rerun()

    # ── Ejecutar scan ─────────────────────────────────────────────────────────
    if escanear or "df_scores" not in st.session_state:
        barra = st.progress(0, text="Iniciando escaneo...")

        def progreso(i, total, ticker):
            pct = int(i / total * 100)
            barra.progress(pct, text=f"Analizando {ticker}... ({i}/{total})")

        with st.spinner("Calculando scores 60/20/20..."):
            df_scores = _scan_cacheado(
                incl_cedears, incl_merval, incl_bonos, incl_intl, incl_fci, max_activos
            )

        barra.empty()
        st.session_state["df_scores"] = df_scores
        st.session_state["ultimo_scan"] = str(date.today())

    df_scores = st.session_state.get("df_scores", pd.DataFrame())

    if df_scores.empty:
        st.warning("No hay datos. Hacé click en 'Escanear universo ahora'.")
        return

    # ── Métricas del scan ─────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    comprar  = len(df_scores[df_scores["Senal"].str.contains("COMPRAR",  na=False)])
    acumular = len(df_scores[df_scores["Senal"].str.contains("ACUMULAR", na=False)])
    mantener = len(df_scores[df_scores["Senal"].str.contains("MANTENER", na=False)])
    reducir  = len(df_scores[df_scores["Senal"].str.contains("REDUCIR|SALIR", na=False, regex=True)])
    m1.metric("🟢 Comprar",  comprar)
    m2.metric("🟡 Acumular", acumular)
    m3.metric("⚪ Mantener", mantener)
    m4.metric("🔴 Reducir",  reducir)

    st.divider()

    # ── SECCIÓN 1: Ranking completo ───────────────────────────────────────────
    st.markdown("### 📊 Ranking universo completo — Score 60/20/20")

    # Filtros inline
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filtro_senal = st.multiselect(
            "Señal", ["🟢 COMPRAR","🟡 ACUMULAR","⚪ MANTENER","🟠 REDUCIR","🔴 SALIR"],
            default=["🟢 COMPRAR","🟡 ACUMULAR"]
        )
    with fc2:
        sectores_disp = sorted(df_scores["Sector"].dropna().unique().tolist())
        filtro_sector = st.multiselect("Sector", sectores_disp, default=[])
    with fc3:
        score_min = st.slider("Score mínimo", 0, 100, 40)

    df_filtrado = df_scores.copy()
    if filtro_senal:
        df_filtrado = df_filtrado[df_filtrado["Senal"].isin(filtro_senal)]
    if filtro_sector:
        df_filtrado = df_filtrado[df_filtrado["Sector"].isin(filtro_sector)]
    df_filtrado = df_filtrado[df_filtrado["Score_Total"] >= score_min]

    # Tabla con colores
    def color_senal(val):
        if "COMPRAR"  in str(val): return "background-color:#D4EDDA; color:#155724"
        if "ACUMULAR" in str(val): return "background-color:#FFF3CD; color:#856404"
        if "MANTENER" in str(val): return "background-color:#F8F9FA; color:#6C757D"
        if "REDUCIR"  in str(val): return "background-color:#FFE0CC; color:#CC5200"
        if "SALIR"    in str(val): return "background-color:#F8D7DA; color:#721C24"
        return ""

    cols_tabla = ["Ticker","Sector","Score_Total","Score_Fund","Score_Tec",
                  "Score_Sector","RSI","Senal"]
    st.dataframe(
        df_filtrado[cols_tabla].style
        .map(color_senal, subset=["Senal"])
        .format({"Score_Total":"{:.1f}","Score_Fund":"{:.1f}",
                 "Score_Tec":"{:.1f}","Score_Sector":"{:.1f}","RSI":"{:.0f}"}), use_container_width=True,
        height=400,
        hide_index=False,
    )

    # Gráfico de burbujas: Score Total vs RSI, tamaño=Score Fundamental
    if len(df_filtrado) >= 3:
        fig = px.scatter(
            df_filtrado.head(30),
            x="RSI", y="Score_Total",
            size="Score_Fund", color="Sector",
            text="Ticker", hover_data=["Score_Fund","Score_Tec","Score_Sector"],
            title="Top 30 — Score Total vs RSI (tamaño = Score Fundamental)",
            height=450,
        )
        fig.add_vline(x=40, line_dash="dash", line_color="green",  annotation_text="RSI compra")
        fig.add_vline(x=70, line_dash="dash", line_color="red",    annotation_text="RSI venta")
        fig.add_hline(y=75, line_dash="dot",  line_color="green",  annotation_text="Comprar")
        fig.add_hline(y=60, line_dash="dot",  line_color="orange", annotation_text="Acumular")
        fig.update_traces(textposition="top center")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── SECCIÓN 2: Cartera óptima y recomendación semanal ────────────────────
    st.markdown("### 🏆 Cartera óptima a largo plazo + Recomendación semanal")

    col_opt1, col_opt2 = st.columns([3, 1])
    with col_opt2:
        n_pos = st.number_input("N° posiciones objetivo", 6, 20, 12)

    df_optima = calcular_cartera_optima(
        df_scores=df_scores,
        cartera_actual=cartera_actual,
        presupuesto_semanal_ars=presupuesto,
        perfil=perfil_cliente,
        n_posiciones=n_pos,
        ccl=ccl,
    )

    if df_optima.empty:
        st.info("Sin datos suficientes para calcular la cartera óptima.")
        return

    # Tabla de cartera óptima
    def highlight_accion(val):
        if "Iniciar"  in str(val): return "background-color:#D4EDDA; font-weight:bold"
        if "Agregar"  in str(val): return "background-color:#CCE5FF; font-weight:bold"
        if "Mantener" in str(val): return "background-color:#F8F9FA"
        if "Esperar"  in str(val): return "background-color:#FFF3CD"
        return ""

    st.dataframe(
        df_optima.style
        .map(color_senal, subset=["Senal"])
        .map(highlight_accion, subset=["Accion_Semanal"])
        .format({"Score_Total":"{:.1f}","Score_Fund":"{:.1f}",
                 "Score_Tec":"{:.1f}","Score_Sector":"{:.1f}",
                 "Peso_Optimo_Pct":"{:.1f}%","RSI":"{:.0f}"}), use_container_width=True,
        height=420,
        hide_index=True,
    )

    # Donut de distribución óptima
    fig_pie = px.pie(
        df_optima, names="Ticker", values="Peso_Optimo_Pct",
        color="Sector",
        title="Distribución óptima por activo",
        hole=0.4, height=380,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    # ── Resumen de acciones semanales ─────────────────────────────────────────
    st.markdown("#### 📋 Acciones para esta semana")
    acciones = df_optima[~df_optima["Accion_Semanal"].isin(["Mantener","Esperar","—"])].copy()
    if acciones.empty:
        st.success("✅ La cartera está alineada con el modelo. Sin operaciones esta semana.")
    else:
        for _, r in acciones.iterrows():
            icono = "🟢" if "Iniciar" in r["Accion_Semanal"] else "🔵"
            st.markdown(
                f"{icono} **{r['Ticker']}** — {r['Accion_Semanal']} "
                f"| Score: {r['Score_Total']:.0f} | RSI: {r['RSI']:.0f} "
                f"| {r['Senal']}"
            )

    st.divider()

    # ── Sección de envío por email ────────────────────────────────────────────
    st.markdown("### 📧 Enviar reporte semanal por email")
    _render_email_widget(df_optima, df_scores, email_destino, perfil_cliente)


# ─── GENERADOR DE EMAIL ───────────────────────────────────────────────────────

def _enviar_reporte_email(
    df_optima:    pd.DataFrame,
    df_scores:    pd.DataFrame,
    email_destino: str,
    perfil:       str,
):
    """Genera y guarda como borrador el reporte semanal en Gmail."""
    hoy    = date.today().strftime("%d/%m/%Y")
    lunes  = (date.today() + timedelta(days=(7 - date.today().weekday()))).strftime("%d/%m/%Y")

    # Top 5 compras
    top_compras = df_optima[
        df_optima["Accion_Semanal"].str.contains("Iniciar|Agregar", na=False)
    ].head(5)

    filas_html = ""
    for _, r in top_compras.iterrows():
        filas_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee"><b>{r['Ticker']}</b></td>
          <td style="padding:8px;border-bottom:1px solid #eee">{r['Sector']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">
            <b>{r['Score_Total']:.0f}</b></td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center">
            {r['RSI']:.0f}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{r['Senal']}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#0066cc">
            <b>{r['Accion_Semanal']}</b></td>
        </tr>"""

    top_ranking = df_scores.head(10)
    filas_rank = ""
    for i, (_, r) in enumerate(top_ranking.iterrows(), 1):
        filas_rank += f"""
        <tr style="background:{'#f9f9f9' if i%2==0 else 'white'}">
          <td style="padding:6px;text-align:center">{i}</td>
          <td style="padding:6px"><b>{r['Ticker']}</b></td>
          <td style="padding:6px">{r.get('Sector','')}</td>
          <td style="padding:6px;text-align:center">{r['Score_Total']:.1f}</td>
          <td style="padding:6px;text-align:center">{r.get('Score_Fund',0):.1f}</td>
          <td style="padding:6px;text-align:center">{r.get('Score_Tec',0):.1f}</td>
          <td style="padding:6px;text-align:center">{r.get('RSI',50):.0f}</td>
          <td style="padding:6px">{r['Senal']}</td>
        </tr>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#222;max-width:700px;margin:auto">
    <div style="background:#1a1a2e;color:white;padding:20px;border-radius:8px 8px 0 0">
      <h2 style="margin:0">📊 Reporte Semanal MQ26</h2>
      <p style="margin:4px 0;color:#aaa">Modelo 60/20/20 · {hoy} · Perfil: {perfil}</p>
    </div>

    <div style="padding:20px;background:#f8f9fa;border-left:4px solid #0066cc">
      <h3 style="color:#0066cc;margin-top:0">🎯 Acciones recomendadas — semana del {lunes}</h3>
      <table style="width:100%;border-collapse:collapse">
        <tr style="background:#0066cc;color:white">
          <th style="padding:8px">Ticker</th><th style="padding:8px">Sector</th>
          <th style="padding:8px">Score</th><th style="padding:8px">RSI</th>
          <th style="padding:8px">Señal</th><th style="padding:8px">Acción</th>
        </tr>
        {filas_html if filas_html else '<tr><td colspan="6" style="padding:12px;text-align:center">Sin operaciones esta semana — cartera alineada</td></tr>'}
      </table>
    </div>

    <div style="padding:20px">
      <h3 style="color:#333">🏆 Top 10 Universo — Ranking Semanal</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="background:#333;color:white">
          <th style="padding:6px">#</th><th style="padding:6px">Ticker</th>
          <th style="padding:6px">Sector</th><th style="padding:6px">Score</th>
          <th style="padding:6px">Fund</th><th style="padding:6px">Tec</th>
          <th style="padding:6px">RSI</th><th style="padding:6px">Señal</th>
        </tr>
        {filas_rank}
      </table>
    </div>

    <div style="background:#fff3cd;padding:15px;border-radius:4px;margin:0 20px 20px">
      <small>⚠️ <b>Disclaimer:</b> Este reporte es generado automáticamente por el sistema
      MQ26-DSS y no constituye asesoramiento financiero. Las recomendaciones se basan
      en modelos cuantitativos y deben ser validadas por el asesor antes de operar.
      Invertir conlleva riesgos. Performance pasada no garantiza resultados futuros.</small>
    </div>

    <div style="background:#1a1a2e;color:#aaa;padding:12px;text-align:center;
                border-radius:0 0 8px 8px;font-size:12px">
      Master Quant 26 | DSS Unificado | Generado el {hoy}
    </div>
    </body></html>
    """

    st.session_state["_email_html_reporte"] = html
    st.session_state["_email_destino"]      = email_destino
    st.session_state["_email_subject"]      = f"📊 MQ26 Reporte Semanal — {hoy}"
    st.success("✅ Reporte preparado. Completá los datos de Gmail abajo y presioná Enviar.")


# ─── WIDGET DE ENVÍO DE EMAIL ─────────────────────────────────────────────────

def _render_email_widget(
    df_optima:    pd.DataFrame,
    df_scores:    pd.DataFrame,
    email_destino: str,
    perfil:       str,
):
    """
    Renderiza la sección de configuración y envío de email.
    Muestra el estado de configuración de Gmail y permite enviar el reporte.
    """
    import os

    from services.email_sender import enviar_email_gmail, verificar_config_email

    # ── Estado actual de la configuración ─────────────────────────────────────
    cfg_ok, gmail_user, cfg_msg = verificar_config_email()

    with st.expander("⚙️ Configuración Gmail" + (" ✅" if cfg_ok else " ❌ No configurado"), expanded=not cfg_ok):
        st.markdown(
            "Para enviar emails desde la app necesitás una **Contraseña de Aplicación** de Google.\n\n"
            "**Pasos:**\n"
            "1. Ir a [myaccount.google.com/security](https://myaccount.google.com/security)\n"
            "2. Activar **Verificación en 2 pasos** (si no está activa)\n"
            "3. Buscar **Contraseñas de aplicaciones** → Seleccionar 'Correo' → Copiar las 16 letras\n"
            "4. Pegar abajo y guardar"
        )
        col_a, col_b = st.columns(2)
        with col_a:
            nuevo_user = st.text_input(
                "Gmail (remitente)",
                value=gmail_user or os.environ.get("GMAIL_USER", ""),
                placeholder="tu_email@gmail.com",
                key="cfg_gmail_user",
            )
        with col_b:
            nuevo_pwd = st.text_input(
                "Contraseña de Aplicación Gmail",
                type="password",
                value="",
                placeholder="xxxx xxxx xxxx xxxx",
                key="cfg_gmail_pwd",
                help="Se genera en Google → Seguridad → Contraseñas de aplicaciones",
            )

        if st.button("💾 Guardar credenciales en sesión", key="btn_guardar_gmail"):
            if nuevo_user and nuevo_pwd:
                os.environ["GMAIL_USER"]         = nuevo_user.strip()
                os.environ["GMAIL_APP_PASSWORD"]  = nuevo_pwd.strip()
                st.success(f"✅ Credenciales guardadas para {nuevo_user}")
                st.rerun()
            else:
                st.warning("Completá ambos campos.")

    st.caption(cfg_msg)

    # ── Formulario de envío ────────────────────────────────────────────────────
    col1, col2 = st.columns([3, 1])
    with col1:
        dest = st.text_input(
            "Destinatario",
            value=email_destino,
            key="email_dest_input",
        )
    with col2:
        st.write("")
        st.write("")
        enviar_ahora = st.button(
            "📧 Enviar ahora",
            type="primary",
            key="btn_enviar_email_real",
            disabled=not cfg_ok,
        )

    if not cfg_ok:
        st.info("Configurá las credenciales de Gmail arriba para poder enviar.")

    if enviar_ahora:
        # Preparar el HTML si no estaba en session_state
        if "_email_html_reporte" not in st.session_state:
            _enviar_reporte_email(df_optima, df_scores, dest, perfil)

        html      = st.session_state.get("_email_html_reporte", "")
        asunto    = st.session_state.get("_email_subject", f"📊 MQ26 Reporte Semanal — {date.today().strftime('%d/%m/%Y')}")

        if not html:
            st.error("No hay reporte generado. Esperá que termine el escaneo.")
            return

        with st.spinner("Enviando email..."):
            ok, msg = enviar_email_gmail(
                destinatario = dest,
                asunto       = asunto,
                cuerpo_html  = html,
            )

        if ok:
            st.success(f"✅ {msg}")
            st.balloons()
            # Limpiar estado
            st.session_state.pop("_email_html_reporte", None)
            st.session_state.pop("_email_subject", None)
        else:
            st.error(f"❌ Error al enviar:\n\n{msg}")
