"""
H04 — Contratos tipados (TypedDict) para payloads API/servicios sin acoplar Pydantic en runtime mínimo.
"""
from __future__ import annotations

from typing import NotRequired, TypedDict


class OptimizePayloadTD(TypedDict, total=False):
    tickers: list[str]
    mu: list[float]
    Sigma: list[list[float]]
    rf: float
    long_only: bool
    method: str
