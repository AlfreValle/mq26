"""
ui/tab_estudio.py — Tab exclusivo del tier Estudio (ES)
Dashboard multi-cliente + wizard de onboarding de 4 pasos.

P0-RBAC-01: mutaciones sensibles usan `can_action(ctx, "write")` (inventario en
docs/product/PENDIENTES_COMITE_EXPERTOS_CARTERAS_AR.md §4a).
"""
from __future__ import annotations

import html
import time
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.diagnostico_types import CARTERA_IDEAL, perfil_diagnostico_valido
from services.plan_simulaciones import (
    agrupar_pesos_torta,
    dias_desde_primera_compra,
    ideal_dict_desde_mix_plan,
)
from ui.mq26_ux import plotly_chart_layout_base
from ui.rbac import can_action

# ─── WIZARD DE ONBOARDING ─────────────────────────────────────────────────────

_PERFILES   = ["Conservador", "Moderado", "Arriesgado"]
_HORIZONTES = ["1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años"]
_TIPOS      = ["Persona", "Empresa", "Fondo"]


def _wizard_paso1(ctx: dict) -> None:
    st.markdown("#### ¿Cómo se llama y qué tipo es?")
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
    st.markdown("#### ¿Cuánto riesgo puede tolerar?")
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
    st.markdown("#### ¿Con cuánto empieza?")

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
    st.markdown("#### Esta sería su cartera inicial")

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

        st.divider()
        col_back, col_confirm = st.columns(2)
        if col_back.button("← Anterior", key="wiz_back_4", use_container_width=True):
            st.session_state["wizard_step"] = 3
            st.rerun()

        if col_confirm.button("✅ Confirmar y crear cliente", key="wiz_btn_confirmar",
                               use_container_width=True, type="primary"):
            if not can_action(ctx, "write"):
                st.warning("No tenés permiso para crear clientes.")
            else:
                dbm        = ctx.get("dbm")
                tenant_id  = ctx.get("tenant_id", "default")
                if dbm:
                    try:
                        import datetime as _dt

                        from core.db_manager import Cliente, get_session
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
    # P0-RBAC-01: todo el wizard (pasos 1–4, propuesta, confirmación) exige escritura Estudio.
    if not can_action(ctx, "write"):
        st.warning(
            "No tenés permiso para el asistente de alta de clientes. "
            "Se requiere rol con permiso de escritura en Estudio."
        )
        st.session_state.pop("wizard_step", None)
        return

    paso = int(st.session_state.get("wizard_step", 1))
    _wiz_labels = {
        1: "¿Cómo se llama y qué tipo es?",
        2: "¿Cuánto riesgo puede tolerar?",
        3: "¿Con cuánto empieza?",
        4: "Esta sería su cartera inicial",
    }
    st.progress(paso / 4, text=f"Paso {paso} de 4 — {_wiz_labels.get(paso, '')}")
    st.divider()
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



def _torre_fingerprint_cartera(df_pos: pd.DataFrame) -> str:
    if df_pos is None or df_pos.empty:
        return "empty"
    try:
        n = len(df_pos)
        v = float(df_pos["VALOR_ARS"].sum()) if "VALOR_ARS" in df_pos.columns else 0.0
        return f"{n}:{v:.0f}"
    except Exception:
        return str(len(df_pos))


_TORRE_CACHE_TTL_SEC = 300.0


def _accion_desde_semaforo(sem: str) -> str:
    return {
        "rojo": "Llamar hoy",
        "amarillo": "Agendar revisión",
        "verde": "Seguimiento OK",
        "neutro": "Completar carga",
    }.get(sem, "Revisar")


def _perfil_horizonte_cliente(cid: int, ctx: dict) -> tuple[str, str]:
    """Perfil y horizonte desde BD o valores por defecto."""
    perfil, horiz = "Moderado", "1 año"
    dbm = ctx.get("dbm")
    if dbm:
        try:
            d = dbm.obtener_cliente(int(cid))
            if d:
                perfil = str(d.get("perfil_riesgo") or perfil)
                horiz = str(d.get("horizonte_label") or horiz)
        except Exception:
            pass
    return perfil_diagnostico_valido(perfil), horiz


