from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.logging_config import get_logger
from services.iol_api.client import IOLApiClient, IOLApiError
from services.iol_api.config import IOLBotSettings

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    message: str
    detail: dict[str, Any]


def validate_catalog_and_quote(
    client: IOLApiClient,
    market: str,
    symbol: str,
    candidate_catalog_paths: list[str] | None = None,
) -> ProbeResult:
    catalogs = candidate_catalog_paths or [
        "/api/v2/Cotizaciones/monedas",
        "/api/v2/Cotizaciones/argentina/Titulos",
        "/api/v2/Cotizaciones/estados_Unidos/Titulos",
    ]
    catalog_result: dict[str, Any] = {}
    for path in catalogs:
        try:
            data = client.get_json(path)
            catalog_result[path] = {"ok": True, "size": len(data.get("items", data))}
        except Exception as exc:
            catalog_result[path] = {"ok": False, "error": str(exc)}

    try:
        quote = client.get_quote(market=market, symbol=symbol)
        return ProbeResult(
            ok=True,
            message="Validacion de catalogo y quote completada.",
            detail={"catalogs": catalog_result, "quote": quote},
        )
    except IOLApiError as exc:
        return ProbeResult(
            ok=False,
            message="No se pudo obtener cotizacion en entorno actual.",
            detail={"catalogs": catalog_result, "error": str(exc)},
        )


def maybe_place_simulated_order(
    client: IOLApiClient,
    settings: IOLBotSettings,
    payload: dict[str, Any],
    enabled: bool,
) -> ProbeResult:
    if not enabled:
        return ProbeResult(
            ok=True,
            message="Orden de prueba omitida (habilitar explicitamente para ejecutar).",
            detail={"enabled": False},
        )
    try:
        response = client.post_json(settings.orders_endpoint, payload)
        return ProbeResult(
            ok=True,
            message="Orden simulada enviada.",
            detail={"response": response},
        )
    except IOLApiError as exc:
        logger.warning("Sandbox order probe fallo: %s", exc)
        return ProbeResult(
            ok=False,
            message="Fallo al enviar orden simulada.",
            detail={"error": str(exc), "payload": payload},
        )
