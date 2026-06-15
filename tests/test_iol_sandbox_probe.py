from __future__ import annotations

from unittest.mock import MagicMock

from services.iol_api.config import IOLBotSettings
from services.iol_api.sandbox_probe import maybe_place_simulated_order, validate_catalog_and_quote


def _settings() -> IOLBotSettings:
    return IOLBotSettings(
        trading_mode="demo",
        username="u",
        password="p",
        timeout_sec=1.0,
        auth_path="/token",
        sandbox_base_url="https://sandbox.example.com",
        real_base_url="https://real.example.com",
        dry_run=True,
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


def test_probe_catalog_and_quote_ok():
    client = MagicMock()
    client.get_json.return_value = {"items": [1, 2]}
    client.get_quote.return_value = {"ultimoPrecio": 123}
    out = validate_catalog_and_quote(client, market="argentina", symbol="GGAL")
    assert out.ok is True
    assert "quote" in out.detail


def test_probe_order_disabled():
    client = MagicMock()
    out = maybe_place_simulated_order(client, _settings(), payload={"x": 1}, enabled=False)
    assert out.ok is True
    client.post_json.assert_not_called()
