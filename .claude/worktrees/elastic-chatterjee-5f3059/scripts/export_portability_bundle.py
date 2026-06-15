"""
export_portability_bundle.py — Empaqueta archivos maestros en un ZIP para portabilidad / backup.

Uso:
  python scripts/export_portability_bundle.py
  python scripts/export_portability_bundle.py --out C:/Backup/mq26_portability.zip

No requiere Streamlit. Lectura desde config.BASE_DIR / 0_Data_Maestra.
"""
from __future__ import annotations

import argparse
import zipfile
from datetime import datetime
from pathlib import Path

# Raíz del repo (parent de scripts/)
ROOT = Path(__file__).resolve().parent.parent
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    RUTA_ANALISIS,
    RUTA_MAESTRA,
    RUTA_TRANSAC,
    RUTA_UNIVERSO,
    RUTA_DB,
)


def _add(zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
    if path.is_file():
        zf.write(path, arcname=arcname)


def main() -> None:
    ap = argparse.ArgumentParser(description="ZIP de portabilidad MQ26")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Ruta del .zip de salida (default: 0_Data_Maestra/portability_YYYYMMDD_HHMM.zip)",
    )
    args = ap.parse_args()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out = args.out
    if out is None:
        out = ROOT / "0_Data_Maestra" / f"mq26_portability_{ts}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)

    files = [
        (RUTA_TRANSAC, "Maestra_Transaccional.csv"),
        (RUTA_MAESTRA, "Maestra_Inversiones.xlsx"),
        (RUTA_ANALISIS, "Analisis_Empresas.xlsx"),
        (RUTA_UNIVERSO, "Universo_120_CEDEARs.xlsx"),
        (RUTA_DB, "master_quant.db"),
    ]
    added = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, name in files:
            if src.is_file():
                _add(zf, src, name)
                added += 1
            else:
                print(f"omitido (no existe): {src}")
    print(f"Listo: {out} ({added} archivos incluidos)")


if __name__ == "__main__":
    main()
