#!/usr/bin/env python3
"""
Genera un Excel de universo CEDEAR desde config.py (RATIOS_CEDEAR, UNIVERSO_BASE, SECTORES).

Uso local:
    python scripts/build_universo_artifact.py

Salida:
    artifacts/Universo_CEDEARs_desde_config.xlsx

Ese archivo NO sustituye automáticamente Universo_120 en producción: descargalo desde
GitHub Actions → Artefactos, revisalo y copialo a 0_Data_Maestra si corresponde.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from config import RATIOS_CEDEAR, SECTORES, UNIVERSO_BASE  # noqa: E402


def main() -> None:
    tickers = sorted({str(t).upper().strip() for t in UNIVERSO_BASE} | set(RATIOS_CEDEAR.keys()))
    rows = []
    for t in tickers:
        if not t:
            continue
        r = float(RATIOS_CEDEAR.get(t, 1.0))
        rows.append({
            "Ticker": t,
            "Ratio": r,
            "Sector": SECTORES.get(t, "Otros"),
            "Tipo": "CEDEAR",
        })
    df = pd.DataFrame(rows).sort_values("Ticker").reset_index(drop=True)
    out_dir = ROOT / "artifacts"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "Universo_CEDEARs_desde_config.xlsx"
    df.to_excel(out_path, index=False)
    print(f"OK: {out_path} ({len(df)} filas)")


if __name__ == "__main__":
    main()
