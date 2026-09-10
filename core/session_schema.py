"""
core/session_schema.py — A1: Esquema centralizado del session_state de MQ26.

Sprint 5 — A1:
  Single source of truth para todas las claves de st.session_state usadas
  en la aplicación. Reemplaza las strings literales dispersas en ~40 archivos.

  Secciones:
    SessionKeys  — clase con constantes tipadas (evita typos)
    SESSION_DEFAULTS — valores por defecto para cada clave
    SessionGuard — context manager que valida integridad del state
    Helpers:
      init_session_defaults()    — inicializa claves faltantes (idempotente)
      get_ss(key, default)       — lectura segura con fallback
      set_ss(key, value)         — escritura con validación de tipo (opcional)
      reset_client_keys()        — limpia claves del cliente activo
      reset_cartera_keys()       — limpia claves de cartera
      snapshot_session()         — dict serializable del estado actual (debug)
      assert_session_valid()     — verifica invariantes (test helper)

  Diseño:
    - Importable sin Streamlit (los helpers hacen import lazy).
    - 100% basado en constantes string → sin riesgo de typos.
    - Sin lógica de negocio: solo nomenclatura y valores por defecto.
"""
from __future__ import annotations

from typing import Any

# ─── A: Constantes de claves ───────────────────────────────────────────────────

class K:
    """
    Namespace de constantes para las claves de session_state.
    Uso: st.session_state[K.CLIENTE_ID] en lugar de st.session_state["cliente_id"].
    """
    # ── Autenticación ─────────────────────────────────────────────────────────
    AUTH              = "mq26_auth"
    AUTH_STATUS       = "authentication_status"
    USER_ROLE         = "mq26_user_role"
    LOGIN_USER        = "mq26_login_user"
    DB_USER_ID        = "mq26_db_user_id"
    # Default solo para app_id="mq26". Callers reales: allowed_clientes_key(app_id).
    ALLOWED_CLIENTES  = "mq26_allowed_cliente_ids"

    @staticmethod
    def allowed_clientes_key(app_id: str | None = None) -> str:
        """Clave de sesión del allowlist, alineada con core.auth (`{app_id}_allowed_cliente_ids`)."""
        aid = str(app_id or "").strip() or "mq26"
        return f"{aid}_allowed_cliente_ids"

    # ── Cliente activo ────────────────────────────────────────────────────────
    CLIENTE_ID        = "cliente_id"
    CLIENTE_NOMBRE    = "cliente_nombre"
    CLIENTE_PERFIL    = "cliente_perfil"
    CLIENTE_HORIZONTE = "cliente_horizonte_label"
    PREV_CLIENTE_ID   = "_prev_cliente_id_run"

    # ── Cartera / Portfolio ───────────────────────────────────────────────────
    CARTERA_ACTIVA    = "mq_cartera_activa_sidebar"
    CARTERA_SYNC_KEY  = "_mq_cartera_selector_sync_"   # prefix (rol + nombre)
    MODO_FIFO         = "modo_ppc_fifo"

    # ── Caché de datos ────────────────────────────────────────────────────────
    DF_AG_CACHE_PFX   = "_df_ag_cache_"
    DF_AG_HASH_PFX    = "_df_ag_hash_"
    DF_AG_FIFO_PFX    = "_df_ag_fifo_"
    CACHED_DF_AG      = "_cached_df_ag"
    CACHED_METRICAS   = "_cached_metricas"
    CACHED_DF_ANALISIS= "_cached_df_analisis"
    CACHED_CARTERA    = "_cached_cartera_activa"

    # ── Simulación y capital ─────────────────────────────────────────────────
    MC_N_ESCENARIOS   = "mc_n_escenarios_select"
    CAPITAL_INYECTADO = "capital_inyectado_mq26"
    CAPITAL_DISPONIBLE= "capital_disponible_mq"

    # ── UI / Tema ─────────────────────────────────────────────────────────────
    LIGHT_MODE        = "mq_light_mode"

    # ── Sidebar / utilidades ──────────────────────────────────────────────────
    LOGOUT_CONFIRM    = "_sb_logout_confirm"
    SYNC_TIMESTAMPS   = "_sync_timestamps"
    HEALTH_STARTED    = "_mq26_health_started"

    # ── Dashboard / alertas ───────────────────────────────────────────────────
    N_ROJOS           = "dashboard_n_rojos"
    N_AMARILLOS       = "dashboard_n_amarillos"
    RECESION_RIESGO   = "recesion_riesgo"

    # ── Tab loading (por tab_id) ──────────────────────────────────────────────
    TAB_LOADED_PFX    = "_mq_tab_loaded_"

    # ── Deeplinks ────────────────────────────────────────────────────────────
    DEEPLINK_OK_PFX   = "mq26_deeplink_ok_"

    # ── Navegación principal (segmented_control / deeplink) ───────────────────
    MAIN_TAB_WIDGET_KEY = "mq26_seg_tabs"

    # ── Prefijos a limpiar cuando cambia el cliente ───────────────────────────
    CLIENT_CLEANUP_PREFIXES: tuple[str, ...] = (
        "cartera_filtro_",
        "opt_preset_",
        "_rpt_preview_",
        "_opt_borrador_",
        "_last_acc_",
        "_mq_tab_loaded_",        # fuerza re-load de tabs
        "_mq_cartera_selector_",  # sync key cartera
        "_mq_torre_",             # torre control cache
    )

    # ── Prefijos a limpiar cuando cambia la cartera ──────────────────────────
    CARTERA_CLEANUP_PREFIXES: tuple[str, ...] = (
        "_df_ag_cache_",
        "_df_ag_hash_",
        "_df_ag_fifo_",
    )


