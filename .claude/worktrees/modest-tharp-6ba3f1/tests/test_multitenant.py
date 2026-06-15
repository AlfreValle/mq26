"""
tests/test_multitenant.py — Tests de aislamiento multi-tenant (Sprint 5)
Invariante central: tenant A no puede ver datos de tenant B.
Usa BD SQLite en memoria — no toca la BD de producción.
Sin llamadas reales a yfinance ni red.
"""
from __future__ import annotations

import pandas as pd
import pytest

# ─── Fixture de BD en memoria ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def dbm_mem():
    """
    db_manager apuntando a SQLite en memoria con tenant_id disponible.
    Scope=module: una sola instancia por módulo de test para performance.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import core.db_manager as dbm

    test_engine = create_engine("sqlite:///:memory:", echo=False)
    dbm.Base.metadata.create_all(bind=test_engine)
    orig_session = dbm.SessionLocal
    orig_engine  = dbm.engine

    dbm.SessionLocal = sessionmaker(bind=test_engine,
                                    autocommit=False, autoflush=False)
    dbm.engine = test_engine

    yield dbm

    dbm.SessionLocal = orig_session
    dbm.engine       = orig_engine


# ─── Aislamiento de datos ──────────────────────────────────────────────────────

class TestAislamientoTenant:
    def test_cliente_tenant_a_no_visible_en_tenant_b(self, dbm_mem):
        """Invariante principal: cliente registrado en A no aparece para B."""
        dbm_mem.registrar_cliente(
            "Juan Perez Aislado", tenant_id="asesorA@mail.com"
        )
        df_b = dbm_mem.obtener_clientes_df(tenant_id="asesorB@mail.com")
        nombres_b = df_b["Nombre"].tolist() if not df_b.empty else []
        assert "Juan Perez Aislado" not in nombres_b

    def test_cliente_tenant_a_visible_en_tenant_a(self, dbm_mem):
        """El cliente sí aparece para su propio tenant."""
        dbm_mem.registrar_cliente(
            "Maria Lopez Visible", tenant_id="asesorA@mail.com"
        )
        df_a = dbm_mem.obtener_clientes_df(tenant_id="asesorA@mail.com")
        nombres_a = df_a["Nombre"].tolist() if not df_a.empty else []
        assert "Maria Lopez Visible" in nombres_a

    def test_tenant_default_no_ve_datos_de_tenant_saas(self, dbm_mem):
        """tenant='default' no ve clientes de tenants SaaS."""
        dbm_mem.registrar_cliente(
            "Cliente Solo SaaS", tenant_id="asesor_saas@mail.com"
        )
        df_def = dbm_mem.obtener_clientes_df(tenant_id="default")
        nombres = df_def["Nombre"].tolist() if not df_def.empty else []
        assert "Cliente Solo SaaS" not in nombres

    def test_multiples_tenants_aislados(self, dbm_mem):
        """Tres tenants diferentes ven solo sus propios clientes."""
        dbm_mem.registrar_cliente("CLI_X1_UNICO", tenant_id="x_unico@mail.com")
        dbm_mem.registrar_cliente("CLI_Y1_UNICO", tenant_id="y_unico@mail.com")
        dbm_mem.registrar_cliente("CLI_Z1_UNICO", tenant_id="z_unico@mail.com")

        df_x = dbm_mem.obtener_clientes_df(tenant_id="x_unico@mail.com")
        df_y = dbm_mem.obtener_clientes_df(tenant_id="y_unico@mail.com")

        nombres_x = df_x["Nombre"].tolist() if not df_x.empty else []
        nombres_y = df_y["Nombre"].tolist() if not df_y.empty else []

        assert "CLI_X1_UNICO" in nombres_x
        assert "CLI_Y1_UNICO" not in nombres_x
        assert "CLI_Y1_UNICO" in nombres_y
        assert "CLI_X1_UNICO" not in nombres_y

    def test_mismo_nombre_dos_tenants_genera_ids_distintos(self, dbm_mem):
        """Dos tenants pueden tener clientes con el mismo nombre — IDs distintos."""
        id_a = dbm_mem.registrar_cliente(
            "Cliente Compartido", tenant_id="tenantA_dup@mail.com"
        )
        id_b = dbm_mem.registrar_cliente(
            "Cliente Compartido", tenant_id="tenantB_dup@mail.com"
        )
        assert isinstance(id_a, int)
        assert isinstance(id_b, int)
        assert id_a != id_b

    def test_mismo_nombre_mismo_tenant_retorna_mismo_id(self, dbm_mem):
        """Registrar el mismo nombre para el mismo tenant retorna el id existente."""
        id1 = dbm_mem.registrar_cliente(
            "Cliente Repetido", tenant_id="tenant_rep@mail.com"
        )
        id2 = dbm_mem.registrar_cliente(
            "Cliente Repetido", tenant_id="tenant_rep@mail.com"
        )
        assert id1 == id2

    def test_df_vacio_para_tenant_sin_clientes(self, dbm_mem):
        """Tenant nuevo sin clientes → DataFrame vacío, no excepción."""
        df = dbm_mem.obtener_clientes_df(tenant_id="nuevo_sin_datos@mail.com")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ─── Tests de auth_saas ────────────────────────────────────────────────────────

class TestAuthSaas:
    def test_importa_sin_error(self):
        from core.auth_saas import get_authenticator, get_tenant_id, login_saas
        assert callable(get_authenticator)
        assert callable(get_tenant_id)
        assert callable(login_saas)

    def test_sin_auth_config_retorna_none(self, monkeypatch):
        """Sin AUTH_CONFIG definida → get_authenticator() retorna None."""
        monkeypatch.delenv("AUTH_CONFIG", raising=False)
        import importlib

        import core.auth_saas as asm
        importlib.reload(asm)
        result = asm.get_authenticator()
        assert result is None

    def test_auth_config_vacia_retorna_none(self, monkeypatch):
        """AUTH_CONFIG vacía → retorna None."""
        monkeypatch.setenv("AUTH_CONFIG", "")
        import importlib

        import core.auth_saas as asm
        importlib.reload(asm)
        result = asm.get_authenticator()
        assert result is None

    def test_auth_config_yaml_invalido_retorna_none(self, monkeypatch):
        """AUTH_CONFIG con YAML inválido → retorna None sin lanzar excepción."""
        monkeypatch.setenv("AUTH_CONFIG", "yaml: {invalido: [sin_cerrar")
        import importlib

        import core.auth_saas as asm
        importlib.reload(asm)
        result = asm.get_authenticator()
        assert result is None

    def test_get_tenant_id_none_retorna_default(self):
        """Con authenticator=None → tenant_id='default'."""
        from core.auth_saas import get_tenant_id
        result = get_tenant_id(None)
        assert result == "default"

    def test_get_tenant_id_nunca_retorna_vacio(self):
        """Invariante: get_tenant_id nunca retorna string vacío."""
        from core.auth_saas import get_tenant_id
        result = get_tenant_id(None)
        assert result != ""
        assert len(result) > 0


# ─── Tests de AppContext con tenant_id ────────────────────────────────────────

class TestAppContextTenantId:
    def test_tenant_id_default_por_defecto(self):
        """AppContext sin parámetro crea tenant_id='default'."""
        from core.app_context import AppContext
        ctx = AppContext()
        assert ctx.tenant_id == "default"

    def test_tenant_id_asignable_en_construccion(self):
        """tenant_id se asigna correctamente en el constructor."""
        from core.app_context import AppContext
        ctx = AppContext(tenant_id="asesor@mail.com")
        assert ctx.tenant_id == "asesor@mail.com"

    def test_tenant_id_accesible_como_dict(self):
        """ctx['tenant_id'] funciona (compatibilidad con código legado)."""
        from core.app_context import AppContext
        ctx = AppContext(tenant_id="test@mail.com")
        assert ctx["tenant_id"] == "test@mail.com"

    def test_tenant_id_en_contains(self):
        """'tenant_id' in ctx funciona."""
        from core.app_context import AppContext
        ctx = AppContext()
        assert "tenant_id" in ctx
