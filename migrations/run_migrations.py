"""
migrations/run_migrations.py — Aplica migraciones Alembic a la BD configurada.

Uso:
    python migrations/run_migrations.py             # aplica hasta head
    python migrations/run_migrations.py --check     # verifica sin aplicar
    python migrations/run_migrations.py --history   # muestra historial

Seguro para ejecutar múltiples veces (idempotente).
Requiere que DATABASE_URL o SQLITE_PATH estén definidas en el entorno.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Asegurar que el root del proyecto está en el path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# MQ26_PASSWORD es requerida por config.py al importarse
os.environ.setdefault("MQ26_PASSWORD", "migration_runner")


def main() -> int:
    from alembic import command
    from alembic.config import Config

    ini_path = ROOT / "alembic.ini"
    if not ini_path.exists():
        print(f"ERROR: alembic.ini no encontrado en {ini_path}", file=sys.stderr)
        return 1

    alembic_cfg = Config(str(ini_path))
    args = sys.argv[1:]

    if "--history" in args:
        print("=== Historial de migraciones ===")
        command.history(alembic_cfg, verbose=True)
        return 0

    if "--check" in args:
        print("=== Verificando migraciones pendientes ===")
        try:
            command.check(alembic_cfg)
            print("OK: BD al día con las migraciones.")
            return 0
        except Exception as e:
            print(f"Hay migraciones pendientes: {e}")
            return 1

    # Aplicar todas las migraciones hasta head
    print("=== Aplicando migraciones hasta head ===")
    try:
        command.upgrade(alembic_cfg, "head")
        print("OK: Migraciones aplicadas correctamente.")
        return 0
    except Exception as e:
        print(f"ERROR al aplicar migraciones: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