# ─── B: Valores por defecto ────────────────────────────────────────────────────

SESSION_DEFAULTS: dict[str, Any] = {
    # Autenticación
    K.AUTH:               False,
    K.AUTH_STATUS:        None,
    K.USER_ROLE:          None,
    K.LOGIN_USER:         "",
    K.DB_USER_ID:         None,
    K.ALLOWED_CLIENTES:   None,

    # Cliente
    K.CLIENTE_ID:         None,
    K.CLIENTE_NOMBRE:     "",
    K.CLIENTE_PERFIL:     "Moderado",
    K.CLIENTE_HORIZONTE:  "1 año",
    K.PREV_CLIENTE_ID:    None,

    # Cartera
    K.CARTERA_ACTIVA:     "",
    K.MODO_FIFO:          False,

    # Simulación
    K.MC_N_ESCENARIOS:    3000,
    K.CAPITAL_INYECTADO:  0.0,
    K.CAPITAL_DISPONIBLE: 500_000.0,

    # UI
    K.LIGHT_MODE:         False,

    # Sidebar
    K.LOGOUT_CONFIRM:     False,
    K.SYNC_TIMESTAMPS:    [],

    # Dashboard
    K.N_ROJOS:            0,
    K.N_AMARILLOS:        0,
    K.RECESION_RIESGO:    False,

    # Health
    K.HEALTH_STARTED:     False,
}


# ─── C: Helpers de lectura/escritura ──────────────────────────────────────────

def get_ss(key: str, default: Any = None) -> Any:
    """Lectura segura de session_state con fallback."""
    try:
        import streamlit as st
        return st.session_state.get(key, default)
    except Exception:
        return default


def set_ss(key: str, value: Any) -> None:
    """Escritura directa a session_state."""
    try:
        import streamlit as st
        st.session_state[key] = value
    except Exception:
        pass


def init_session_defaults(force: bool = False) -> None:
    """
    Inicializa claves faltantes con sus valores por defecto.
    Idempotente: no sobreescribe claves ya existentes (salvo force=True).

    Args:
        force: si True, resetea TODAS las claves a sus defaults.
    """
    try:
        import streamlit as st
        for key, default in SESSION_DEFAULTS.items():
            if force or key not in st.session_state:
                st.session_state[key] = (
                    default() if callable(default) else
                    list(default) if isinstance(default, list) else
                    default
                )
    except Exception:
        pass


