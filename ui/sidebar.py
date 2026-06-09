"""
ui/sidebar.py — Sidebar de MQ26: estado centralizado y renderizado.

Responsabilidades:
  · Mostrar info de rol, cliente, CCL, BD.
  · State machine para el selector de cartera activa (B10).
  · Botones de cierre de sesión y cambio de cliente.
  · Expanders de admin (sync, fallback, motor, salud, Telegram).
  · Devolver SidebarState al script principal.

El script principal (run_mq26.py) solo llama a render_sidebar() y
consume SidebarState — sin lógica de sidebar dispersa en el script.
"""
from __future__ import annotations

import html as _html
import os
from dataclasses import dataclass
from datetime import datetime as _dt
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core.logging_config import get_logger
from core.structured_logging import log_degradacion

logger = get_logger(__name__)


# ─── Contrato de salida del sidebar ──────────────────────────────────────────


@dataclass(frozen=True)
class SidebarState:
    """
    Valores producidos por render_sidebar() que el script principal necesita.

    Todos los campos son inmutables (frozen=True) — sirven de contrato entre
    el sidebar y el cuerpo de la app.
    """

    cartera_activa: str       # Libro seleccionado (o "" si no hay datos)
    ccl: float                # Tipo de cambio CCL vigente
    n_escenarios: int         # Nro de simulaciones Monte Carlo
    capital_disponible: float # Capital ARS para Motor de Salida


# ─── State machine del selector de cartera (B10) ─────────────────────────────


def _resolver_cartera_activa(
    *,
    role: str,
    cliente_nombre: str,
    carteras_opciones: list[str],
    tenant_id: str,
) -> str:
    """
    State machine limpia para el selector de cartera activa.

    Transiciones:
    ┌──────────────────────────────────────────────────────┐
    │ ENTRADA                        ACCIÓN                │
    ├──────────────────────────────────────────────────────┤
    │ carteras_opciones vacío        → devuelve ""         │
    │ role == "inversor"             → primera cartera,    │
    │                                  sin selectbox       │
    │ contexto cambió (sync token)   → reset a default     │
    │ valor actual fuera de lista    → corrige a default   │
    │ estado válido                  → renderiza selectbox │
    └──────────────────────────────────────────────────────┘

    Parámetros:
        role              — Rol del usuario activo.
        cliente_nombre    — Nombre del cliente (puede contener "|").
        carteras_opciones — Lista de strings de carteras disponibles.
        tenant_id         — ID del tenant para el sync token.

    Efectos secundarios en session_state:
        "mq_cartera_activa_sidebar"  — valor seleccionado actualmente.
        "_mq_cartera_sync_key"       — token de detección de cambio de contexto.
    """
    KEY_VAL  = "mq_cartera_activa_sidebar"
    KEY_SYNC = "_mq_cartera_sync_key"

    if not carteras_opciones:
        return ""

    # Calcular índice default: preferir cartera del cliente activo con datos
    default_idx = 0
    if role != "inversor":
        cnorm = (cliente_nombre or "").strip()
        if cnorm:
            hit_datos: int | None = None
            hit_sin:   int | None = None
            for i, opt in enumerate(carteras_opciones):
                if opt == "-- Todas las carteras --" or "|" not in opt:
                    continue
                if opt.split("|")[0].strip() != cnorm:
                    continue
                if opt.endswith("| (sin datos)"):
                    hit_sin = i
                else:
                    hit_datos = i
                    break
            if hit_datos is not None:
                default_idx = hit_datos
            elif hit_sin is not None:
                default_idx = hit_sin

    default_idx = min(default_idx, len(carteras_opciones) - 1)

    # Inversor: siempre la primera cartera disponible, sin selectbox visible
    if role == "inversor":
        return carteras_opciones[0]

    # Demás roles: selectbox persistido, con detección de cambio de contexto
    sync_token = (tenant_id, (cliente_nombre or "").strip(), tuple(carteras_opciones))

    if st.session_state.get(KEY_SYNC) != sync_token:
        # Contexto cambió (otro cliente, otro tenant, carteras distintas) → resetear
        st.session_state[KEY_SYNC] = sync_token
        st.session_state[KEY_VAL]  = carteras_opciones[default_idx]
    elif st.session_state.get(KEY_VAL) not in carteras_opciones:
        # Valor stale (la cartera fue eliminada, etc.) → corregir silenciosamente
        st.session_state[KEY_VAL] = carteras_opciones[default_idx]

    cartera = st.sidebar.selectbox(
        "📁 Cartera activa:",
        carteras_opciones,
        key=KEY_VAL,
    )
    st.sidebar.caption(
        "Elegí el **libro** del cliente. "
        "«— Todas—» solo sirve para vistas agregadas; "
        "en **Posición actual** necesitás una cartera concreta."
    )
    return cartera


