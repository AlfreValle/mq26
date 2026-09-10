"""
ui/error_boundaries.py — Sprint 6: Error boundaries reutilizables para MQ26.

Ofrece:
  @safe_render     — decorator para funciones de render; captura excepciones
                     y muestra un bloque de error amigable en lugar de crashear.
  @safe_tab        — decorator especializado para tabs; preserva el tab header.
  error_block_html — HTML de bloque de error con ARIA (role="alert").
  render_error_block — renderiza el bloque en Streamlit.
  ErrorContext     — context manager para bloques de código críticos.
  error_boundary   — decorator factory con configuración personalizada.

Diseño:
  - No importa streamlit en módulo-nivel (lazy import).
  - Loggea con traceback completo antes de mostrar el error al usuario.
  - En producción: muestra mensaje genérico sin tracebacks.
  - En debug (MQ26_DEBUG=1): muestra traceback completo plegado.
  - Compatible con feature flag ERROR_BOUNDARIES si se agrega al registry.
"""
from __future__ import annotations

import functools
import logging
import os
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

_LOG = logging.getLogger(__name__)

_DEBUG = os.environ.get("MQ26_DEBUG", "").strip() == "1"


# ─── HTML de error ────────────────────────────────────────────────────────────

def error_block_html(
    title: str = "Error inesperado",
    message: str = "Ocurrió un error al cargar esta sección.",
    *,
    detail: str = "",
    show_detail: bool = False,
    compact: bool = False,
) -> str:
    """Delega en ``ui.mq26_ux.error_message_html`` (misma tarjeta, paleta del design system)."""
    from ui.mq26_ux import error_message_html

    _ = compact  # layout lo define la clase mq-error-boundary
    cta = ""
    if show_detail and detail:
        cta = str(detail)[:1500]
    return error_message_html(title, message, cta=cta)


def render_error_block(
    title: str = "Error inesperado",
    message: str = "Ocurrió un error al cargar esta sección.",
    *,
    exc: Exception | None = None,
    compact: bool = False,
) -> None:
    """
    Renderiza el bloque de error directamente en Streamlit.

    Args:
        title:   Título del error.
        message: Mensaje amigable.
        exc:     Excepción original (traceback se muestra en debug).
        compact: Versión compacta.
    """
    try:
        import streamlit as st
        detail = ""
        show_detail = False
        if exc is not None and _DEBUG:
            detail = traceback.format_exc()
            show_detail = True
        html = error_block_html(title, message, detail=detail, show_detail=show_detail, compact=compact)
        st.markdown(html, unsafe_allow_html=True)
    except Exception:
        # Último recurso: usar st.error
        try:
            import streamlit as st
            st.error(f"**{title}**: {message}")
        except Exception:
            pass


# ─── Decorator @safe_render ──────────────────────────────────────────────────

def safe_render[F: Callable[..., Any]](
    func: F | None = None,
    *,
    title: str = "Error al renderizar",
    message: str = "Esta sección no pudo cargarse.",
    compact: bool = False,
    reraise: bool = False,
) -> F | Callable[[F], F]:
    """
    Decorator que captura excepciones en funciones de render.
    Si la función lanza, muestra un error_block amigable y loggea.

    Uso:
        @safe_render
        def render_mi_tab(ctx):
            ...

        @safe_render(title="Error en cartera", compact=True)
        def render_cartera(ctx):
            ...

    Args:
        title:   Título del bloque de error.
        message: Mensaje amigable.
        compact: Bloque de error compacto.
        reraise: Si True, relanza la excepción tras mostrar el error.
    """
    def decorator(f: F) -> F:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return f(*args, **kwargs)
            except Exception as exc:
                _LOG.error(
                    "safe_render[%s]: %s — %s",
                    f.__name__, type(exc).__name__, exc,
                    exc_info=True,
                )
                render_error_block(title, message, exc=exc, compact=compact)
                if reraise:
                    raise
                return None
        return wrapper  # type: ignore[return-value]

    if func is not None:
        # Llamado sin paréntesis: @safe_render
        return decorator(func)  # type: ignore[return-value]
    # Llamado con paréntesis: @safe_render(...)
    return decorator  # type: ignore[return-value]


