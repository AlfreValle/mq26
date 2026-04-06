"""
Revierte width='stretch' → use_container_width=True
y    width='content'    → use_container_width=False
en todos los archivos .py del proyecto (idempotente).

Uso: python scripts/fix_stretch_to_container_width.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent


def main() -> int:
    total_files = 0
    total_replacements = 0

    for f in root.rglob("*.py"):
        if any(p in f.parts for p in (".venv", "venv", "__pycache__", "site-packages", ".git")):
            continue
        if f.name in ("fix_stretch_to_container_width.py",):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            new = content
            new = re.sub(r",\s*width=['\"]stretch['\"]", ", use_container_width=True", new)
            new = re.sub(r"\bwidth=['\"]stretch['\"]\s*,", "use_container_width=True,", new)
            new = re.sub(r"\bwidth=['\"]stretch['\"]\b", "use_container_width=True", new)
            new = re.sub(r",\s*width=['\"]content['\"]", ", use_container_width=False", new)
            new = re.sub(r"\bwidth=['\"]content['\"]\s*,", "use_container_width=False,", new)
            new = re.sub(r"\bwidth=['\"]content['\"]\b", "use_container_width=False", new)
            if new != content:
                n = len(re.findall(r"width=['\"](?:stretch|content)['\"]", content))
                f.write_text(new, encoding="utf-8")
                total_files += 1
                total_replacements += n
                print(f"  ok {f.relative_to(root)} ({n} ocurrencias)")
        except OSError as e:
            print(f"  err {f}: {e}", file=sys.stderr)

    print(f"\nTotal: {total_files} archivos, {total_replacements} reemplazos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