# ─── Render principal ─────────────────────────────────────────────────────────


def render_sidebar(
    *,
    role: str,
    tenant_id: str,
    cliente_id: int | None,
    cliente_nombre: str,
    cliente_perfil: str,
    horiz_label: str,
    df_clientes: pd.DataFrame,
    trans: pd.DataFrame,
    ccl: float,
    can_sensitive: bool,
    # servicios inyectados para evitar imports circulares
    dbm: Any,
    cs: Any,
    ab: Any,
    base_dir: Path,
) -> SidebarState:
    """
    Renderiza el sidebar completo y devuelve SidebarState.

    Parámetros:
        role           — Rol del usuario activo ("inversor", "estudio", …).
        tenant_id      — ID del tenant activo.
        cliente_id     — ID del cliente seleccionado (None si no hay).
        cliente_nombre — Nombre completo del cliente (puede contener "|").
        cliente_perfil — "Conservador" / "Moderado" / "Agresivo".
        horiz_label    — "1 año" / "2 años" / etc.
        df_clientes    — DataFrame de clientes en alcance del rol.
        trans          — DataFrame del transaccional ya filtrado por rol.
        ccl            — Tipo de cambio CCL (ya calculado antes de llamar aquí).
        can_sensitive  — True si el rol puede usar herramientas de admin.
        dbm            — Módulo core.db_manager (ya importado en el script).
        cs             — Módulo services.cartera_service.
        ab             — Módulo alertas_broker.
        base_dir       — Path base del proyecto.
    """

    # ── Header + toggle modo claro ──────────────────────────────────────────
    st.sidebar.markdown("## 📈 MQ26 — Inversiones")
    st.sidebar.toggle("☀️ Modo claro", key="mq_light_mode")

    # ── Info de sesión / rol ────────────────────────────────────────────────
    login_u = st.session_state.get("mq26_login_user", "")
    if login_u and str(role).lower() != "inversor":
        st.sidebar.caption(f"Sesión: **{login_u}** · rol {role}")
    if role in ("estudio", "inversor"):
        st.sidebar.info(
            "👁️ **Solo lectura**: sincronización, credenciales y escrituras a BD están deshabilitadas."
        )

    # ── Badge circuit breaker yfinance ──────────────────────────────────────
    try:
        from services.precio_cache_service import estado_circuit_breaker as _cb_estado

        _cb = _cb_estado()
        if _cb["degradado"]:
            st.sidebar.error(
                f"🔴 **Precios offline** — yfinance bloqueado por {_cb['segundos_restantes']}s. "
                "Usando precios fallback."
            )
    except Exception as _e_cb:
        log_degradacion("sidebar", "circuit_breaker_sidebar_estado_fallo", _e_cb)

    # ── Cerrar sesión ────────────────────────────────────────────────────────
    if st.sidebar.button("🔒 Cerrar sesión", key="btn_cerrar_sesion_mq", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()

    # ── BD + CCL ─────────────────────────────────────────────────────────────
    info_bd = dbm.info_backend()
    backend_label = "🟢 PostgreSQL" if info_bd["backend"] == "postgresql" else "🟡 SQLite Local"
    st.sidebar.caption(f"BD: {backend_label}")
    st.sidebar.markdown(
        f"""
<div style="padding:0.5rem 0;">
  <div style="font-size:0.65rem;color:var(--c-text-3,#94a3b8);text-transform:uppercase;
              letter-spacing:0.06em;">Dólar hoy (CCL)</div>
  <div style="font-family:'DM Mono',monospace;font-size:1.2rem;font-weight:600;
              color:var(--c-text,#f1f5f9);">${ccl:,.0f}</div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Cliente activo ───────────────────────────────────────────────────────
    nombre_corto = cliente_nombre.split("|")[0].strip() if cliente_nombre else ""
    if role == "estudio":
        n_rojos = int(st.session_state.get("dashboard_n_rojos", 0) or 0)
        if n_rojos > 0:
            st.sidebar.error(f"🔴 {n_rojos} cliente(s) necesitan atención")
        st.sidebar.divider()

    st.sidebar.markdown(
        f"""
<div style="padding:0.25rem 0 0.5rem 0;">
  <div style="font-size:0.875rem;font-weight:600;color:var(--c-text,#f1f5f9);">
    👤 {_html.escape(nombre_corto or "—")}
  </div>
  <div style="font-size:0.72rem;color:var(--c-text-3,#94a3b8);margin-top:2px;">
    {_html.escape(str(cliente_perfil))} · {_html.escape(str(horiz_label))}
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # Mostrar "Cambiar cliente" excepto cuando el inversor tiene un solo cliente
    if role != "inversor" or len(df_clientes) > 1:
        if st.sidebar.button(
            "🔄 Cambiar cliente", key="btn_cambiar_cliente", use_container_width=True
        ):
            for k in [
                "cliente_id",
                "cliente_nombre",
                "cliente_perfil",
                "cliente_horizonte_label",
            ]:
                st.session_state.pop(k, None)
            st.session_state.pop("mq_cartera_activa_sidebar", None)
            st.session_state.pop("_mq_cartera_sync_key", None)
            st.rerun()

    st.sidebar.divider()

    # ── Construir lista de carteras ──────────────────────────────────────────
    carteras_csv: list[str] = []
    if not trans.empty and "CARTERA" in trans.columns:
        carteras_csv = sorted(trans["CARTERA"].dropna().unique().tolist())

    if role == "inversor":
        if carteras_csv:
            carteras_opciones: list[str] = [carteras_csv[0]]
        elif cliente_nombre.strip():
            carteras_opciones = [f"{cliente_nombre.strip()} | (sin datos)"]
        else:
            carteras_opciones = []
    else:
        carteras_opciones = ["-- Todas las carteras --"] + list(carteras_csv)
        if not df_clientes.empty:
            propietarios_csv = {c.split("|")[0].strip() for c in carteras_csv}
            for _nom in sorted(df_clientes["Nombre"].dropna().tolist()):
                if _nom.strip() not in propietarios_csv:
                    carteras_opciones.append(f"{_nom.strip()} | (sin datos)")

    # ── State machine selector de cartera ───────────────────────────────────
    cartera_activa = _resolver_cartera_activa(
        role=role,
        cliente_nombre=cliente_nombre,
        carteras_opciones=carteras_opciones,
        tenant_id=tenant_id,
    )

    # ── Simulaciones Monte Carlo ─────────────────────────────────────────────
    _mc_niveles = [1000, 3000, 5000, 10000]
    st.session_state.setdefault("mc_n_escenarios_select", 3000)
    if role != "inversor":
        _mc_cur = st.session_state.get("mc_n_escenarios_select", 3000)
        if _mc_cur not in _mc_niveles:
            _mc_cur = 3000
        n_escenarios: int = int(
            st.sidebar.selectbox(
                "Simulaciones MC:",
                _mc_niveles,
                index=_mc_niveles.index(_mc_cur),
                key="mc_n_escenarios_select",
            )
        )
    else:
        n_escenarios = int(st.session_state.get("mc_n_escenarios_select", 3000) or 3000)

    st.sidebar.divider()

    # ── Log context ──────────────────────────────────────────────────────────
    try:
        from core.logging_config import set_log_context

        _cshort = ""
        if cartera_activa:
            _cshort = (
                cartera_activa.split("|")[-1].strip()[:20]
                if "|" in cartera_activa
                else cartera_activa[:20]
            )
        set_log_context(
            tenant=tenant_id,
            cartera=_cshort,
            env=os.environ.get("RAILWAY_ENVIRONMENT", "dev"),
        )
    except Exception as _e_logctx:
        log_degradacion("sidebar", "set_log_context_fallo", _e_logctx)

    # ── Label de cartera para inversor ──────────────────────────────────────
    if role == "inversor":
        st.session_state["modo_ppc_fifo"] = False
        if cartera_activa:
            st.sidebar.caption(
                f"📁 **Tu cartera:** "
                f"{_html.escape(cartera_activa.split('|')[-1].strip() or '—')} "
                "(un solo libro por usuario inversor)"
            )

    # ── Expanders de admin (solo roles no-inversor) ──────────────────────────
    capital_disponible = float(
        st.session_state.get(
            "capital_disponible_mq",
            float(dbm.obtener_config("capital_disponible_mq", "500000") or 500000),
        )
    )

    if role != "inversor":
        st.session_state.setdefault("modo_ppc_fifo", False)

        _ruta_transac_sb = base_dir / "0_Data_Maestra" / "Maestra_Transaccional.csv"

        # Sincronización de datos
        with st.sidebar.expander("🔄 Sincronización de datos"):
            if not can_sensitive:
                st.info(
                    "Utilidad sensible: solo administradores pueden regenerar datos."
                )
            if _ruta_transac_sb.exists():
                _mtime = _dt.fromtimestamp(
                    _ruta_transac_sb.stat().st_mtime
                ).strftime("%d/%m %H:%M")
                st.caption(f"CSV: {_mtime}")

            import time as _time_rl

            _sync_times = st.session_state.get("_sync_timestamps", [])
            _ahora_rl = _time_rl.monotonic()
            _sync_times = [t for t in _sync_times if _ahora_rl - t < 60]
            _bloqueado = len(_sync_times) >= 3
            _espera_rl = (
                max(0, int(60 - (_ahora_rl - _sync_times[0]))) if _bloqueado else 0
            )

            if _bloqueado:
                st.warning(
                    f"⏳ Rate limit — esperá {_espera_rl}s antes de sincronizar de nuevo."
                )
            else:
                if st.button(
                    "🔄 Regenerar desde Excel",
                    key="btn_regen_csv",
                    disabled=_bloqueado or not can_sensitive,
                ):
                    _sync_times.append(_ahora_rl)
                    st.session_state["_sync_timestamps"] = _sync_times
                    if _ruta_transac_sb.exists():
                        _ruta_transac_sb.unlink()
                    st.cache_data.clear()
                    st.rerun()
            st.session_state["_sync_timestamps"] = _sync_times

        # Precios fallback
        with st.sidebar.expander("💰 Precios fallback"):
            if not can_sensitive:
                st.info(
                    "Utilidad sensible: solo administradores pueden editar precios fallback."
                )
            _fb = cs.PRECIOS_FALLBACK_ARS.copy()
            _df_fb = pd.DataFrame(
                [{"Ticker": t, "Precio ARS": p} for t, p in sorted(_fb.items())]
            )
            _df_fb_edit = st.data_editor(
                _df_fb.reset_index(drop=True),
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
                    "Precio ARS": st.column_config.NumberColumn(
                        "Precio ARS", min_value=0, format="$%d"
                    ),
                },
                key="editor_fallback_sb",
                hide_index=True,
                disabled=not can_sensitive,
            )
            if st.button(
                "💾 Aplicar precios", key="btn_aplicar_fb", disabled=not can_sensitive
            ):
                _nuevos = {
                    t: float(p)
                    for t, p in zip(
                        _df_fb_edit["Ticker"], _df_fb_edit["Precio ARS"]
                    )
                    if t and p and float(p) > 0
                }
                # MQ2-S3: validar diff > 50% antes de aplicar
                _sospechosos = []
                for _t_fb, _p_fb in _nuevos.items():
                    _p_ant = _fb.get(_t_fb, _p_fb)
                    if _p_ant > 0 and abs(_p_fb / _p_ant - 1) > 0.50:
                        _sospechosos.append(
                            f"{_t_fb}: {_p_ant:,.0f} → {_p_fb:,.0f} "
                            f"({(_p_fb / _p_ant - 1):+.0%})"
                        )
                if _sospechosos:
                    st.warning(
                        "⚠️ **Cambio > 50% detectado** en:\n"
                        + "\n".join(_sospechosos)
                        + "\n\nPresioná nuevamente para confirmar."
                    )
                    if not st.session_state.get("_fb_confirm"):
                        st.session_state["_fb_confirm"] = True
                        st.stop()
                st.session_state.pop("_fb_confirm", None)
                # MQ2-S4: auditoría de cambios
                for _t_fb, _p_fb in _nuevos.items():
                    _p_ant = _fb.get(_t_fb, _p_fb)
                    if _p_ant != _p_fb:
                        try:
                            dbm.registrar_alerta(
                                tipo_alerta="PRECIO_MANUAL",
                                mensaje=f"Fallback {_t_fb}: {_p_ant:,.0f} → {_p_fb:,.0f}",
                                ticker=_t_fb,
                            )
                        except Exception as _e_alerta:
                            log_degradacion(
                                "sidebar",
                                "registrar_alerta_precio_manual_fallo",
                                _e_alerta,
                                ticker=str(_t_fb)[:32],
                            )
                cs.actualizar_fallback(_nuevos)
                try:
                    dbm.registrar_admin_audit_event(
                        "precios_fallback.rf_rv_manual",
                        actor=str(
                            st.session_state.get("mq26_login_user") or ""
                        )[:200],
                        tenant_id=str(
                            st.session_state.get("tenant_id") or "default"
                        ),
                        detail={
                            "n_tickers": len(_nuevos),
                            "tickers_muestra": sorted(
                                [str(x) for x in _nuevos.keys()]
                            )[:40],
                            "nota": (
                                "Precios manuales RF/RV (tabla fallback sidebar); "
                                "afectan valoración y motor."
                            ),
                        },
                    )
                except Exception:
                    pass
                st.cache_data.clear()
                st.rerun()

            st.divider()
            st.caption("🔒 Integridad de backups")
            _bak_files = (
                sorted(
                    (base_dir / "0_Data_Maestra").glob("*.bak_*.xlsx")
                )
                if (base_dir / "0_Data_Maestra").exists()
                else []
            )
            st.caption(
                f"{len(_bak_files)} backups disponibles"
                if _bak_files
                else "Sin backups locales"
            )

        # Motor de Salida — configuración de capital
        with st.sidebar.expander("🚀 Motor de Salida — Config"):
            if not can_sensitive:
                st.info(
                    "Utilidad sensible: solo administradores pueden editar capital global."
                )
            _cap_default = float(
                dbm.obtener_config("capital_disponible_mq", "500000") or 500000
            )
            _capital_disp = st.number_input(
                "Capital disponible (ARS):",
                min_value=0.0,
                value=_cap_default,
                step=10_000.0,
                format="%.0f",
                key="capital_disponible_input",
                help="Capital para calcular órdenes de compra",
                disabled=not can_sensitive,
            )
            if st.button(
                "💾 Guardar capital",
                key="btn_guardar_cap",
                disabled=not can_sensitive,
            ):
                dbm.guardar_config("capital_disponible_mq", str(_capital_disp))
                st.success("✅ Capital guardado")
            st.session_state["capital_disponible_mq"] = _capital_disp
            capital_disponible = float(_capital_disp)

        # Salud del sistema
        with st.sidebar.expander("⚙️ Salud del sistema"):
            st.markdown(f"**Última sync:** {_dt.now().strftime('%H:%M:%S')}")
            st.markdown(f"**BD:** {dbm.info_backend()['backend'].upper()}")
            st.markdown(f"**CCL:** ${ccl:,.0f}")
            st.checkbox(
                "Usar FIFO para PPC (detalle contable)",
                key="modo_ppc_fifo",
                help="Afecta cómo se calcula el precio promedio de compra con múltiples operaciones.",
            )

        # Telegram
        with st.sidebar.expander("📱 Alertas Telegram"):
            if not can_sensitive:
                st.info(
                    "Utilidad sensible: solo administradores pueden configurar Telegram."
                )
            _tg_token_bd = dbm.obtener_config("telegram_token", "")
            _tg_chat_bd  = dbm.obtener_config("telegram_chat_id", "")
            tg_token = st.text_input(
                "Bot Token",
                type="password",
                value=_tg_token_bd or os.environ.get("TELEGRAM_TOKEN", ""),
                disabled=not can_sensitive,
            )
            tg_chat = st.text_input(
                "Chat ID",
                value=_tg_chat_bd or os.environ.get("TELEGRAM_CHAT_ID", ""),
                disabled=not can_sensitive,
            )
            if st.button(
                "💾 Guardar credenciales",
                key="btn_tg_guardar",
                disabled=not can_sensitive,
            ):
                if tg_token:
                    dbm.guardar_config("telegram_token", tg_token)
                if tg_chat:
                    dbm.guardar_config("telegram_chat_id", tg_chat)
                st.success("✅ Guardadas en BD")
            if st.button(
                "🔔 Probar conexión",
                key="btn_tg_probar",
                disabled=not can_sensitive,
            ):
                if tg_token and tg_chat:
                    os.environ["TELEGRAM_TOKEN"]   = tg_token
                    os.environ["TELEGRAM_CHAT_ID"] = tg_chat
                    ok = ab.test_conexion()
                    (st.success("✅ Telegram OK") if ok else st.error("❌ Sin respuesta"))

    else:
        # Inversor: leer capital_disponible de config sin mostrar UI de edición
        st.session_state.setdefault(
            "capital_disponible_mq",
            float(dbm.obtener_config("capital_disponible_mq", "500000") or 500000),
        )
        capital_disponible = float(
            st.session_state.get("capital_disponible_mq", 500000)
        )

    return SidebarState(
        cartera_activa=cartera_activa,
        ccl=ccl,
        n_escenarios=int(n_escenarios),
        capital_disponible=capital_disponible,
    )