def _render_ficha_cliente_rapida(cid: int, nombre: str, ctx: dict) -> None:
    """
    Vista rápida: semáforo, score, valor, resultado ref. USD, primera observación.
    Caché por fingerprint de cartera; no relanza si falla el diagnóstico.
    """
    from services.cartera_service import metricas_resumen
    from services.diagnostico_cartera import diagnosticar

    ccl = float(ctx.get("ccl") or 1150.0)
    udf = ctx.get("universo_df")

    try:
        df_ag = _cargar_cartera_cliente(cid, nombre, ctx)
    except Exception:
        df_ag = None

    if df_ag is None or df_ag.empty:
        st.markdown(
            '<p class="mq-estudio-caption-muted">Sin posiciones cargadas.</p>',
            unsafe_allow_html=True,
        )
        return

    fp = _torre_fingerprint_cartera(df_ag)
    cache_key = f"ficha_rapida_{cid}_{fp}"
    diag = st.session_state.get(cache_key)
    if diag is None:
        try:
            perfil_cli, horiz_cli = _perfil_horizonte_cliente(cid, ctx)
            met = metricas_resumen(df_ag) if not df_ag.empty else {}
            diag = diagnosticar(
                df_ag=df_ag,
                perfil=perfil_cli,
                horizonte_label=horiz_cli,
                metricas=met,
                ccl=ccl,
                universo_df=udf,
                senales_salida=None,
                cliente_nombre=nombre,
            )
            st.session_state[cache_key] = diag
        except Exception:
            st.caption("No se pudo calcular el diagnóstico rápido.")
            return

    sem_v = str(getattr(getattr(diag, "semaforo", None), "value", "neutro") or "neutro")
    score = float(getattr(diag, "score_total", 0) or 0)
    sem_card_cls = {
        "verde": "mq-estudio-card--sem-verde",
        "amarillo": "mq-estudio-card--sem-amarillo",
        "rojo": "mq-estudio-card--sem-rojo",
    }.get(sem_v, "mq-estudio-card--sem-neutro")
    sem_emoji = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(sem_v, "⚪")

    valor_ars = float(pd.to_numeric(df_ag.get("VALOR_ARS", 0), errors="coerce").fillna(0.0).sum()) if "VALOR_ARS" in df_ag.columns else 0.0
    valor_usd = valor_ars / max(ccl, 1.0)
    if getattr(diag, "valor_cartera_usd", 0):
        valor_usd = float(diag.valor_cartera_usd)

    pnl_pct = float(getattr(diag, "rendimiento_ytd_usd_pct", 0) or 0)
    pnl_sign = "+" if pnl_pct >= 0 else ""
    pnl_cls = "mq-estudio-card-pnl--gain" if pnl_pct >= 0 else "mq-estudio-card-pnl--loss"

    obs_list = getattr(diag, "observaciones", []) or []
    obs_txt = ""
    if obs_list:
        o = obs_list[0]
        obs_txt = html.escape(
            f"{getattr(o, 'icono', '')} {getattr(o, 'titulo', '')}".strip()[:72]
        )

    st.markdown(
        f"""
    <div class="mq-estudio-card {sem_card_cls}">
        <div class="mq-estudio-card-head">
            <div class="mq-estudio-card-left">
                <span class="mq-estudio-card-emoji">{sem_emoji}</span>
                <strong class="mq-estudio-card-score">
                    Score {score:.0f}/100
                </strong>
                <span class="mq-estudio-card-obs">
                    {obs_txt}
                </span>
            </div>
            <div class="mq-estudio-card-right">
                <span class="mq-estudio-card-usd">
                    USD {valor_usd:,.0f}
                </span>
                <span class="mq-estudio-card-pnl {pnl_cls}">
                    {pnl_sign}{pnl_pct:.1f}%
                </span>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


# Objetivo del aporte → perfil efectivo que usa el motor (CARTERA_IDEAL).
# Permite que el asesor incline la recomendación sin tocar el perfil de riesgo
# guardado del cliente. Default = perfil del cliente.
_OBJETIVOS_APORTE_ESTUDIO: list[tuple[str, str]] = [
    ("🛡️ Preservar capital", "Conservador"),
    ("⚖️ Equilibrio", "Moderado"),
    ("🚀 Crecimiento", "Arriesgado"),
]


def _ctx_scoped_cliente(cid: int, nombre: str, ctx: dict) -> dict:
    """ctx superficial apuntado al cliente seleccionado (perfil, horizonte, cartera).

    Garantiza que recomendar/persistir trabajen sobre ESTE cliente y no sobre el
    activo en sesión — evita cruzar datos entre clientes del estudio.
    """
    sc = dict(ctx)
    nombre_corto = str(nombre).split("|")[0].strip()
    perfil_v, horiz = _perfil_horizonte_cliente(int(cid), ctx)
    sc["cliente_id"] = int(cid)
    sc["cliente_nombre"] = nombre
    sc["cliente_perfil"] = perfil_v
    sc["cliente_horizonte_label"] = horiz
    df_trans = ctx.get("df_trans")
    lbl = _etiqueta_cartera_para_cliente(
        nombre_corto, df_trans if isinstance(df_trans, pd.DataFrame) else pd.DataFrame()
    )
    if not lbl or lbl.endswith("(sin datos)"):
        lbl = f"{nombre_corto} | Cartera principal"
    sc["cartera_activa"] = lbl
    return sc


def _render_wizard_capital_estudio(cid: int, nombre: str, ctx: dict) -> None:
    """Wizard de capital del cliente seleccionado (pasos 3-5 del flujo de estudio).

    Paso 3: cuánto capital agregar + objetivo. Paso 4: recomendar activos a
    comprar (editable). Paso 5: adjuntar a la cartera del cliente (opcional,
    con confirmación). Reusa el motor de recomendación; no duplica lógica cuant.
    """
    from ui.inversor._helpers import (
        _TIPOS_EDICION_PRIMERA_CARTERA,
        _precios_para_recomendar,
        _tipo_universo_ticker,
    )

    if not can_action(ctx, "write"):
        st.caption(
            "Necesitás permiso de escritura en Estudio para agregar capital y recomendar."
        )
        return

    nombre_corto = str(nombre).split("|")[0].strip()
    sc = _ctx_scoped_cliente(int(cid), nombre, ctx)
    perfil_cli = str(sc["cliente_perfil"])
    horiz = str(sc["cliente_horizonte_label"])
    ccl = float(ctx.get("ccl") or 1150.0)
    rr_key = f"est_wiz_rr_{cid}"

    # ── Paso 3: capital + objetivo ─────────────────────────────────────────
    st.markdown(
        '<p class="mq-estudio-torre-kicker">💰 Paso 3 — Agregar capital y objetivo</p>',
        unsafe_allow_html=True,
    )
    col_cap, col_obj = st.columns([3, 2])
    with col_cap:
        capital_ars = st.number_input(
            "¿Cuánto capital quiere agregar? (ARS)",
            min_value=0.0,
            max_value=1_000_000_000.0,
            value=float(st.session_state.get(f"est_wiz_cap_{cid}", 500_000.0)),
            step=50_000.0,
            format="%.0f",
            key=f"est_wiz_cap_{cid}",
            help="El motor distribuye este monto según el objetivo y el perfil del cliente.",
        )
    with col_obj:
        _labels = [lbl for lbl, _ in _OBJETIVOS_APORTE_ESTUDIO]
        _default_idx = next(
            (i for i, (_, p) in enumerate(_OBJETIVOS_APORTE_ESTUDIO) if p == perfil_cli),
            1,
        )
        obj_label = st.selectbox(
            "Objetivo del aporte",
            _labels,
            index=_default_idx,
            key=f"est_wiz_obj_{cid}",
            help=f"Perfil de riesgo guardado del cliente: {perfil_cli}. Podés inclinar este aporte sin cambiarlo.",
        )
    perfil_ef = dict(_OBJETIVOS_APORTE_ESTUDIO).get(obj_label, perfil_cli)
    perfil_ef = perfil_diagnostico_valido(perfil_ef)

    st.caption(
        f"~ USD {capital_ars / max(ccl, 1.0):,.0f} (CCL {ccl:,.0f}) · "
        f"objetivo orienta la cartera a perfil **{perfil_ef}**"
    )

    if st.button(
        "🧠 Recomendar activos a comprar",
        type="primary",
        use_container_width=True,
        key=f"est_wiz_calc_{cid}",
        disabled=capital_ars <= 0,
    ):
        with st.spinner("Calculando recomendación…"):
            try:
                precios_d = _precios_para_recomendar(ctx)
                # El wizard responde "¿qué compro con ESTE capital nuevo?": arma una
                # canasta de despliegue total para el monto, tenga o no posiciones el
                # cliente. Antes, los clientes CON posiciones usaban recomendar()
                # (rebalanceo por déficit), que dejaba el capital nuevo casi sin
                # invertir (hasta 88% en efectivo) cuando ya estaban cerca del ideal.
                # generar_primera_cartera(desplegar_todo=True) garantiza <5% ocioso.
                from services.recomendacion_capital import generar_primera_cartera

                rr = generar_primera_cartera(
                    capital_ars=float(capital_ars),
                    perfil=perfil_ef,
                    ccl=ccl,
                    precios_dict=precios_d,
                    universo_df=ctx.get("universo_df"),
                    cliente_nombre=nombre_corto,
                    df_analisis=ctx.get("df_analisis"),
                    df_scores=None,
                    desplegar_todo=True,
                )
                st.session_state[rr_key] = {
                    "rr": rr,
                    "capital": float(capital_ars),
                    "perfil": perfil_ef,
                }
                # Audit: simulación de recomendación para este cliente.
                try:
                    from services.audit_trail import registrar_recomendacion_evento

                    registrar_recomendacion_evento(
                        evento="SIMULACION_RECOMENDACION",
                        origen="estudio_wizard_capital",
                        cliente_id=int(cid),
                        cliente_nombre=nombre_corto,
                        tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                        actor=str(ctx.get("login_user", "") or ""),
                        correlation_id=str(st.session_state.get("session_correlation_id", "")),
                        cartera=str(sc["cartera_activa"]),
                        perfil=perfil_ef,
                        capital_ars=float(capital_ars),
                        filas=len(list(getattr(rr, "compras_recomendadas", None) or [])),
                        payload={"objetivo": obj_label},
                    )
                except Exception:
                    pass
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo calcular la recomendación: {e}")

    # ── Paso 4: activos recomendados (editable) ────────────────────────────
    res = st.session_state.get(rr_key)
    if not res:
        return
    rr = res["rr"]
    cap_calc = float(res.get("capital", 0) or 0)
    perfil_res = str(res.get("perfil") or perfil_ef)

    st.markdown(
        '<p class="mq-estudio-torre-kicker">🧾 Paso 4 — Activos recomendados</p>',
        unsafe_allow_html=True,
    )
    if getattr(rr, "alerta_mercado", False):
        st.warning(f"⚠️ {getattr(rr, 'mensaje_alerta', 'Alerta de mercado.')}")

    items = list(getattr(rr, "compras_recomendadas", None) or [])
    if not items:
        st.info(
            "No se encontraron compras posibles con ese capital. "
            "Probá con otro monto u objetivo."
        )
        return

    _udf = ctx.get("universo_df")
    _rows: list[dict] = []
    for it in items:
        _tk = str(getattr(it, "ticker", "") or "").strip().upper()
        if not _tk:
            continue
        _rows.append(
            {
                "Ticker": _tk,
                "Unidades": int(getattr(it, "unidades", 0) or 0),
                "Precio_ARS": float(getattr(it, "precio_ars_estimado", 0) or 0),
                "TIPO": _tipo_universo_ticker(_tk, _udf),
                "Notas": str(getattr(it, "justificacion", "") or "")[:120],
            }
        )
    df_ed = pd.DataFrame(_rows)
    edited = st.data_editor(
        df_ed,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"est_wiz_editor_{cid}",
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", width="small"),
            "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1, width="small"),
            "Precio_ARS": st.column_config.NumberColumn("Precio ARS c/u", min_value=0.0, format="%.2f"),
            "TIPO": st.column_config.SelectboxColumn(
                "Tipo", options=_TIPOS_EDICION_PRIMERA_CARTERA, width="small"
            ),
            "Notas": st.column_config.TextColumn("Notas (guía)", width="large"),
        },
    )
    try:
        _nu = pd.to_numeric(edited["Unidades"], errors="coerce").fillna(0)
        _npx = pd.to_numeric(edited["Precio_ARS"], errors="coerce").fillna(0)
        monto_editado = float((_nu * _npx).sum())
    except Exception:
        monto_editado = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)
    st.caption(
        f"Total tabla ≈ **${monto_editado:,.0f} ARS** · queda en efectivo (ref.) "
        f"${remanente:,.0f} ARS · perfil {perfil_res}"
    )

    # Pilar 3: plan explicado (el porqué de cada compra), si el flag está activo.
    try:
        from ui.inversor._helpers import _flag_plan_explicado

        if _flag_plan_explicado(ctx):
            from services.recomendador_explicable import construir_plan_accion

            _plan = construir_plan_accion(
                perfil=perfil_res,
                rr=rr,
                capital_ars=cap_calc,
                precio_records=ctx.get("precio_records"),
            )
            with st.expander("🧭 Por qué estos activos — plan explicado", expanded=False):
                from ui.components.plan_accion_view import render_plan_accion

                render_plan_accion(_plan, key_prefix=f"est_wiz_plan_{cid}")
    except Exception:
        pass

    # ── Paso 5: adjuntar a la cartera del cliente ──────────────────────────
    st.markdown(
        '<p class="mq-estudio-torre-kicker">📎 Paso 5 — Adjuntar a la cartera del cliente</p>',
        unsafe_allow_html=True,
    )
    st.caption(f"Al confirmar, las compras se registran en: **`{sc['cartera_activa']}`**")
    _confirm = st.checkbox(
        "Confirmo que el cliente ejecutó estas operaciones en su broker",
        key=f"est_wiz_confirm_{cid}",
    )
    col_adj, col_reset = st.columns(2)
    with col_adj:
        if st.button(
            "📎 Adjuntar a la cartera principal",
            type="primary",
            use_container_width=True,
            key=f"est_wiz_adjuntar_{cid}",
            disabled=not _confirm,
        ):
            from ui.carga_activos import _persist_filas

            _ccl_ok = float(ctx.get("ccl") or 0.0)
            if _ccl_ok <= 0:
                st.error("CCL inválido: no se puede derivar PPC USD.")
            elif edited.empty:
                st.warning("La tabla está vacía.")
            else:
                _filas: list[dict] = []
                for _, row in edited.iterrows():
                    _tick = str(row.get("Ticker", "")).strip().upper()
                    _u = int(pd.to_numeric(row.get("Unidades", 0), errors="coerce") or 0)
                    _px = float(pd.to_numeric(row.get("Precio_ARS", 0), errors="coerce") or 0.0)
                    _ti = str(row.get("TIPO", "CEDEAR") or "CEDEAR").strip().upper()
                    if _ti in ("NAN", "NONE", "", "COMPRA", "VENTA"):
                        _ti = "CEDEAR"
                    if not _tick or _u <= 0 or _px <= 0:
                        continue
                    _ppc_ars = round(_px, 4)
                    _filas.append(
                        {
                            "FECHA_COMPRA": date.today(),
                            "TICKER": _tick,
                            "CANTIDAD": _u,
                            "PPC_USD": round(_ppc_ars / max(_ccl_ok, 1e-9), 6),
                            "PPC_ARS": _ppc_ars,
                            "TIPO": _ti,
                            "LAMINA_VN": float("nan"),
                        }
                    )
                if not _filas:
                    st.error(
                        "No hay filas válidas: cada una necesita Ticker, Unidades > 0 y Precio ARS > 0."
                    )
                else:
                    try:
                        from services.audit_trail import registrar_recomendacion_evento

                        registrar_recomendacion_evento(
                            evento="EJECUCION_CONFIRMADA",
                            origen="estudio_wizard_capital",
                            cliente_id=int(cid),
                            cliente_nombre=nombre_corto,
                            tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                            actor=str(ctx.get("login_user", "") or ""),
                            correlation_id=str(st.session_state.get("session_correlation_id", "")),
                            cartera=str(sc["cartera_activa"]),
                            perfil=perfil_res,
                            capital_ars=float(cap_calc),
                            filas=len(_filas),
                            payload={"confirmacion_broker": True},
                        )
                    except Exception:
                        pass
                    _persist_filas(
                        sc,
                        _filas,
                        "agregar",
                        cartera_override=str(sc["cartera_activa"]),
                        session_keys_clear=[rr_key, f"est_wiz_confirm_{cid}"],
                    )
    with col_reset:
        if st.button(
            "🔄 Recalcular con otro monto",
            use_container_width=True,
            key=f"est_wiz_reset_{cid}",
        ):
            st.session_state.pop(rr_key, None)
            st.rerun()


def _render_plan_cliente_estudio(cid: int, nombre: str, ctx: dict) -> None:
    """Resumen de plan / mix ideal (misma lógica que inversor, sin duplicar motor cuant)."""
    df_ag = _cargar_cartera_cliente(cid, nombre, ctx)
    if df_ag is None or df_ag.empty:
        st.info("Sin posiciones cargadas para este cliente.")
        return

    perfil_v, _hz = _perfil_horizonte_cliente(cid, ctx)
    dias = dias_desde_primera_compra(df_ag)
    ideal_base = CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"])
    ideal_d, _src_lbl = ideal_dict_desde_mix_plan(perfil_v, ideal_base, None)
    w_torta = {k: float(v) for k, v in (ideal_d or {}).items() if str(k).strip()}
    w_torta = agrupar_pesos_torta(w_torta, min_frac=0.02) if w_torta else {}

    ccl = float(ctx.get("ccl") or 1150.0)
    valor_ars = float(pd.to_numeric(df_ag["VALOR_ARS"], errors="coerce").fillna(0.0).sum()) if "VALOR_ARS" in df_ag.columns else 0.0
    valor_usd = valor_ars / max(ccl, 1.0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Patrimonio ref.", f"USD {valor_usd:,.0f}")
    c2.metric("Días en cartera", f"{dias} d" if dias is not None else "—")
    c3.metric("Perfil", perfil_v)

    if w_torta:
        labels = list(w_torta.keys())
        vals = [max(0.0, float(v)) for v in w_torta.values()]
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=vals,
                    hole=0.45,
                    textinfo="label+percent",
                    hoverinfo="label+percent",
                    marker=dict(line=dict(color="rgba(15,23,42,0.35)", width=1)),
                )
            ]
        )
        fig.update_layout(
            **plotly_chart_layout_base(
                title=dict(text=f"Referencia de mix — {perfil_v}", font=dict(size=14)),
                height=280,
                showlegend=False,
                margin=dict(t=44, b=12, l=10, r=10),
            ),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"est_plan_torta_{cid}")

    st.caption(
        f"Distribución objetivo del modelo (CARTERA_IDEAL) para **{perfil_v}**. "
        "En la app inversor el cliente ve también escenarios y Montecarlo."
    )


def _render_dashboard_estudio(ctx: dict) -> None:
    """
    Torre de control: tabla hero por urgencia + filtros R/A/V + caché por sesión.
    Invariante: nunca lanza — falla por cliente silenciosamente.
    """
    from services.diagnostico_cartera import diagnosticar

    try:
        from core.db_manager import obtener_notas_asesor
    except Exception:
        obtener_notas_asesor = None  # type: ignore[assignment]

    dbm = ctx.get("dbm")
    ccl = float(ctx.get("ccl") or 1200.0)
    tid = str(ctx.get("tenant_id", "default"))
    if not dbm:
        return
    try:
        df_cli = dbm.obtener_clientes_df(tenant_id=tid)
    except Exception:
        return
    if df_cli is None or df_cli.empty:
        return

    st.markdown(
        '<p class="mq-estudio-torre-kicker">Torre de control — excepciones por cliente</p>',
        unsafe_allow_html=True,
    )

    cache_store: dict = st.session_state.setdefault("mq26_torre_control_cache", {})
    now = time.time()
    filas: list[dict] = []

    for _, row in df_cli.iterrows():
        try:
            cid = int(row["ID"])
            nombre = str(row.get("Nombre", "—"))
            perfil = str(row.get("Perfil", "Moderado"))
            horizonte = str(row.get("Horizonte", row.get("horizonte_label", "1 año")))
            pv = perfil_diagnostico_valido(perfil)
            df_pos = _cargar_cartera_cliente(cid, nombre, ctx)
            fp = _torre_fingerprint_cartera(df_pos)
            cache_key = f"{tid}:{cid}:{fp}"

            if df_pos.empty:
                filas.append({
                    "ID": cid,
                    "NombreFull": nombre,
                    "Cliente": nombre.split("|")[0].strip()[:48],
                    "Semáforo": "neutro",
                    "Score": None,
                    "Pos.": 0,
                    "Acción sugerida": _accion_desde_semaforo("neutro"),
                    "Notas / contacto": "—",
                })
                continue

            ent = cache_store.get(cache_key)
            if ent and (now - float(ent[0])) < _TORRE_CACHE_TTL_SEC:
                diag = ent[1]
            else:
                diag = diagnosticar(
                    df_ag=df_pos,
                    perfil=pv,
                    horizonte_label=horizonte,
                    metricas={},
                    ccl=ccl,
                    universo_df=ctx.get("universo_df"),
                    senales_salida=None,
                    cliente_nombre=nombre,
                )
                cache_store[cache_key] = (now, diag)

            sv = str(getattr(diag.semaforo, "value", str(diag.semaforo))).lower()
            nota_txt = "—"
            if obtener_notas_asesor:
                try:
                    raw = (obtener_notas_asesor(cid, tenant_id=tid) or "").strip()
                    if raw:
                        nota_txt = raw.replace("\n", " ")[:56] + ("…" if len(raw) > 56 else "")
                except Exception:
                    pass

            filas.append({
                "ID": cid,
                "NombreFull": nombre,
                "Cliente": nombre.split("|")[0].strip()[:48],
                "Semáforo": sv,
                "Score": round(float(diag.score_total), 1),
                "Pos.": len(df_pos),
                "Acción sugerida": _accion_desde_semaforo(sv),
                "Notas / contacto": nota_txt,
            })
        except Exception:
            continue

    if not filas:
        return

    orden = {"rojo": 0, "amarillo": 1, "verde": 2, "neutro": 3}
    filas.sort(
        key=lambda r: (
            orden.get(str(r.get("Semáforo", "")), 9),
            float(r["Score"] or 0) if r["Score"] is not None else 0,
            str(r.get("Cliente", "")),
        )
    )

    n_rojos = sum(1 for r in filas if str(r.get("Semáforo", "")).lower() == "rojo")
    n_amarillos = sum(1 for r in filas if str(r.get("Semáforo", "")).lower() == "amarillo")
    n_verdes = sum(1 for r in filas if str(r.get("Semáforo", "")).lower() == "verde")
    st.session_state["dashboard_n_rojos"] = int(n_rojos)
    st.session_state["dashboard_n_amarillos"] = int(n_amarillos)
    st.session_state["dashboard_n_verdes"] = int(n_verdes)
    if n_rojos > 0 or n_amarillos > 0:
        st.markdown(
            f'<span class="mq-estudio-chip--rojo">{n_rojos} urgente(s)</span> · '
            f'<span class="mq-estudio-chip--amarillo">{n_amarillos} para revisar</span> · '
            f'<span class="mq-estudio-chip--verde">{n_verdes} OK</span>',
            unsafe_allow_html=True,
        )

    opts_sem = ["rojo", "amarillo", "verde", "neutro"]
    sel_sem = st.multiselect(
        "Filtrar por semáforo",
        opts_sem,
        default=opts_sem,
        format_func=lambda x: {"rojo": "Rojo (urgente)", "amarillo": "Amarillo", "verde": "Verde", "neutro": "Sin cartera"}[x],
        key="estudio_torre_filtro_sem",
    )
    filas_f = [r for r in filas if str(r.get("Semáforo")) in sel_sem] if sel_sem else filas

    st.markdown('<div class="mq-dataframe-wrap">', unsafe_allow_html=True)
    _df_torre = pd.DataFrame(filas_f)
    if "NombreFull" in _df_torre.columns:
        _df_torre = _df_torre.drop(columns=["NombreFull"])
    st.dataframe(_df_torre, use_container_width=True, hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<p class="mq-estudio-torre-kicker mq-estudio-torre-kicker--actions">'
        "Acciones rápidas</p>",
        unsafe_allow_html=True,
    )
    for fila in filas_f:
        cid_f = int(fila["ID"])
        nom_f = str(fila.get("NombreFull") or fila.get("Cliente", ""))
        sem_f = str(fila.get("Semáforo", "neutro"))
        score_f = fila.get("Score")
        acc_f = str(fila.get("Acción sugerida", "—"))
        sem_attr_f = sem_f if sem_f in ("verde", "amarillo", "rojo") else "neutro"
        sem_emoji_f = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(sem_f, "⚪")
        sc_txt = f"{float(score_f):.0f}" if score_f is not None else "—"

        col_sem, col_info, col_btns = st.columns([0.5, 5, 2.2])
        with col_sem:
            st.markdown(
                f'<div class="mq-estudio-hero-col" data-mq-sem="{html.escape(sem_attr_f)}">'
                f"{sem_emoji_f}"
                f'<br><span class="mq-estudio-hero-score">{html.escape(sc_txt)}</span></div>',
                unsafe_allow_html=True,
            )
        with col_info:
            nom_corto = nom_f.split("|")[0].strip()[:28]
            st.markdown(
                f'<div class="mq-estudio-hero-info">'
                f'<strong class="mq-estudio-hero-info-name">{html.escape(nom_corto)}</strong>'
                f'<br><span class="mq-estudio-hero-info-acc">{html.escape(acc_f[:72])}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with col_btns:
            bc1, bc2 = st.columns(2)
            if bc1.button("Abrir", key=f"est_ver_{cid_f}", use_container_width=True):
                st.session_state["cliente_id"] = cid_f
                st.session_state["cliente_nombre"] = nom_f
                st.success(f"Activo: {nom_f.split('|')[0].strip()}")
                st.rerun()
            if bc2.button("📊 Plan", key=f"est_plan_{cid_f}", use_container_width=True):
                k_plan = f"show_plan_{cid_f}"
                st.session_state[k_plan] = not bool(st.session_state.get(k_plan, False))
                st.rerun()
        if st.session_state.get(f"show_plan_{cid_f}"):
            _render_plan_cliente_estudio(cid_f, nom_f, ctx)
        st.markdown('<hr class="mq-estudio-torre-sep">', unsafe_allow_html=True)

    if st.button("Invalidar caché de diagnósticos (torre)", key="estudio_torre_inval_cache"):
        if not can_action(ctx, "write"):
            st.warning("No tenés permiso para esta acción.")
        else:
            st.session_state.pop("mq26_torre_control_cache", None)
            st.rerun()

    SEM_LABEL = {
        "verde": "Al día",
        "amarillo": "Revisar",
        "rojo": "Urgente",
    }
    with st.expander("Vista en tarjetas (compacta)", expanded=False):
        n_cols = min(4, max(1, len(filas_f)))
        cols = st.columns(n_cols)
        for i, r in enumerate(filas_f):
            sem = str(r.get("Semáforo", "neutro"))
            sem_attr = sem if sem in SEM_LABEL else "neutro"
            label = SEM_LABEL.get(sem, "Sin datos")
            score_txt = f"{r['Score']:.0f}/100" if r.get("Score") is not None else "—"
            n_txt = f"{r['Pos.']} pos." if r.get("Pos.", 0) > 0 else "Sin cartera"
            nombre_corto = str(r.get("Cliente", "—"))[:28]
            with cols[i % n_cols]:
                st.markdown(
                    f"""
                <div class="mq-estudio-torre-card" data-mq-sem="{html.escape(sem_attr)}">
                    <div class="mq-estudio-torre-card__nombre">{html.escape(nombre_corto)}</div>
                    <div class="mq-estudio-torre-card__row">
                        <span class="mq-estudio-torre-card__label">{html.escape(label)}</span>
                        <span class="mq-estudio-torre-card__score">{html.escape(score_txt)}</span>
                    </div>
                    <div class="mq-estudio-torre-card__meta">{html.escape(n_txt)}</div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
    st.divider()


# ─── RENDER PRINCIPAL ─────────────────────────────────────────────────────────

def render_tab_estudio(ctx: dict) -> None:
    st.markdown(
        """
<h2 class="mq-estudio-page-h2">
    Mis clientes
</h2>
""",
        unsafe_allow_html=True,
    )

    dbm       = ctx.get("dbm")
    tenant_id = ctx.get("tenant_id", "default")

    # Obtener lista de clientes del tenant
    df = None
    if dbm:
        try:
            df = dbm.obtener_clientes_df(tenant_id)
        except Exception:
            df = None

    # Sin clientes → mostrar wizard (solo si hay permiso de escritura; P0-RBAC-01)
    if df is None or df.empty:
        if not can_action(ctx, "write"):
            st.warning(
                "No tenés permiso para dar de alta clientes en este entorno. "
                "Contactá a un administrador si necesitás acceso de escritura en Estudio."
            )
            return
        st.info(
            "Todavía no agregaste clientes. "
            "Presioná **Alta de cliente** para empezar a trabajar."
        )
        _render_wizard_onboarding(ctx)
        return

    # ── Flujo primario: elegir el cliente a gestionar ──────────────────────
    # Carga diferida (P-estudio): el diagnóstico de TODOS los clientes (Torre de
    # control) es caro y antes corría en cada rerun — de ahí la lentitud al
    # "Abrir". Ahora queda detrás de un expander colapsado: solo se calcula si
    # el asesor lo pide. El camino normal es seleccionar un cliente (barato) y
    # ver su detalle (diagnóstico de uno solo).
    st.markdown(
        '<p class="mq-estudio-torre-kicker">👤 Elegí el cliente a gestionar</p>',
        unsafe_allow_html=True,
    )

    with st.expander("📊 Tablero general — diagnóstico de todos los clientes (cálculo completo)", expanded=False):
        _render_dashboard_estudio(ctx)

    # ── Seleccionar cliente para abrir / generar informe ───────────────────
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
            _nom_btn = str(df.loc[df["ID"] == cid, "Nombre"].iloc[0])
            _nom_corto = _nom_btn.split("|")[0].strip()[:20]
            if col_ver.button(f"Abrir {_nom_corto}", key="btn_estudio_ver",
                              use_container_width=True):
                st.session_state["cliente_id"] = cid
                st.session_state["cliente_nombre"] = _nom_btn
                st.success(f"Cartera del cliente ID {cid} activa.")
                st.rerun()

            _render_ficha_cliente_rapida(int(cid), _nom_btn, ctx)

            # Pasos 3-5: agregar capital → objetivo → recomendar → adjuntar.
            # Expander para no abrumar la ficha; se abre al gestionar el aporte.
            with st.expander(
                f"💰 Agregar capital y recomendar — {_nom_corto}", expanded=False
            ):
                _render_wizard_capital_estudio(int(cid), _nom_btn, ctx)

            if col_rpt.button("📄 Generar informe", key="btn_estudio_rpt",
                              use_container_width=True):
                with st.spinner("Generando informe..."):
                    try:
                        from core.diagnostico_types import (
                            RENDIMIENTO_MODELO_YTD_REF,
                            perfil_diagnostico_valido,
                        )
                        from services.diagnostico_cartera import diagnosticar
                        from services.recomendacion_capital import recomendar
                        from services.reporte_inversor import generar_reporte_inversor

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
                        st.markdown(
                            '<div class="mq-estudio-spacer-sm" aria-hidden="true"></div>',
                            unsafe_allow_html=True,
                        )
                        with st.expander("📧 Enviar informe al cliente por email", expanded=False):
                            from services.email_sender import (
                                enviar_email_gmail,
                                verificar_config_email,
                            )
                            ok_cfg, _gmail_user, msg_cfg = verificar_config_email(
                                ctx.get("dbm")
                            )
                            if not ok_cfg:
                                st.caption(
                                    "Gmail no configurado: " + str(msg_cfg) + "  \n"
                                    "Agregá `GMAIL_USER` y `GMAIL_APP_PASSWORD` en `.env`."
                                )
                            else:
                                email_dest = st.text_input(
                                    "Email del cliente",
                                    key="email_dest_informe",
                                    placeholder="cliente@email.com",
                                )
                                if st.button(
                                    "Enviar informe",
                                    key="btn_enviar_email_informe",
                                    use_container_width=True,
                                    type="primary",
                                ):
                                    if not can_action(ctx, "write"):
                                        st.warning("No tenés permiso para enviar informes por email.")
                                    elif not email_dest or "@" not in email_dest:
                                        st.error("Ingresá un email válido.")
                                    else:
                                        with st.spinner("Enviando..."):
                                            ok, msg = enviar_email_gmail(
                                                destinatario=email_dest,
                                                asunto=(
                                                    "Informe de cartera — "
                                                    + nombre_cli
                                                    + " — "
                                                    + date.today().strftime("%B %Y")
                                                ),
                                                cuerpo_html=html,
                                            )
                                            if ok:
                                                st.success("✓ Enviado a " + email_dest)
                                            else:
                                                st.error("Error: " + str(msg))

                    except Exception as e:
                        st.warning(f"No se pudo generar el informe: {e}")

            with st.expander("📝 Mis notas (privadas — no las ve el cliente)", expanded=False):
                _notas_act = dbm.obtener_notas_asesor(int(cid), tenant_id=tenant_id)
                _notas_new = st.text_area(
                    "Notas internas",
                    value=_notas_act,
                    height=90,
                    key=f"notas_asesor_{cid}",
                    placeholder=(
                        "Próxima reunión: 15/05. "
                        "No invertir en tabaco. "
                        "Horizonte real: 5 años..."
                    ),
                )
                if st.button("Guardar notas", key=f"btn_notas_{cid}"):
                    if not can_action(ctx, "write"):
                        st.warning("No tenés permiso para guardar notas.")
                    else:
                        dbm.guardar_notas_asesor(int(cid), _notas_new, tenant_id=tenant_id)
                        st.success("✓ Notas guardadas")

    with col_nuevo:
        if st.button("➕ Nuevo cliente", key="btn_nuevo_cliente",
                     use_container_width=True):
            if not can_action(ctx, "write"):
                st.warning("No tenés permiso para crear clientes.")
            else:
                st.session_state["wizard_step"] = 1
                st.rerun()

    # Si hay wizard activo (botón "Nuevo cliente" presionado previamente)
    if st.session_state.get("wizard_step"):
        st.divider()
        _render_wizard_onboarding(ctx)
