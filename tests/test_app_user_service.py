"""Usuarios app_usuarios: autenticación y alcance de clientes."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


def test_authenticate_app_user_super_admin_sin_filtro(db_en_memoria):
    dbm = db_en_memoria
    dbm.registrar_cliente("C1", "Moderado", 1_000.0, "Persona", "1 año", tenant_id="default")
    dbm.create_app_usuario(
        tenant_id="default",
        username="boss",
        plain_password="87654321",
        rol="super_admin",
        rama="profesional",
        cliente_default_id=None,
        cliente_ids=[],
    )
    from services.app_user_service import authenticate_app_user

    bad = authenticate_app_user("default", "boss", "wrong")
    assert bad is None
    ok = authenticate_app_user("default", "boss", "87654321")
    assert ok is not None
    assert ok["session_role"] == "admin"
    assert ok["allowed_cliente_ids"] is None


def test_authenticate_inversor_solo_cliente_vinculado(db_en_memoria):
    dbm = db_en_memoria
    cid = dbm.registrar_cliente("Solo Yo", "Moderado", 5_000.0, "Persona", "1 año", tenant_id="default")
    dbm.create_app_usuario(
        tenant_id="default",
        username="inv1",
        plain_password="87654321",
        rol="inversor",
        rama="retail",
        cliente_default_id=cid,
        cliente_ids=[cid],
    )
    from services.app_user_service import authenticate_app_user

    ok = authenticate_app_user("default", "inv1", "87654321")
    assert ok["allowed_cliente_ids"] == [cid]
