"""
services/optimization_jobs.py — Cola de jobs de optimización + versionado de artefactos (Fase 2).

Persistencia SQLite local (`MQ26_OPT_JOBS_DB` o `data/mq26_optimization_jobs.sqlite`).
API REST opcional en `api/optimization_app.py`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.export_lineage import (
    DEFAULT_MODEL_VERSION,
    build_export_manifest,
    sha256_hex,
    stable_json_dumps,
)

_lock = threading.Lock()
_ARTIFACT_ROOT = Path(os.environ.get("MQ26_ARTIFACTS_DIR", "data/artifacts/optimization"))


def _db_path() -> Path:
    env = (os.environ.get("MQ26_OPT_JOBS_DB") or "").strip()
    if env:
        return Path(env)
    root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "mq26_optimization_jobs.sqlite"


def _connect() -> sqlite3.Connection:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS optimization_jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            job_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            result TEXT,
            error TEXT,
            artifact_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def init_schema() -> None:
    with _connect() as c:
        c.execute("SELECT 1 FROM optimization_jobs LIMIT 1")


def submit_job(job_type: str, payload: dict[str, Any]) -> str:
    """Encola job en estado ``pending``. Retorna job_id."""
    jid = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with _lock, _connect() as c:
        c.execute(
            """
            INSERT INTO optimization_jobs
            (id, status, job_type, payload, result, error, artifact_path, created_at, updated_at)
            VALUES (?, 'pending', ?, ?, NULL, NULL, NULL, ?, ?)
            """,
            (jid, job_type, stable_json_dumps(payload), now, now),
        )
        c.commit()
    return jid


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock, _connect() as c:
        cur = c.execute(
            """
            SELECT id, status, job_type, payload, result, error, artifact_path, created_at, updated_at
            FROM optimization_jobs WHERE id = ?
            """,
            (job_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "status": row[1],
        "job_type": row[2],
        "payload": json.loads(row[3]),
        "result": json.loads(row[4]) if row[4] else None,
        "error": row[5],
        "artifact_path": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def _update_job(
    job_id: str,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    artifact_path: str | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    with _lock, _connect() as c:
        c.execute(
            """
            UPDATE optimization_jobs
            SET status = ?, result = ?, error = ?, artifact_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                stable_json_dumps(result) if result is not None else None,
                error,
                artifact_path,
                now,
                job_id,
            ),
        )
        c.commit()


def _write_artifact(job_id: str, obj: dict[str, Any]) -> str:
    _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = _ARTIFACT_ROOT / f"{job_id}.json"
    path.write_text(stable_json_dumps(obj), encoding="utf-8")
    return str(path.resolve())


def process_job_sync(
    job_id: str,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Ejecuta un job en el mismo proceso (worker síncrono).
    ``runner`` recibe payload y devuelve dict resultado; por defecto demo mín-vol sintética.
    """
    from core.otel_tracing import span

    row = get_job(job_id)
    if not row:
        raise ValueError("job not found")
    if row["status"] not in ("pending", "failed"):
        return row

    payload = row["payload"]
    try:
        with span("optimization_job_sync", job_id=job_id, job_type=row["job_type"]):
            if runner is not None:
                result = runner(payload)
            else:
                result = _default_demo_runner(payload)

            manifest = build_export_manifest(
                model_version=payload.get("model_version", DEFAULT_MODEL_VERSION),
                optimization_method=str(payload.get("method", "demo_minimum_variance")),
                inputs_digest=payload.get("inputs_digest", "na"),
                parameters={k: v for k, v in payload.items() if k != "secret"},
                tickers=list(payload.get("tickers", [])),
                tenant_id=payload.get("tenant_id"),
                user_id=payload.get("user_id"),
            )
            bundle = {
                "result": result,
                "manifest": manifest,
            }
            art = _write_artifact(job_id, bundle)
            _update_job(job_id, status="completed", result=bundle, artifact_path=art)
            try:
                from core.rbac_audit import audit_optimization_run

                mh = sha256_hex(stable_json_dumps(manifest).encode("utf-8"))
                audit_optimization_run(
                    job_id=job_id,
                    method=str(payload.get("method", "unknown")),
                    manifest_sha256=mh,
                    usuario=str(payload.get("user_id", "")),
                    tenant_id=payload.get("tenant_id"),
                )
            except Exception:
                pass
    except Exception as e:
        _update_job(job_id, status="failed", error=str(e))
        raise
    return get_job(job_id)  # type: ignore[return-value]


def _default_demo_runner(payload: dict[str, Any]) -> dict[str, Any]:
    """Delega en F01 ``run_optimize`` (misma firma de caché y métricas)."""
    from services.optimization_service import run_optimize

    return run_optimize(payload)


@dataclass
class OptimizationJobWorker:
    """Worker mínimo: procesar jobs pendientes uno a uno (misma máquina)."""

    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def run_one(self, job_id: str) -> dict[str, Any]:
        return process_job_sync(job_id, runner=self.runner)