def safe_tab[F: Callable[..., Any]](
    func: F | None = None,
    *,
    tab_label: str = "",
    compact: bool = True,
) -> F | Callable[[F], F]:
    """
    Decorator especializado para funciones de render de tabs.
    Igual que safe_render pero con defaults pensados para tabs (compact=True).

    Uso:
        @safe_tab
        def render_tab_optimizacion(ctx):
            ...

        @safe_tab(tab_label="Cartera")
        def render_tab_cartera(ctx):
            ...
    """
    label = tab_label or (func.__name__ if func else "tab")
    return safe_render(
        func,
        title=f"Error en {label}" if func is None else f"Error en {func.__name__}",
        message="Esta pestaña no pudo cargarse. Recargá la página o contactá soporte.",
        compact=compact,
    )  # type: ignore[return-value]


# ─── error_boundary factory ───────────────────────────────────────────────────

def error_boundary[F: Callable[..., Any]](
    *,
    title: str = "Error inesperado",
    message: str = "Ocurrió un error al cargar esta sección.",
    compact: bool = False,
    on_error: Callable[[Exception], None] | None = None,
    reraise: bool = False,
) -> Callable[[F], F]:
    """
    Factory que retorna un decorator de error boundary configurable.

    Args:
        title:    Título del bloque de error.
        message:  Mensaje amigable para el usuario.
        compact:  Bloque de error compacto.
        on_error: Callback opcional llamado con la excepción.
        reraise:  Si True, relanza la excepción tras manejarla.

    Ejemplo:
        @error_boundary(title="Error de optimización", on_error=sentry_capture)
        def run_optimizer(ctx):
            ...
    """
    def decorator(f: F) -> F:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return f(*args, **kwargs)
            except Exception as exc:
                _LOG.error(
                    "error_boundary[%s]: %s — %s",
                    f.__name__, type(exc).__name__, exc,
                    exc_info=True,
                )
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception:
                        pass
                render_error_block(title, message, exc=exc, compact=compact)
                if reraise:
                    raise
                return None
        return wrapper  # type: ignore[return-value]
    return decorator


# ─── Context manager ErrorContext ─────────────────────────────────────────────

class ErrorContext:
    """
    Context manager para envolver bloques de código críticos con manejo de error.

    Uso:
        with ErrorContext("cargando cartera"):
            df = cartera_service.get_df_ag(cliente_id)
            # Si lanza, se muestra error_block y continúa sin crashear

        # con configuración:
        with ErrorContext("diagnóstico", title="Error de diagnóstico", compact=True) as ec:
            result = diagnosticar(...)
            if ec.failed:
                return  # el error ya se mostró
    """

    def __init__(
        self,
        context_name: str = "",
        *,
        title: str = "",
        message: str = "",
        compact: bool = False,
        reraise: bool = False,
    ) -> None:
        self.context_name = context_name
        self.title   = title or f"Error en {context_name or 'esta operación'}"
        self.message = message or "Esta operación no pudo completarse."
        self.compact  = compact
        self.reraise  = reraise
        self.exception: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.exception is None

    @property
    def failed(self) -> bool:
        return self.exception is not None

    def __enter__(self) -> ErrorContext:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if exc_type is not None and issubclass(exc_type, Exception):
            self.exception = exc_val
            _LOG.error(
                "ErrorContext[%s]: %s — %s",
                self.context_name, exc_type.__name__, exc_val,
                exc_info=True,
            )
            render_error_block(self.title, self.message, exc=exc_val, compact=self.compact)
            if self.reraise:
                return False  # propaga la excepción
            return True   # suprime la excepción
        return False


# ─── Convenience: @contextmanager version ─────────────────────────────────────

@contextmanager
def safe_section(
    section_name: str = "",
    *,
    title: str = "",
    message: str = "",
    compact: bool = False,
) -> Generator[None, None, None]:
    """
    Context manager funcional para secciones de render.

    Uso:
        with safe_section("cargando tabla de posiciones"):
            render_tabla(df)
    """
    t = title or f"Error en {section_name or 'esta sección'}"
    m = message or "Esta sección no pudo cargarse."
    try:
        yield
    except Exception as exc:
        _LOG.error("safe_section[%s]: %s", section_name, exc, exc_info=True)
        render_error_block(t, m, exc=exc, compact=compact)
