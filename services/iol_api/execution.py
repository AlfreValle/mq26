from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.logging_config import get_logger
from services.iol_api.client import IOLApiClient
from services.iol_api.config import IOLBotSettings

logger = get_logger(__name__)


@dataclass(frozen=True)
class OrderIntent:
    side: str
    market: str
    symbol: str
    quantity: float
    price: float

    def normalized_side(self) -> str:
        side = self.side.strip().upper()
        if side in {"BUY", "COMPRA"}:
            return "BUY"
        if side in {"SELL", "VENTA"}:
            return "SELL"
        raise ValueError(f"Lado no soportado: {self.side}")

    def notional(self) -> float:
        return float(self.quantity) * float(self.price)


@dataclass(frozen=True)
class RiskLimits:
    max_notional_ars: float
    max_daily_loss_ars: float
    max_orders_per_day: int
    kill_switch_file: str


class IOLExecutionService:
    def __init__(
        self,
        client: IOLApiClient,
        settings: IOLBotSettings,
        risk_limits: RiskLimits,
    ) -> None:
        self.client = client
        self.settings = settings
        self.risk_limits = risk_limits
        self._sent_order_cache: dict[str, float] = {}
        self._orders_today = 0
        self._realized_pnl_ars = 0.0

    def _is_duplicate(self, intent: OrderIntent) -> bool:
        window = max(1, int(self.settings.order_idempotency_window_sec))
        key = hashlib.sha256(
            json.dumps(asdict(intent), sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        now = time.time()
        ts = self._sent_order_cache.get(key)
        if ts and now - ts <= window:
            return True
        self._sent_order_cache[key] = now
        return False

    def _is_kill_switch_enabled(self) -> bool:
        return bool(self.risk_limits.kill_switch_file and self.risk_limits.kill_switch_file.strip()) and (
            __import__("pathlib").Path(self.risk_limits.kill_switch_file).exists()
        )

    def _validate_risk(self, intent: OrderIntent) -> None:
        if self._is_kill_switch_enabled():
            raise RuntimeError("Kill switch activo. No se permiten nuevas ordenes.")
        if intent.notional() > self.risk_limits.max_notional_ars:
            raise RuntimeError(
                f"Notional excedido {intent.notional():.2f} > {self.risk_limits.max_notional_ars:.2f}"
            )
        if self._orders_today >= self.risk_limits.max_orders_per_day:
            raise RuntimeError("Limite diario de ordenes alcanzado.")
        if self._realized_pnl_ars <= -abs(self.risk_limits.max_daily_loss_ars):
            raise RuntimeError("Limite de perdida diaria alcanzado.")

    def place_order(self, intent: OrderIntent) -> dict[str, Any]:
        intent = OrderIntent(
            side=intent.normalized_side(),
            market=intent.market,
            symbol=intent.symbol,
            quantity=float(intent.quantity),
            price=float(intent.price),
        )
        self._validate_risk(intent)
        if self._is_duplicate(intent):
            return {"status": "skipped_duplicate", "intent": asdict(intent)}

        payload = {
            "side": intent.side,
            "market": intent.market,
            "symbol": intent.symbol,
            "quantity": intent.quantity,
            "price": intent.price,
            "mode": self.settings.trading_mode,
        }

        self._orders_today += 1
        if self.settings.dry_run:
            logger.info("IOL dry-run order %s", payload)
            return {"status": "dry_run", "payload": payload}

        result = self.client.post_json(self.settings.orders_endpoint, payload)
        return {"status": "submitted", "payload": payload, "broker_response": result}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        payload = {"order_id": order_id}
        if self.settings.dry_run:
            return {"status": "dry_run_cancel", "payload": payload}
        result = self.client.post_json(f"{self.settings.orders_endpoint}/cancelar", payload)
        return {"status": "cancel_submitted", "broker_response": result}

    def get_positions(self) -> dict[str, Any]:
        return self.client.get_json(self.settings.positions_endpoint)

    def get_orders(self) -> dict[str, Any]:
        return self.client.get_json(self.settings.orders_status_endpoint)

    def update_realized_pnl(self, pnl_ars: float) -> None:
        self._realized_pnl_ars = float(pnl_ars)
