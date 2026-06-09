from __future__ import annotations

from unittest.mock import MagicMock

from services.iol_api.client import IOLApiClient
from services.iol_api.config import IOLBotSettings


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
        max_orders_per_day=10,
        kill_switch_file="",
        quote_endpoint_template="/quote/{market}/{symbol}",
        orders_endpoint="/orders",
        positions_endpoint="/positions",
        orders_status_endpoint="/orders/status",
        order_idempotency_window_sec=60,
    )


def test_client_login_y_quote():
    session = MagicMock()
    resp_login = MagicMock()
    resp_login.json.return_value = {"access_token": "abc", "refresh_token": "r1", "expires_in": 900}
    resp_login.status_code = 200
    resp_login.raise_for_status.return_value = None

    resp_quote = MagicMock()
    resp_quote.json.return_value = {"ultimoPrecio": 1234.5}
    resp_quote.status_code = 200
    resp_quote.raise_for_status.return_value = None

    session.request.side_effect = [resp_login, resp_quote]
    client = IOLApiClient(settings=_settings(), session=session)
    data = client.get_quote("argentina", "GGAL")
    assert data["ultimoPrecio"] == 1234.5
    assert session.request.call_count == 2


def test_client_refresh_en_401():
    session = MagicMock()
    resp_login = MagicMock()
    resp_login.json.return_value = {"access_token": "abc", "refresh_token": "r1", "expires_in": 900}
    resp_login.status_code = 200
    resp_login.raise_for_status.return_value = None

    resp_401 = MagicMock()
    resp_401.status_code = 401
    resp_401.raise_for_status.side_effect = Exception("401")

    resp_refresh = MagicMock()
    resp_refresh.json.return_value = {"access_token": "new", "refresh_token": "r1", "expires_in": 900}
    resp_refresh.status_code = 200
    resp_refresh.raise_for_status.return_value = None

    resp_ok = MagicMock()
    resp_ok.json.return_value = {"ok": True}
    resp_ok.status_code = 200
    resp_ok.raise_for_status.return_value = None

    session.request.side_effect = [resp_login, resp_401, resp_refresh, resp_ok]
    client = IOLApiClient(settings=_settings(), session=session, max_retries=1)
    out = client.get_json("/x")
    assert out["ok"] is True
