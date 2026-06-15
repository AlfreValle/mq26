"""CLI smoke_produccion: falla limpio si el host no responde."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_script_falla_si_puerto_cerrado():
    script = ROOT / "scripts" / "smoke_produccion.py"
    r = subprocess.run(
        [sys.executable, str(script), "--base-url", "http://127.0.0.1:1", "--timeout", "1"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 1
