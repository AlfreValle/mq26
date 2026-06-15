"""
Helpers de logging estructurado para degradaciones no fatales.
"""
from __future__ import annotations

from typing import Any

from core.logging_config import get_logger


def log_degradacion(logger_name: str, evento: str, exc: Exception | None = None, **ctx: Any) -> None:
    """
    Emite warning estructurado para errores no fatales.
    """
    _log = get_logger(logger_name)
    payload = {"evento": str(evento), **ctx}
    if exc is not None:
        _log.warning("degradacion: %s | error=%s", payload, exc, exc_info=True)
    else:
        _log.warning("degradacion: %s", payload)
