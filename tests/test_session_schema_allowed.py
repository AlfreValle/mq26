"""Allowlist de clientes parametrizado por app_id (anti-IDOR latente)."""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from core.domain_ctx import TenantCtx
from core.session_schema import K


def test_allowed_clientes_key_por_app_id():
    assert K.allowed_clientes_key("mq26") == "mq26_allowed_cliente_ids"
    assert K.allowed_clientes_key("app") == "app_allowed_cliente_ids"
    assert K.allowed_clientes_key("") == "mq26_allowed_cliente_ids"
    assert K.allowed_clientes_key(None) == "mq26_allowed_cliente_ids"
    assert K.ALLOWED_CLIENTES == K.allowed_clientes_key("mq26")


def test_tenant_lee_clave_dinamica_no_mq26_fija(monkeypatch):
    """Si app_id='app', un allowlist en mq26_* no abre el acceso (fail-closed)."""

    def fake_get_ss(key, default=None):
        if key == "app_allowed_cliente_ids":
            return [7, 9]
        if key == "mq26_allowed_cliente_ids":
            return None
        return default

    monkeypatch.setattr("core.session_schema.get_ss", fake_get_ss)
    ctx = SimpleNamespace(app_id="app", tenant_id="t1", df_clientes=pd.DataFrame())
    tenant = TenantCtx.from_app(ctx)
    assert tenant.cliente_permitido(7) is True
    assert tenant.cliente_permitido(9) is True
    assert tenant.cliente_permitido(1) is False


def test_tenant_allowlist_vacio_no_es_irrestricto(monkeypatch):
    def fake_get_ss(key, default=None):
        if key == "mq26_allowed_cliente_ids":
            return []
        return default

    monkeypatch.setattr("core.session_schema.get_ss", fake_get_ss)
    ctx = SimpleNamespace(app_id="mq26", tenant_id="t1", df_clientes=pd.DataFrame())
    tenant = TenantCtx.from_app(ctx)
    assert tenant.allowed_cliente_ids == ()
    assert tenant.cliente_permitido(1) is False
