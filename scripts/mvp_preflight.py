#!/usr/bin/env python3
"""
Verifica que el entorno esté listo para un MVP sólido (SQLite local, contraseñas).

Uso (desde la raíz del repo):
    python scripts/mvp_preflight.py
    python scripts/mvp_preflight.py --try-postgres   # si DATABASE_URL está definida
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="MQ26 MVP — comprobaciones de entorno")
    parser.add_argument(
        "--try-postgres",
        action="store_true",
        help="Probar conexión si DATABASE_URL o DB_URL es PostgreSQL",
    )
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]

    env_path = ROOT / ".env"
    if load_dotenv and env_path.is_file():
        load_dotenv(env_path)

    from services.mvp_preflight import run_checks, try_postgres_connect

    errors, warnings = run_checks()

    for w in warnings:
        print(f"[aviso] {w}")
    for e in errors:
        print(f"[error] {e}")

    if args.try_postgres:
        import os

        url = (os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or "").strip()
        if not url or "postgresql" not in url.lower():
            print("[aviso] --try-postgres omitido (sin URL PostgreSQL en entorno).")
        else:
            ok, msg = try_postgres_connect(url)
            tag = "[ok]" if ok else "[error]"
            print(f"{tag} Postgres: {msg}")
            if not ok:
                errors.append(msg)

    if errors:
        print("\nCorregí los [error] y volvé a ejecutar este script.")
        return 1
    print("\nPreflight MVP: sin errores bloqueantes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
