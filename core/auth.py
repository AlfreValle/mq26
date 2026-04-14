"""
core/auth.py — Autenticación centralizada (MQ-A2)
Elimina la duplicación entre mq26_main.py y dss_main.py.
Soporta rate limiting (MQ-S4) y log de accesos (DS-S3).
"""
from __future__ import annotations

import hashlib
import html as html_module
import hmac
import os
import secrets
import time

import streamlit as st

from core.logging_config import get_logger
from core.mq26_disclaimers import LOGIN_LEGAL_DISCLAIMER_ES

# Importación lazy para evitar circular (se usa solo al registrar acceso)
_dbm_imported: bool = False
_log = get_logger(__name__)


# ─── CONSTANTES ───────────────────────────────────────────────────────────────
_SESSION_TIMEOUT_DEFAULT = 3600    # 1 hora
_MAX_FAILED_ATTEMPTS     = 5
_LOCKOUT_SECONDS         = 300     # 5 minutos


def _hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def verificar_password(pwd_input: str, pwd_env: str) -> bool:
    """Comparación segura resistente a timing attacks."""
    if not pwd_env:
        return False
    return hmac.compare_digest(_hash_password(pwd_env), _hash_password(pwd_input))


def _registrar_acceso(app_id: str, exito: bool) -> None:
    """Registra el intento de login en alertas_log sin fallar si la BD no está lista."""
    try:
        import datetime

        import core.db_manager as _dbm
        _dbm.registrar_alerta_log(
            tipo_alerta="ACCESO",
            mensaje=f"Login {'exitoso' if exito else 'fallido'} en {app_id} — {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            enviada=False,
        )
    except Exception as exc:
        _log.warning("degradacion_auth_registro_acceso app=%s exito=%s err=%s", app_id, exito, exc, exc_info=True)


def _esta_bloqueado(auth_key: str) -> tuple[bool, int]:
    """Retorna (bloqueado, segundos_restantes)."""
    fails      = st.session_state.get(f"{auth_key}_fails", 0)
    lock_since = st.session_state.get(f"{auth_key}_lock_ts", 0)
    if fails >= _MAX_FAILED_ATTEMPTS and lock_since:
        elapsed   = time.time() - lock_since
        remaining = int(_LOCKOUT_SECONDS - elapsed)
        if remaining > 0:
            return True, remaining
        else:
            # Desbloquear
            st.session_state[f"{auth_key}_fails"]   = 0
            st.session_state[f"{auth_key}_lock_ts"] = 0
    return False, 0


def _login_user_table(
    *,
    password_env: str,
    viewer_password_env: str,
    investor_password_env: str,
    user_admin: str,
    user_estudio: str,
    user_inversor: str,
) -> dict[str, tuple[str, str]]:
    """username normalizado -> (clave_rol_sesión, contraseña_env). Primera definición gana si hay duplicados."""
    out: dict[str, tuple[str, str]] = {}
    rows: list[tuple[str, str, str]] = [
        (user_admin, "admin", password_env),
        (user_estudio, "viewer", viewer_password_env),
        (user_inversor, "inversor", investor_password_env),
    ]
    for u_raw, role_key, secret in rows:
        u = (u_raw or "").strip().lower()
        if not u or u in out:
            continue
        out[u] = (role_key, secret or "")
    return out


