"""
core/rbac_audit.py — Roles mínimos y auditoría de parámetros (Fase 0: G73–G74).

G73: roles viewer / analyst / admin (Streamlit: st.session_state['mq_role']).
G74: eventos AUDIT_PARAM vía registrar_alerta (append-only lógico).
"""
from __future__ import annotations

import json
import logging
from typing import Literal

logger = logging.getLogger(__name__)

Role = Literal["viewer", "analyst", "admin"]

ROLES_ORDER: tuple[Role, ...] = ("viewer", "analyst", "admin")

ROLE_RANK: dict[Role, int] = {"viewer": 0, "analyst": 1, "admin": 2}


def get_effective_role(session_state: dict) -> Role:
    """Lee rol desde session_state; default analyst si no existe."""
    r = session_state.get("mq_role", "analyst")
    if r not in ROLES_ORDER:
        return "analyst"
    return r  # type: ignore[return-value]


def require_can_edit_optimization_params(session_state: dict) -> None:
    """G73: viewers no pueden cambiar parámetros globales de optimización."""
    require_role(session_state, "analyst")


def require_role(session_state: dict, min_role: Role) -> None:
    """Exige al menos ``min_role`` (orden: viewer < analyst < admin)."""
    role = get_effective_role(session_state)
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise PermissionError(
            f"Se requiere rol mínimo '{min_role}'; el rol actual es '{role}'."
        )


def audit_optimization_run(
    *,
    job_id: str,
    method: str,
    manifest_sha256: str,
    usuario: str = "",
    tenant_id: str | None = None,
) -> None:
    """G74 / G76: traza quién disparó una optimización (jobs o UI)."""
    payload = {
        "evento": "OPTIMIZATION_RUN",
        "job_id": job_id,
        "method": method,
        "manifest_sha256": manifest_sha256,
        "usuario": usuario or "anon",
        "tenant_id": tenant_id,
    }
    try:
        import core.db_manager as dbm

        dbm.registrar_alerta(
            tipo_alerta="AUDIT_OPTIMIZATION_RUN",
            mensaje=json.dumps(payload, ensure_ascii=False),
            ticker="",
            cliente_id=None,
        )
    except Exception as e:
        logger.warning("audit_optimization_run: no persistido (%s)", e)


def audit_param_change(
    clave: str,
    valor_anterior: str,
    valor_nuevo: str,
    *,
    usuario: str = "",
) -> None:
    """
    G74: registra cambio de parámetro (best-effort; no tumba la app si falla BD).
    """
    payload = {
        "clave": clave,
        "antes": valor_anterior,
        "despues": valor_nuevo,
        "usuario": usuario or "anon",
    }
    try:
        import core.db_manager as dbm

        dbm.registrar_alerta(
            tipo_alerta="AUDIT_PARAM",
            mensaje=json.dumps(payload, ensure_ascii=False),
            ticker="",
            cliente_id=None,
        )
    except Exception as e:
        logger.warning("audit_param_change: no persistido (%s)", e)
