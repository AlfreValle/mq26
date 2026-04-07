"""Tests del script CLI scripts/enviar_reportes_mensuales.py."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_enviar_module():
    path = ROOT / "scripts" / "enviar_reportes_mensuales.py"
    spec = importlib.util.spec_from_file_location("enviar_reportes_mensuales", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_cargar_mapa_desde_archivo_tmp(tmp_path):
    mod = _load_enviar_module()
    p = tmp_path / "dest.json"
    p.write_text(json.dumps({"12": "uno@test.com", "13": "dos@test.com"}), encoding="utf-8")
    m = mod.cargar_mapa_destinatarios(str(p))
    assert m == {12: "uno@test.com", 13: "dos@test.com"}


def test_main_sin_mapa_retorna_1(monkeypatch):
    monkeypatch.delenv("MQ26_REPORTES_DESTINATARIOS", raising=False)
    mod = _load_enviar_module()
    assert mod.main(["--dry-run"]) == 1


def test_main_dry_run_cliente_inexistente_retorna_1(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ26_REPORTES_DESTINATARIOS", raising=False)
    p = tmp_path / "dest.json"
    p.write_text(json.dumps({"999999999": "nadie@test.com"}), encoding="utf-8")
    mod = _load_enviar_module()
    assert mod.main(["--dry-run", "--map", str(p)]) == 1


def test_procesar_dry_run_cliente_faltante_fallo():
    mod = _load_enviar_module()
    rows = mod.procesar_reportes_mensuales("default", {999_999_999: "x@y.com"}, dry_run=True)
    assert len(rows) == 1
    assert rows[0][2] is False
