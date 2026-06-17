"""Tests Pilar 4 — core/feature_flags.py: flags por tenant (A08)."""
from __future__ import annotations

import pytest

import core.feature_flags as ff


@pytest.fixture()
def store(monkeypatch):
    """BD en memoria: monkeypatch sobre db_manager + cache limpio."""
    datos: dict[str, str] = {}
    eventos: list[dict] = []

    import core.db_manager as dbm

    monkeypatch.setattr(dbm, "obtener_config", lambda clave, default=None: datos.get(clave, default))
    monkeypatch.setattr(dbm, "guardar_config", lambda clave, valor, **k: datos.__setitem__(clave, valor))
    monkeypatch.setattr(
        dbm, "registrar_admin_audit_event",
        lambda event_type, **k: eventos.append({"event": event_type, **k}),
    )
    ff.invalidar_cache()
    yield {"datos": datos, "eventos": eventos}
    ff.invalidar_cache()


class TestGetFlag:
    def test_default_declarado(self, store):
        assert ff.get_flag("plan_explicado") is True
        assert ff.get_flag("byma_first") is False  # env no seteada

    def test_flag_desconocido_false(self, store):
        assert ff.get_flag("no_existe") is False

    def test_override_tenant(self, store):
        store["datos"]["FLAG.estudio1.plan_explicado"] = "false"
        assert ff.get_flag("plan_explicado", "estudio1") is False
        assert ff.get_flag("plan_explicado", "otro_tenant") is True  # aislado

    def test_fallback_a_default_tenant(self, store):
        store["datos"]["FLAG.default.byma_first"] = "true"
        assert ff.get_flag("byma_first", "estudio1") is True  # hereda de default

    def test_override_tenant_gana_sobre_default(self, store):
        store["datos"]["FLAG.default.byma_first"] = "true"
        store["datos"]["FLAG.estudio1.byma_first"] = "false"
        assert ff.get_flag("byma_first", "estudio1") is False

    def test_bd_caida_usa_default(self, store, monkeypatch):
        import core.db_manager as dbm

        def _boom(*a, **k):
            raise RuntimeError("BD caída")

        monkeypatch.setattr(dbm, "obtener_config", _boom)
        ff.invalidar_cache()
        assert ff.get_flag("plan_explicado") is True  # default, sin explotar

    def test_env_default_byma_first(self, store, monkeypatch):
        monkeypatch.setenv("MQ26_BYMA_FIRST", "true")
        ff.invalidar_cache()
        assert ff.get_flag("byma_first") is True


class TestSetFlag:
    def test_set_y_get_roundtrip(self, store):
        assert ff.set_flag("byma_first", True, "estudio1", actor="alfredo")
        assert ff.get_flag("byma_first", "estudio1") is True
        assert store["datos"]["FLAG.estudio1.byma_first"] == "true"

    def test_set_audita(self, store):
        ff.set_flag("plan_explicado", False, "estudio1", actor="alfredo")
        ev = store["eventos"][-1]
        assert ev["event"] == "feature_flag.plan_explicado"
        assert ev["actor"] == "alfredo"
        assert ev["detail"]["nuevo"] is False

    def test_set_desconocido_no_guarda(self, store):
        assert not ff.set_flag("no_existe", True)
        assert not store["datos"]

    def test_set_invalida_cache(self, store):
        assert ff.get_flag("plan_explicado", "t1") is True  # cachea default (sin override)
        ff.set_flag("plan_explicado", False, "t1")
        assert ff.get_flag("plan_explicado", "t1") is False  # sin esperar TTL


class TestCacheTTL:
    def test_lecturas_repetidas_no_pegan_a_bd(self, store, monkeypatch):
        import core.db_manager as dbm

        llamadas = {"n": 0}
        original = dbm.obtener_config

        def _contado(clave, default=None):
            llamadas["n"] += 1
            return original(clave, default)

        monkeypatch.setattr(dbm, "obtener_config", _contado)
        ff.invalidar_cache()
        for _ in range(50):
            ff.get_flag("byma_first")  # camino caliente
        assert llamadas["n"] <= 2  # 1 lectura (+1 si consulta default-tenant)


class TestListarFlags:
    def test_lista_todos_con_estado(self, store):
        store["datos"]["FLAG.estudio1.byma_first"] = "true"
        flags = ff.listar_flags("estudio1")
        por_nombre = {f.nombre: f for f in flags}
        assert set(por_nombre) == set(ff.FLAGS_CONOCIDOS)
        assert por_nombre["byma_first"].valor is True
        assert por_nombre["byma_first"].tiene_override
        assert por_nombre["plan_explicado"].valor is True
        assert not por_nombre["plan_explicado"].tiene_override


class TestIntegracionDataProviders:
    def test_byma_first_activo_respeta_flag(self, store):
        from core.data_providers import byma_first_activo

        assert byma_first_activo("t9") is False
        ff.set_flag("byma_first", True, "default")
        assert byma_first_activo("t9") is True  # hereda del default tenant
