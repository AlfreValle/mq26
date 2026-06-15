"""Parsea todos los .py del repo con ast (excluye .git, __pycache__, .pytest_cache, htmlcov)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = frozenset({".git", "__pycache__", ".pytest_cache", "htmlcov"})


def _skip(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return True
    return any(p in SKIP_PARTS for p in rel.parts)


def main() -> int:
    errors: list[tuple[Path, SyntaxError]] = []
    for py in ROOT.rglob("*.py"):
        if _skip(py):
            continue
        try:
            src = py.read_text(encoding="utf-8")
        except OSError as e:
            print(f"read error {py}: {e}", file=sys.stderr)
            return 2
        try:
            ast.parse(src, filename=str(py))
        except SyntaxError as e:
            errors.append((py, e))
    if errors:
        for p, e in errors:
            print(f"{p}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
