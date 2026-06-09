"""
Validador CI: consistencia docs <-> entrypoints <-> runbook (P2-03).

Uso:
    python scripts/validate_docs_entrypoints_runbook.py
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "map": ROOT / "docs" / "MAP_MQ26_ENTRYPOINTS.md",
    "runbook": ROOT / "docs" / "product" / "MVP_SOLIDO_RUNBOOK.md",
    "deploy": ROOT / "docs" / "DEPLOY_RAILWAY.md",
    "run_mq26": ROOT / "run_mq26.py",
    "app_main": ROOT / "app_main.py",
    "docker_entrypoint": ROOT / "docker-entrypoint.sh",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    for name, p in FILES.items():
        if not p.is_file():
            errors.append(f"[missing] {name}: {p}")

    if errors:
        print("FAIL: archivos requeridos no encontrados\n" + "\n".join(errors))
        return 1

    map_txt = _read(FILES["map"])
    runbook_txt = _read(FILES["runbook"])
    deploy_txt = _read(FILES["deploy"])
    run_txt = _read(FILES["run_mq26"])
    app_txt = _read(FILES["app_main"])
    de_txt = _read(FILES["docker_entrypoint"])

    checks = [
        ("docs map referencia run_mq26 prod", "Producción multi-tenant (Railway)" in map_txt and "`run_mq26.py`" in map_txt),
        ("docs map referencia app_main legacy", "Operación legacy / compatibilidad" in map_txt and "`app_main.py`" in map_txt),
        ("runbook arranca con run_mq26", "streamlit run run_mq26.py" in runbook_txt),
        ("deploy menciona healthcheck stcore", "_stcore/health" in deploy_txt),
        ("run_mq26 usa auth mq26", "check_password(" in run_txt and "'mq26'" in run_txt),
        ("app_main usa auth app", "check_password(" in app_txt and '"app"' in app_txt),
        ("docker entrypoint usa run_mq26", "run_mq26.py" in de_txt),
    ]

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("FAIL: inconsistencias docs/entrypoints/runbook")
        for f in failed:
            print(f"- {f}")
        return 1

    print("OK: docs, entrypoints y runbook consistentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
