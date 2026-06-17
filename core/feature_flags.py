"""
core/feature_flags.py — A08: feature flags por tenant, sin deploy.

Hasta hoy los toggles eran constantes de módulo o variables de entorno
(BYMA_FIRST se evaluaba al import: cambiarlo exigía reiniciar la app).
Este módulo da flags persistidos en BD con scoping por tenant:

- Storage: reusa la tabla ``configuracion`` (db_manager) con clave compuesta
  ``FLAG.{tenant}.{flag}`` — sin migraciones nuevas.
- Resolución: override del tenant → override de "default" → default declarado
  (que puede venir de una env var, ej. MQ26_BYMA_FIRST).
- Cache TTL en memoria (60 s): los camino-calientes (price_engine) pueden
  consultar sin costo de BD por llamada; un cambio desde el panel admin
  tarda ≤60 s en propagarse (o usar invalidar_cache()).
- Auditoría: cada set_flag registra un evento ADMIN.feature_flag.* — quién
  cambió qué y cuándo.

Vive en core/ a propósito: db_manager es core y price_engine (core) lo
consume — services/ también puede importarlo, la inversa no valdría.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.logging_config import get_logger

_log = get_logger(__name__)

_PREFIJO = "FLAG"
_TTL_CACHE_S = 60.0


def _default_byma_first() -> bool:
    return os.environ.get("MQ26_BYMA_FIRST", "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class FlagDef:
    nombre: str
    descripcion: str
    default: bool = False
    default_fn: Any = None  # callable sin args → bool (evaluado en runtime)

    def valor_default(self) -> bool:
        if self.default_fn is not None:
            try:
                return bool(self.default_fn())
            except Exception:
                return self.default
        return self.default


FLAGS_CONOCIDOS: dict[str, FlagDef] = {
    "byma_first": FlagDef(
        "byma_first",
        "Priorizar BYMA sobre yfinance en la cadena de precios. "
        "Default: env MQ26_BYMA_FIRST.",
        default_fn=_default_byma_first,
    ),
    "plan_explicado": FlagDef(
        "plan_explicado",
        "Mostrar el plan explicado (motivos + confianza, Pilar 3) en los flujos de recomendación.",
        default=True,
    ),
    "ficha_velas": FlagDef(
        "ficha_velas",
        "Permitir el gráfico de velas (descarga de red) en la ficha de ticker.",
        default=True,
    ),
    "ficha_consenso": FlagDef(
        "ficha_consenso",
        "Incluir la sección consenso de analistas en la ficha de ticker.",
        default=True,
    ),
    "ping_proveedores": FlagDef(
        "ping_proveedores",
        "Habilitar el botón de ping a proveedores externos en Salud de datos.",
        default=True,
    ),
}


# ─── Cache TTL (apto para camino caliente) ────────────────────────────────────

_lock = threading.Lock()
_cache: dict[str, tuple[float, bool | None]] = {}  # clave_bd → (ts, valor|None=no override)


def invalidar_cache() -> None:
    with _lock:
        _cache.clear()


def _clave_bd(flag: str, tenant_id: str) -> str:
    return f"{_PREFIJO}.{tenant_id}.{flag}"


def _leer_override(flag: str, tenant_id: str) -> bool | None:
    """Override persistido para (tenant, flag); None si no hay. Con cache TTL."""
    clave = _clave_bd(flag, tenant_id)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(clave)
        if hit is not None and (now - hit[0]) < _TTL_CACHE_S:
            return hit[1]
    valor: bool | None = None
    try:
        from core import db_manager as dbm

        raw = dbm.obtener_config(clave, default=None)
        if raw is not None:
            valor = str(raw).strip().lower() in ("1", "true", "yes")
    except Exception as exc:  # BD caída: el flag cae al default, nunca rompe
        _log.warning("feature_flags: lectura de %s falló: %s", clave, exc)
    with _lock:
        _cache[clave] = (now, valor)
    return valor


# ─── API ──────────────────────────────────────────────────────────────────────

def _norm_tenant(tenant_id: str | None) -> str:
    t = str(tenant_id or "").strip()
    return t or "default"


def get_flag(flag: str, tenant_id: str | None = None) -> bool:
    """
    Valor efectivo del flag para el tenant.
    Resolución: override del tenant → override "default" → default declarado.
    Flags desconocidos devuelven False (y avisan en log).
    """
    f = str(flag or "").strip().lower()
    definicion = FLAGS_CONOCIDOS.get(f)
    if definicion is None:
        _log.warning("feature_flags: flag desconocido %r — devolviendo False", flag)
        return False
    tid = _norm_tenant(tenant_id)
    v = _leer_override(f, tid)
    if v is not None:
        return v
    if tid != "default":
        v = _leer_override(f, "default")
        if v is not None:
            return v
    return definicion.valor_default()


def set_flag(
    flag: str,
    valor: bool,
    tenant_id: str | None = None,
    *,
    actor: str = "",
) -> bool:
    """
    Persiste el override del flag para el tenant y lo audita.
    Devuelve True si se guardó. Nunca lanza.
    """
    f = str(flag or "").strip().lower()
    if f not in FLAGS_CONOCIDOS:
        _log.warning("feature_flags: intento de setear flag desconocido %r", flag)
        return False
    tid = _norm_tenant(tenant_id)
    clave = _clave_bd(f, tid)
    try:
        from core import db_manager as dbm

        anterior = get_flag(f, tid)
        dbm.guardar_config(clave, "true" if valor else "false")
        try:
            dbm.registrar_admin_audit_event(
                f"feature_flag.{f}",
                actor=actor,
                tenant_id=tid,
                detail={"anterior": anterior, "nuevo": bool(valor)},
            )
        except Exception:
            pass
        invalidar_cache()
        return True
    except Exception as exc:
        _log.warning("feature_flags: no se pudo guardar %s: %s", clave, exc)
        return False


@dataclass
class EstadoFlag:
    nombre: str
    descripcion: str
    valor: bool
    default: bool
    tiene_override: bool
    flags_extra: dict[str, Any] = field(default_factory=dict)


def listar_flags(tenant_id: str | None = None) -> list[EstadoFlag]:
    """Estado efectivo de todos los flags conocidos para el tenant (panel admin)."""
    tid = _norm_tenant(tenant_id)
    out: list[EstadoFlag] = []
    for nombre, d in FLAGS_CONOCIDOS.items():
        override = _leer_override(nombre, tid)
        if override is None and tid != "default":
            override = _leer_override(nombre, "default")
        out.append(
            EstadoFlag(
                nombre=nombre,
                descripcion=d.descripcion,
                valor=get_flag(nombre, tid),
                default=d.valor_default(),
                tiene_override=override is not None,
            )
        )
    return out
