from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pandas as pd

from services.iol_api.config import IOLBotSettings
from services.iol_api.execution import IOLExecutionService, RiskLimits
from services.iol_api.runner import RegimeRouterConfig, RunnerInput, TradingBotRunner


def _settings_dry_run() -> IOLBotSettings:
    return IOLBotSettings(
        trading_mode="demo",
        username="u",
        password="p",
        timeout_sec=1.0,
        auth_path="/token",
        sandbox_base_url="https://sandbox.example.com",
        real_base_url="https://real.example.com",
        dry_run=True,
        max_notional_ars=1e9,
        max_daily_loss_ars=1e9,
        max_orders_per_day=99,
        kill_switch_file="",
        quote_endpoint_template="/q/{market}/{symbol}",
        orders_endpoint="/o",
        positions_endpoint="/p",
        orders_status_endpoint="/s",
        order_idempotency_window_sec=60,
    )


def test_runner_router_blocks_when_not_dry_run():
    s = replace(_settings_dry_run(), dry_run=False)
    client = MagicMock()
    risk = RiskLimits(1e9, 1e9, 99, "")
    execution = IOLExecutionService(client=client, settings=s, risk_limits=risk)
    cfg = RegimeRouterConfig(
        regime_to_strategy={0: "ma_cross_10_30", 1: "ma_cross_5_20"},
        default_strategy="ma_cross_10_30",
        vol_window=20,
        rank_window=60,
    )
    runner = TradingBotRunner(execution=execution, regime_router=cfg)
    prices = pd.Series([100.0 + i * 0.5 for i in range(200)])
    out = runner.run_once(
        RunnerInput(
            market="argentina",
            symbol="TEST",
            quantity=1.0,
            price_hint=100.0,
            price_series=prices,
        )
    )
    assert out.get("mode") == "regime_router"
    assert "strategy_selected" in out
    assert out.get("router_safety") is True
    if out.get("decision") != "HOLD":
        assert out.get("execution", {}).get("status") == "router_safety_blocked"
    client.post_json.assert_not_called()
