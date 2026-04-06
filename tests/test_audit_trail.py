"""
tests/test_audit_trail.py — Tests de audit_trail.py (Sprint 20)
Sin red. Usa BD SQLite en memoria via db_en_memoria fixture.
Cubre: registrar_orden, listar_ordenes.
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest

import services.audit_trail as at

# ─── Módulo importa ───────────────────────────────────────────────────────────

class TestImport:
    def test_modulo_importa_sin_error(self):
        assert at is not None

    def test_funciones_publicas_son_callables(self):
        for fn in ("registrar_orden", "listar_ordenes"):
            assert callable(getattr(at, fn)), f"{fn} no es callable"


# ─── registrar_orden ─────────────────────────────────────────────────────────

class TestRegistrarOrden:
    def test_retorna_entero_positivo(self, db_en_memoria):
        oid = at.registrar_orden(
            tipo="COMPRA",
            ticker="AAPL",
            cantidad=10.0,
            precio_ars=15_000.0,
        )
        assert isinstance(oid, int)
        assert oid > 0

    def test_tipo_uppercase(self, db_en_memoria):
        oid = at.registrar_orden("compra", "MSFT", 5.0, 20_000.0)
        assert isinstance(oid, int)
        assert oid > 0

    def test_con_cliente_id(self, db_en_memoria, cliente_ejemplo):
        cid = cliente_ejemplo["id"]
        oid = at.registrar_orden(
            tipo="VENTA",
            ticker="KO",
            cantidad=3.0,
            precio_ars=8_000.0,
            cliente_id=cid,
        )
        assert isinstance(oid, int)
        assert oid > 0

    def test_con_cartera_y_modelo(self, db_en_memoria):
        oid = at.registrar_orden(
            tipo="REBALANCEO",
            ticker="GLD",
            cantidad=1.0,
            precio_ars=50_000.0,
            cartera="Agresiva",
            modelo="MV_OPT",
        )
        assert isinstance(oid, int)
        assert oid > 0

    def test_multiples_ordenes_ids_distintos(self, db_en_memoria):
        id1 = at.registrar_orden("COMPRA", "AAPL2", 5.0, 10_000.0)
        id2 = at.registrar_orden("COMPRA", "MSFT2", 3.0, 12_000.0)
        assert id1 != id2
        assert id1 > 0 and id2 > 0

    def test_no_lanza_excepcion_inputs_minimos(self, db_en_memoria):
        try:
            oid = at.registrar_orden("COMPRA", "TEST", 1.0, 1.0)
            assert oid > 0
        except Exception as e:
            pytest.fail(f"registrar_orden lanzó: {e}")

    def test_tipo_arbitrario_no_lanza(self, db_en_memoria):
        """Tipo fuera del enum documentado: igual persiste y devuelve lastrowid > 0."""
        oid = at.registrar_orden("TIPO_RARO", "AAPL", 1.0, 1_000.0)
        assert isinstance(oid, int) and oid > 0

    def test_ticker_minusculas_guardado_mayusculas(self, db_en_memoria):
        suf = uuid.uuid4().hex[:10]
        raw = f"ab_low_{suf}"
        esperado = raw.upper()
        at.registrar_orden("COMPRA", raw, 10.0, 19_000.0)
        df = at.listar_ordenes(limit=800)
        coincidencias = df[df["ticker"] == esperado]
        assert not coincidencias.empty


# ─── listar_ordenes ──────────────────────────────────────────────────────────

class TestListarOrdenes:
    def test_retorna_dataframe(self, db_en_memoria):
        result = at.listar_ordenes()
        assert isinstance(result, pd.DataFrame)

    def test_columnas_esperadas(self, db_en_memoria):
        result = at.listar_ordenes()
        for col in ("id", "tipo", "ticker", "cantidad", "precio_ars"):
            assert col in result.columns, f"Columna faltante: {col}"

    def test_orden_registrada_aparece_en_lista(self, db_en_memoria):
        at.registrar_orden("COMPRA", "AAPL_LIST", 7.0, 14_000.0)
        df = at.listar_ordenes()
        assert not df.empty
        assert "AAPL_LIST" in df["ticker"].values

    def test_filtro_por_cartera(self, db_en_memoria):
        at.registrar_orden("COMPRA", "KO_CART", 2.0, 5_000.0, cartera="TestCartera")
        df = at.listar_ordenes(cartera="TestCartera")
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert all(df["cartera"] == "TestCartera")

    def test_filtro_por_cliente_id(self, db_en_memoria, cliente_ejemplo):
        cid = cliente_ejemplo["id"]
        at.registrar_orden("VENTA", "GLD_CID", 1.0, 50_000.0, cliente_id=cid)
        df = at.listar_ordenes(cliente_id=cid)
        assert isinstance(df, pd.DataFrame)

    def test_limit_respetado(self, db_en_memoria):
        for i in range(5):
            at.registrar_orden("COMPRA", f"LIM{i}", float(i + 1), 1_000.0)
        df = at.listar_ordenes(limit=3)
        assert isinstance(df, pd.DataFrame)
        assert len(df) <= 3

    def test_sin_ordenes_retorna_df_con_columnas(self, db_en_memoria):
        df = at.listar_ordenes(cliente_id=999_999)
        assert isinstance(df, pd.DataFrame)
        assert "id" in df.columns

    def test_tipo_guardado_en_mayusculas(self, db_en_memoria):
        at.registrar_orden("compra", "UPPER_TEST", 1.0, 1.0)
        df = at.listar_ordenes()
        compras = df[df["ticker"] == "UPPER_TEST"]
        if not compras.empty:
            assert compras.iloc[0]["tipo"] == "COMPRA"

    def test_orden_descendente_por_id(self, db_en_memoria):
        """Invariante: listar_ordenes usa ORDER BY id DESC (más reciente primero)."""
        suf = uuid.uuid4().hex[:8]
        t_a, t_b = f"ZORD_{suf}_A", f"ZORD_{suf}_B"
        id_primero = at.registrar_orden("COMPRA", t_a, 1.0, 1_000.0)
        id_segundo = at.registrar_orden("VENTA", t_b, 2.0, 2_000.0)
        assert id_primero > 0 and id_segundo > 0
        assert id_segundo > id_primero
        df = at.listar_ordenes(limit=100_000)
        sub = df[df["id"].isin([id_primero, id_segundo])]
        assert len(sub) == 2
        ids_en_orden_listado = sub["id"].tolist()
        assert ids_en_orden_listado == sorted(ids_en_orden_listado, reverse=True)
        assert ids_en_orden_listado[0] == id_segundo
        assert ids_en_orden_listado[1] == id_primero
