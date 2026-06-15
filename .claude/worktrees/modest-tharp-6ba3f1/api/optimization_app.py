"""
API interna de jobs de optimización (FastAPI).

Ejecutar (con dependencias opcionales instaladas):
    pip install -e ".[api]"
    uvicorn api.optimization_app:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from services import optimization_jobs as jobs

app = FastAPI(title="MQ26 Optimization Jobs", version="0.2.0")


class JobCreate(BaseModel):
    job_type: str = "default"
    payload: dict = {}


class OptimizeSyncBody(BaseModel):
    """F06 — cuerpo síncrono de optimización (serializable)."""

    tickers: list[str] = Field(default_factory=list)
    mu: list[float] | None = None
    Sigma: list[list[float]] | None = None
    rf: float = 0.0
    long_only: bool = True
    method: str = "minimum_variance"


@app.post("/jobs/optimization")
def create_optimization_job(body: JobCreate):
    jid = jobs.submit_job(body.job_type, body.payload)
    return {"job_id": jid, "status": "pending"}


@app.post("/jobs/optimization/{job_id}/run")
def run_optimization_job(job_id: str):
    try:
        jobs.process_job_sync(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="job not found") from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@app.get("/jobs/optimization/{job_id}")
def get_optimization_job(job_id: str):
    j = jobs.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@app.get("/health")
def health():
    from services.latency_metrics import snapshot

    return {
        "status": "ok",
        "service": "mq26-optimization-jobs",
        "latency_ms": snapshot(),
    }


@app.post("/optimize")
def optimize_sync(body: OptimizeSyncBody):
    """F06 — optimización síncrona mínima varianza (sin cola)."""
    from services.latency_metrics import measure
    from services.optimization_service import run_optimize

    payload = body.model_dump(exclude_none=True)
    with measure("optimize_sync_ms"):
        out = run_optimize(payload)
    if out.get("error"):
        raise HTTPException(status_code=400, detail=out["error"])
    return out