def check_password(
    app_id:   str = "mq26",
    app_name: str = "MQ26 Terminal",
    subtitle: str = "Sistema Cuantitativo Institucional",
    icon:     str = "🏛️",
    password_env: str = "",
    viewer_password_env: str = "",
    investor_password_env: str = "",
    user_admin: str = "admin",
    user_estudio: str = "estudio",
    user_inversor: str = "inversor",
    username_login: bool = False,
    try_database_users: bool = True,
    db_tenant_id: str | None = None,
    session_timeout: int = _SESSION_TIMEOUT_DEFAULT,
) -> bool:
    """
    Widget de login completo con:
    - SHA-256 + hmac.compare_digest (seguro a timing attacks)
    - Rate limiting: bloquea 5 min tras 5 intentos fallidos
    - Timeout de sesión configurable
    - Log de accesos en alertas_log
    - Token de sesión único por login exitoso
    - Por defecto: usuario + contraseña para distinguir admin / estudio / inversor

    Uso:
        from core.auth import check_password
        if not check_password("mq26", "MQ26 Terminal", password_env=APP_PASSWORD, ...):
            st.stop()
    """
    auth_key    = f"{app_id}_auth"
    role_key    = f"{app_id}_user_role"
    user_key    = f"{app_id}_login_user"
    ts_key      = f"{auth_key}_ts"
    token_key   = f"{auth_key}_token"
    input_key   = f"pwd_{app_id}"
    user_input_key = f"user_{app_id}"
    error_key   = f"{auth_key}_error"
    timeout_key = f"{auth_key}_timeout"

    # Verificar sesión activa
    if st.session_state.get(auth_key):
        elapsed = time.time() - st.session_state.get(ts_key, 0)
        if elapsed > session_timeout:
            # Limpiar solo las claves de esta app
            for k in [
                auth_key, ts_key, token_key, error_key, role_key, user_key,
                f"{app_id}_auth_source",
                f"{app_id}_allowed_cliente_ids",
                f"{app_id}_cliente_default_id",
                f"{app_id}_rama",
                f"{app_id}_db_user_id",
            ]:
                st.session_state.pop(k, None)
            st.session_state[timeout_key] = True
        else:
            st.session_state[ts_key] = time.time()
            st.session_state.setdefault(role_key, "admin")
            st.session_state.setdefault(f"{app_id}_auth_source", "env")
            st.session_state.setdefault(f"{app_id}_allowed_cliente_ids", None)
            st.session_state.setdefault(f"{app_id}_cliente_default_id", None)
            _rk = str(st.session_state.get(role_key, "admin")).lower()
            st.session_state.setdefault(
                f"{app_id}_rama",
                "retail" if _rk == "inversor" else "profesional",
            )
            return True

    # Pantalla de login (clases mq-auth-* + tokens CSS; sin #888 fijo sobre fondo oscuro)
    col = st.columns([1, 2, 1])[1]
    with col:
        _ic = html_module.escape(str(icon))
        _an = html_module.escape(str(app_name))
        _sub = html_module.escape(str(subtitle))
        st.markdown(
            f"<div class='mq-auth-login-hero'>"
            f"<div class='mq-auth-login-icon' aria-hidden='true'>{_ic}</div>"
            f"<h2 class='mq-auth-login-title'>{_an}</h2>"
            f"<p class='mq-auth-login-subtitle'>{_sub}</p></div>",
            unsafe_allow_html=True,
        )
        if st.session_state.get(timeout_key):
            st.warning("Sesión expirada por inactividad. Ingresá nuevamente.")

        bloqueado, segs_restantes = _esta_bloqueado(auth_key)
        if bloqueado:
            st.error(
                f"Demasiados intentos fallidos. Reintentá en "
                f"**{segs_restantes // 60}:{segs_restantes % 60:02d}** minutos."
            )
            # Barra de progreso del bloqueo
            progreso = 1 - (segs_restantes / _LOCKOUT_SECONDS)
            st.progress(progreso, text=f"Desbloqueando en {segs_restantes}s...")
            st.caption(LOGIN_LEGAL_DISCLAIMER_ES)
        else:
            if st.session_state.get(error_key):
                fails = st.session_state.get(f"{auth_key}_fails", 0)
                restantes = _MAX_FAILED_ATTEMPTS - fails
                msg_err = (
                    "Usuario o contraseña incorrectos. "
                    if username_login
                    else "Contraseña incorrecta. "
                )
                st.error(
                    msg_err
                    + (f"Quedan **{restantes}** intento(s) antes del bloqueo." if restantes > 0 else "")
                )
            with st.form(key=f"login_form_{app_id}"):
                user_field: str | None = None
                if username_login:
                    user_field = st.text_input(
                        "Usuario:",
                        key=user_input_key,
                        placeholder="admin, estudio, inversor…",
                    )
                pwd_field = st.text_input(
                    "Contraseña:",
                    type="password",
                    key=input_key,
                    placeholder="Tu clave del rol elegido",
                )
                submitted = st.form_submit_button("Ingresar")
            if username_login:
                hint_users = ", ".join(
                    sorted(
                        {
                            (user_admin or "").strip().lower(),
                            (user_estudio or "").strip().lower(),
                            (user_inversor or "").strip().lower(),
                        }
                        - {""},
                    )
                )
                st.caption(
                    f"**admin**: acceso total · **estudio**: profesional · "
                    f"**inversor** — usuarios configurables: {hint_users}"
                )
            st.caption(LOGIN_LEGAL_DISCLAIMER_ES)
            if st.session_state.get(f"{app_id}_degraded_auth"):
                st.caption("⚠️ Login BD degradado temporalmente; operando con fallback local.")
            if submitted is True:
                bloqueado, _ = _esta_bloqueado(auth_key)
                if not bloqueado:
                    pwd = pwd_field if isinstance(pwd_field, str) else ""
                    ok_login = False
                    assigned_role: str | None = None
                    db_hit: dict | None = None
                    if username_login:
                        u_raw = user_field if isinstance(user_field, str) else ""
                        u = (u_raw or "").strip().lower()
                        db_required = bool(try_database_users and (db_tenant_id or "").strip())
                        breakglass_user = (os.getenv("MQ26_BREAKGLASS_USER") or "").strip().lower()
                        breakglass_pass = os.getenv("MQ26_BREAKGLASS_PASSWORD") or ""
                        if try_database_users and (db_tenant_id or "").strip():
                            try:
                                from services.app_user_service import authenticate_app_user
                                db_hit = authenticate_app_user(db_tenant_id, u, pwd)
                            except Exception as exc:
                                _log.warning("degradacion_auth_db_lookup app=%s err=%s", app_id, exc, exc_info=True)
                                st.session_state[f"{app_id}_degraded_auth"] = True
                                db_hit = None
                        if db_hit:
                            ok_login = True
                            assigned_role = db_hit["session_role"]
                        # Fail-closed: si el login por BD es requerido, NO hacer fallback ENV,
                        # salvo cuenta breakglass explícita para contingencias.
                        if not ok_login and db_required:
                            if breakglass_user and u == breakglass_user and breakglass_pass:
                                if verificar_password(pwd, breakglass_pass):
                                    ok_login = True
                                    assigned_role = "admin"
                        if not ok_login and not db_required:
                            table = _login_user_table(
                                password_env=password_env,
                                viewer_password_env=viewer_password_env,
                                investor_password_env=investor_password_env,
                                user_admin=user_admin,
                                user_estudio=user_estudio,
                                user_inversor=user_inversor,
                            )
                            pair = table.get(u)
                            if pair:
                                sk, secret = pair
                                if secret and verificar_password(pwd, secret):
                                    ok_login = True
                                    assigned_role = sk
                    else:
                        ok_admin = verificar_password(pwd, password_env)
                        ok_viewer = bool(viewer_password_env) and verificar_password(
                            pwd, viewer_password_env
                        )
                        ok_investor = bool(investor_password_env) and verificar_password(
                            pwd, investor_password_env
                        )
                        if ok_investor:
                            ok_login = True
                            assigned_role = "inversor"
                        elif ok_viewer:
                            ok_login = True
                            assigned_role = "viewer"
                        elif ok_admin:
                            ok_login = True
                            assigned_role = "admin"
                    if ok_login and assigned_role:
                        st.session_state[auth_key] = True
                        st.session_state[ts_key] = time.time()
                        st.session_state[token_key] = secrets.token_urlsafe(32)
                        st.session_state[f"{auth_key}_fails"] = 0
                        st.session_state[f"{auth_key}_lock_ts"] = 0
                        st.session_state.pop(error_key, None)
                        st.session_state[role_key] = assigned_role
                        if db_hit:
                            st.session_state[f"{app_id}_auth_source"] = "db"
                            st.session_state[f"{app_id}_allowed_cliente_ids"] = db_hit["allowed_cliente_ids"]
                            st.session_state[f"{app_id}_cliente_default_id"] = db_hit.get("cliente_default_id")
                            st.session_state[f"{app_id}_rama"] = db_hit["rama"]
                            st.session_state[f"{app_id}_db_user_id"] = db_hit["user_id"]
                        else:
                            st.session_state[f"{app_id}_auth_source"] = "env"
                            st.session_state[f"{app_id}_allowed_cliente_ids"] = None
                            st.session_state[f"{app_id}_cliente_default_id"] = None
                            st.session_state[f"{app_id}_rama"] = (
                                "retail" if assigned_role == "inversor" else "profesional"
                            )
                            st.session_state.pop(f"{app_id}_db_user_id", None)
                        if username_login:
                            u_save = (user_field if isinstance(user_field, str) else "").strip()
                            st.session_state[user_key] = (
                                (db_hit.get("username") if db_hit else "")
                                or u_save
                                or u
                            )
                        _registrar_acceso(app_id, exito=True)
                    else:
                        fails = st.session_state.get(f"{auth_key}_fails", 0) + 1
                        st.session_state[f"{auth_key}_fails"] = fails
                        if fails >= _MAX_FAILED_ATTEMPTS:
                            st.session_state[f"{auth_key}_lock_ts"] = time.time()
                        st.session_state[error_key] = True
                        st.session_state.pop(auth_key, None)
                        _registrar_acceso(app_id, exito=False)
                st.rerun()
    return False


