"""
api/healthcheck.py — Endpoint de salud para Railway / Docker / load-balancers.

#100 Performance & Reliability: expone GET /health con estado de dependencias críticas.

Uso standalone (fuera de Streamlit):
    uvicorn api.healthcheck:app --port 8080

O desde run_mq26.py via threading (opcional):
    from api.healthcheck import start_health_server
    start_health_server(port=8080)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_LOG = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent
_TRANSAC_PATH = _BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
_SQLITE_PATH  = _BASE_DIR / "0_Data_Maestra" / "master_quant.db"

_START_TIME = time.time()


def _build_status() -> dict:
    """Construye el payload de salud."""
    checks: dict[str, dict] = {}

    # CSV transaccional
    if _TRANSAC_PATH.exists():
        age_s = time.time() - _TRANSAC_PATH.stat().st_mtime
        checks["transaccional_csv"] = {
            "ok": True,
            "age_minutes": round(age_s / 60, 1),
        }
    else:
        checks["transaccional_csv"] = {"ok": False, "error": "archivo no encontrado"}

    # SQLite / PostgreSQL
    _db_url = os.environ.get("DATABASE_URL", "")
    if _db_url.startswith("postgresql"):
        try:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(_db_url, connect_timeout=3)
            conn.close()
            checks["database"] = {"ok": True, "backend": "postgresql"}
        except Exception as exc:
            _LOG.warning("healthcheck postgres falló: %s", exc)
            checks["database"] = {"ok": False, "backend": "postgresql"}
    elif _SQLITE_PATH.exists():
        checks["database"] = {"ok": True, "backend": "sqlite"}
    else:
        checks["database"] = {"ok": False, "backend": "sqlite", "error": "db no encontrada"}

    # Uptime
    uptime_s = int(time.time() - _START_TIME)

    overall_ok = all(v.get("ok", False) for v in checks.values())
    return {
        "status": "ok" if overall_ok else "degraded",
        "uptime_seconds": uptime_s,
        "version": os.environ.get("MQ26_VERSION", "v10"),
        "env": os.environ.get("RAILWAY_ENVIRONMENT", "local"),
        "checks": checks,
    }


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/health", "/", "/healthz"):
            self.send_response(404)
            self.end_headers()
            return

        payload = _build_status()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_code = 200 if payload["status"] == "ok" else 503
        self.send_response(http_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:  # silencia logs de acceso en prod
        pass


def start_health_server(port: int | None = None) -> threading.Thread:
    """
    Arranca el servidor HTTP de salud en un daemon thread.
    El puerto se lee de MQ26_HEALTH_PORT (default 8080).
    Retorna el thread para que el caller pueda ignorarlo o unirlo.
    """
    _port = port or int(os.environ.get("MQ26_HEALTH_PORT", "8080"))

    def _serve() -> None:
        server = HTTPServer(("0.0.0.0", _port), _HealthHandler)
        server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True, name="mq26-health")
    t.start()
    return t


# ── FastAPI opcional (si uvicorn/fastapi disponibles) ────────────────────────
try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="MQ26 Health", docs_url=None, redoc_url=None)

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> JSONResponse:
        payload = _build_status()
        code = 200 if payload["status"] == "ok" else 503
        return JSONResponse(content=payload, status_code=code)

except ImportError:
    app = None  # type: ignore


if __name__ == "__main__":
    import sys

    _p = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"[MQ26 health] escuchando en :{_p}")
    server = HTTPServer(("0.0.0.0", _p), _HealthHandler)
    server.serve_forever()
