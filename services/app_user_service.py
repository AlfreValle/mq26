"""
Autenticación de usuarios MQ26 almacenados en BD (app_usuarios / app_usuario_cliente).

Sin Streamlit. Misma huella SHA-256 en hex que core.auth (verificar_password).
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

# Rol en BD → clave interna de sesión (compatible con get_user_role)
SESSION_ROLE_BY_DB: dict[str, str] = {
    "super_admin": "admin",
    "asesor": "asesor",
    "estudio": "viewer",
    "inversor": "inversor",
}


def _digest(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def authenticate_app_user(tenant_id: str, username: str, plain_password: str) -> dict[str, Any] | None:
    """
    Valida usuario activo del tenant. Devuelve dict para session_state o None.

    allowed_cliente_ids: None = todos los clientes del tenant (super_admin);
    lista vacía = sin clientes asignados; lista con ids = alcance explícito.
    """
    from core.db_manager import AppUsuario, AppUsuarioCliente, get_session

    tid = (tenant_id or "default").strip() or "default"
    uname = (username or "").strip().lower()
    if not uname or not plain_password:
        return None

    with get_session() as s:
        u = (
            s.query(AppUsuario)
            .filter(
                AppUsuario.tenant_id == tid,
                AppUsuario.username == uname,
                AppUsuario.activo == True,  # noqa: E712
            )
            .first()
        )
        if u is None:
            return None
        if not hmac.compare_digest(u.password_hash, _digest(plain_password)):
            return None
        session_role = SESSION_ROLE_BY_DB.get(u.rol)
        if not session_role:
            return None

        allowed: list[int] | None
        if u.rol == "super_admin":
            allowed = None
        else:
            ids = {row[0] for row in s.query(AppUsuarioCliente.cliente_id).filter(
                AppUsuarioCliente.usuario_id == u.id
            ).all()}
            if u.cliente_default_id:
                ids.add(int(u.cliente_default_id))
            allowed = sorted(ids)

        rama = u.rama if u.rama in ("retail", "profesional") else (
            "retail" if u.rol == "inversor" else "profesional"
        )
        return {
            "session_role": session_role,
            "rama": rama,
            "allowed_cliente_ids": allowed,
            "user_id": u.id,
            "username": u.username,
        }
