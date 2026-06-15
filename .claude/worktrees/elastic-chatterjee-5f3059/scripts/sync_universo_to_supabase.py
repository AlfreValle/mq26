#!/usr/bin/env python3
"""
Sincroniza el universo CEDEAR desde config.py hacia la tabla ``activos`` en PostgreSQL.

Uso (local o CI):
    export DATABASE_URL="postgresql://..."   # Linux / macOS / Git Bash
    python scripts/sync_universo_to_supabase.py

En Windows (CMD):
    set DATABASE_URL=postgresql://...
    python scripts\\sync_universo_to_supabase.py

En Windows (PowerShell):
    $env:DATABASE_URL = "postgresql://..."
    python scripts\\sync_universo_to_supabase.py

Si ``DATABASE_URL`` no está definida o no es PostgreSQL, sale 0 y no hace nada
(así los forks sin secret no rompen el workflow).

Requisitos: mismas variables que el resto del proyecto (MQ26_PASSWORD opcional para silenciar logs).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _ticker_yf(ticker: str, tipo: str) -> str:
    t = ticker.upper().strip()
    tp = (tipo or "CEDEAR").strip()
    trad = {"BRKB": "BRK-B", "YPFD": "YPF", "PAMP": "PAM", "DISN": "DIS"}
    if tp.upper() in ("ACCION_LOCAL", "ACCION", "ACCIONES") or "LOCAL" in tp.upper():
        return f"{t}.BA"
    return trad.get(t, t)


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or "").strip()
    if not url or "postgresql" not in url.lower():
        print("sync_universo_to_supabase: omitido (sin DATABASE_URL PostgreSQL).")
        return 0

    os.environ.setdefault("MQ26_PASSWORD", "ci_sync_universo")

    from config import RATIOS_CEDEAR, SECTORES, UNIVERSO_BASE  # noqa: E402
    from core.db_manager import Activo, SessionLocal, ensure_schema  # noqa: E402

    ensure_schema()

    tickers = sorted({str(t).upper().strip() for t in UNIVERSO_BASE} | set(RATIOS_CEDEAR.keys()))
    n_ins, n_up = 0, 0

    with SessionLocal() as session:
        for t in tickers:
            if not t:
                continue
            ratio = float(RATIOS_CEDEAR.get(t, 1.0))
            sector = SECTORES.get(t, "Otros")
            tipo = "CEDEAR"
            tyf = _ticker_yf(t, tipo)
            row = session.query(Activo).filter(Activo.ticker_local == t).first()
            if row:
                row.ratio = ratio
                row.sector = sector
                row.tipo = tipo
                row.ticker_yf = tyf
                if not row.nombre:
                    row.nombre = t
                n_up += 1
            else:
                session.add(
                    Activo(
                        tipo=tipo,
                        ticker_local=t,
                        ticker_yf=tyf,
                        nombre=t,
                        ratio=ratio,
                        sector=sector,
                        pais="Estados Unidos",
                        activo=True,
                    )
                )
                n_ins += 1
        session.commit()

    print(f"sync_universo_to_supabase: OK — insertados={n_ins}, actualizados={n_up}, total_tickers={len(tickers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
