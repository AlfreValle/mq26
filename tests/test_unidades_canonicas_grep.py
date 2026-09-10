"""CI grep: PPC_USD × CCL y .get('RATIO', 1.0) fuera del helper canónico."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_unidades_canonicas.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_unidades_canonicas", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_unidades_canonicas_grep_verde():
    mod = _load_checker()
    hits = mod.collect_violations(ROOT)
    assert hits == [], "Patrones peligrosos:\n" + "\n".join(hits)


def test_cuatro_pantallas_optima_usan_pills_compartidas():
    tabs = (
        ROOT / "ui" / "tab_recomendador.py",
        ROOT / "ui" / "tab_mercado.py",
        ROOT / "ui" / "tab_optimizacion.py",
        ROOT / "ui" / "tab_riesgo.py",
    )
    for p in tabs:
        src = p.read_text(encoding="utf-8")
        assert "html_pills_fuente" in src, f"{p.name} no usa html_pills_fuente"


def test_wrapper_ruta_decision_delega_en_pills_compartidas():
    h = (ROOT / "ui" / "inversor" / "_helpers.py").read_text(encoding="utf-8")
    assert "def _html_pills_ruta_decision" in h
    assert "html_pills_fuente" in h
    ux = (ROOT / "ui" / "mq26_ux.py").read_text(encoding="utf-8")
    assert "def html_pills_fuente" in ux
