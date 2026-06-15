"""
Verificación rápida de umbrales mínimos de líneas (Sprint documentación v2).

Uso: python scripts/check_critical_module_lines.py
Fallará con código distinto de 0 si algún módulo cae por debajo del mínimo.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Módulos UI grandes que no deberían “encogerse” sin revisión consciente.
THRESHOLDS: dict[str, int] = {
    "ui/tab_estudio.py": 700,
    "ui/tab_cartera.py": 1000,
    "ui/tab_inversor.py": 2000,
    "run_mq26.py": 1500,
}


def main() -> int:
    bad: list[str] = []
    for rel, minimum in sorted(THRESHOLDS.items()):
        path = ROOT / rel
        if not path.is_file():
            bad.append(f"{rel}: archivo no encontrado")
            continue
        n = sum(1 for _ in path.open(encoding="utf-8", errors="replace"))
        if n < minimum:
            bad.append(f"{rel}: {n} líneas (< {minimum})")
    if bad:
        print("Umbrales no cumplidos:\n" + "\n".join(bad))
        return 1
    print("OK: todos los umbrales de líneas cumplidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
