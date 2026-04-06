"""
Comprobaciones de entorno para modo MVP (SQLite local, sin gastos de nube).

Sin Streamlit; vive en ``services`` para no importar ``core`` (evita cargar db_manager al vuelo).
Usado por ``scripts/mvp_preflight.py`` y tests.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

_DEFAULT_SQLITE = Path(__file__).resolve().parent.parent / "0_Data_Maestra" / "master_quant.db"


def run_checks(
    environ: Mapping[str, str] | None = None,
    sqlite_path: Path | None = None,
) -> tuple[list[str], list[str]]:
    """
    Devuelve (errores, advertencias). Errores bloquean un MVP coherente;
    advertencias informan (Postgres opcional, claves débiles, etc.).
    """
    env = dict(os.environ if environ is None else environ)
    err: list[str] = []
    warn: list[str] = []

    pwd = (env.get("MQ26_PASSWORD") or "").strip()
    if len(pwd) < 8:
        err.append(
            "MQ26_PASSWORD: definir en .env con al menos 8 caracteres (acceso a la app)."
        )

    du = (env.get("DATABASE_URL") or "").strip()
    dbu = (env.get("DB_URL") or "").strip()
    if du and dbu and du != dbu:
        warn.append(
            "DATABASE_URL y DB_URL están definidas y difieren; db_manager usa DATABASE_URL primero."
        )

    pg_url = du or dbu
    if pg_url:
        low = pg_url.lower()
        if "postgresql" not in low and "postgres://" not in low:
            warn.append(
                "La URL de BD no parece PostgreSQL; si es intencional, ignorá este aviso."
            )
        if "pooler.supabase.com" in low and ":5432/" in low:
            warn.append(
                "Supabase en pooler suele usar puerto 6543 (transaction mode); revisá la cadena."
            )
    else:
        warn.append(
            "MVP modo SQLite: DATABASE_URL y DB_URL vacíos (correcto para desarrollo sin costo de nube)."
        )

    sp = sqlite_path or _DEFAULT_SQLITE
    if not sp.exists():
        warn.append(
            f"SQLite aún no existe ({sp}); se creará al primer arranque de la app."
        )

    viewer = (env.get("MQ26_VIEWER_PASSWORD") or "").strip()
    investor = (env.get("MQ26_INVESTOR_PASSWORD") or "").strip()
    if viewer and len(viewer) < 8:
        warn.append("MQ26_VIEWER_PASSWORD definida pero muy corta (< 8).")
    if investor and len(investor) < 8:
        warn.append("MQ26_INVESTOR_PASSWORD definida pero muy corta (< 8).")

    return err, warn


def try_postgres_connect(url: str, timeout_s: float = 5.0) -> tuple[bool, str]:
    """Intenta SELECT 1. Devuelve (ok, mensaje)."""
    try:
        from sqlalchemy import create_engine, text
    except ImportError as e:
        return False, f"sqlalchemy no disponible: {e}"
    try:
        eng = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": int(timeout_s)},
        )
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return True, "PostgreSQL responde OK."
    except Exception as e:
        return False, str(e)
