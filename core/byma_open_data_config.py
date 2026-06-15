"""
Parametros unificados para la API BYMA Open Data (POST free/<tipo>).

Todas las claves pueden sobreescribirse por entorno sin tocar el motor.
"""
from __future__ import annotations

import os
from typing import Any

_DEFAULT_BASE = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"
_DEFAULT_TIMEOUT_SEC = 15
_DEFAULT_CACHE_TTL_SEC = 300
_DEFAULT_USER_AGENT = "MQ26Terminal/1.0"
_DEFAULT_PRECIO_UMBRAL_ARS = 500.0


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip() or default)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "").strip() or default)
    except (TypeError, ValueError):
        return default


def byma_open_data_base_url() -> str:
    u = os.environ.get("MQ26_BYMA_OPEN_DATA_BASE_URL", "").strip().rstrip("/")
    return u or _DEFAULT_BASE


def byma_open_data_timeout_sec() -> int:
    return max(5, _env_int("MQ26_BYMA_OPEN_DATA_TIMEOUT", _DEFAULT_TIMEOUT_SEC))


def byma_open_data_cache_ttl_sec() -> int:
    return max(30, _env_int("MQ26_BYMA_OPEN_DATA_CACHE_TTL", _DEFAULT_CACHE_TTL_SEC))


def byma_open_data_user_agent() -> str:
    return os.environ.get("MQ26_BYMA_OPEN_DATA_USER_AGENT", "").strip() or _DEFAULT_USER_AGENT


def byma_open_data_post_body() -> dict[str, Any]:
    return {
        "excludeZeroPxAndQty": _env_bool("MQ26_BYMA_OPEN_DATA_EXCLUDE_ZERO", True),
        "T2": _env_bool("MQ26_BYMA_OPEN_DATA_T2", True),
        "T1": _env_bool("MQ26_BYMA_OPEN_DATA_T1", False),
        "T0": _env_bool("MQ26_BYMA_OPEN_DATA_T0", False),
    }


def byma_on_precio_umbral_ars() -> float:
    v = _env_float("MQ26_BYMA_ON_PRECIO_UMBRAL_ARS", _DEFAULT_PRECIO_UMBRAL_ARS)
    return v if v > 0 else _DEFAULT_PRECIO_UMBRAL_ARS


BYMA_HTTP_TIMEOUT_DEFAULT: int = _DEFAULT_TIMEOUT_SEC
