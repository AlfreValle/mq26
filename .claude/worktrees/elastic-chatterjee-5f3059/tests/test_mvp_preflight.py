"""Tests para comprobaciones MVP (sin cargar .env real)."""
from __future__ import annotations

from pathlib import Path

from services.mvp_preflight import run_checks


def test_run_checks_mvp_sqlite_ok():
    env = {
        "MQ26_PASSWORD": "12345678",
        "DATABASE_URL": "",
        "DB_URL": "",
    }
    err, warn = run_checks(environ=env, sqlite_path=Path("/no/existe/test.db"))
    assert not err
    assert any("SQLite aún no existe" in w for w in warn)
    assert any("MVP modo SQLite" in w for w in warn)


def test_run_checks_password_corta():
    env = {
        "MQ26_PASSWORD": "short",
        "DATABASE_URL": "",
        "DB_URL": "",
    }
    err, warn = run_checks(environ=env, sqlite_path=Path(__file__))
    assert err
    assert any("MQ26_PASSWORD" in e for e in err)


def test_run_checks_urls_distintas():
    env = {
        "MQ26_PASSWORD": "12345678",
        "DATABASE_URL": "postgresql://a@b:5432/db",
        "DB_URL": "postgresql://c@d:5432/db",
    }
    err, warn = run_checks(environ=env, sqlite_path=Path(__file__))
    assert not err
    assert any("difieren" in w for w in warn)
