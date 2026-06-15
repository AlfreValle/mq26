"""
core/otel_tracing.py — Observabilidad OpenTelemetry opcional (Fase 2, I2).

Si ``opentelemetry-api`` no está instalado, las funciones son no-op y no rompen la app.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


class _NoopSpan:
    def set_attribute(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def record_exception(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def end(self) -> None:
        return

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return


class _NoopTracer:
    def start_as_current_span(
        self, _name: str, attributes: dict | None = None, **_kwargs: Any
    ) -> _NoopSpan:
        return _NoopSpan()


def get_tracer(name: str = "mq26.optimization") -> Any:
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except Exception:
        return _NoopTracer()


@contextmanager
def span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    tracer = get_tracer()
    attrs = {k: v for k, v in attributes.items() if v is not None}
    try:
        cm = tracer.start_as_current_span(name, attributes=attrs or None)
    except TypeError:
        cm = tracer.start_as_current_span(name)
    with cm as sp:
        yield sp
