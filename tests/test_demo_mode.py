# tests/test_demo_mode.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


def test_generate_demo_crea_db(tmp_path):
    """El script de demo crea la BD con las tablas mínimas."""
    demo_path = str(tmp_path / "demo_test.db")
    from scripts.generate_demo_data import run
    result = run(demo_path)
    assert Path(result).exists(), "La BD demo debe crearse"
    with sqlite3.connect(result) as cn:
        tablas = {
            r[0]
            for r in cn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "clientes" in tablas, "Debe tener tabla clientes"
    assert "demo_prices" in tablas, "Debe tener tabla demo_prices"


def test_generate_demo_tiene_10_clientes(tmp_path):
    """La BD demo debe tener 10 clientes representativos."""
    demo_path = str(tmp_path / "demo_clientes.db")
    from scripts.generate_demo_data import run
    run(demo_path)
    with sqlite3.connect(demo_path) as cn:
        n = cn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    assert n == 10, f"Debe haber 10 clientes demo, hay {n}"


def test_generate_demo_trans_distintas_carteras(tmp_path):
    """CSV/transacciones deben cubrir varias carteras (smoke integración)."""
    demo_path = str(tmp_path / "demo_trans.db")
    from scripts.generate_demo_data import run
    run(demo_path)
    with sqlite3.connect(demo_path) as cn:
        n = cn.execute("SELECT COUNT(DISTINCT cliente_id) FROM transacciones").fetchone()[0]
    assert n >= 5, f"Esperaba varios clientes con transacciones, distintos={n}"


def test_generate_demo_precios_multiples_tickers(tmp_path):
    """La BD demo debe tener precios sintéticos para una paleta amplia de tickers."""
    demo_path = str(tmp_path / "demo_precios.db")
    from scripts.generate_demo_data import run
    run(demo_path)
    with sqlite3.connect(demo_path) as cn:
        cols = [
            r[1]
            for r in cn.execute("PRAGMA table_info(demo_prices)").fetchall()
        ]
    assert len(cols) >= 12, f"Debe haber columnas de tickers, hay {len(cols)}: {cols}"


def test_config_demo_mode_false_por_defecto():
    """DEMO_MODE debe ser False si la variable de entorno no está definida."""
    os.environ.pop("DEMO_MODE", None)
    import importlib
    import config
    importlib.reload(config)
    assert config.DEMO_MODE is False, "DEMO_MODE debe ser False por defecto"
