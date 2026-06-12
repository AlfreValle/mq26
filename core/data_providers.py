"""
J04 / J01 — Abstracción de proveedores de mercado; preferencia BYMA-first opcional.

`BymaRestMarketProvider` implementa el protocolo vía REST (`MQ26_BYMA_API_URL`).
"""
from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

# Default por env (evaluado al import) — el valor efectivo se consulta con
# byma_first_activo(), que respeta el feature flag por tenant (A08).
BYMA_FIRST: bool = os.environ.get("MQ26_BYMA_FIRST", "").strip().lower() in ("1", "true", "yes")


def byma_first_activo(tenant_id: str | None = None) -> bool:
    """
    ¿Priorizar BYMA sobre yfinance? Flag por tenant con cache TTL (60 s);
    si los flags no responden, cae al default por env (BYMA_FIRST).
    """
    try:
        from core.feature_flags import get_flag

        return get_flag("byma_first", tenant_id)
    except Exception:
        return BYMA_FIRST


@runtime_checkable
class MarketDataProvider(Protocol):
    """Contrato mínimo para precios históricos. Ver `BymaRestMarketProvider` para último ARS (intraday)."""

    def fetch_close(self, tickers: list[str], **kwargs: Any) -> Any:
        """Devuelve serie o DataFrame de cierres; implementación concreta TBD."""
        ...
