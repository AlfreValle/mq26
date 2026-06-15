"""
J04 / J01 — Abstracción de proveedores de mercado; preferencia BYMA-first opcional.

`BymaRestMarketProvider` implementa el protocolo vía REST (`MQ26_BYMA_API_URL`).
"""
from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from services.byma_provider import BymaRestMarketProvider

BYMA_FIRST: bool = os.environ.get("MQ26_BYMA_FIRST", "").strip().lower() in ("1", "true", "yes")


@runtime_checkable
class MarketDataProvider(Protocol):
    """Contrato mínimo para precios históricos. Ver `BymaRestMarketProvider` para último ARS (intraday)."""

    def fetch_close(self, tickers: list[str], **kwargs: Any) -> Any:
        """Devuelve serie o DataFrame de cierres; implementación concreta TBD."""
        ...
