"""
ui/inversor/plata_nueva.py — bloque «¿Qué compro ahora?» (capital incremental).

Extraído de ui/tab_inversor.py (Fase 2.1, tercer slice). Flujo completo:
input de capital → motor de recomendación sobre la cartera actual → plan
explicado (Pilar 3) → tabla editable → confirmación con persistencia y
auditoría.
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
    _market_stress_optional,
    _mix_objetivo_desde_sesion,
    _mix_rf_desde_filas_primera,
    _precios_para_recomendar,
    _senales_precalculadas,
    _tipo_universo_ticker,
)
from ui.mq26_ux import fig_torta_ideal


def _render_bloque_plata_nueva(ctx: dict, df_ag, _diag, ccl: float) -> None:
    """
    Capital nuevo + sugerencias: mismo flujo que «Armar mi primera cartera», pero
    el motor recibe tu cartera actual (df_ag) y un diagnóstico alineado al perfil.
    """
    st.markdown("### ¿Qué compro ahora?")
    perfil = str(ctx.get("cliente_perfil", "Moderado"))
    perfil_v = perfil_diagnostico_valido(perfil)
    horizonte = _horizonte_ui(ctx)
    ccl_f = float(ccl or 1150.0)
    df_ag_use = df_ag if df_ag is not None else pd.DataFrame()

    cap_default = float(ctx.get("capital_nuevo", 0.0) or 0.0)
    cap_side = float(st.session_state.get("capital_disponible_mq", 0.0) or 0.0)
    if cap_side > 0:
        cap_default = cap_side

    st.markdown(
        """
    <p class="mq-inv-step-label">
        Paso 1 de 2 — Capital que querés sumar
    </p>
    """,
        unsafe_allow_html=True,
    )
    col_monto, col_info = st.columns([3, 2])
    with col_monto:
        cap_in = st.number_input(
            "¿Cuánto querés invertir ahora? (ARS)",
            min_value=10_000.0,
            max_value=100_000_000.0,
            value=float(max(10_000.0, cap_default)) if cap_default > 0 else 500_000.0,
            step=50_000.0,
            format="%.0f",
            key="inversor_capital_ars",
            help="El motor reparte este monto respetando tu cartera actual y tu perfil.",
        )
    with col_info:
        cap_usd = float(cap_in) / max(ccl_f, 1.0)
        st.markdown(
            f"""
        <div class="mq-inv-kpi-box mq-inv-kpi-box--offset">
            <div class="mq-inv-kpi-label">Plata nueva</div>
            <div class="mq-inv-kpi-value">$ {float(cap_in):,.0f} ARS</div>
            <div class="mq-inv-kpi-hint">
                Referencia ~ USD {cap_usd:,.0f} (CCL {ccl_f:,.0f}) · ya tenés cartera cargada</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
    <p class="mq-inv-step-label mq-inv-step-label--tight">
        Paso 2 de 2 — La app calcula por vos
    </p>
    <p class="mq-inv-muted-p">
        Misma lógica que «mi primera cartera»: perfil, mercado y señales. Incluye lo que ya tenés para no duplicar el espíritu del plan.
    </p>
    """,
        unsafe_allow_html=True,
    )

    stress = _market_stress_optional()
    if st.button(
        f"🧠 Calcular sugerencias (perfil {perfil})",
        type="primary",
        use_container_width=True,
        key="btn_recomendar_inversor",
    ):
        with st.spinner("Calculando sugerencias sobre tu cartera actual…"):
            try:
                from services.diagnostico_cartera import diagnosticar
                from services.recomendacion_capital import recomendar

                metricas = ctx.get("metricas") or {}
                senales = _senales_precalculadas(ctx)
                mix_o = _mix_objetivo_desde_sesion(df_ag_use, ctx.get("universo_df"))
                diag_fresh = diagnosticar(
                    df_ag=df_ag_use,
                    perfil=perfil,
                    horizonte_label=horizonte,
                    metricas=metricas,
                    ccl=ccl_f,
                    universo_df=ctx.get("universo_df"),
                    senales_salida=senales,
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                    mix_objetivo_rf=mix_o,
                )
                rr = recomendar(
                    df_ag=df_ag_use,
                    perfil=perfil_v,
                    horizonte_label=horizonte,
                    capital_ars=float(cap_in),
                    ccl=ccl_f,
                    precios_dict=_precios_para_recomendar(ctx),
                    diagnostico=diag_fresh,
                    universo_df=ctx.get("universo_df"),
                    df_analisis=ctx.get("df_analisis"),
                    market_stress=stress,
                    cliente_nombre=str(ctx.get("cliente_nombre", "")),
                )
                st.session_state["inv_plata_resultado"] = {
                    "capital": float(cap_in),
                    "rr": rr,
                    "perfil": perfil_v,
                    "ideal": CARTERA_IDEAL.get(perfil_v, CARTERA_IDEAL["Moderado"]),
                }
                st.session_state["inv_recomendacion"] = {"capital": float(cap_in), "rr": rr}
                try:
                    from services.audit_trail import registrar_recomendacion_evento

                    registrar_recomendacion_evento(
                        evento="SIMULACION_RECOMENDACION",
                        origen="capital_incremental",
                        cliente_id=ctx.get("cliente_id"),
                        cliente_nombre=str(ctx.get("cliente_nombre", "")),
                        tenant_id=str(ctx.get("tenant_id", "default") or "default"),
                        actor=str(ctx.get("login_user", "") or ""),
                        correlation_id=str(st.session_state.get("session_correlation_id", "")),
                        cartera=str(_cartera_resuelta_primera_cartera(ctx)),
                        perfil=perfil_v,
                        capital_ars=float(cap_in),
                        filas=len(list(getattr(rr, "compras_recomendadas", None) or [])),
                        payload={
                            "alerta_mercado": bool(getattr(rr, "alerta_mercado", False)),
                            "capital_remanente_ars": float(getattr(rr, "capital_remanente_ars", 0) or 0),
                        },
                    )
                except Exception:
                    pass
                # Pilar 3: plan explicado con motivos + trazabilidad al audit trail
                try:
                    from services.recomendador_explicable import (
                        auditar_plan,
                        construir_plan_accion,
                    )

                    plan = construir_plan_accion(
                        perfil=perfil_v,
                        rr=rr,
                        senales=senales,
                        capital_ars=float(cap_in),
                        precio_records=ctx.get("precio_records"),
                    )
                    st.session_state["inv_plan_explicado"] = plan
                    auditar_plan(
                        plan,
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
                    st.session_state.pop("inv_plan_explicado", None)
                st.rerun()
            except Exception as e:
                st.error(f"Error al calcular: {e}")

    res = st.session_state.get("inv_plata_resultado") or {}
    cap_ui = float(st.session_state.get("inversor_capital_ars", 0) or 0)
    if not res or abs(float(res.get("capital", -1)) - cap_ui) >= 1.0:
        return

    rr = res.get("rr")
    perfil_res = str(res.get("perfil") or perfil_v)
    if rr is None:
        return

    if getattr(rr, "alerta_mercado", False):
        st.warning(f"⚠️ {rr.mensaje_alerta}")

    if getattr(rr, "resumen_recomendacion", ""):
        st.caption(str(rr.resumen_recomendacion))

    # Pilar 3: cada sugerencia con su porqué, confianza de datos y link a ficha
    _plan_exp = st.session_state.get("inv_plan_explicado")
    if _plan_exp is not None and _flag_plan_explicado(ctx):
        with st.expander("🧭 Por qué estas sugerencias — plan explicado", expanded=False):
            from ui.components.plan_accion_view import render_plan_accion

            render_plan_accion(_plan_exp, key_prefix="inv_plan")

    items = list(getattr(rr, "compras_recomendadas", None) or [])
    if not items:
        st.info(
            "No se encontraron compras posibles con este capital y tu cartera actual. "
            "Probá con otro monto o consultá a tu asesor."
        )
        pend0 = getattr(rr, "pendientes_proxima_inyeccion", []) or []
        if pend0:
            st.markdown("**Para la próxima vez**")
            for p in pend0[:6]:
                tk_raw = str(p.get("ticker", "") or "")
                tk_lbl = (
                    "Renta fija AR (soberanos / cupo no cubierto por ON del modelo)"
                    if tk_raw == "_RENTA_AR"
                    else tk_raw
                )
                st.caption(
                    f"**{html.escape(tk_lbl)}:** {html.escape(str(p.get('motivo', '') or ''))}"
                )
        return

    st.markdown(
        """
    <p style="font-size:0.72rem;font-weight:700;color:var(--c-green);
              text-transform:uppercase;letter-spacing:0.08em;
              margin:1.25rem 0 0.35rem 0;">Paso 3 — Sugerencias (editables)</p>
    <p style="font-size:0.8125rem;color:var(--c-text-2);margin:0 0 0.75rem 0;">
        Ajustá cantidades, precio por cuotaparte (ARS) o el instrumento. Podés agregar o quitar filas.
        Confirmá para registrar <strong>COMPRAS</strong> en tu libro (se suman a lo que ya tenés).
    </p>
    """,
        unsafe_allow_html=True,
    )

    monto_total = sum(float(getattr(it, "monto_ars", 0) or 0) for it in items)
    remanente = float(getattr(rr, "capital_remanente_ars", 0) or 0)
    _udf_pln = ctx.get("universo_df")
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
                "TIPO": _tipo_universo_ticker(_tk, _udf_pln),
                "Notas": str(getattr(it, "justificacion", "") or "")[:120],
            }
        )
    df_ed_base = pd.DataFrame(_rows_ed)
    edited = st.data_editor(
        df_ed_base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="pln_data_editor_cartera",
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
    except Exception:
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
            with st.expander("Ver distribución objetivo del perfil", expanded=False):
                st.plotly_chart(fig_t, use_container_width=True)

    _cart_guardar = _cartera_resuelta_primera_cartera(ctx)
    st.caption(f"Al confirmar, las compras se agregan a: **`{_cart_guardar}`**")

    st.info(
        "💡 Es una sugerencia según tu perfil, tu cartera actual y el mercado. "
        "La confirmación registra **COMPRAS** en tu libro, sumadas a posiciones existentes."
    )
    _confirm_exec_real = st.checkbox(
        "Confirmo que ya ejecuté estas operaciones en mi broker",
        key="pln_confirm_exec_real",
    )

    col_ok, col_act, col_reset = st.columns(3)
    with col_ok:
        if st.button(
            "✅ Confirmar compras sugeridas",
            type="primary",
            use_container_width=True,
            key="pln_confirmar_cartera",
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
                            origen="capital_incremental",
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
                        session_keys_clear=["inv_plata_resultado", "inv_recomendacion"],
                    )

    with col_act:
        if st.button("✏️ Cargar lo que compré", use_container_width=True, key="pln_ir_a_carga"):
            st.session_state["inv_carga_open"] = True
            st.session_state["inv_carga_tab"] = "manual"
            st.session_state.pop("inv_plata_resultado", None)
            st.session_state.pop("inv_recomendacion", None)
            st.rerun()
    with col_reset:
        if st.button("🔄 Recalcular con otro monto", use_container_width=True, key="pln_reset"):
            st.session_state.pop("inv_plata_resultado", None)
            st.session_state.pop("inv_recomendacion", None)
            st.rerun()

    pend = getattr(rr, "pendientes_proxima_inyeccion", []) or []
    if pend:
        st.markdown("**Para la próxima vez**")
        for p in pend[:6]:
            tk_raw = str(p.get("ticker", "") or "")
            if tk_raw == "_RENTA_AR":
                tk_lbl = "Renta fija AR (soberanos / cupo no cubierto por ON del modelo)"
            else:
                tk_lbl = tk_raw
            st.caption(
                f"**{html.escape(tk_lbl)}:** {html.escape(str(p.get('motivo', '') or ''))}"
            )

