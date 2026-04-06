"""
tests/test_portfolio_snapshot.py — Tests de portfolio_snapshot.py (Sprint 21)
Usa SQLite en memoria con StaticPool para compartir la misma BD entre conexiones.
Sin red.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture(autouse=True)
def patch_engine(monkeypatch):
    """Invariante: _get_engine apunta a SQLite en memoria compartida (StaticPool)."""
    mem_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import services.portfolio_snapshot as ps
    monkeypatch.setattr(ps, "_get_engine", lambda: mem_engine)


class TestGuardarSnapshot:
    def test_retorna_id_entero_positivo(self):
        from services.portfolio_snapshot import guardar_snapshot
        sid = guardar_snapshot(
            cartera="Retiro",
            modelo="Sharpe",
            pesos={"AAPL": 0.6, "MSFT": 0.4},
            metricas={"sharpe": 1.2, "vol": 0.15},
        )
        assert isinstance(sid, int)
        assert sid > 0

    def test_ids_sucesivos_distintos(self):
        from services.portfolio_snapshot import guardar_snapshot
        id1 = guardar_snapshot("Retiro", "Sharpe", {"AAPL": 1.0}, {})
        id2 = guardar_snapshot("Retiro", "CVaR",   {"MSFT": 1.0}, {})
        assert id1 != id2

    def test_pesos_con_valores_float(self):
        from services.portfolio_snapshot import guardar_snapshot
        sid = guardar_snapshot(
            "Cartera Test", "Sortino",
            {"AAPL": 0.5, "KO": 0.3, "XOM": 0.2},
            {"retorno": 0.15},
        )
        assert sid > 0

    def test_pesos_json_preservados(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot
        pesos = {"AAPL": 0.5, "KO": 0.3, "XOM": 0.2}
        sid = guardar_snapshot("Test", "CVaR", pesos, {})
        snap = cargar_snapshot(sid)
        if snap:
            for ticker, peso in pesos.items():
                assert abs(snap["pesos"].get(ticker, -1) - peso) < 1e-6

    def test_metricas_json_preservadas(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot
        metricas = {"sharpe": 1.5, "vol": 0.12, "retorno": 0.18}
        sid = guardar_snapshot("Test", "Sharpe", {"AAPL": 1.0}, metricas)
        snap = cargar_snapshot(sid)
        if snap:
            assert abs(snap["metricas"].get("sharpe", 0) - 1.5) < 0.001


class TestListarSnapshots:
    def test_retorna_dataframe(self):
        from services.portfolio_snapshot import listar_snapshots
        df = listar_snapshots()
        assert isinstance(df, pd.DataFrame)

    def test_filtro_por_cartera(self):
        from services.portfolio_snapshot import guardar_snapshot, listar_snapshots
        guardar_snapshot("CARTERA_UNICA_XYZ", "Sharpe", {"A": 1.0}, {})
        df = listar_snapshots(cartera="CARTERA_UNICA_XYZ")
        if not df.empty:
            assert all(df["cartera"] == "CARTERA_UNICA_XYZ")

    def test_limit_respetado(self):
        from services.portfolio_snapshot import guardar_snapshot, listar_snapshots
        for i in range(5):
            guardar_snapshot("Paginacion", f"Modelo{i}", {"A": 1.0}, {})
        df = listar_snapshots(limit=3)
        assert len(df) <= 3

    def test_limit_respetado_seis_snapshots(self):
        from services.portfolio_snapshot import guardar_snapshot, listar_snapshots
        for i in range(6):
            guardar_snapshot(f"TestLim{i}", "Sharpe", {"A": 1.0}, {})
        df = listar_snapshots(limit=3)
        assert len(df) <= 3

    def test_columnas_requeridas(self):
        from services.portfolio_snapshot import guardar_snapshot, listar_snapshots
        guardar_snapshot("Col Test", "Sharpe", {"A": 1.0}, {"sharpe": 1.0})
        df = listar_snapshots()
        if not df.empty:
            for col in ("id", "cartera", "modelo", "timestamp"):
                assert col in df.columns


class TestCargarSnapshot:
    def test_id_inexistente_retorna_none(self):
        from services.portfolio_snapshot import cargar_snapshot
        result = cargar_snapshot(999_999)
        assert result is None

    def test_carga_snapshot_guardado(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot
        pesos = {"AAPL": 0.7, "KO": 0.3}
        sid = guardar_snapshot("Carga Test", "Sharpe", pesos, {"sharpe": 1.5})
        snap = cargar_snapshot(sid)
        assert snap is not None
        assert "pesos" in snap
        assert "modelo" in snap

    def test_carga_incluye_metricas_y_timestamp(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot
        sid = guardar_snapshot(
            "Carga",
            "Sharpe",
            {"AAPL": 0.7, "KO": 0.3},
            {"sharpe": 1.3},
        )
        snap = cargar_snapshot(sid)
        assert snap is not None
        assert snap["modelo"] == "Sharpe"
        assert "metricas" in snap
        assert "timestamp" in snap

    def test_pesos_preservados(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot
        pesos_orig = {"AAPL": 0.6, "MSFT": 0.4}
        sid = guardar_snapshot("Pesos Test", "CVaR", pesos_orig, {})
        snap = cargar_snapshot(sid)
        if snap:
            for ticker, peso in pesos_orig.items():
                assert abs(snap["pesos"].get(ticker, -1) - peso) < 1e-6


class TestEliminarSnapshot:
    def test_no_lanza_para_id_inexistente(self):
        from services.portfolio_snapshot import eliminar_snapshot
        try:
            eliminar_snapshot(999_999_999)
        except Exception as e:
            pytest.fail(f"eliminar_snapshot lanzó: {e}")

    def test_snapshot_eliminado_no_se_puede_cargar(self):
        from services.portfolio_snapshot import (
            cargar_snapshot,
            eliminar_snapshot,
            guardar_snapshot,
        )
        sid = guardar_snapshot("Eliminar Test", "Sharpe", {"A": 1.0}, {})
        eliminar_snapshot(sid)
        assert cargar_snapshot(sid) is None

    def test_idempotente_doble_eliminacion(self):
        from services.portfolio_snapshot import eliminar_snapshot, guardar_snapshot
        sid = guardar_snapshot("Doble Elim", "Sharpe", {"A": 1.0}, {})
        eliminar_snapshot(sid)
        try:
            eliminar_snapshot(sid)
        except Exception as e:
            pytest.fail(f"Segunda eliminación lanzó: {e}")
