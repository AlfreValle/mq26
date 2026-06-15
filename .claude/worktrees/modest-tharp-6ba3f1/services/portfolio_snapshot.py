"""
services/portfolio_snapshot.py — Persistencia de snapshots de cartera optimizada
MQ2-A6: Guarda el estado de cada optimización para comparación histórica entre sesiones.

Tabla: portfolio_snapshots
    id, cliente_id, cartera, modelo, pesos_json, metricas_json, timestamp
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
    """Crea la tabla portfolio_snapshots si no existe."""
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id  INTEGER,
                cartera     TEXT,
                modelo      TEXT,
                pesos_json  TEXT,
                metricas_json TEXT,
                timestamp   TEXT DEFAULT (datetime('now'))
            )
        """))
        conn.commit()


def guardar_snapshot(
    cartera:    str,
    modelo:     str,
    pesos:      dict[str, float],
    metricas:   dict,
    cliente_id: int | None = None,
) -> int:
    """
    Persiste un snapshot de cartera optimizada.
    Devuelve el ID del snapshot creado.
    """
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            INSERT INTO portfolio_snapshots (cliente_id, cartera, modelo, pesos_json, metricas_json)
            VALUES (:cli, :cart, :mod, :pesos, :met)
        """), {
            "cli":   cliente_id,
            "cart":  cartera,
            "mod":   modelo,
            "pesos": json.dumps(pesos, ensure_ascii=False),
            "met":   json.dumps(
                {k: round(float(v), 6) if isinstance(v, (int, float)) else str(v)
                 for k, v in metricas.items()},
                ensure_ascii=False
            ),
        })
        conn.commit()
        return result.lastrowid or 0


def listar_snapshots(
    cartera: str | None = None,
    cliente_id: int | None = None,
    limit: int = 10,
) -> pd.DataFrame:
    """
    Devuelve los últimos N snapshots como DataFrame.
    Columnas: id, cartera, modelo, metricas_json, timestamp
    """
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    filtros = []
    params: dict = {"limit": limit}
    if cartera:
        filtros.append("cartera = :cartera")
        params["cartera"] = cartera
    if cliente_id:
        filtros.append("cliente_id = :cli")
        params["cli"] = cliente_id
    where = "WHERE " + " AND ".join(filtros) if filtros else ""
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, cartera, modelo, metricas_json, pesos_json, timestamp "
            f"FROM portfolio_snapshots {where} ORDER BY id DESC LIMIT :limit"
        ), params).fetchall()
    if not rows:
        return pd.DataFrame(columns=["id","cartera","modelo","metricas","pesos","timestamp"])
    records = []
    for r in rows:
        try:
            met = json.loads(r[3] or "{}")
        except Exception:
            met = {}
        try:
            pes = json.loads(r[4] or "{}")
        except Exception:
            pes = {}
        records.append({
            "id": r[0], "cartera": r[1], "modelo": r[2],
            "metricas": met, "pesos": pes, "timestamp": r[5],
        })
    return pd.DataFrame(records)


def cargar_snapshot(snapshot_id: int) -> dict | None:
    """Carga un snapshot por ID. Devuelve dict con pesos y metricas."""
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT modelo, pesos_json, metricas_json, timestamp FROM portfolio_snapshots WHERE id = :id"
        ), {"id": snapshot_id}).fetchone()
    if not row:
        return None
    return {
        "modelo":    row[0],
        "pesos":     json.loads(row[1] or "{}"),
        "metricas":  json.loads(row[2] or "{}"),
        "timestamp": row[3],
    }


def eliminar_snapshot(snapshot_id: int) -> None:
    _ensure_table()
    from sqlalchemy import text
    engine = _get_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM portfolio_snapshots WHERE id = :id"), {"id": snapshot_id})
        conn.commit()
