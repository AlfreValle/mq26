"""
services/audit_trail.py — Auditoría de órdenes calculadas
MQ2-S9: Persiste cada orden calculada (aunque no ejecutada) para auditoría regulatoria.

Tabla: ordenes_calculadas
    id, tipo, ticker, cantidad, precio_ars, cliente_id, cartera, modelo, timestamp
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _get_engine():
    from core.db_manager import get_engine as _ge
    return _ge()


def _ensure_table() -> None:
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ordenes_calculadas (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo        TEXT,
                ticker      TEXT,
                cantidad    REAL,
                precio_ars  REAL,
                cliente_id  INTEGER,
                cartera     TEXT,
                modelo      TEXT,
                timestamp   TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.commit()


def registrar_orden(
    tipo:       str,
    ticker:     str,
    cantidad:   float,
    precio_ars: float,
    cliente_id: int | None = None,
    cartera:    str = "",
    modelo:     str = "",
) -> int:
    """
    Registra una orden calculada.
    tipo: 'COMPRA' | 'VENTA' | 'REBALANCEO'
    Devuelve el ID del registro.
    """
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO ordenes_calculadas (tipo, ticker, cantidad, precio_ars, cliente_id, cartera, modelo)
            VALUES (:tipo, :tick, :cant, :precio, :cli, :cart, :mod)
        """), {
            "tipo":   tipo.upper(),
            "tick":   ticker.upper(),
            "cant":   cantidad,
            "precio": precio_ars,
            "cli":    cliente_id,
            "cart":   cartera,
            "mod":    modelo,
        })
        conn.commit()
        return result.lastrowid or 0


def listar_ordenes(
    cliente_id: int | None = None,
    cartera:    str | None = None,
    limit:      int = 50,
) -> pd.DataFrame:
    """Devuelve órdenes calculadas como DataFrame."""
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    filtros = []
    params: dict = {"limit": limit}
    if cliente_id:
        filtros.append("cliente_id = :cli")
        params["cli"] = cliente_id
    if cartera:
        filtros.append("cartera = :cart")
        params["cart"] = cartera
    where = "WHERE " + " AND ".join(filtros) if filtros else ""
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, tipo, ticker, cantidad, precio_ars, cartera, modelo, timestamp "
            f"FROM ordenes_calculadas {where} ORDER BY id DESC LIMIT :limit"
        ), params).fetchall()
    if not rows:
        return pd.DataFrame(columns=["id","tipo","ticker","cantidad","precio_ars","cartera","modelo","timestamp"])
    return pd.DataFrame(rows, columns=["id","tipo","ticker","cantidad","precio_ars","cartera","modelo","timestamp"])
