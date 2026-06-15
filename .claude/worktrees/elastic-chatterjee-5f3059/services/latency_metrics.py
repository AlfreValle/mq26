"""
I01 — Métricas de latencia en memoria (sin dependencias de observabilidad).

Uso: ``record_latency("optimize_ms", elapsed_seconds * 1000)`` desde servicios/API.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_lock = threading.Lock()
_buckets: dict[str, list[float]] = defaultdict(list)
_MAX_SAMPLES = 512


def record_latency(name: str, value_ms: float) -> None:
    """Registra una muestra de latencia en milisegundos."""
    with _lock:
        b = _buckets[name]
        b.append(float(value_ms))
        if len(b) > _MAX_SAMPLES:
            del b[: len(b) - _MAX_SAMPLES]


def snapshot() -> dict[str, dict[str, float]]:
    """Resumen p50/p95 aproximado (percentiles naïve sobre buffer)."""
    with _lock:
        out: dict[str, dict[str, float]] = {}
        for name, vals in _buckets.items():
            if not vals:
                continue
            s = sorted(vals)
            n = len(s)
            out[name] = {
                "count": float(n),
                "p50_ms": s[n // 2],
                "p95_ms": s[int(0.95 * (n - 1))] if n > 1 else s[0],
                "last_ms": s[-1],
            }
        return out


def reset_metrics() -> None:
    with _lock:
        _buckets.clear()


@contextmanager
def measure(name: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record_latency(name, (time.perf_counter() - t0) * 1000.0)


def latency_middleware_hook(operation: str) -> dict[str, Any]:
    """Hook para ensamblar respuesta de health/diagnóstico."""
    return {"operation": operation, "latency": snapshot()}
