#!/usr/bin/env python3
"""
Copia de seguridad de master_quant.db (modo MVP / SQLite).

Crea 0_Data_Maestra/backups/master_quant_YYYYMMDD_HHMMSS.db

Uso:
    python scripts/backup_sqlite_mvp.py
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "0_Data_Maestra" / "master_quant.db"
BACKUP_DIR = ROOT / "0_Data_Maestra" / "backups"


def main() -> int:
    if not DB.is_file():
        print(f"No existe {DB}; no hay nada que respaldar (primer arranque aún no creó la BD).")
        return 1
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"master_quant_{stamp}.db"
    shutil.copy2(DB, dest)
    print(f"Backup OK -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
