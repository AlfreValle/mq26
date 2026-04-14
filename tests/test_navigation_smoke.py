"""Smoke: mapa de navegación y contexto sin levantar Streamlit."""
from __future__ import annotations

from core.context_builder import ContextBuilder, finalize_ctx
from ui.navigation import get_main_tabs


def test_get_main_tabs_mq26_inversor_single():
    specs = get_main_tabs("mq26", "inversor")
    assert len(specs) == 1
    assert specs[0].tab_id == "mi_cartera"


def test_get_main_tabs_mq26_estudio_four():
    specs = get_main_tabs("mq26", "estudio")
    assert len(specs) == 4
    ids = [s.tab_id for s in specs]
    assert ids == ["estudio", "cartera", "reporte", "universo"]


def test_get_main_tabs_mq26_super_admin_seven():
    specs = get_main_tabs("mq26", "super_admin")
    assert len(specs) == 7
    assert specs[-1].tab_id == "admin"


def test_get_main_tabs_app_inversor_four_distinct_order():
    specs = get_main_tabs("app", "inversor")
    assert len(specs) == 4
    assert [s.tab_id for s in specs] == ["cartera", "como_va", "ejecucion", "reporte"]


def test_get_main_tabs_app_institutional_six_no_admin():
    specs = get_main_tabs("app", "estudio")
    assert len(specs) == 6
    assert all(s.tab_id != "admin" for s in specs)


def test_finalize_ctx_tenant_from_env(monkeypatch):
    monkeypatch.setenv("MQ26_DB_TENANT_ID", "acme")
    ctx = finalize_ctx({"user_role": "inversor"})
    assert ctx["tenant_id"] == "acme"
    assert ctx["metricas"] == {}


def test_context_builder_chain():
    b = ContextBuilder({"foo": 1}).with_defaults()
    out = b.build()
    assert out["foo"] == 1
    assert "tenant_id" in out
