"""
tests/test_db_manager.py — Tests de la capa de base de datos.
Usa BD SQLite en memoria (fixture db_en_memoria de conftest.py).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest


def test_registrar_y_obtener_cliente(db_en_memoria):
    dbm = db_en_memoria
    nid = dbm.registrar_cliente("Juan Perez", "Moderado", 5_000.0, "Persona", "1 año")
    assert nid > 0
    df = dbm.obtener_clientes_df()
    assert not df.empty
    assert "Juan Perez" in df["Nombre"].values


def test_registrar_objetivo(db_en_memoria, cliente_ejemplo):
    dbm = db_en_memoria
    cid = cliente_ejemplo["id"]
    oid = dbm.registrar_objetivo(
        cliente_id=cid,
        ticker="AAPL",
        monto_ars=1_000_000.0,
        plazo_label="1 año",
        target_pct=0.20,
        stop_pct=-0.10,
    )
    assert oid > 0
    df_obj = dbm.obtener_objetivos_cliente(cid)
    assert not df_obj.empty


def test_set_get_config(db_en_memoria):
    dbm = db_en_memoria
    dbm.set_config("test_clave_x", "valor_123")
    v = dbm.get_config("test_clave_x")
    assert v == "valor_123"


def test_registrar_y_obtener_objetivo(db_en_memoria, cliente_ejemplo):
    dbm = db_en_memoria
    cid = cliente_ejemplo["id"]
    oid2 = dbm.registrar_objetivo(
        cliente_id=cid, ticker="MSFT",
        monto_ars=500_000.0, plazo_label="6 meses",
        target_pct=0.15, stop_pct=-0.08,
    )
    assert oid2 > 0
    df_obj = dbm.obtener_objetivos_cliente(cid)
    assert not df_obj.empty


# ─── TestObtenerCliente ───────────────────────────────────────────────────────

class TestObtenerCliente:
    def test_cliente_existente_retorna_dict(self, db_en_memoria):
        dbm = db_en_memoria
        nid = dbm.registrar_cliente("Ana García", "Agresivo", 50_000.0)
        cliente = dbm.obtener_cliente(nid)
        assert isinstance(cliente, dict)
        assert (
            cliente.get("nombre") == "Ana García"
            or cliente.get("Nombre") == "Ana García"
        )

    def test_id_inexistente_retorna_dict_vacio(self, db_en_memoria):
        dbm = db_en_memoria
        result = dbm.obtener_cliente(999_999)
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_campos_esperados_presentes(self, db_en_memoria):
        dbm = db_en_memoria
        nid = dbm.registrar_cliente("Carlos López", "Moderado", 10_000.0)
        cliente = dbm.obtener_cliente(nid)
        assert any(
            k.lower() in ("id", "nombre", "perfil_riesgo")
            for k in (k.lower() for k in cliente.keys())
        )


# ─── TestActualizarCapitalCliente ─────────────────────────────────────────────

class TestActualizarCapitalCliente:
    def test_actualiza_capital(self, db_en_memoria):
        dbm = db_en_memoria
        nid = dbm.registrar_cliente("Test Capital", "Moderado", 5_000.0)
        dbm.actualizar_capital_cliente(nid, 15_000.0)
        cliente = dbm.obtener_cliente(nid)
        capital = float(
            cliente.get("capital_usd")
            or cliente.get("Capital_USD")
            or 0
        )
        assert capital == pytest.approx(15_000.0)

    def test_id_inexistente_no_lanza(self, db_en_memoria):
        dbm = db_en_memoria
        try:
            dbm.actualizar_capital_cliente(999_999, 1_000.0)
        except Exception as e:
            pytest.fail(f"actualizar_capital_cliente lanzó: {e}")


# ─── TestActivos ──────────────────────────────────────────────────────────────

class TestActivos:
    def test_registrar_y_obtener_activo(self, db_en_memoria):
        dbm = db_en_memoria
        aid = dbm.registrar_activo(
            tipo="CEDEAR",
            ticker_local="AAPL_TEST",
            ticker_yf="AAPL",
            nombre="Apple Inc Test",
            ratio=20.0,
            sector="Tecnología",
        )
        assert isinstance(aid, int) and aid > 0

    def test_registrar_activo_idempotente(self, db_en_memoria):
        dbm = db_en_memoria
        id1 = dbm.registrar_activo("CEDEAR", "MSFT_TEST2", "MSFT", "Microsoft Test")
        id2 = dbm.registrar_activo("CEDEAR", "MSFT_TEST2", "MSFT", "Microsoft Test")
        assert id1 == id2

    def test_get_activos_df_retorna_dataframe(self, db_en_memoria):
        dbm = db_en_memoria
        result = dbm.get_activos_df()
        assert isinstance(result, pd.DataFrame)

    def test_get_activo_by_ticker_none_si_no_existe(self, db_en_memoria):
        dbm = db_en_memoria
        result = dbm.get_activo_by_ticker("TICKER_QUE_NO_EXISTE_ZZZ")
        assert result is None


# ─── TestTransacciones ────────────────────────────────────────────────────────

class TestTransacciones:
    def test_registrar_transaccion_no_lanza(self, db_en_memoria):
        dbm = db_en_memoria
        cid = dbm.registrar_cliente("Trans Test User", "Moderado", 10_000.0)
        try:
            dbm.registrar_transaccion(
                cliente_id=cid,
                ticker="AAPL_TX",
                tipo_op="COMPRA",
                nominales=10,
                precio_ars=8.0,
                fecha=str(dt.date.today()),
            )
        except Exception as e:
            pytest.fail(f"registrar_transaccion lanzó: {e}")
        log = dbm.obtener_trade_log(cid)
        assert isinstance(log, pd.DataFrame)

    def test_obtener_trade_log_retorna_dataframe(self, db_en_memoria):
        dbm = db_en_memoria
        cid = dbm.registrar_cliente("TradeLog User", "Moderado", 5_000.0)
        result = dbm.obtener_trade_log(cid)
        assert isinstance(result, pd.DataFrame)

    def test_obtener_portafolio_cliente_retorna_dataframe(self, db_en_memoria):
        dbm = db_en_memoria
        cid = dbm.registrar_cliente("Portfolio User", "Moderado", 5_000.0)
        result = dbm.obtener_portafolio_cliente(cid)
        assert isinstance(result, pd.DataFrame)

    def test_obtener_todos_los_trades_retorna_dataframe(self, db_en_memoria):
        """Invariante: tras un trade, el consolidado global es DataFrame con al menos una fila."""
        dbm = db_en_memoria
        cid = dbm.registrar_cliente("AllTrades_S30", "Moderado", 10_000.0)
        dbm.registrar_transaccion(
            cliente_id=cid,
            ticker="ZZZ_S30_TRADE",
            tipo_op="COMPRA",
            nominales=5,
            precio_ars=100.0,
            fecha=str(dt.date.today()),
        )
        result = dbm.obtener_todos_los_trades()
        assert isinstance(result, pd.DataFrame)
        assert len(result) >= 1


# ─── TestPreciosFallback ──────────────────────────────────────────────────────

class TestPreciosFallback:
    def test_guardar_y_obtener_precio(self, db_en_memoria):
        dbm = db_en_memoria
        dbm.guardar_precio_fallback("AAPL_FB_TEST", 19_000.0, fuente="manual")
        precios = dbm.obtener_precios_fallback()
        assert "AAPL_FB_TEST" in precios
        assert precios["AAPL_FB_TEST"] == pytest.approx(19_000.0)

    def test_actualizar_precio_existente(self, db_en_memoria):
        dbm = db_en_memoria
        dbm.guardar_precio_fallback("KO_FB", 22_000.0)
        dbm.guardar_precio_fallback("KO_FB", 23_500.0)
        precios = dbm.obtener_precios_fallback()
        assert precios.get("KO_FB", 0) == pytest.approx(23_500.0)

    def test_obtener_precios_retorna_dict(self, db_en_memoria):
        dbm = db_en_memoria
        result = dbm.obtener_precios_fallback()
        assert isinstance(result, dict)


# ─── TestAlertaLog ────────────────────────────────────────────────────────────

class TestAlertaLog:
    def test_registrar_alerta_log_no_lanza(self, db_en_memoria):
        dbm = db_en_memoria
        try:
            dbm.registrar_alerta_log(
                tipo_alerta="AUDITORIA",
                mensaje="Test log mensaje",
                ticker="AAPL",
                enviada=False,
            )
        except Exception as e:
            pytest.fail(f"registrar_alerta_log lanzó: {e}")

    def test_info_backend_retorna_dict(self, db_en_memoria):
        dbm = db_en_memoria
        result = dbm.info_backend()
        assert isinstance(result, dict)
        assert "backend" in result

    def test_obtener_alertas_recientes_retorna_dataframe(self, db_en_memoria):
        """Invariante: consulta reciente no falla; resultado tabular."""
        dbm = db_en_memoria
        dbm.registrar_alerta_log(
            tipo_alerta="AUDITORIA",
            mensaje="S30 alertas recientes",
            ticker="KO",
            enviada=False,
        )
        result = dbm.obtener_alertas_recientes(limite=5)
        assert isinstance(result, pd.DataFrame)


# ─── TestActualizarCliente ─────────────────────────────────────────────────────

class TestActualizarCliente:
    """Invariante: actualizar_cliente persiste sin excepción en BD de test."""

    def test_actualizar_campos_sin_excepcion(self, db_en_memoria):
        dbm = db_en_memoria
        nid = dbm.registrar_cliente("Upd_S30", "Conservador", 1_000.0)
        try:
            dbm.actualizar_cliente(
                nid, "Upd_S30", "Agresivo", 8_000.0, "Empresa", "3 años",
            )
        except Exception as e:
            pytest.fail(f"actualizar_cliente lanzó: {e}")

    def test_obtener_cliente_refleja_cambios(self, db_en_memoria):
        dbm = db_en_memoria
        nid = dbm.registrar_cliente("Upd_S30b", "Conservador", 500.0)
        dbm.actualizar_cliente(
            nid, "Upd_S30b", "Agresivo", 8_000.0, "Empresa", "3 años",
        )
        c = dbm.obtener_cliente(nid)
        assert c.get("perfil_riesgo") == "Agresivo"
        assert float(c.get("capital_usd", 0)) == pytest.approx(8_000.0)
        assert c.get("tipo_cliente") == "Empresa"
        assert c.get("horizonte_label") == "3 años"


# ─── TestObjetivosMarcado ─────────────────────────────────────────────────────

class TestObjetivosMarcado:
    """Invariante: operaciones sobre objetivos inexistentes no rompen la sesión."""

    def test_marcar_objetivo_completado_id_inexistente_no_lanza(self, db_en_memoria):
        dbm = db_en_memoria
        try:
            dbm.marcar_objetivo_completado(999_999_903)
        except Exception as e:
            pytest.fail(f"marcar_objetivo_completado lanzó: {e}")

    def test_actualizar_objetivo_id_inexistente_no_lanza(self, db_en_memoria):
        dbm = db_en_memoria
        try:
            dbm.actualizar_objetivo(999_999_904, monto_ars=1.0)
        except Exception as e:
            pytest.fail(f"actualizar_objetivo lanzó: {e}")


def test_registrar_optimization_audit_inserta_alertas_log(db_en_memoria, cliente_ejemplo):
    dbm = db_en_memoria
    cid = cliente_ejemplo["id"]
    dbm.registrar_optimization_audit(
        cliente_id=cid,
        usuario="tester",
        accion="unit_test",
        modelo="Sharpe",
        ccl=1000.0,
        tickers=["GGAL", "YPF"],
        pesos={"GGAL": 0.6, "YPF": 0.4},
        run_id="run_unit",
    )
    df_al = dbm.obtener_alertas_recientes(limite=50)
    assert not df_al.empty
    opt = df_al[df_al["tipo_alerta"] == "OPTIMIZATION_AUDIT"]
    assert not opt.empty
    assert "Sharpe" in str(opt.iloc[0]["mensaje"])
    assert "GGAL" in str(opt.iloc[0]["mensaje"])


def test_version_universo_incrementa_en_update(db_en_memoria):
    dbm = db_en_memoria
    dbm.registrar_activo("CEDEAR", "ZZUVER", "ZZUVER.US", nombre="t", ratio=10.0)
    df0 = dbm.get_activos_df()
    v0 = int(df0.loc[df0["ticker_local"] == "ZZUVER", "universo_version"].iloc[0])
    v1 = dbm.actualizar_activo_universo("ZZUVER", ratio=11.0)
    assert v1 == v0 + 1
    df1 = dbm.get_activos_df()
    assert int(df1.loc[df1["ticker_local"] == "ZZUVER", "universo_version"].iloc[0]) == v1
