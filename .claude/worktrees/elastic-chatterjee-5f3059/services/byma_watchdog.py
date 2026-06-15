"""
services/byma_watchdog.py — Estado de conectividad BYMA Open Data.

Sin Streamlit. Retorna estado y mensaje para que la UI decida cómo mostrarlo.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.structured_logging import log_degradacion

_LOG_NAME = "services.byma_watchdog"
_LAST_OK: datetime | None = None
_LAST_ERR: str | None = None


def check_byma_status(timeout: float = 8.0) -> dict[str, Any]:
    """Intenta conectar a BYMA Open Data y retorna el estado de la consulta."""
    global _LAST_OK, _LAST_ERR

    import time
    from services.byma_market_data import _fetch_tipo

    t0 = time.perf_counter()
    try:
        data = _fetch_tipo("cedears")
        latencia = round((time.perf_counter() - t0) * 1000, 0)
        _LAST_OK = datetime.now(timezone.utc)
        _LAST_ERR = None
        return {
            "ok": True,
            "latencia_ms": latencia,
            "mensaje": f"BYMA conectado · {latencia:.0f} ms · {len(data)} instrumentos",
            "timestamp": _LAST_OK.isoformat(),
        }
    except Exception as exc:
        latencia_err = round((time.perf_counter() - t0) * 1000, 0)
        _LAST_ERR = str(exc)[:120]
        log_degradacion(_LOG_NAME, "byma_no_responde", exc, latencia_ms=latencia_err)
        return {
            "ok": False,
            "latencia_ms": None,
            "mensaje": (
                "BYMA Open Data no responde en este momento. "
                "Los precios mostrados pueden no estar actualizados. "
                "Intentá actualizar en unos minutos."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def get_last_ok() -> datetime | None:
    """Última vez que BYMA respondió correctamente en esta sesión."""
    return _LAST_OK
