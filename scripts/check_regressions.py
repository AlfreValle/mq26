#!/usr/bin/env python3
"""
Verificación rápida de las 2 regresiones persistentes.
Correr antes de cada commit importante.

Uso: python scripts/check_regressions.py
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).parent.parent
errors: list[str] = []

# R1: use_light condicional
app_main = (ROOT / "app_main.py").read_text(encoding="utf-8")
if "build_theme_css_bundle(BASE_DIR, use_light=True)" in app_main:
    errors.append(
        "R1 FALLA: app_main.py tiene use_light=True hardcodeado.\n"
        "  Debe ser condicional según mq_light_mode de session_state."
    )
else:
    print("R1 OK — use_light condicional en app_main.py")

# R2: paleta gastronómica en tema claro
retail = (ROOT / "assets" / "style_retail_light.css").read_text(encoding="utf-8")
if "--c-accent: #2563eb" in retail or "--c-accent:#2563eb" in retail:
    errors.append(
        "R2 FALLA: style_retail_light.css tiene acento azul #2563eb.\n"
        "  Debe ser #8B1A2E (borgoña)."
    )
else:
    print("R2 OK — acento borgoña en style_retail_light.css")

if errors:
    print("\n" + "\n".join(errors))
    raise SystemExit(1)

print("\nOK Sin regresiones detectadas.")
