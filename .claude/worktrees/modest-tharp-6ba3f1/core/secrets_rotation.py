"""
G03 — Convención de secretos por entorno (rotación manual documentada).

No almacena valores; solo nombres esperados para runbooks.
"""
from __future__ import annotations

EXPECTED_SECRET_ENV_KEYS = (
    "MQ26_PASSWORD",
    "MQ26_DATABASE_URL",
    "MQ26_OPT_JOBS_DB",
)


def list_expected_secret_env_keys() -> tuple[str, ...]:
    return EXPECTED_SECRET_ENV_KEYS


def secret_env_documented(key: str) -> bool:
    """True si la clave está en la lista de secretos gestionados por nombre."""
    return key in EXPECTED_SECRET_ENV_KEYS
