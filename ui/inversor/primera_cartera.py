"""
ui/inversor/primera_cartera.py — bienvenida + wizard de objetivos + armado de primera cartera.

Extraído de ui/tab_inversor.py (Fase 2.1, cuarto slice). Cluster autocontenido:
_render_bienvenida_inversor (entrada desde el orquestador) → primera cartera
con wizard de objetivos, plan multi-objetivo, plan explicado (Pilar 3),
tabla editable y confirmación con auditoría.
"""
from __future__ import annotations

import html
import time
from datetime import date

import pandas as pd
import streamlit as st

from core.diagnostico_types import CARTERA_IDEAL, perfil_diagnostico_valido
from ui.inversor._helpers import (
    _TIPOS_EDICION_PRIMERA_CARTERA,
    _cartera_resuelta_primera_cartera,
    _flag_plan_explicado,
    _horizonte_ui,
    _log_degradacion,
    _mix_rf_desde_filas_primera,
    _precios_para_recomendar,
    _tipo_universo_ticker,
)
from ui.mq26_ux import fig_torta_ideal


def _render_bienvenida_inversor(ctx: dict) -> None:
    """Bienvenida sin cartera: una pregunta, dos caminos, carga o primera cartera."""
    st.session_state.setdefault("inv_carga_open", False)
    nombre = str(ctx.get("cliente_nombre", "")).split("|")[0].strip() or "inversor"
    perfil = str(ctx.get("cliente_perfil", "Moderado"))

    st.markdown(
        f"""
    <div class="mq-motion-page-fade mq-inv-hero-wrap">
        <h2 class="mq-inv-h2-hero">
            Hola, {html.escape(nombre)} 👋
        </h2>
        <p class="mq-inv-lead">
            ¿Ya tenés activos en el broker o querés armar tu primera cartera con una sugerencia?
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact" style="margin-top:0.5rem;">
        Mi primera cartera
    </h3>
    """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Todavía no hay posiciones cargadas. Podés importar lo que ya tenés en el broker, "
        "cargar a mano, o pedir una **cartera sugerida** según tu perfil de arriba "
        "(simulación; no es promesa de resultado)."
    )

    col_si, col_no = st.columns(2, gap="large")

    with col_si:
        st.markdown(
            """
        <div class="mq-inv-card mq-inv-card--accent">
            <div class="mq-inv-card-emoji">📂</div>
            <div class="mq-inv-card-title">
                Ya tengo activos
            </div>
            <div class="mq-inv-card-body">
                Importá tu resumen del broker (Balanz, IOL, BMB)
                o cargá tus posiciones una por una.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mq-inv-spacer-sm"></div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📥 Importar broker", use_container_width=True, key="bienvenida_importar"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "importar"
                st.rerun()
        with c2:
            if st.button("✏️ Cargar uno por uno", use_container_width=True, key="bienvenida_manual"):
                st.session_state["inv_carga_open"] = True
                st.session_state["inv_carga_tab"] = "manual"
                st.rerun()

    with col_no:
        st.markdown(
            f"""
        <div class="mq-inv-card mq-inv-card--green">
            <div class="mq-inv-card-emoji">🚀</div>
            <div class="mq-inv-card-title">
                Cartera sugerida (desde cero)
            </div>
            <div class="mq-inv-card-body">
                El motor propone una primera cartera para tu perfil
                <strong class="mq-inv-strong-green">{html.escape(perfil)}</strong>
                con el monto en pesos que indiques. La operación real la hacés en tu broker.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="mq-inv-spacer-sm"></div>', unsafe_allow_html=True)
        if st.button(
            "✨ Armar mi primera cartera",
            use_container_width=True,
            type="primary",
            key="bienvenida_sugerencia",
        ):
            st.session_state["inv_mostrar_sugerencia"] = True
            st.rerun()

    if st.session_state.get("inv_carga_open"):
        st.divider()
        _fn = ctx.get("render_carga_activos_fn")
        if _fn is None:
            from ui.carga_activos import render_carga_activos as _fn
        _fn(ctx)

    if st.session_state.get("inv_mostrar_sugerencia"):
        st.divider()
        _render_primera_cartera_inversor(ctx)


def _render_wizard_objetivos(ctx: dict) -> None:
    """
    Paso 0 del wizard de primera cartera: ¿Qué querés lograr?

    Presenta 9 objetivos CP/MP/LP en 3 columnas. El inversor elige
    los que aplican y continúa. Los seleccionados se guardan en
    session_state["pci_objetivos"] para que el motor los use.
    """
    from services.portfolio_optimizer import CATALOGO_OBJETIVOS

    st.markdown(
        """
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact">
        ¿Qué querés lograr con esta inversión?
    </h3>
    <p class="mq-inv-muted-p" style="margin-bottom:1rem;">
        Elegí uno o más objetivos. La cartera se va a armar en función de lo que necesitás.
        Podés seleccionar objetivos de distintos horizontes — el motor distribuye el capital entre ellos.
    </p>
    """,
        unsafe_allow_html=True,
    )

    # Definición visual de cada objetivo (ícono, color de borde, descripción corta)
    _OBJ_UI: dict[str, dict] = {
        "CP1": {"icono": "🛡️", "color": "#2ECC71",
                "titulo": "Fondo de emergencia",
                "corto": "3–6 meses de gastos, liquidez inmediata."},
        "CP2": {"icono": "⚡", "color": "#27AE60",
                "titulo": "Capital de trabajo",
                "corto": "Plata operativa a 30–90 días."},
        "CP3": {"icono": "🎯", "color": "#F39C12",
                "titulo": "Reserva de oportunidad",
                "corto": "Dry powder para aprovechar bajas de mercado."},
        "MP1": {"icono": "💵", "color": "#3498DB",
                "titulo": "Renta en dólares",
                "corto": "Flujo semestral en USD vía ONs 7–9% TIR."},
        "MP2": {"icono": "📊", "color": "#9B59B6",
                "titulo": "Cobertura inflación",
                "corto": "BONCER/LECAP — preservar poder adquisitivo ARS."},
        "MP3": {"icono": "🌐", "color": "#1ABC9C",
                "titulo": "Diversificación internacional",
                "corto": "S&P 500 / Nasdaq vía CEDEARs."},
        "LP1": {"icono": "🏦", "color": "#E67E22",
                "titulo": "Acumulación patrimonial",
                "corto": "ONs largas 2030+, TIR ≥ 7%, capital en USD."},
        "LP2": {"icono": "🌅", "color": "#E74C3C",
                "titulo": "Jubilación / FIRE",
                "corto": "Construir independencia financiera a 10–20 años."},
        "LP3": {"icono": "🚀", "color": "#2980B9",
                "titulo": "Crecimiento USD",
                "corto": "Acciones growth/value, retorno esperado 12–15%/año."},
    }

    # Agrupar por horizonte
    grupos = {
        "⚡ Corto Plazo  ≤ 12 meses": ["CP1", "CP2", "CP3"],
        "📈 Mediano Plazo  1–3 años":  ["MP1", "MP2", "MP3"],
        "🏦 Largo Plazo  3–15 años":   ["LP1", "LP2", "LP3"],
    }

    # Recuperar selección previa (si el usuario vuelve)
    seleccionados: set[str] = set(st.session_state.get("pci_objetivos") or [])

    for grupo_label, codigos in grupos.items():
        st.markdown(
            f"<p style='font-size:0.72rem;font-weight:700;color:var(--c-text-3);"
            f"text-transform:uppercase;letter-spacing:0.08em;margin:0.8rem 0 0.3rem 0;'>"
            f"{grupo_label}</p>",
            unsafe_allow_html=True,
        )
        cols = st.columns(3, gap="small")
        for col, cod in zip(cols, codigos, strict=False):
            ui = _OBJ_UI[cod]
            cfg = CATALOGO_OBJETIVOS[cod]
            activo = cod in seleccionados
            borde = f"2px solid {ui['color']}" if activo else "1px solid #3a3a3a"
            bg = f"{ui['color']}1A" if activo else "transparent"
            with col:
                # Tarjeta visual
                st.markdown(
                    f"""<div style="border:{borde};border-radius:8px;padding:0.65rem 0.75rem;
                    background:{bg};margin-bottom:0.2rem;min-height:90px;">
                    <span style="font-size:1.3rem;">{ui['icono']}</span>
                    <span style="font-weight:600;font-size:0.82rem;"> {ui['titulo']}</span><br>
                    <span style="font-size:0.72rem;color:var(--c-text-3);">{ui['corto']}</span><br>
                    <span style="font-size:0.68rem;color:{ui['color']};">
                        ~{cfg.retorno_esperado_usd_anual:.0f}% USD/año · {cfg.liquidez} liquidez
                    </span></div>""",
                    unsafe_allow_html=True,
                )
                checked = st.checkbox(
                    "Seleccionar" if not activo else "✔ Elegido",
                    value=activo,
                    key=f"pci_obj_{cod}",
                    label_visibility="collapsed",
                )
                if checked:
                    seleccionados.add(cod)
                else:
                    seleccionados.discard(cod)

    st.session_state["pci_objetivos"] = list(seleccionados)

    st.divider()

    if not seleccionados:
        st.info("👆 Elegí al menos un objetivo para continuar.")
        return

    # Resumen de lo seleccionado
    obj_labels = " · ".join(
        f"{_OBJ_UI[c]['icono']} **{_OBJ_UI[c]['titulo']}**"
        for c in sorted(seleccionados)
        if c in _OBJ_UI
    )
    st.success(f"Objetivos elegidos: {obj_labels}")

    if st.button(
        "Continuar — ingresar capital →",
        type="primary",
        use_container_width=True,
        key="btn_pci_objetivos_ok",
    ):
        st.session_state["pci_wizard_paso"] = 1
        st.rerun()


def _render_primera_cartera_inversor(ctx: dict) -> None:
    """Primera cartera: wizard objetivos → capital → cálculo."""
    # ── Paso 0: objetivos (wizard) ────────────────────────────────────────────
    wizard_paso = st.session_state.get("pci_wizard_paso", 0)
    objetivos_elegidos: list[str] = st.session_state.get("pci_objetivos") or []

    if wizard_paso == 0:
        _render_wizard_objetivos(ctx)
        return

    # ── Pasó el wizard — mostrar resumen de objetivos + link para volver ──────
    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    horizonte = _horizonte_ui(ctx)
    ccl = float(ctx.get("ccl") or 1150.0)
    perfil_v = perfil_diagnostico_valido(perfil)

    # Encabezado con breadcrumb de objetivos
    from services.portfolio_optimizer import CATALOGO_OBJETIVOS as _CAT_OBJ
    obj_resumen = ", ".join(
        f"{cod} {_CAT_OBJ[cod].nombre}" for cod in objetivos_elegidos if cod in _CAT_OBJ
    ) or "sin objetivos"

    st.markdown(
        f"""
    <h3 class="mq-inv-h2-hero mq-inv-h2-hero--compact">
        Cartera sugerida — armá tu primera cartera
    </h3>
    <p class="mq-inv-muted-p" style="margin-bottom:0.5rem;">
        <strong>Objetivos:</strong> {obj_resumen}
    </p>
    <p class="mq-inv-muted-p" style="margin-bottom:0.75rem;">
        La cartera se construye en función de esos objetivos, tu perfil
        <strong>{html.escape(perfil)}</strong> y el monto disponible.
    </p>
    <p class="mq-inv-step-label">
        Paso 2 de 3 — Tu capital disponible
    </p>
    """,
        unsafe_allow_html=True,
    )

    if st.button("← Cambiar objetivos", key="btn_pci_volver_obj"):
        st.session_state["pci_wizard_paso"] = 0
        st.session_state.pop("pci_resultado", None)
        st.rerun()

    col_monto, col_info = st.columns([3, 2])
    with col_monto:
        capital_ars = st.number_input(
            "¿Cuánto querés invertir? (ARS)",
            min_value=10_000.0,
            max_value=100_000_000.0,
            value=500_000.0,
            step=50_000.0,
            format="%.0f",
            key="pci_capital_ars",
            help="El motor distribuye este monto según tus objetivos y perfil.",
        )
        flujo_mensual_ars = st.number_input(
            "Aporte mensual recurrente (ARS, opcional)",
            min_value=0.0,
            max_value=10_000_000.0,
            value=0.0,
            step=10_000.0,
            format="%.0f",
            key="pci_flujo_mensual_ars",
            help="¿Pensás sumar plata todos los meses? Mejora la proyección a futuro.",
        )
    with col_info:
        capital_usd = capital_ars / max(ccl, 1.0)
        flujo_usd = flujo_mensual_ars / max(ccl, 1.0)
        st.markdown(
            f"""
        <div class="mq-inv-kpi-box">
            <div class="mq-inv-kpi-label">Tu inversión</div>
            <div class="mq-inv-kpi-value">$ {capital_ars:,.0f} ARS</div>
            <div class="mq-inv-kpi-hint">
                ~ USD {capital_usd:,.0f} (CCL {ccl:,.0f})</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if flujo_mensual_ars > 0:
            st.markdown(
                f"""
            <div class="mq-inv-kpi-box" style="margin-top:0.5rem;">
                <div class="mq-inv-kpi-label">Aporte mensual</div>
                <div class="mq-inv-kpi-value">$ {flujo_mensual_ars:,.0f} ARS</div>
                <div class="mq-inv-kpi-hint">~ USD {flujo_usd:,.0f}/mes</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--tight">
        Paso 3 de 3 — La app calcula por vos
    </p>
    <p class="mq-inv-muted-p">
        Perfil, objetivos, mercado y señales técnicas. Solo presioná el botón.
    </p>
    """,
        unsafe_allow_html=True,
    )

    if st.button(
        f"🧠 Calcular cartera óptima para perfil {perfil}",
        type="primary",
        use_container_width=True,
        key="btn_calcular_primera_cartera",
    ):
        with st.spinner("Calculando tu cartera óptima…"):
            try:
                from services.recomendacion_capital import generar_primera_cartera

                # Guardar flujo mensual en session_state para mostrarlo en resultados
                st.session_state["pci_flujo_mensual_ars_calc"] = float(flujo_mensual_ars)

                # df_scores (scanner 60/20/20) mejora selección de CEDEARs;
                # si no está disponible, el motor usa scoring estático por sector.
                _df_scores_pci = st.session_state.get("df_scores")
                if not isinstance(_df_scores_pci, pd.DataFrame) or _df_scores_pci.empty:
                    _df_scores_pci = None

                rr = generar_primera_cartera(
                    capital_ars=float(capital_ars),
                    perfil=perfil_v,
                    ccl=ccl,
                    precios_dict=_precios_para_recomendar(ctx),
                    universo_df=ctx.get("universo_df"),
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                    df_analisis=ctx.get("df_analisis"),
                    df_scores=_df_scores_pci,
                )
                from services.recomendacion_capital import _expandir_ideal
                st.session_state["pci_resultado"] = {
                    "capital": float(capital_ars),
                    "rr": rr,
                    "perfil": perfil_v,
                    "ideal": _expandir_ideal(
                        CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"]),
                        perfil_v,
                        df_scores=_df_scores_pci,
                    ),
                }

                # ── Plan multi-objetivo (sidebar del resultado) ───────────────
                # Si el usuario eligió objetivos, calculamos el plan CP/MP/LP en
                # paralelo y lo guardamos para mostrarlo como contexto de la cartera.
                if objetivos_elegidos:
                    try:
                        from services.portfolio_optimizer import calcular_plan_multifuncional
                        _flujo_usd = float(flujo_mensual_ars) / max(ccl, 1.0)
                        _capital_usd = float(capital_ars) / max(ccl, 1.0)
                        plan = calcular_plan_multifuncional(
                            objetivos_elegidos,
                            capital_inicial_usd=_capital_usd,
                            flujo_mensual_usd=_flujo_usd,
                            ccl=ccl,
                        )
                        st.session_state["pci_plan_objetivos"] = plan
                    except Exception as _ep:
                        _log_degradacion(ctx, "pci_plan_objetivos_error", _ep)
                        st.session_state.pop("pci_plan_objetivos", None)

                try:
                    from services.audit_trail import registrar_recomendacion_evento

                    registrar_recomendacion_evento(
                        evento="SIMULACION_RECOMENDACION",
                        origen="primera_cartera",
                        cliente_id=ctx.get("cliente_id"),
                        cliente_nombre=str(ctx.get("cliente_nombre", "")),
                        tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                        actor=str(ctx.get("login_user", "") or ""),
                        correlation_id=str(st.session_state.get("session_correlation_id", "")),
                        cartera=str(_cartera_resuelta_primera_cartera(ctx)),
                        perfil=perfil_v,
                        capital_ars=float(capital_ars),
                        filas=len(list(getattr(rr, "compras_recomendadas", None) or [])),
                        payload={
                            "alerta_mercado": bool(getattr(rr, "alerta_mercado", False)),
                            "capital_remanente_ars": float(getattr(rr, "capital_remanente_ars", 0) or 0),
                            "objetivos": objetivos_elegidos,
                            "flujo_mensual_ars": float(flujo_mensual_ars),
                        },
                    )
                except Exception as exc:
                    _log_degradacion(ctx, "audit_evento_simulacion_fallo", exc)
                # Pilar 3: plan explicado de la primera cartera al audit trail
                try:
                    from services.recomendador_explicable import (
                        auditar_plan,
                        construir_plan_accion,
                    )

                    _plan_pci = construir_plan_accion(
                        perfil=perfil_v,
                        rr=rr,
                        capital_ars=float(capital_ars),
                        precio_records=ctx.get("precio_records"),
                    )
                    st.session_state["pci_plan_explicado"] = _plan_pci
                    auditar_plan(
                        _plan_pci,
                        ctx={
                            "cliente_id": ctx.get("cliente_id"),
                            "cliente_nombre": str(ctx.get("cliente_nombre", "")),
                            "tenant_id": str(ctx.get("tenant_id", "default") or "default"),
                            "login_user": str(ctx.get("login_user", "") or ""),
                            "correlation_id": str(st.session_state.get("session_correlation_id", "")),
                            "cartera_activa": str(_cartera_resuelta_primera_cartera(ctx)),
                        },
                    )
                except Exception:
                    st.session_state.pop("pci_plan_explicado", None)
                st.rerun()
            except Exception as e:
                st.error(f"Error al calcular: {e}")

    res = st.session_state.get("pci_resultado")
    cap_ui = float(st.session_state.get("pci_capital_ars", 0) or 0)
    if not res or abs(float(res.get("capital", -1)) - cap_ui) >= 1.0:
        return

    rr = res["rr"]
    perfil_res = str(res.get("perfil") or perfil_v)

    if getattr(rr, "alerta_mercado", False):
        st.warning(f"⚠️ {rr.mensaje_alerta}")

    items = list(getattr(rr, "compras_recomendadas", None) or [])
    if not items:
        st.info(
            "No se encontraron compras posibles con el capital disponible. "
            "Probá con otro monto o consultá a tu asesor."
        )
        return

    # Pilar 3: cada sugerencia con su porqué, confianza de datos y link a ficha
    _plan_pci_exp = st.session_state.get("pci_plan_explicado")
    if _plan_pci_exp is not None and _flag_plan_explicado(ctx):
        with st.expander("🧭 Por qué esta cartera — plan explicado", expanded=False):
            from ui.components.plan_accion_view import render_plan_accion

            render_plan_accion(_plan_pci_exp, key_prefix="pci_plan")

    # ── Panel de objetivos — plan multi-objetivo (si está disponible) ──────────
    plan_obj = st.session_state.get("pci_plan_objetivos")
    if plan_obj is not None and objetivos_elegidos:
        try:
            import plotly.express as px
            import plotly.graph_objects as go

            from services.portfolio_optimizer import (
                proyeccion_consolidada_df as _proy_df,
            )

            _colores_obj = {
                "CP1": "#2ECC71", "CP2": "#27AE60", "CP3": "#F39C12",
                "MP1": "#3498DB", "MP2": "#9B59B6", "MP3": "#1ABC9C",
                "LP1": "#E67E22", "LP2": "#E74C3C", "LP3": "#2980B9",
            }

            with st.expander("📊 Plan por objetivos — proyección y distribución", expanded=True):
                st.markdown(
                    f"Capital **USD {plan_obj.capital_total_usd:,.0f}** distribuido entre "
                    f"**{len(plan_obj.tramos)} objetivo(s)**: "
                    + " · ".join(
                        f"`{t.objetivo}` {t.nombre} ({t.horizonte_meses}m)"
                        for t in plan_obj.tramos
                    )
                )

                col_pie, col_proy = st.columns([1, 2], gap="medium")

                with col_pie:
                    from services.portfolio_optimizer import asignacion_pie_df as _pie_df
                    df_pie = _pie_df(plan_obj)
                    if not df_pie.empty:
                        df_pie["label"] = df_pie["objetivo"] + "<br>" + df_pie["nombre"].str[:18]
                        fig_pie = px.pie(
                            df_pie,
                            names="label",
                            values="capital_usd",
                            color="objetivo",
                            color_discrete_map=_colores_obj,
                            hole=0.42,
                            title="Capital por objetivo",
                        )
                        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        fig_pie.update_layout(
                            height=260, margin=dict(l=5, r=5, t=35, b=5), showlegend=False
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)

                with col_proy:
                    df_proy = _proy_df(plan_obj)
                    if not df_proy.empty:
                        fig_l = go.Figure()
                        for t in plan_obj.tramos:
                            sub = df_proy[df_proy["objetivo"] == t.objetivo]
                            color = _colores_obj.get(t.objetivo, "#888")
                            fig_l.add_trace(go.Scatter(
                                x=sub["fecha"], y=sub["valor_usd"],
                                mode="lines",
                                name=f"{t.objetivo} — {t.nombre}",
                                line=dict(color=color, width=2),
                                hovertemplate=f"<b>{t.objetivo}</b><br>USD %{{y:,.0f}}<extra></extra>",
                            ))
                        fig_l.update_layout(
                            title="Proyección FV USD por objetivo",
                            xaxis_title="Fecha", yaxis_title="USD",
                            height=260,
                            margin=dict(l=10, r=10, t=35, b=10),
                            legend=dict(orientation="h", y=-0.25),
                            hovermode="x unified",
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                        )
                        fig_l.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
                        fig_l.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
                        st.plotly_chart(fig_l, use_container_width=True)

                # KPIs de valor final por tramo
                _tcols = st.columns(min(len(plan_obj.tramos), 4))
                for _i, _t in enumerate(plan_obj.tramos):
                    _ret = _t.valor_final_usd - _t.capital_inicial_usd
                    _pct = (_ret / _t.capital_inicial_usd * 100) if _t.capital_inicial_usd > 0 else 0
                    _tcols[_i % len(_tcols)].metric(
                        f"{_t.objetivo} ({_t.horizonte_meses}m)",
                        f"USD {_t.valor_final_usd:,.0f}",
                        f"+USD {_ret:,.0f} ({_pct:.1f}%)" if _ret >= 0 else f"USD {_ret:,.0f}",
                    )

                if plan_obj.advertencias_globales:
                    for _adv in plan_obj.advertencias_globales:
                        st.warning(_adv)
        except Exception as _ep:
            _log_degradacion(ctx, "pci_plan_objetivos_render", _ep)

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--step3">Paso 3 — Tu cartera sugerida (editable)</p>
    <p class="mq-inv-muted-p">
        Ajustá cantidades, precio por cuotaparte (ARS) o el instrumento. Podés agregar o quitar filas.
        Cuando esté bien, confirmá para guardarla como punto de partida y seguir en la app.
    </p>
    """,
        unsafe_allow_html=True,
    )

    monto_total = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)
    _udf_pc = ctx.get("universo_df")
    _rows_ed: list[dict] = []
    for it in items:
        _tk = str(getattr(it, "ticker", "") or "").strip().upper()
        if not _tk:
            continue
        _rows_ed.append(
            {
                "Ticker": _tk,
                "Unidades": int(getattr(it, "unidades", 0) or 0),
                "Precio_ARS": float(getattr(it, "precio_ars_estimado", 0) or 0),
                "TIPO": _tipo_universo_ticker(_tk, _udf_pc),
                "Notas": str(getattr(it, "justificacion", "") or "")[:120],
            }
        )
    df_ed_base = pd.DataFrame(_rows_ed)
    edited = st.data_editor(
        df_ed_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="pci_data_editor_cartera",
        column_config={
            "Ticker": st.column_config.TextColumn("Ticker", help="Código BYMA", width="small"),
            "Unidades": st.column_config.NumberColumn("Unidades", min_value=0, step=1, width="small"),
            "Precio_ARS": st.column_config.NumberColumn(
                "Precio ARS c/u",
                min_value=0.0,
                format="%.2f",
                help="Pesos por cuotaparte en BYMA.",
            ),
            "TIPO": st.column_config.SelectboxColumn(
                "Tipo",
                options=_TIPOS_EDICION_PRIMERA_CARTERA,
                width="small",
            ),
            "Notas": st.column_config.TextColumn("Notas (solo guía)", width="large"),
        },
    )

    ideal_dict = res.get("ideal") or {}
    try:
        _nu = pd.to_numeric(edited["Unidades"], errors="coerce").fillna(0)
        _npx = pd.to_numeric(edited["Precio_ARS"], errors="coerce").fillna(0)
        monto_editado = float((_nu * _npx).sum())
    except Exception as exc:
        _log_degradacion(ctx, "monto_editado_calculo_fallo", exc)
        monto_editado = monto_total

    st.markdown(
        f"""
    <div class="mq-inv-totals-bar">
        <div><div class="mq-inv-totals-kpi-label">Total tabla (estim.)</div>
        <div class="mq-inv-totals-kpi-num">
            ${monto_editado:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Motor (referencia)</div>
        <div class="mq-inv-totals-kpi-num mq-inv-totals-kpi-num--muted">
            ${monto_total:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Queda en efectivo (ref.)</div>
        <div class="mq-inv-totals-kpi-num--plain">${remanente:,.0f} ARS</div></div>
        <div><div class="mq-inv-totals-kpi-label">Perfil</div>
        <div class="mq-inv-perfil-name">{html.escape(perfil_res)}</div></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if ideal_dict:
        fig_t = fig_torta_ideal(perfil_res, ideal_dict)
        if fig_t:
            with st.expander("Ver distribución objetivo de la cartera", expanded=False):
                st.plotly_chart(fig_t, use_container_width=True)

    _cart_guardar = _cartera_resuelta_primera_cartera(ctx)
    st.caption(f"Al confirmar, las compras se guardan en: **`{_cart_guardar}`**")

    st.info(
        "💡 Es una sugerencia según tu perfil y el mercado. "
        "La confirmación registra **COMPRAS** en tu libro (como si ya hubieras operado), para poder ver métricas y el resto de la app."
    )
    _confirm_exec_real = st.checkbox(
        "Confirmo que ya ejecuté estas operaciones en mi broker",
        key="pci_confirm_exec_real",
    )

    col_ok, col_act, col_reset = st.columns(3)
    with col_ok:
        if st.button(
            "✅ Confirmar como mi cartera",
            type="primary",
            use_container_width=True,
            key="pci_confirmar_cartera",
            disabled=not _confirm_exec_real,
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
                    if _ti in ("NAN", "NONE", ""):
                        _ti = "CEDEAR"
                    if _ti in ("COMPRA", "VENTA"):
                        _ti = "CEDEAR"
                    if not _tick or _u <= 0 or _px <= 0:
                        continue
                    _ppc_ars = round(_px, 4)
                    _ppc_usd = round(_ppc_ars / max(_ccl_ok, 1e-9), 6)
                    _filas.append(
                        {
                            "FECHA_COMPRA": date.today(),
                            "TICKER": _tick,
                            "CANTIDAD": _u,
                            "PPC_USD": _ppc_usd,
                            "PPC_ARS": _ppc_ars,
                            "TIPO": _ti,
                            "LAMINA_VN": float("nan"),
                        }
                    )
                if not _filas:
                    st.error(
                        "No hay filas válidas: cada una necesita **Ticker**, **Unidades** > 0 y **Precio ARS** > 0."
                    )
                else:
                    _mix_rf = _mix_rf_desde_filas_primera(_filas)
                    st.session_state["inv_mix_plan"] = {
                        "rf": round(_mix_rf, 5),
                        "ts": time.time(),
                    }
                    st.session_state.pop("inv_diagnostico", None)
                    try:
                        from services.audit_trail import registrar_recomendacion_evento

                        registrar_recomendacion_evento(
                            evento="EJECUCION_CONFIRMADA",
                            origen="primera_cartera",
                            cliente_id=ctx.get("cliente_id"),
                            cliente_nombre=str(ctx.get("cliente_nombre", "")),
                            tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                            actor=str(ctx.get("login_user", "") or ""),
                            correlation_id=str(st.session_state.get("session_correlation_id", "")),
                            cartera=str(_cart_guardar),
                            perfil=perfil_res,
                            capital_ars=float(cap_ui),
                            filas=len(_filas),
                            payload={"confirmacion_broker": True},
                        )
                    except Exception:
                        pass
                    _persist_filas(
                        ctx,
                        _filas,
                        "agregar",
                        cartera_override=_cart_guardar,
                        session_keys_clear=["pci_resultado", "inv_mostrar_sugerencia"],
                    )

    with col_act:
        if st.button("✏️ Cargar lo que compré", use_container_width=True, key="pci_ir_a_carga"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "manual"
            st.session_state.pop("pci_resultado", None)
            st.rerun()
    with col_reset:
        if st.button("🔄 Recalcular con otro monto", use_container_width=True, key="pci_reset"):
            st.session_state.pop("pci_resultado", None)
            st.session_state.pop("inv_mix_plan", None)
            st.rerun()


