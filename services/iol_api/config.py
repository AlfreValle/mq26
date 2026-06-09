from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IOLBotSettings:
    trading_mode: str
    username: str
    password: str
    timeout_sec: float
    auth_path: str
    sandbox_base_url: str
    real_base_url: str
    dry_run: bool
    max_notional_ars: float
    max_daily_loss_ars: float
    max_orders_per_day: int
    kill_switch_file: str
    quote_endpoint_template: str
    orders_endpoint: str
    positions_endpoint: str
    orders_status_endpoint: str
    order_idempotency_window_sec: int

    @property
    def base_url(self) -> str:
        if self.trading_mode == "real":
            return self.real_base_url
        return self.sandbox_base_url


def load_iol_bot_settings() -> IOLBotSettings:
    mode = (os.environ.get("IOL_TRADING_MODE", "demo").strip().lower() or "demo")
    if mode not in {"demo", "real"}:
        mode = "demo"

    return IOLBotSettings(
        trading_mode=mode,
        username=os.environ.get("IOL_USERNAME", "").strip(),
        password=os.environ.get("IOL_PASSWORD", "").strip(),
        timeout_sec=float(os.environ.get("IOL_TIMEOUT_SEC", "15").strip()),
        auth_path=os.environ.get("IOL_AUTH_PATH", "/token").strip() or "/token",
        sandbox_base_url=os.environ.get(
            "IOL_SANDBOX_BASE_URL",
            "https://sandboxapi.invertironline.com",
        ).strip(),
        real_base_url=os.environ.get("IOL_REAL_BASE_URL", "https://api.invertironline.com").strip(),
        dry_run=_as_bool(os.environ.get("IOL_DRY_RUN"), default=True),
        max_notional_ars=float(os.environ.get("IOL_MAX_NOTIONAL_ARS", "250000").strip()),
        max_daily_loss_ars=float(os.environ.get("IOL_MAX_DAILY_LOSS_ARS", "50000").strip()),
        max_orders_per_day=int(os.environ.get("IOL_MAX_ORDERS_PER_DAY", "20").strip()),
        kill_switch_file=os.environ.get(
            "IOL_KILL_SWITCH_FILE",
            str(Path(os.getenv("TEMP", ".")) / "iol_bot.kill"),
        ).strip(),
        quote_endpoint_template=os.environ.get(
            "IOL_QUOTE_ENDPOINT_TEMPLATE",
            "/api/v2/{market}/Titulos/{symbol}/Cotizacion",
        ).strip(),
        orders_endpoint=os.environ.get("IOL_ORDERS_ENDPOINT", "/api/v2/operar/Simular").strip(),
        positions_endpoint=os.environ.get("IOL_POSITIONS_ENDPOINT", "/api/v2/portafolio/argentina").strip(),
        orders_status_endpoint=os.environ.get("IOL_ORDERS_STATUS_ENDPOINT", "/api/v2/operaciones").strip(),
        order_idempotency_window_sec=int(
            os.environ.get("IOL_ORDER_IDEMPOTENCY_WINDOW_SEC", "90").strip()
        ),
    )
