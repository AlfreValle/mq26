"""P0-TNT-01 — aislamiento tenant en db_manager (no IDOR en actualizar/borrar)."""
from __future__ import annotations

import pytest


def test_actualizar_cliente_rechaza_otro_tenant(db_en_memoria):
    dbm = db_en_memoria
    ca = dbm.registrar_cliente(
        "A", "Moderado", 1.0, "Persona", tenant_id="tenant_a",
    )
    with pytest.raises(ValueError, match="fuera de tenant"):
        dbm.actualizar_cliente(
            ca, "X", "Moderado", 2.0, "Persona", "1 año", tenant_id="tenant_b",
        )


def test_obtener_cliente_vacio_si_otro_tenant(db_en_memoria):
    dbm = db_en_memoria
    ca = dbm.registrar_cliente(
        "SoloA", "Moderado", 1.0, "Persona", tenant_id="tenant_a",
    )
    assert dbm.obtener_cliente(ca, tenant_id="tenant_a")
    assert dbm.obtener_cliente(ca, tenant_id="tenant_b") == {}


def test_delete_app_usuario_rechaza_otro_tenant(db_en_memoria):
    dbm = db_en_memoria
    cid = dbm.registrar_cliente("U1", "Moderado", 1.0, "Persona", tenant_id="ta")
    uid = dbm.create_app_usuario(
        tenant_id="ta",
        username="u1",
        plain_password="password123",
        rol="inversor",
        rama="retail",
        cliente_default_id=cid,
        cliente_ids=[cid],
    )
    with pytest.raises(ValueError, match="no pertenece"):
        dbm.delete_app_usuario(uid, tenant_id="otro")


def test_delete_app_usuario_ok_mismo_tenant(db_en_memoria):
    dbm = db_en_memoria
    cid = dbm.registrar_cliente("U2", "Moderado", 1.0, "Persona", tenant_id="tb")
    uid = dbm.create_app_usuario(
        tenant_id="tb",
        username="u2",
        plain_password="password123",
        rol="inversor",
        rama="retail",
        cliente_default_id=cid,
        cliente_ids=[cid],
    )
    dbm.delete_app_usuario(uid, tenant_id="tb")
    assert dbm.list_app_usuarios("tb") == []
