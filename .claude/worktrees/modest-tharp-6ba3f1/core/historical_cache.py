"""
C07: caché determinista en memoria para paneles históricos (misma llave → mismo DataFrame).

La llave es SHA-256 de: tickers Yahoo ordenados, periodo, flags de alineación.
Invalidación: cambia cualquier ticker o periodo → llave distinta.
"""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

_CACHE: dict[str, pd.DataFrame] = {}


def historico_cache_key(
    tickers_yf: list[str],
    period: str,
    *,
    align_calendar_strict: bool,
    relax_alignment_if_short: bool,
    min_filas: int,
) -> str:
    tnorm = "|".join(sorted({str(x).strip().upper() for x in tickers_yf}))
    payload = f"{tnorm}|p={period}|acs={align_calendar_strict}|r={relax_alignment_if_short}|m={min_filas}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def historico_cache_get(key: str) -> pd.DataFrame | None:
    v = _CACHE.get(key)
    return None if v is None else v.copy()


def historico_cache_set(key: str, df: pd.DataFrame) -> None:
    _CACHE[key] = df.copy()


def historico_cache_clear() -> None:
    _CACHE.clear()


def historico_cache_stats() -> dict[str, Any]:
    return {"n_entries": len(_CACHE), "keys": list(_CACHE.keys())}
