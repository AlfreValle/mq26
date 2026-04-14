"""
core/context_builder.py — Estandarización y defaults del contexto ``ctx`` Streamlit.

Evita campos faltantes en tabs que usan ``ctx.get`` con supuestos implícitos.
"""
from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

# Defaults seguros (no sustituyen claves ya definidas por el entrypoint).
_CTX_DEFAULTS: dict[str, Any] = {
    "metricas": {},
    "precios_dict": {},
    "tickers_sin_precio": [],
    "price_coverage_pct": 0.0,
    "valoracion_audit": {},
    "precio_records": {},
    "flow_resumen": {},
}


def finalize_ctx(ctx: dict) -> dict:
    """
    Devuelve un nuevo dict con ``setdefault`` aplicado para claves transversales.

    ``tenant_id``: en app multi-tenant suele inferirse del entorno si falta.
    """
    out = dict(ctx)
    for key, default in _CTX_DEFAULTS.items():
        out.setdefault(key, deepcopy(default) if isinstance(default, dict) else default)

    tid_existing = str(out.get("tenant_id") or "").strip()
    if tid_existing:
        out["tenant_id"] = tid_existing
    else:
        tid_env = (os.environ.get("MQ26_DB_TENANT_ID") or "").strip()
        out["tenant_id"] = tid_env or "default"
    # app: pestañas múltiples (Railway); mq26: típicamente una vista principal por rol
    out.setdefault("app_kind", "mq26")
    return out


class ContextBuilder:
    """Constructor fluido opcional; el camino simple es ``finalize_ctx``."""

    def __init__(self, base: dict | None = None) -> None:
        self._ctx: dict = dict(base or {})

    def with_defaults(self) -> ContextBuilder:
        self._ctx = finalize_ctx(self._ctx)
        return self

    def build(self) -> dict:
        return dict(self._ctx)