def reset_client_keys(cliente_id: int | None = None) -> int:
    """
    Limpia todas las claves de session_state asociadas al cliente activo.
    Incluye prefijos de caché, tab-load, cartera sync, etc.

    Args:
        cliente_id: si se provee, solo limpia si el cliente cambió.

    Returns:
        Número de claves eliminadas.
    """
    try:
        import streamlit as st
        prev = st.session_state.get(K.PREV_CLIENTE_ID)
        if cliente_id is not None and prev == cliente_id:
            return 0  # mismo cliente — no limpiar

        keys_to_del = [
            k for k in list(st.session_state.keys())
            if any(k.startswith(pfx) for pfx in K.CLIENT_CLEANUP_PREFIXES)
        ]
        for k in keys_to_del:
            del st.session_state[k]
        st.session_state[K.PREV_CLIENTE_ID] = cliente_id
        return len(keys_to_del)
    except Exception:
        return 0


def cleanup_session_on_cliente_change(new_cliente_id: Any) -> int:
    """
    Si el cliente activo cambió respecto de ``K.PREV_CLIENTE_ID``, elimina claves
    bajo ``K.CLIENT_CLEANUP_PREFIXES`` y actualiza el marcador previo.

    Idempotente en reruns con el mismo ``new_cliente_id``.
    Usar desde ``run_mq26`` (no confundir con ``reset_client_keys()`` del botón Cambiar).
    """
    try:
        import streamlit as st

        prev = st.session_state.get(K.PREV_CLIENTE_ID)
        if prev == new_cliente_id:
            return 0
        keys_to_del = [
            k
            for k in list(st.session_state.keys())
            if any(str(k).startswith(pfx) for pfx in K.CLIENT_CLEANUP_PREFIXES)
        ]
        for _sk in keys_to_del:
            st.session_state.pop(_sk, None)
        st.session_state[K.PREV_CLIENTE_ID] = new_cliente_id
        return len(keys_to_del)
    except Exception:
        return 0


def reset_cartera_keys(cartera_nombre: str | None = None) -> int:
    """
    Limpia caché de DataFrame de cartera cuando la cartera cambia.

    Returns:
        Número de claves eliminadas.
    """
    try:
        import streamlit as st
        keys_to_del = [
            k for k in list(st.session_state.keys())
            if any(k.startswith(pfx) for pfx in K.CARTERA_CLEANUP_PREFIXES)
        ]
        for k in keys_to_del:
            del st.session_state[k]
        return len(keys_to_del)
    except Exception:
        return 0


def snapshot_session() -> dict[str, Any]:
    """
    Retorna un dict serializable del estado de session_state actual.
    Útil para logging, debugging y tests de regresión.
    """
    try:
        import streamlit as st
        snapshot: dict[str, Any] = {}
        for k, v in st.session_state.items():
            try:
                import json
                json.dumps(v)  # test serializability
                snapshot[k] = v
            except (TypeError, ValueError):
                snapshot[k] = f"<{type(v).__name__}>"
        return snapshot
    except Exception:
        return {}


def assert_session_valid() -> list[str]:
    """
    Verifica invariantes del session_state.
    Retorna lista de errores (vacía si todo OK). Usar en tests.
    """
    errors: list[str] = []
    try:
        import streamlit as st

        # Cliente: si hay id debe haber nombre
        cid   = st.session_state.get(K.CLIENTE_ID)
        cnomb = st.session_state.get(K.CLIENTE_NOMBRE, "")
        if cid is not None and not cnomb:
            errors.append(f"cliente_id={cid} pero cliente_nombre está vacío")

        # Rol válido
        role = st.session_state.get(K.USER_ROLE)
        valid_roles = {"inversor", "estudio", "admin", "super_admin", "viewer", None}
        if role not in valid_roles:
            errors.append(f"user_role={role!r} no reconocido")

        # Capital no negativo
        cap = st.session_state.get(K.CAPITAL_DISPONIBLE, 0)
        if isinstance(cap, (int, float)) and cap < 0:
            errors.append(f"capital_disponible={cap} es negativo")

    except Exception as e:
        errors.append(f"assert_session_valid excepción: {e}")

    return errors


# ─── D: Context manager de validación ─────────────────────────────────────────

class SessionGuard:
    """
    Context manager que inicializa defaults al entrar y valida al salir.

    Uso:
        with SessionGuard():
            st.session_state[K.CLIENTE_ID] = 42
            ...  # lógica del run
    """

    def __enter__(self) -> SessionGuard:
        init_session_defaults()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            errors = assert_session_valid()
            if errors:
                import logging
                logging.getLogger(__name__).warning(
                    "SessionGuard: invariantes violadas: %s", errors
                )
        return False  # no suprime excepciones
