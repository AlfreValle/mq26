from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.iol_api.config import IOLBotSettings
from services.iol_api.execution import IOLExecutionService, OrderIntent, RiskLimits


def _settings(dry_run: bool = True) -> IOLBotSettings:
    return IOLBotSettings(
        trading_mode="demo",
        username="u",
        password="p",
        timeout_sec=1.0,
        auth_path="/token",
        sandbox_base_url="https://sandbox.example.com",
        real_base_url="https://real.example.com",
        dry_run=dry_run,
        max_notional_ars=100000.0,
        max_daily_loss_ars=10000.0,
        max_orders_per_day=2,
        kill_switch_file="",
        quote_endpoint_template="/quote/{market}/{symbol}",
        orders_endpoint="/orders",
        positions_endpoint="/positions",
        orders_status_endpoint="/orders/status",
        order_idempotency_window_sec=120,
    )


def test_execution_dry_run_y_idempotencia():
    client = MagicMock()
    svc = IOLExecutionService(
        client=client,
        settings=_settings(dry_run=True),
        risk_limits=RiskLimits(100000, 10000, 2, ""),
    )
    intent = OrderIntent("BUY", "argentina", "GGAL", 1, 1000)
    r1 = svc.place_order(intent)
    r2 = svc.place_order(intent)
    assert r1["status"] == "dry_run"
    assert r2["status"] == "skipped_duplicate"
    client.post_json.assert_not_called()


def test_execution_respeta_kill_switch(tmp_path):
    kill_file = Path(tmp_path / "kill.switch")
    kill_file.write_text("1", encoding="utf-8")
    client = MagicMock()
    svc = IOLExecutionService(
        client=client,
        settings=_settings(dry_run=True),
        risk_limits=RiskLimits(100000, 10000, 2, str(kill_file)),
    )
    with pytest.raises(RuntimeError):
        svc.place_order(OrderIntent("BUY", "argentina", "GGAL", 1, 1000))
