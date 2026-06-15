"""
E07 — Estados borrador → revisión → publicado (SQLite, patrón jobs).

Tabla ligera para carteras/modelos versionados sin acoplar Streamlit.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_lock = threading.Lock()

VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("review",),
    "review": ("published", "draft"),
    "published": (),
}


def _db_path() -> Path:
    env = (os.environ.get("MQ26_WORKFLOW_DB") or "").strip()
    if env:
        return Path(env)
    root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "mq26_workflow.sqlite"


def _connect() -> sqlite3.Connection:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_entities (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            state TEXT NOT NULL,
            payload TEXT NOT NULL,
            user_role TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def init_workflow_schema() -> None:
    with _connect() as c:
        c.execute("SELECT 1 FROM workflow_entities LIMIT 1")


def create_entity(kind: str, payload: dict[str, Any], *, user_role: str | None = None) -> str:
    eid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    import json

    with _lock, _connect() as c:
        c.execute(
            """
            INSERT INTO workflow_entities (id, kind, state, payload, user_role, updated_at)
            VALUES (?, ?, 'draft', ?, ?, ?)
            """,
            (eid, kind, json.dumps(payload, sort_keys=True), user_role, now),
        )
        c.commit()
    return eid


def transition_state(entity_id: str, new_state: str) -> dict[str, Any] | None:
    import json

    with _lock, _connect() as c:
        cur = c.execute(
            "SELECT state, payload FROM workflow_entities WHERE id = ?",
            (entity_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        old, payload_s = row[0], row[1]
        allowed = VALID_TRANSITIONS.get(old, ())
        if new_state not in allowed:
            raise ValueError(f"transición inválida: {old} -> {new_state}")
        now = datetime.now(UTC).isoformat()
        c.execute(
            "UPDATE workflow_entities SET state = ?, updated_at = ? WHERE id = ?",
            (new_state, now, entity_id),
        )
        c.commit()
    return {"id": entity_id, "state": new_state, "payload": json.loads(payload_s)}


def get_entity(entity_id: str) -> dict[str, Any] | None:
    import json

    with _lock, _connect() as c:
        cur = c.execute(
            "SELECT id, kind, state, payload, user_role, updated_at FROM workflow_entities WHERE id = ?",
            (entity_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "kind": row[1],
        "state": row[2],
        "payload": json.loads(row[3]),
        "user_role": row[4],
        "updated_at": row[5],
    }
