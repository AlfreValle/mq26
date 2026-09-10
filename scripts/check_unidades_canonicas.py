#!/usr/bin/env python3
"""
CI estático: PPC_USD × CCL y RATIO default 1.0 solo vía helpers canónicos.

La conversión ``PPC_USD → ARS`` vive en ``core.pricing_utils.precio_ars_desde_ppc_usd``.
El ratio CEDEAR vive en ``core.pricing_utils.obtener_ratio`` (no ``.get("RATIO", 1.0)``).

Uso: python scripts/check_unidades_canonicas.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("core", "services", "ui", "1_Scripts_Motor")
SCAN_FILES = ("run_mq26.py", "app_main.py")

ALLOWLIST = {
    ROOT / "core" / "pricing_utils.py",
    ROOT / "scripts" / "check_unidades_canonicas.py",
}

# Multiplicación inmediata de un token PPC_USD por CCL (opcional /100).
RE_PPC_X_CCL = re.compile(
    r"(?i)"
    r"(?:ppc_usd(?:_[a-z0-9]+)?|\[[\"']PPC_USD(?:_PROM)?[\"']\]\)?)"
    r"\s*(?:/\s*100(?:\.0)?)?\)?\s*\*"
    r"[^\n#]{0,80}ccl"
)
RE_CCL_X_PPC = re.compile(
    r"(?i)ccl(?:_hist|_f|_fila|_lm|_spot|_historico)?\s*\*[^\n#]{0,80}ppc_usd"
)
RE_RATIO_DEFAULT = re.compile(
    r"""\.get\(\s*[\"']RATIO[\"']\s*,\s*1(?:\.0+)?\s*\)"""
)


def _iter_py_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    for name in SCAN_FILES:
        p = root / name
        if p.is_file():
            out.append(p)
    return sorted(out)


def collect_violations(root: Path | None = None) -> list[str]:
    base = root or ROOT
    hits: list[str] = []
    for path in _iter_py_files(base):
        if path.resolve() in {p.resolve() for p in ALLOWLIST}:
            continue
        rel = path.relative_to(base).as_posix()
        if rel.startswith("tests/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            hits.append(f"{rel}: no se pudo leer ({e})")
            continue
        for i, raw in enumerate(text.splitlines(), start=1):
            code = raw.split("#", 1)[0]
            if "precio_ars_desde_ppc_usd" in code:
                continue
            if "obtener_ratio(" in code:
                # Ratio resuelto por el helper canónico (aunque la línea mencione RATIO).
                if RE_RATIO_DEFAULT.search(code):
                    hits.append(f"{rel}:{i}: .get('RATIO', 1) junto a obtener_ratio")
                continue
            if RE_PPC_X_CCL.search(code) or RE_CCL_X_PPC.search(code):
                hits.append(f"{rel}:{i}: PPC_USD × CCL fuera de precio_ars_desde_ppc_usd")
                continue
            if RE_RATIO_DEFAULT.search(code):
                hits.append(f"{rel}:{i}: .get('RATIO', 1.0) — usá obtener_ratio()")
    return hits


def main() -> int:
    hits = collect_violations()
    if hits:
        print("UNIDADES CANÓNICAS: violaciones")
        for h in hits:
            print(f"  {h}")
        print(
            "\nConvertí PPC_USD×CCL con core.pricing_utils.precio_ars_desde_ppc_usd "
            "y el ratio con obtener_ratio(..., default=0) si no debe inventar 1.0."
        )
        return 1
    print("OK unidades canónicas (PPC_USD×CCL y RATIO default).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
