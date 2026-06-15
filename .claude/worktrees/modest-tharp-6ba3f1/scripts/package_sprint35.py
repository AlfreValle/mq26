"""Genera un .zip de cierre sin cachés ni incluir archivos de salida previos."""
from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAMP = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
OUT_NAME = f"MQ26_DSS_Sprint35_FINAL_{STAMP}.zip"
LEGACY_NAMES = frozenset(
    {"MQ26_DSS_Sprint35_FINAL.zip", "MQ26_DSS_Sprint35_FINAL_alt.zip"}
)
SKIP_PARTS = frozenset({
    ".git",
    ".cursor",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    ".mypy_cache",
    ".venv",
    "venv",
    "node_modules",
    ".eggs",
    "dist",
    "build",
})
SKIP_SUFFIXES = (".pyc", ".db", ".sqlite", ".sqlite3")


def main() -> int:
    """Empaqueta el proyecto; invariante: no incluye otros zips de entrega Sprint 35."""
    print("Empaquetando (puede tardar en discos lentos / OneDrive)...", flush=True)
    out = ROOT / OUT_NAME
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if rel.suffix.lower() == ".zip" and (
                rel.name.startswith("MQ26_DSS_Sprint35_FINAL")
                or rel.name in LEGACY_NAMES
            ):
                continue
            if any(p in SKIP_PARTS for p in rel.parts):
                continue
            if path.suffix in SKIP_SUFFIXES:
                continue
            zf.write(path, rel)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
