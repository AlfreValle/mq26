"""Healthcheck público no filtra detalles de Postgres al cliente."""
from __future__ import annotations

import json
import sys
import types

import api.healthcheck as hc


def test_postgres_fallo_no_incluye_str_exc(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:supersecret@localhost/db")

    fake = types.ModuleType("psycopg2")

    def _boom(*_a, **_k):
        raise RuntimeError("password authentication failed for user supersecret")

    fake.connect = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg2", fake)

    payload = hc._build_status()
    blob = json.dumps(payload)
    assert "supersecret" not in blob
    assert payload["checks"]["database"]["ok"] is False
    assert "error" not in payload["checks"]["database"]
