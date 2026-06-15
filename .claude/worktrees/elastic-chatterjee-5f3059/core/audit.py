"""
core/audit.py — Registro de acciones críticas (MQ-S10 / DS-S3)
Reemplaza print() y st.toast() de acciones críticas por auditoría en alertas_log.
"""
from __future__ import annotations

import datetime as dt

from core.logging_config import get_logger

_log = get_logger(__name__)


def registrar_accion(
    accion: str,
    detalle: str = "",
    cliente_id: int | None = None,
    ticker: str | None = None,
    tipo_alerta: str = "AUDITORIA",
    usuario: str | None = None,
) -> None:
    """
    Registra una acción crítica en alertas_log.
    No lanza excepciones — si la BD no está disponible, solo logea.

    Args:
        accion:     Nombre corto de la acción (ej. "GUARDAR_CARTERA", "ELIMINAR_OBJETIVO")
        detalle:    Descripción larga del evento
        cliente_id: ID del cliente involucrado (opcional)
        ticker:     Ticker involucrado (opcional)
        tipo_alerta: Tipo de alerta en alertas_log (default: "AUDITORIA")
        usuario:    Nombre del usuario que realizó la acción
    """
    mensaje = f"[{accion}]"
    if usuario:
        mensaje += f" usuario={usuario}"
    if ticker:
        mensaje += f" ticker={ticker}"
    if detalle:
        mensaje += f" — {detalle}"

    _log.info("AUDIT: %s", mensaje)

    try:
        import core.db_manager as dbm
        dbm.registrar_alerta_log(
            tipo_alerta=tipo_alerta,
            mensaje=mensaje,
            ticker=ticker or "",
            enviada=False,
        )
    except Exception as _e:
        _log.warning("No se pudo registrar auditoría en BD: %s", _e)


def registrar_login(app_id: str, exito: bool, usuario: str = "") -> None:
    """Registra intento de login (exitoso o fallido)."""
    registrar_accion(
        accion="LOGIN_EXITOSO" if exito else "LOGIN_FALLIDO",
        detalle=f"app={app_id} timestamp={dt.datetime.now().isoformat()}",
        tipo_alerta="ACCESO",
        usuario=usuario,
    )


def registrar_eliminacion(entidad: str, id_registro: int, cliente_id: int = None, usuario: str = "") -> None:
    """Registra eliminación de un registro (soft o hard delete)."""
    registrar_accion(
        accion=f"ELIMINAR_{entidad.upper()}",
        detalle=f"id={id_registro} cliente_id={cliente_id}",
        cliente_id=cliente_id,
        tipo_alerta="AUDITORIA",
        usuario=usuario,
    )


def registrar_modificacion(entidad: str, id_registro: int, campos: dict, cliente_id: int = None) -> None:
    """Registra modificación de un registro existente."""
    campos_str = ", ".join(f"{k}={v}" for k, v in campos.items())
    registrar_accion(
        accion=f"MODIFICAR_{entidad.upper()}",
        detalle=f"id={id_registro} campos=[{campos_str}]",
        cliente_id=cliente_id,
        tipo_alerta="AUDITORIA",
    )


def registrar_backup(ruta_backup: str, hash_hmac: str) -> None:
    """Registra la generación de un backup con su firma HMAC."""
    registrar_accion(
        accion="BACKUP_GENERADO",
        detalle=f"ruta={ruta_backup} hmac={hash_hmac[:16]}...",
        tipo_alerta="AUDITORIA",
    )
