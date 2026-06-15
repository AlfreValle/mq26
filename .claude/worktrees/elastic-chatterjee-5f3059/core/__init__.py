"""core — Capa de infraestructura compartida (DB, auth, caché, contexto)."""
from core.app_context import AppContext
from core.audit import registrar_accion
from core.auth import cerrar_sesion, check_password, get_user_role, has_feature, verificar_password
from core.ctx_builder import build_ctx
from core.db_manager import (
    get_config,
    get_session,
    guardar_config,
    init_db,
    obtener_config,
    set_config,
)
from core.validators import validar_categoria, validar_fecha, validar_monto

__all__ = [
    "init_db", "get_session", "guardar_config", "obtener_config", "set_config", "get_config",
    "check_password", "verificar_password", "cerrar_sesion", "get_user_role", "has_feature",
    "AppContext", "build_ctx",
    "validar_monto", "validar_fecha", "validar_categoria",
    "registrar_accion",
]
