#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None  # type: ignore[assignment]

_env_path = ROOT / ".env"
if _load_dotenv and _env_path.is_file():
    _load_dotenv(_env_path)

from services.iol_api.client import IOLApiClient
from services.iol_api.config import load_iol_bot_settings
from services.iol_api.sandbox_probe import maybe_place_simulated_order, validate_catalog_and_quote


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida conectividad API IOL (catalogo + quote + orden opcional).")
    parser.add_argument("--market", default="argentina", help="Mercado para cotizacion.")
    parser.add_argument("--symbol", default="GGAL", help="Ticker para cotizacion.")
    parser.add_argument("--send-order", action="store_true", help="Enviar orden de prueba.")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--quantity", default="1")
    parser.add_argument("--price", default="1000")
    args = parser.parse_args()

    settings = load_iol_bot_settings()
    client = IOLApiClient(settings=settings)

    quote_probe = validate_catalog_and_quote(client, market=args.market, symbol=args.symbol)
    print(json.dumps({"ok": quote_probe.ok, "message": quote_probe.message, "detail": quote_probe.detail}, ensure_ascii=False, indent=2))

    order_payload = {
        "side": args.side,
        "market": args.market,
        "symbol": args.symbol,
        "quantity": float(args.quantity),
        "price": float(args.price),
        "mode": settings.trading_mode,
    }
    order_probe = maybe_place_simulated_order(
        client=client,
        settings=settings,
        payload=order_payload,
        enabled=bool(args.send_order),
    )
    print(json.dumps({"ok": order_probe.ok, "message": order_probe.message, "detail": order_probe.detail}, ensure_ascii=False, indent=2))

    if quote_probe.ok and order_probe.ok:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
