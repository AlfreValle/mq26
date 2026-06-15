"""Configuracion unificada BYMA Open Data."""
from __future__ import annotations

import importlib

import core.byma_open_data_config as cfg


def test_byma_open_data_post_body_defaults():
    b = cfg.byma_open_data_post_body()
    assert b["excludeZeroPxAndQty"] is True
    assert b["T2"] is True
    assert b["T1"] is False
    assert b["T0"] is False


def test_byma_open_data_base_url_default():
    assert "bymadata.com.ar" in cfg.byma_open_data_base_url()


def test_byma_open_data_timeout_min_floor(monkeypatch):
    monkeypatch.setenv("MQ26_BYMA_OPEN_DATA_TIMEOUT", "2")
    importlib.reload(cfg)
    try:
        assert cfg.byma_open_data_timeout_sec() >= 5
    finally:
        monkeypatch.delenv("MQ26_BYMA_OPEN_DATA_TIMEOUT", raising=False)
        importlib.reload(cfg)


def test_byma_on_precio_umbral_ars(monkeypatch):
    monkeypatch.setenv("MQ26_BYMA_ON_PRECIO_UMBRAL_ARS", "600")
    importlib.reload(cfg)
    try:
        assert cfg.byma_on_precio_umbral_ars() == 600.0
    finally:
        monkeypatch.delenv("MQ26_BYMA_ON_PRECIO_UMBRAL_ARS", raising=False)
        importlib.reload(cfg)


def test_byma_http_timeout_default_matches_open_data():
    assert cfg.BYMA_HTTP_TIMEOUT_DEFAULT == 15
