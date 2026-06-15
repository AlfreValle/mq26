#!/usr/bin/env python3
"""Verificación rápida pre-deploy: navegación y ctx sin arrancar Streamlit."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.context_builder import finalize_ctx
from ui.navigation import get_main_tabs


def main() -> int:
    for kind, role, n in (
        ("mq26", "inversor", 1),
        ("mq26", "estudio", 5),
        ("mq26", "super_admin", 8),
        ("app", "inversor", 4),
        ("app", "estudio", 6),
    ):
        specs = get_main_tabs(kind, role)  # type: ignore[arg-type]
        if len(specs) != n:
            print(f"FAIL {kind}/{role}: esperado {n} tabs, hay {len(specs)}")
            return 1
    ctx = finalize_ctx({"user_role": "inversor"})
    if not ctx.get("tenant_id"):
        print("FAIL finalize_ctx sin tenant_id")
        return 1
    print("OK smoke_entrypoints_nav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
