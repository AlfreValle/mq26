"""Tests Pilar 3 sprint 3 — lectura del audit trail de recomendaciones."""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import create_engine

import services.audit_trail as at


@pytest.fixture()
def engine_tmp(monkeypatch, tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'audit_test.db'}")
    monkeypatch.setattr(at, "_get_engine", lambda: eng)
    return eng


class TestListarRecomendaciones:
    def test_vacio_devuelve_df_con_columnas(self, engine_tmp):
        df = at.listar_recomendaciones()
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert "evento" in df.columns and "perfil" in df.columns

    def test_roundtrip_registro_listado_payload(self, engine_tmp):
        rid = at.registrar_recomendacion_evento(
            evento="PLAN_ACCION_EXPLICADO",
            origen="test",
            cliente_id=1,
            cliente_nombre="Cliente Test",
            tenant_id="default",
            actor="alfredo",
            correlation_id="corr-1",
            cartera="Test | Principal",
            perfil="Moderado",
            capital_ars=100_000.0,
            filas=2,
            payload={"comprar": [{"ticker": "AAPL", "motivos": [{"texto": "x", "origen": "motor_capital"}]}]},
        )
        assert rid > 0
        df = at.listar_recomendaciones(evento="PLAN_ACCION_EXPLICADO")
        assert len(df) == 1
        assert df.iloc[0]["cliente_nombre"] == "Cliente Test"
        payload = at.obtener_payload_recomendacion(int(df.iloc[0]["id"]))
        assert payload["comprar"][0]["ticker"] == "AAPL"
        assert payload["comprar"][0]["motivos"]

    def test_filtro_evento_excluye_otros(self, engine_tmp):
        at.registrar_recomendacion_evento(
            evento="SIMULACION_RECOMENDACION", origen="t", cliente_id=None,
            cliente_nombre="", tenant_id="default", actor="", correlation_id="",
            cartera="", perfil="Moderado", capital_ars=0.0, filas=0, payload={},
        )
        assert at.listar_recomendaciones(evento="PLAN_ACCION_EXPLICADO").empty
        assert len(at.listar_recomendaciones()) == 1

    def test_payload_inexistente_none(self, engine_tmp):
        assert at.obtener_payload_recomendacion(99_999) is None
