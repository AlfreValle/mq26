"""
services/audit_trail.py — Auditoría de órdenes calculadas
MQ2-S9: Persiste cada orden calculada (aunque no ejecutada) para auditoría regulatoria.

Tabla: ordenes_calculadas
    id, tipo, ticker, cantidad, precio_ars, cliente_id, cartera, modelo, timestamp
"""
from __future__ import annotations

import json
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
                tenant_id   TEXT,
                actor       TEXT,
                correlation_id TEXT,
                cartera     TEXT,
                modelo      TEXT,
                timestamp   TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recomendaciones_auditoria (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                evento        TEXT NOT NULL,
                origen        TEXT,
                cliente_id    INTEGER,
                cliente_nombre TEXT,
                tenant_id     TEXT,
                actor         TEXT,
                correlation_id TEXT,
                cartera       TEXT,
                perfil        TEXT,
                capital_ars   REAL,
                filas         INTEGER,
                payload_json  TEXT,
                timestamp     TEXT DEFAULT (datetime('now'))
            )
        """))
        # Migración ligera para tablas existentes (SQLite tolera errores con try/except).
        for ddl in (
            "ALTER TABLE ordenes_calculadas ADD COLUMN tenant_id TEXT",
            "ALTER TABLE ordenes_calculadas ADD COLUMN actor TEXT",
            "ALTER TABLE ordenes_calculadas ADD COLUMN correlation_id TEXT",
            "ALTER TABLE recomendaciones_auditoria ADD COLUMN tenant_id TEXT",
            "ALTER TABLE recomendaciones_auditoria ADD COLUMN actor TEXT",
            "ALTER TABLE recomendaciones_auditoria ADD COLUMN correlation_id TEXT",
        ):
            try:
                conn.execute(text(ddl))
            except Exception:
                pass
        conn.commit()


def registrar_orden(
    tipo:       str,
    ticker:     str,
    cantidad:   float,
    precio_ars: float,
    cliente_id: int | None = None,
    tenant_id: str = "default",
    actor: str = "",
    correlation_id: str = "",
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
            INSERT INTO ordenes_calculadas
            (tipo, ticker, cantidad, precio_ars, cliente_id, tenant_id, actor, correlation_id, cartera, modelo)
            VALUES
            (:tipo, :tick, :cant, :precio, :cli, :tid, :actor, :corr, :cart, :mod)
        """), {
            "tipo":   tipo.upper(),
            "tick":   ticker.upper(),
            "cant":   cantidad,
            "precio": precio_ars,
            "cli":    cliente_id,
            "tid":    str(tenant_id or "default"),
            "actor":  str(actor or ""),
            "corr":   str(correlation_id or ""),
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


def registrar_recomendacion_evento(
    evento: str,
    origen: str,
    cliente_id: int | None = None,
    cliente_nombre: str = "",
    tenant_id: str = "default",
    actor: str = "",
    correlation_id: str = "",
    cartera: str = "",
    perfil: str = "",
    capital_ars: float = 0.0,
    filas: int = 0,
    payload: dict | None = None,
) -> int:
    """
    Auditoría explícita de recomendaciones:
    - SIMULACION_RECOMENDACION
    - EJECUCION_CONFIRMADA
    """
    _ensure_table()
    from sqlalchemy import text

    engine = _get_engine()
    payload_json = json.dumps(payload or {}, ensure_ascii=True, default=str)
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO recomendaciones_auditoria
                (
                    evento, origen, cliente_id, cliente_nombre, tenant_id, actor, correlation_id,
                    cartera, perfil, capital_ars, filas, payload_json
                )
                VALUES
                (
                    :evento, :origen, :cliente_id, :cliente_nombre, :tenant_id, :actor, :correlation_id,
                    :cartera, :perfil, :capital_ars, :filas, :payload_json
                )
            """),
            {
                "evento": str(evento or "").strip().upper(),
                "origen": str(origen or "").strip(),
                "cliente_id": cliente_id,
                "cliente_nombre": str(cliente_nombre or "").strip(),
                "tenant_id": str(tenant_id or "default").strip() or "default",
                "actor": str(actor or "").strip(),
                "correlation_id": str(correlation_id or "").strip(),
                "cartera": str(cartera or "").strip(),
                "perfil": str(perfil or "").strip(),
                "capital_ars": float(capital_ars or 0.0),
                "filas": int(filas or 0),
                "payload_json": payload_json,
            },
        )
        conn.commit()
        return result.lastrowid or 0
