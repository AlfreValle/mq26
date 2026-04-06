"""
core/logging_config.py — Logging estructurado centralizado MQ26-DSS (Sprint 16)
En producción (RAILWAY_ENVIRONMENT definida): JSON para parsing en Railway.
En desarrollo: texto legible con colores.
Preserva _SensitiveDataFilter para redactar tokens y credenciales.
Invariante: get_logger(name) siempre retorna un Logger válido, nunca lanza.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ── Entorno y nivel ──────────────────────────────────────────────────────────
_ENVIRONMENT = os.environ.get("RAILWAY_ENVIRONMENT",
               os.environ.get("ENVIRONMENT", "development"))
_LOG_LEVEL   = os.environ.get("LOG_LEVEL", "INFO").upper()
_IS_PROD     = _ENVIRONMENT not in ("development", "dev", "local", "test")

_ROOT    = Path(__file__).resolve().parent.parent
_LOG_DIR = _ROOT / "0_Data_Maestra" / "logs"

# Contexto de sesión inyectado en todos los logs
_EXTRA_FIELDS: dict[str, Any] = {}


# ── Contexto de sesión ───────────────────────────────────────────────────────

def set_log_context(**kwargs) -> None:
    """
    Inyecta campos adicionales en todos los logs de la sesión actual.
    Uso: set_log_context(tenant_id="x@mail.com", cartera="Retiro")
    Invariante: no lanza, ignora silenciosamente errores.
    """
    try:
        _EXTRA_FIELDS.update(kwargs)
    except Exception:
        pass


def clear_log_context() -> None:
    """Limpia el contexto de log de la sesión actual."""
    try:
        _EXTRA_FIELDS.clear()
    except Exception:
        pass


# ── Filtro de datos sensibles (preservado de versión anterior) ───────────────

_PATRONES_SENSIBLES = [
    (re.compile(r'\d{8,12}:[A-Za-z0-9_\-]{25,}'), '[TELEGRAM_TOKEN_REDACTED]'),
    (re.compile(r'(password|passwd|pwd|secret|token)\s*[:=]\s*\S+', re.I), r'\1: [REDACTED]'),
    (re.compile(r'MQ26_PASSWORD\s*=\s*\S+'), 'MQ26_PASSWORD=[REDACTED]'),
]


class _SensitiveDataFilter(logging.Filter):
    """Redacta tokens y credenciales de los mensajes de log."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for patron, reemplazo in _PATRONES_SENSIBLES:
                msg = patron.sub(reemplazo, msg)
            record.msg  = msg
            record.args = ()
        except Exception:
            pass
        return True


# ── Formatters ───────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Formatter que emite cada log como una línea JSON (producción)."""
    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts":     datetime.now(UTC).isoformat(),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        doc.update(_EXTRA_FIELDS)
        # Campos extra pasados con extra={} al logger
        for k, v in record.__dict__.items():
            if k not in logging.LogRecord.__dict__ and not k.startswith("_"):
                try:
                    json.dumps(v)
                    doc[k] = v
                except (TypeError, ValueError):
                    doc[k] = str(v)
        return json.dumps(doc, ensure_ascii=False)


class _DevFormatter(logging.Formatter):
    """Formatter legible con colores para desarrollo local."""
    _COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color  = self._COLORS.get(record.levelname, "")
        reset  = self._RESET
        ts     = datetime.now().strftime("%H:%M:%S")
        prefix = f"{color}{record.levelname:8s}{reset}"
        ctx    = ""
        if _EXTRA_FIELDS:
            ctx = " " + " ".join(f"{k}={v}" for k, v in _EXTRA_FIELDS.items())
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{ts} {prefix} [{record.name}]{ctx} {msg}"


# ── Configuración ─────────────────────────────────────────────────────────────

_configurado = False
_handler: logging.Handler | None = None


def _get_handler() -> logging.Handler:
    global _handler
    if _handler is None:
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setFormatter(_JsonFormatter() if _IS_PROD else _DevFormatter())
    return _handler


def _configurar_raiz() -> None:
    global _configurado
    raiz = logging.getLogger()
    raiz.setLevel(logging.DEBUG)

    filtro_sensible = _SensitiveDataFilter()
    raiz.addFilter(filtro_sensible)

    # Handler de consola (JSON en prod, texto en dev)
    ch = _get_handler()
    ch.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
    raiz.addHandler(ch)

    # Handler de archivo rotativo (solo en desarrollo para no llenar disco en Railway)
    if not _IS_PROD:
        try:
            _LOG_DIR.mkdir(parents=True, exist_ok=True)
            fmt_file = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            fh = RotatingFileHandler(
                _LOG_DIR / "mq26_dss.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt_file)
            raiz.addHandler(fh)
        except Exception:
            pass

    # Silenciar librerías externas verbosas
    for lib in ("yfinance", "urllib3", "peewee", "sqlalchemy.engine"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    _configurado = True


def get_logger(name: str) -> logging.Logger:
    """
    Retorna un Logger configurado para el entorno actual.
    En producción emite JSON; en desarrollo emite texto legible con colores.
    Invariante: siempre retorna un Logger válido, nunca lanza.
    """
    global _configurado
    if not _configurado:
        _configurar_raiz()
    return logging.getLogger(name)