def get_session_token(app_id: str) -> str | None:
    """Devuelve el token de sesión único generado en el login."""
    return st.session_state.get(f"{app_id}_auth_token")


def cerrar_sesion(app_id: str) -> None:
    """Invalida la sesión actual del app_id dado."""
    auth_key = f"{app_id}_auth"
    for k in [
        auth_key,
        f"{auth_key}_ts",
        f"{auth_key}_token",
        f"{app_id}_auth_error",
        f"{app_id}_user_role",
        f"{app_id}_login_user",
        f"{app_id}_auth_source",
        f"{app_id}_allowed_cliente_ids",
        f"{app_id}_cliente_default_id",
        f"{app_id}_rama",
        f"{app_id}_db_user_id",
    ]:
        st.session_state.pop(k, None)


def get_user_role(app_id: str) -> str:
    """
    Rol normalizado de la sesión.

    Compatibilidad:
    - admin -> super_admin
    - viewer -> estudio
    """
    raw = str(st.session_state.get(f"{app_id}_user_role", "admin")).lower()
    role_map = {"admin": "super_admin", "viewer": "estudio"}
    return role_map.get(raw, raw)


FEATURE_DEFAULTS = {
    "super_admin": {
        "lab_quant": True,
        "estudio_dashboard": True,
        "tab_admin": True,
        "exportar_rrss": True,
        "analisis_empresa": True,
        "backtest_avanzado": True,
    },
    "estudio": {
        "lab_quant": False,
        "estudio_dashboard": True,
        "tab_admin": False,
        "exportar_rrss": False,
        "analisis_empresa": True,
        "backtest_avanzado": False,
    },
    "inversor": {
        "lab_quant": False,
        "estudio_dashboard": False,
        "tab_admin": False,
        "exportar_rrss": False,
        "analisis_empresa": False,
        "backtest_avanzado": False,
    },
}


def has_feature(role: str, feature: str) -> bool:
    """Autorización por feature flags con defaults por tier."""
    return bool(FEATURE_DEFAULTS.get(str(role).lower(), {}).get(feature, False))
