"""
services/byma_provider.py — Proveedor REST genérico para precios BYMA / tercero.

Contrato y variables: ver docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md (§6).

Configuración (opcional):
  MQ26_BYMA_API_URL   — base URL (ej. https://api.proveedor.com/v1)
  MQ26_BYMA_API_KEY   — header Authorization Bearer o X-Api-Key según MQ26_BYMA_AUTH_HEADER
  MQ26_BYMA_AUTH_HEADER — default: Authorization

Contrato esperado del endpoint (ajustable al proveedor real):
  POST {MQ26_BYMA_API_URL}/cotizaciones
  Body JSON: {"tickers": ["GGAL", "AL30", ...]}
  Response JSON: {"precios": {"GGAL": 5234.5, "AL30": 72.3}, ...}

Si la URL no está definida o la respuesta falla, devuelve dict vacío (no rompe la app).
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_BYMA_URL = os.environ.get("MQ26_BYMA_API_URL", "").strip().rstrip("/")
_BYMA_KEY = os.environ.get("MQ26_BYMA_API_KEY", "").strip()
_BYMA_HDR = os.environ.get("MQ26_BYMA_AUTH_HEADER", "Authorization").strip() or "Authorization"
_TIMEOUT = int(os.environ.get("MQ26_BYMA_TIMEOUT", "12"))


def byma_configurado() -> bool:
    return bool(_BYMA_URL)


def fetch_precios_ars_batch(tickers: list[str]) -> dict[str, float]:
    """
    Obtiene precios ARS por lote. Sin URL configurada retorna {}.
    """
    if not _BYMA_URL or not tickers:
        return {}

    body = json.dumps({"tickers": [str(t).upper().strip() for t in tickers if t]}).encode("utf-8")
    endpoint = f"{_BYMA_URL}/cotizaciones"
    headers = {"Content-Type": "application/json", "User-Agent": "MQ26/1.0"}
    if _BYMA_KEY:
        headers[_BYMA_HDR] = f"Bearer {_BYMA_KEY}" if _BYMA_HDR.lower() == "authorization" else _BYMA_KEY

    try:
        req = Request(endpoint, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        return {}

    precios = raw.get("precios") or raw.get("prices") or raw.get("data") or {}
    out: dict[str, float] = {}
    if isinstance(precios, dict):
        for k, v in precios.items():
            try:
                if float(v) > 0:
                    out[str(k).upper().strip()] = float(v)
            except (TypeError, ValueError):
                continue
    return out


class BymaRestMarketProvider:
    """Implementación mínima del Protocol MarketDataProvider (fetch_close)."""

    def fetch_close(self, tickers: list[str], **kwargs: Any) -> Any:
        """Para históricos el proxy suele devolver vacío; caller debe usar yfinance."""
        import pandas as pd

        return pd.DataFrame()

    def fetch_last_ars(self, tickers: list[str]) -> dict[str, float]:
        return fetch_precios_ars_batch(tickers)
