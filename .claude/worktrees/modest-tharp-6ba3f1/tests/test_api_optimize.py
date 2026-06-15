"""F06 — API síncrona POST /optimize (httpx TestClient, sin red)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MQ26_OPT_JOBS_DB", str(tmp_path / "opt_api.db"))
    monkeypatch.setenv("MQ26_ARTIFACTS_DIR", str(tmp_path / "art"))
    from api.optimization_app import app

    return TestClient(app)


def test_optimize_happy_path(client):
    mu = [0.08, 0.10, 0.09]
    sigma = [[0.04, 0.01, 0.0], [0.01, 0.05, 0.01], [0.0, 0.01, 0.04]]
    r = client.post(
        "/optimize",
        json={"tickers": ["A", "B", "C"], "mu": mu, "Sigma": sigma},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert set(body["weights"].keys()) == {"A", "B", "C"}
    assert sum(body["weights"].values()) == pytest.approx(1.0, abs=1e-5)
    assert "cache_fingerprint" in body["meta"]


def test_optimize_invalid_shape_returns_400(client):
    r = client.post(
        "/optimize",
        json={"tickers": ["A"], "mu": [0.1, 0.2], "Sigma": [[0.04]]},
    )
    assert r.status_code == 400


def test_optimize_demo_sin_matrices(client):
    r = client.post("/optimize", json={})
    assert r.status_code == 200
    w = r.json()["weights"]
    assert len(w) == 3


def test_health_includes_latency_snapshot(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "latency_ms" in r.json()
