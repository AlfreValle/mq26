"""
tests/conftest.py — Fixtures compartidos entre todos los tests.
Usa SQLite en memoria para no tocar la BD de producción.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Asegurar que el directorio raíz esté en el path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "core") not in sys.path:
    sys.path.insert(0, str(ROOT / "core"))
if str(ROOT / "services") not in sys.path:
    sys.path.insert(0, str(ROOT / "services"))

# Inyectar variables de entorno de test ANTES de que pytest importe los módulos.
# config.py advierte si falta MQ26_PASSWORD; los tests fijan una por defecto.
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")
os.environ.setdefault("SQLITE_PATH", ":memory:")

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_en_memoria():
    """BD SQLite en memoria — aislada por sesión de tests, no toca master_quant.db."""
    os.environ["SQLITE_PATH"] = ":memory:"

    # Reinicializar engine con :memory:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import core.db_manager as dbm
    test_engine = create_engine("sqlite:///:memory:", echo=False)
    dbm.Base.metadata.create_all(bind=test_engine)
    _orig_session = dbm.SessionLocal
    dbm.SessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    dbm.engine = test_engine

    yield dbm

    # Restaurar
    dbm.SessionLocal = _orig_session


@pytest.fixture
def df_cartera_ejemplo() -> pd.DataFrame:
    """DataFrame de cartera de ejemplo con 4 CEDEARs.
    Columnas en el formato que espera calcular_posicion_neta().
    """
    return pd.DataFrame({
        "TICKER":            ["AAPL", "MSFT",   "COST",   "KO"],
        "CANTIDAD_TOTAL":    [10.0,   5.0,      2.0,      20.0],
        "PPC_USD_PROM":      [8.0,    10.0,     12.5,     4.4],
        "INV_USD_TOTAL":     [80.0,   50.0,     25.0,     88.0],
        "INV_ARS_HISTORICO": [120_000, 75_000,  37_500,   66_000],
        "TIPO":              ["CEDEAR", "CEDEAR", "CEDEAR", "CEDEAR"],
        "ES_LOCAL":          [False,   False,    False,    False],
        "CARTERA":           ["Test | Retiro"] * 4,
    })


@pytest.fixture
def precios_mock() -> dict[str, float]:
    """Precios ARS mock para tests (sin llamadas a yfinance)."""
    return {
        "AAPL": 19_000.0,
        "MSFT": 19_000.0,
        "COST": 31_000.0,
        "KO":   23_000.0,
    }


@pytest.fixture
def cliente_ejemplo(db_en_memoria) -> dict:
    """Crea y devuelve un cliente de ejemplo en la BD de test."""
    dbm = db_en_memoria
    nid = dbm.registrar_cliente("Test Usuario", "Moderado", 10_000.0, "Persona", "1 año")
    return {"id": nid, "nombre": "Test Usuario", "perfil": "Moderado"}


