"""
ui/tab_estudio.py — Tab exclusivo del tier Estudio (ES)
Dashboard multi-cliente + wizard de onboarding de 4 pasos.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core.auth import has_feature


# ─── WIZARD DE ONBOARDING ─────────────────────────────────────────────────────

_PERFILES   = ["Conservador", "Moderado", "Arriesgado"]
_HORIZONTES = ["1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años"]
_TIPOS      = ["Persona", "Empresa", "Fondo"]


def _wizard_paso1(ctx: dict) -> None:
    st.markdown("#### Datos del cliente")
    nombre = st.text_input(
        "Nombre completo / razón social",
        value=st.session_state.get("wiz_nombre", ""),
        key="wiz_inp_nombre",
    )
    tipo = st.selectbox(
        "Tipo de cliente", _TIPOS,
        index=_TIPOS.index(st.session_state.get("wiz_tipo", "Persona")),
        key="wiz_inp_tipo",
    )
    if st.button("Siguiente →", key="wiz_btn_1", use_container_width=True,
                 disabled=not nombre.strip()):
        st.session_state["wiz_nombre"] = nombre.strip()
        st.session_state["wiz_tipo"]   = tipo
        st.session_state["wizard_step"] = 2
        st.rerun()


def _wizard_paso2(ctx: dict) -> None:
    st.markdown("#### Perfil de riesgo")
    st.caption("Respondé las siguientes preguntas para determinar el perfil.")

    col1, col2 = st.columns(2)
    horizonte = col1.selectbox(
        "Horizonte de inversión", _HORIZONTES,
        index=_HORIZONTES.index(st.session_state.get("wiz_horizonte", "1 año")),
        key="wiz_inp_horizonte",
    )
    perfil = col2.selectbox(
        "Perfil de riesgo declarado", _PERFILES,
        index=_PERFILES.index(st.session_state.get("wiz_perfil", "Moderado")),
        key="wiz_inp_perfil",
    )
    tolerancia = st.slider(
        "Tolerancia a pérdidas temporales (%)",
        min_value=5, max_value=50, step=5,
        value=st.session_state.get("wiz_tolerancia", 15),
        key="wiz_inp_tolerancia",
    )
    # Sugerir perfil según tolerancia
    if tolerancia <= 10:
        sugerencia = "Conservador"
    elif tolerancia <= 25:
        sugerencia = "Moderado"
    else:
        sugerencia = "Arriesgado"
    if sugerencia != perfil:
        st.info(f"Según la tolerancia declarada, el perfil sugerido es **{sugerencia}**.")

    col_back, col_next = st.columns(2)
    if col_back.button("← Anterior", key="wiz_back_2", use_container_width=True):
        st.session_state["wizard_step"] = 1
        st.rerun()
    if col_next.button("Siguiente →", key="wiz_btn_2", use_container_width=True):
        st.session_state["wiz_perfil"]     = perfil
        st.session_state["wiz_horizonte"]  = horizonte
        st.session_state["wiz_tolerancia"] = tolerancia
        st.session_state["wizard_step"]    = 3
        st.rerun()


def _wizard_paso3(ctx: dict) -> None:
    st.markdown("#### Capital y aportes")

    capital = st.number_input(
        "Capital inicial (USD)",
        min_value=0.0, step=500.0,
        value=float(st.session_state.get("wiz_capital", 0.0)),
        key="wiz_inp_capital",
    )
    aporte_mensual = st.number_input(
        "Aporte mensual estimado (USD)",
        min_value=0.0, step=100.0,
        value=float(st.session_state.get("wiz_aporte", 0.0)),
        key="wiz_inp_aporte",
    )
    objetivo = st.number_input(
        "Objetivo patrimonial (USD, opcional)",
        min_value=0.0, step=1000.0,
        value=float(st.session_state.get("wiz_objetivo", 0.0)),
        key="wiz_inp_objetivo",
    )

    col_back, col_next = st.columns(2)
    if col_back.button("← Anterior", key="wiz_back_3", use_container_width=True):
        st.session_state["wizard_step"] = 2
        st.rerun()
    if col_next.button("Siguiente →", key="wiz_btn_3", use_container_width=True):
        st.session_state["wiz_capital"]  = capital
        st.session_state["wiz_aporte"]   = aporte_mensual
        st.session_state["wiz_objetivo"] = objetivo
        st.session_state["wizard_step"]  = 4
        st.rerun()


def _wizard_paso4(ctx: dict) -> None:
    st.markdown("#### Propuesta de cartera")

    perfil_key = st.session_state.get("wiz_perfil", "Moderado").lower()
    nombre     = st.session_state.get("wiz_nombre", "—")
    capital    = st.session_state.get("wiz_capital", 0.0)

    st.markdown(f"**Cliente:** {nombre} · **Perfil:** {perfil_key.title()} · "
                f"**Capital:** USD {capital:,.0f}")

    # Propuesta optimizada (con fallback si yfinance no responde)
    if st.button("Generar propuesta optimizada", key="wiz_btn_propuesta",
                 use_container_width=True):
        with st.spinner("Calculando pesos óptimos…"):
            try:
                from services.profile_proposals import build_profile_proposal
                propuesta = build_profile_proposal(perfil_key)
                st.session_state["wiz_propuesta"] = propuesta
            except Exception as e:
                st.warning(f"No se pudo optimizar ({e}). Se usarán pesos igual-peso.")
                universos = {
                    "conservador": ["INCOME","XLV","GLD","KO","BRKB"],
                    "moderado":    ["SPY","MSFT","GOOGL","AMZN","META"],
                    "arriesgado":  ["IVW","NVDA","MELI","TSLA","PLTR"],
                }
                tks = universos.get(perfil_key, ["SPY"])
                st.session_state["wiz_propuesta"] = {
                    "pesos": {t: round(1/len(tks), 4) for t in tks},
                    "perfil": perfil_key, "modelo": "igual-peso",
                }

    propuesta = st.session_state.get("wiz_propuesta")
    if propuesta:
        import pandas as pd
        pesos = propuesta.get("pesos", {})
        df_p = pd.DataFrame(
            [(t, round(p * 100, 2)) for t, p in sorted(pesos.items(),
             key=lambda x: x[1], reverse=True)],
            columns=["Activo", "Peso %"],
        )
        st.dataframe(df_p.style.format({"Peso %": "{:.2f}%"}),
                     use_container_width=True, hide_index=True, height=220)
        if propuesta.get("metricas"):
            m = propuesta["metricas"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Retorno esperado", f"{m.get('retorno_anual', 0)*100:.1f}%")
            c2.metric("Volatilidad anual", f"{m.get('volatilidad_anual', 0)*100:.1f}%")
            c3.metric("Sharpe", f"{m.get('sharpe', 0):.2f}")

        st.markdown("---")
        col_back, col_confirm = st.columns(2)
        if col_back.button("← Anterior", key="wiz_back_4", use_container_width=True):
            st.session_state["wizard_step"] = 3
            st.rerun()

        if col_confirm.button("✅ Confirmar y crear cliente", key="wiz_btn_confirmar",
                               use_container_width=True, type="primary"):
            dbm        = ctx.get("dbm")
            tenant_id  = ctx.get("tenant_id", "default")
            if dbm:
                try:
                    from core.db_manager import Cliente, get_session
                    import datetime as _dt
                    with get_session() as s:
                        nuevo = Cliente(
                            nombre         = st.session_state["wiz_nombre"],
                            perfil_riesgo  = st.session_state.get("wiz_perfil", "Moderado"),
                            horizonte_label= st.session_state.get("wiz_horizonte", "1 año"),
                            capital_usd    = st.session_state.get("wiz_capital", 0.0),
                            tipo_cliente   = st.session_state.get("wiz_tipo", "Persona"),
                            tenant_id      = tenant_id,
                            activo         = True,
                            created_at     = _dt.datetime.utcnow(),
                        )
                        s.add(nuevo)
                        s.commit()
                        cid = nuevo.id
                    st.success(f"Cliente **{st.session_state['wiz_nombre']}** creado (ID {cid}).")
                    # Limpiar wizard
                    for k in ["wiz_nombre","wiz_tipo","wiz_perfil","wiz_horizonte",
                               "wiz_tolerancia","wiz_capital","wiz_aporte",
                               "wiz_objetivo","wiz_propuesta","wizard_step"]:
                        st.session_state.pop(k, None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear cliente: {e}")
            else:
                st.warning("Sin conexión a base de datos.")


def _render_wizard_onboarding(ctx: dict) -> None:
    paso = int(st.session_state.get("wizard_step", 1))
    st.progress(paso / 4, text=f"Paso {paso} de 4 — Nuevo cliente")
    st.markdown("---")
    if paso == 1:
        _wizard_paso1(ctx)
    elif paso == 2:
        _wizard_paso2(ctx)
    elif paso == 3:
        _wizard_paso3(ctx)
    else:
        _wizard_paso4(ctx)


def _etiqueta_cartera_para_cliente(nombre_cliente: str, df_trans: pd.DataFrame) -> str:
    """Primera cartera en el transaccional cuyo prefijo coincide con el nombre del cliente."""
    n = (nombre_cliente or "").strip()
    if not n:
        return ""
    if df_trans is None or df_trans.empty or "CARTERA" not in df_trans.columns:
        return f"{n} | (sin datos)"
    matches = sorted({str(x).strip() for x in df_trans["CARTERA"].dropna().unique()})
    pref = n + " |"
    real = [c for c in matches if c.startswith(pref) and "(sin datos)" not in c]
    if real:
        return real[0]
    fall = [c for c in matches if c.startswith(pref)]
    if fall:
        return fall[0]
    return f"{n} | (sin datos)"


def _enriquecer_ag_desde_cartera(cartera_lbl: str, ctx: dict) -> pd.DataFrame:
    """Posición neta enriquecida (precios + PnL) para una etiqueta CARTERA del CSV."""
    trans = ctx.get("df_trans")
    ed = ctx.get("engine_data")
    cs = ctx.get("cs")
    if not isinstance(trans, pd.DataFrame) or trans.empty or ed is None or cs is None:
        return pd.DataFrame()
    if not cartera_lbl or cartera_lbl.endswith("| (sin datos)"):
        return pd.DataFrame()
    fifo = bool(st.session_state.get("modo_ppc_fifo", False))
    try:
        raw = (
            ed.agregar_cartera_fifo(trans, cartera_lbl)
            if fifo
            else ed.agregar_cartera(trans, cartera_lbl)
        )
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    ccl = float(ctx.get("ccl") or 0.0) or 1200.0
    universo = ctx.get("universo_df")
    tickers = raw["TICKER"].astype(str).str.upper().tolist()
    try:
        cs.asegurar_precios_fallback_cargados()
    except Exception:
        pass
    precios = cs.resolver_precios(tickers, {}, ccl, universo_df=universo)
    return cs.calcular_posicion_neta(raw, precios, ccl, universo_df=universo)


def _cargar_cartera_cliente(cid: int, nombre_cliente: str, ctx: dict) -> pd.DataFrame:
    """
    Cartera del cliente seleccionado: si es el activo en sesión, usa ctx['df_ag'];
    si no, reconstruye desde el transaccional + motor de cartera.
    """
    if cid == ctx.get("cliente_id"):
        out = ctx.get("df_ag")
        if isinstance(out, pd.DataFrame):
            return out.copy()
        return pd.DataFrame()
    df_trans = ctx.get("df_trans")
    if not isinstance(df_trans, pd.DataFrame):
        df_trans = pd.DataFrame()
    lbl = _etiqueta_cartera_para_cliente(nombre_cliente, df_trans)
    return _enriquecer_ag_desde_cartera(lbl, ctx)


# ─── RENDER PRINCIPAL ─────────────────────────────────────────────────────────

def render_tab_estudio(ctx: dict) -> None:
    st.header("👥 Mis Clientes")

    dbm       = ctx.get("dbm")
    tenant_id = ctx.get("tenant_id", "default")

    # Obtener lista de clientes del tenant
    df = None
    if dbm:
        try:
            df = dbm.obtener_clientes_df(tenant_id)
        except TypeError:
            # versión antigua sin tenant_id como arg
            df = dbm.obtener_clientes_df()

    # Sin clientes → mostrar wizard
    if df is None or df.empty:
        st.info("Todavía no tenés clientes registrados. Completá el wizard para agregar el primero.")
        _render_wizard_onboarding(ctx)
        return

    # ── Dashboard de clientes ──────────────────────────────────────────────
    st.dataframe(df, use_container_width=True, hide_index=True)

    col_sel, col_nuevo = st.columns([3, 1])
    with col_sel:
        if "ID" in df.columns:
            cid = st.selectbox(
                "Seleccionar cliente",
                df["ID"].tolist(),
                format_func=lambda i: df.loc[df["ID"] == i, "Nombre"].iloc[0]
                            if "Nombre" in df.columns else str(i),
                key="estudio_cliente_sel",
            )
            col_ver, col_rpt = st.columns(2)
            if col_ver.button("Ver cartera", key="btn_estudio_ver",
                              use_container_width=True):
                st.session_state["cliente_id"] = cid
                st.success(f"Cartera del cliente ID {cid} activa.")

            if col_rpt.button("Informe completo", key="btn_estudio_rpt",
                              use_container_width=True):
                with st.spinner("Generando informe..."):
                    try:
                        from services.diagnostico_cartera import diagnosticar
                        from services.recomendacion_capital import recomendar
                        from services.reporte_inversor import generar_reporte_inversor
                        from core.diagnostico_types import (
                            RENDIMIENTO_MODELO_YTD_REF,
                            perfil_diagnostico_valido,
                        )

                        fila = df.loc[df["ID"] == cid].iloc[0]
                        nombre_cli = str(fila.get("Nombre", "—") or "—")
                        perfil_cli = str(fila.get("Perfil", "Moderado") or "Moderado")
                        horiz_cli = str(
                            fila.get("Horizonte", fila.get("horizonte_label", "1 año"))
                            or "1 año"
                        )
                        ccl_ctx = float(ctx.get("ccl") or 1200.0)

                        df_pos = _cargar_cartera_cliente(int(cid), nombre_cli, ctx)
                        cs = ctx.get("cs")
                        metricas_ctx: dict = {}
                        if cid == ctx.get("cliente_id"):
                            m0 = ctx.get("metricas")
                            if isinstance(m0, dict) and m0:
                                metricas_ctx = dict(m0)
                        if not metricas_ctx and cs is not None and not df_pos.empty:
                            metricas_ctx = cs.metricas_resumen(df_pos)
                        metricas_ctx = dict(metricas_ctx)
                        metricas_ctx.setdefault("ccl", ccl_ctx)

                        perfil_v = perfil_diagnostico_valido(perfil_cli)
                        diag = diagnosticar(
                            df_ag=df_pos,
                            perfil=perfil_v,
                            horizonte_label=horiz_cli,
                            metricas=metricas_ctx,
                            ccl=ccl_ctx,
                            universo_df=ctx.get("universo_df"),
                            senales_salida=None,
                            cliente_nombre=nombre_cli,
                        )

                        precios_d = ctx.get("precios_dict") or {}
                        if not isinstance(precios_d, dict):
                            precios_d = {}
                        rr = recomendar(
                            df_ag=df_pos,
                            perfil=perfil_v,
                            horizonte_label=horiz_cli,
                            capital_ars=0.0,
                            ccl=ccl_ctx,
                            precios_dict=precios_d,
                            diagnostico=diag,
                            universo_df=ctx.get("universo_df"),
                            cliente_nombre=nombre_cli,
                        )

                        modelo_frac = float(RENDIMIENTO_MODELO_YTD_REF.get(perfil_v, 0.09))
                        bloque_comp = {
                            "rend_cliente_ytd": diag.rendimiento_ytd_usd_pct,
                            "rend_modelo_ytd": modelo_frac,
                            "perfil": perfil_v,
                            "benchmark_label": f"Cartera modelo {perfil_v}",
                        }

                        html = generar_reporte_inversor(
                            diagnostico=diag,
                            recomendacion=rr,
                            metricas=metricas_ctx,
                            bloque_competitivo=bloque_comp,
                        )

                        mes_actual = date.today().strftime("%Y%m")
                        nombre_base = (
                            nombre_cli.split("|")[0].strip().lower().replace(" ", "_")
                        )
                        nombre_base = "".join(c for c in nombre_base if c.isalnum() or c == "_")
                        if not nombre_base:
                            nombre_base = "cliente"
                        st.download_button(
                            "Descargar informe PDF-ready",
                            data=html,
                            file_name=f"informe_{nombre_base}_{mes_actual}.html",
                            mime="text/html",
                            use_container_width=True,
                            key="btn_dl_informe_estudio",
                        )
                        sem = getattr(diag.semaforo, "value", str(diag.semaforo))
                        icono = {"verde": "OK", "amarillo": "Atencion", "rojo": "Alerta"}.get(
                            sem, "—"
                        )
                        st.success(
                            f"{icono} Informe listo — Score: {diag.score_total:.0f}/100"
                        )
                    except Exception as e:
                        st.warning(f"No se pudo generar el informe: {e}")

    with col_nuevo:
        if st.button("➕ Nuevo cliente", key="btn_nuevo_cliente",
                     use_container_width=True):
            st.session_state["wizard_step"] = 1
            st.rerun()

    # Si hay wizard activo (botón "Nuevo cliente" presionado previamente)
    if st.session_state.get("wizard_step"):
        st.markdown("---")
        _render_wizard_onboarding(ctx)
