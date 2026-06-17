"""
Test de seguridad A21: ningún secret real debe entrar al control de versiones.

Blinda contra regresión — si alguien commitea `.env`, una clave de bróker, un
token de Telegram real o una connection string con credenciales, CI falla acá.
Auditoría 2026-06: el código versionado lee todo de os.environ; este test lo
mantiene así.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _archivos_trackeados() -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files"], cwd=REPO, text=True, encoding="utf-8", errors="replace"
    )
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def test_env_real_no_trackeado():
    """El .env real (credenciales de producción) nunca debe estar en git."""
    tracked = _archivos_trackeados()
    prohibidos = [f for f in tracked if f == ".env" or f.endswith("/.env") or f == ".env.demo"]
    assert not prohibidos, f"Archivos .env con secrets no deben trackearse: {prohibidos}"


_PLACEHOLDER_TOKENS = (
    "tu_", "your_", "<", "xxx", "...", "placeholder", "cambia", "change",
    "ejemplo", "example", "abcxyz", "project_ref", "password", "secret",
    "contrase", "segura", "token_aca", "aca", "here",
)


def _es_placeholder(val: str) -> bool:
    v = val.strip().strip('"').strip("'").lower()
    return v == "" or any(tok in v for tok in _PLACEHOLDER_TOKENS)


def test_env_example_es_plantilla_sin_valores_reales():
    """`.env.example` puede estar versionado, pero solo como plantilla."""
    ej = REPO / ".env.example"
    if not ej.exists():
        return
    txt = ej.read_text(encoding="utf-8", errors="replace")
    # No debe contener la password real de bróker detectada en la auditoría
    assert "5nkUDUjs" not in txt
    # Las claves sensibles deben quedar vacías o como placeholder evidente
    for ln in txt.splitlines():
        if re.match(r"\s*(IOL_PASSWORD|MQ26_PASSWORD|TELEGRAM_TOKEN)\s*=", ln):
            val = ln.split("=", 1)[1]
            assert _es_placeholder(val), f"`.env.example` no debe traer valor real: {ln!r}"


# Patrones de secrets REALES (no placeholders ni tests).
_PATRONES_SECRET = [
    (re.compile(r"IOL_PASSWORD\s*=\s*['\"]?[^'\"\s#]{6,}"), "password de bróker IOL"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9]{20,}"), "API key Anthropic"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "API key OpenAI"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "token Telegram real"),
    (re.compile(r"postgres(?:ql)?://[^:]+:[^@/\s]{4,}@(?!localhost|usuario|user|host)"),
     "connection string Postgres con password"),
]

# Tokens de ejemplo/test conocidos que NO son hallazgos.
_PERMITIDOS = ("1234567890:ABC", "tu_token", "your_token", "test", "demo", "example", "xxx")


def test_codigo_versionado_sin_secrets_crudos():
    """Ningún archivo de código/config trackeado contiene un secret real."""
    sospechosos: list[str] = []
    for rel in _archivos_trackeados():
        if not rel.endswith((".py", ".toml", ".yml", ".yaml", ".json")):
            continue
        # tests/ usan credenciales dummy; .env.example y docs traen placeholders
        # (cubiertos por test_env_example_es_plantilla_sin_valores_reales).
        if rel.startswith(("tests/", "docs/")) or rel.endswith(".example"):
            continue
        p = REPO / rel
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for rx, desc in _PATRONES_SECRET:
            for m in rx.finditer(txt):
                frag = m.group(0)
                if any(tok in frag for tok in _PERMITIDOS):
                    continue
                sospechosos.append(f"{rel}: {desc} → {frag[:40]}")
    assert not sospechosos, "Posibles secrets en código versionado:\n" + "\n".join(sospechosos)
