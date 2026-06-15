"""
Autenticación de usuarios MQ26 almacenados en BD (app_usuarios / app_usuario_cliente).

Sin Streamlit. Soporta bcrypt (estándar) y migración lazy desde SHA-256 legacy.
"""
from __future__ import annotations

from typing import Any
from core.password_hashing import hash_password_bcrypt, verify_password

# Rol en BD → clave interna de sesión (compatible con get_user_role)
SESSION_ROLE_BY_DB: dict[str, str] = {
    "super_admin": "admin",
    "estudio": "estudio",
    "inversor": "inversor",
}


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
        ok_pwd, needs_upgrade = verify_password(plain_password, u.password_hash)
        if not ok_pwd:
            return None
        if needs_upgrade:
            # Migración lazy: al autenticar legacy SHA-256, se reescribe en bcrypt.
            u.password_hash = hash_password_bcrypt(plain_password)
            s.flush()
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
        default_id: int | None
        if u.rol == "super_admin":
            default_id = None
        else:
            default_id = int(u.cliente_default_id) if u.cliente_default_id is not None else None
        return {
            "session_role": session_role,
            "rama": rama,
            "allowed_cliente_ids": allowed,
            "cliente_default_id": default_id,
            "user_id": u.id,
            "username": u.username,
        }
