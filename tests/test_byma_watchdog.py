import pytest


def test_byma_watchdog_retorna_estructura(monkeypatch):
    def _fake_fetch(endpoint):
        return [{"symbol": "GGAL", "lastPrice": 3500}]

    monkeypatch.setattr("services.byma_market_data._fetch_tipo", _fake_fetch)

    from services.byma_watchdog import check_byma_status

    status = check_byma_status()

    assert isinstance(status, dict)
    assert status["ok"] is True
    assert "mensaje" in status
    assert "timestamp" in status
    assert isinstance(status["latencia_ms"], (int, float))


def test_byma_watchdog_falla_gracefully(monkeypatch):
    def _fake_fetch_err(endpoint):
        raise ConnectionError("timeout simulado")

    monkeypatch.setattr("services.byma_market_data._fetch_tipo", _fake_fetch_err)

    from services.byma_watchdog import check_byma_status

    status = check_byma_status()

    assert status["ok"] is False
    assert len(status["mensaje"]) > 10
    assert "BYMA" in status["mensaje"]
