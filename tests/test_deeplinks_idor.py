"""Deeplink de cliente: fail-closed si no hay df scoped o el id está fuera."""
from __future__ import annotations

import pandas as pd

from ui.deeplinks import ApplyResult, DeeplinkParams, _apply_cliente


def _params(cliente_id: int, raw: str | None = None) -> DeeplinkParams:
    return DeeplinkParams(
        tab=None,
        cliente_id=cliente_id,
        cliente_raw=raw if raw is not None else str(cliente_id),
        cartera="",
        cartera_id=None,
        modo_fifo=None,
        debug=False,
        raw={},
    )


def _capture_set_ss(monkeypatch) -> dict:
    captured: dict = {}

    def fake_set(key, value):
        captured[key] = value

    monkeypatch.setattr("core.session_schema.set_ss", fake_set)
    return captured


def test_sin_df_no_setea_cliente_id(monkeypatch):
    captured = _capture_set_ss(monkeypatch)
    result = ApplyResult()
    _apply_cliente(_params(99), None, None, result)
    assert "cliente_id" not in captured
    assert any("no se aplica" in w for w in result.warnings)


def test_df_vacio_no_setea_cliente_id(monkeypatch):
    captured = _capture_set_ss(monkeypatch)
    result = ApplyResult()
    _apply_cliente(_params(99), None, pd.DataFrame(), result)
    assert "cliente_id" not in captured
    assert any("no se aplica" in w for w in result.warnings)


def test_id_fuera_de_scope_no_setea_aunque_df_este_poblado(monkeypatch):
    """El warning + fall-through anterior era IDOR: avisaba y setea igual."""
    captured = _capture_set_ss(monkeypatch)
    df = pd.DataFrame({"ID": [1, 2], "Nombre": ["Ana", "Beto"]})
    result = ApplyResult()
    _apply_cliente(_params(99), None, df, result)
    assert "cliente_id" not in captured
    assert any("no encontrado" in w for w in result.warnings)


def test_id_en_scope_con_columna_ID_setea(monkeypatch):
    captured = _capture_set_ss(monkeypatch)
    df = pd.DataFrame({"ID": [1, 2], "Nombre": ["Ana", "Beto"]})
    result = ApplyResult()
    _apply_cliente(_params(2), None, df, result)
    assert captured.get("cliente_id") == 2
    assert captured.get("cliente_nombre") == "Beto"
    assert result.changes


def test_id_en_scope_con_columna_cliente_id_setea(monkeypatch):
    captured = _capture_set_ss(monkeypatch)
    df = pd.DataFrame({"cliente_id": [7], "nombre": ["Clara"]})
    result = ApplyResult()
    _apply_cliente(_params(7), None, df, result)
    assert captured.get("cliente_id") == 7
    assert captured.get("cliente_nombre") == "Clara"
