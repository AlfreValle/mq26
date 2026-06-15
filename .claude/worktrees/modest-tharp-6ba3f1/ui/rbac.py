"""
ui/rbac.py — RBAC ligero para Streamlit (Excelencia Industrial #3).

Centraliza chequeos de rol en lugar de ``if role`` dispersos en cada tab.
"""
from __future__ import annotations

from collections.abc import Callable, Container
from functools import wraps
from typing import Any, TypeVar

import streamlit as st

F = TypeVar("F", bound=Callable[..., Any])


# Matriz rol × acción: tests/test_rbac_p0_policy.py (P0-RBAC-02).
ACTION_POLICY: dict[str, set[str]] = {
    # Mutaciones y utilidades sensibles: deny-by-default.
    "sensitive_utils": {"admin", "super_admin"},
    # Estudio: crear/editar clientes, notas, informes (tab_estudio); cartera activa compartida con admin.
    "write": {"admin", "super_admin", "estudio"},
    "read": {"admin", "super_admin", "estudio", "inversor", "viewer"},
    # Panel Admin (tab_admin): solo super_admin en UI; defensa en profundidad en cada mutación.
    "panel_admin_write": {"super_admin"},
}


def user_role_lower(ctx: dict | None) -> str:
    return str((ctx or {}).get("user_role") or "").strip().lower()


def has_role(ctx: dict | None, allowed: Container[str]) -> bool:
    r = user_role_lower(ctx)
    return r in {str(x).strip().lower() for x in allowed}


def require_role(ctx: dict | None, allowed: Container[str], *, message: str | None = None) -> bool:
    """
    Si el rol no está permitido, muestra advertencia y retorna False.
    Si ctx es None, usa ``st.session_state`` si existe ``user_role`` (fallback poco frecuente).
    """
    c = ctx if ctx is not None else {}
    if not c.get("user_role"):
        try:
            c = {**c, "user_role": st.session_state.get("mq26_last_user_role", "")}
        except Exception:
            pass
    if has_role(c, allowed):
        return True
    st.warning(message or "No tenés permiso para ver esta sección.")
    return False


def require_roles(*allowed_roles: str) -> Callable[[F], F]:
    """Decorador para funciones ``render_tab_*(ctx)``."""

    def deco(fn: F) -> F:
        @wraps(fn)
        def wrapper(ctx: dict, *a: Any, **kw: Any) -> Any:
            if not require_role(ctx, allowed_roles):
                return None
            return fn(ctx, *a, **kw)

        return wrapper  # type: ignore[return-value]

    return deco


def can_action(ctx: dict | None, action: str, *, default: bool = False) -> bool:
    """
    Verifica permisos por acción con política centralizada.
    deny-by-default para acciones no definidas.
    """
    roles = ACTION_POLICY.get(str(action).strip().lower())
    if not roles:
        return default
    return has_role(ctx, roles)
