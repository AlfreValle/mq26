"""Tests de la apertura de cliente sin posiciones en Estudio."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture()
def te(monkeypatch):
    mock = MagicMock()
    mock.session_state = {}

    def _cols(*a, **k):
        n = a[0] if (a and isinstance(a[0], int)) else (len(a[0]) if a and isinstance(a[0], (list, tuple)) else 2)
        return tuple(MagicMock() for _ in range(n))

    mock.columns.side_effect = _cols
    mock.button.return_value = False
    original = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock
    import importlib

    import ui.tab_estudio as te_mod
    importlib.reload(te_mod)
    yield te_mod
    if original is not None:
        sys.modules["streamlit"] = original


def test_sin_posiciones_true_para_df_vacio(te, monkeypatch):
    monkeypatch.setattr(te, "_cargar_cartera_cliente", lambda *a, **k: pd.DataFrame())
    assert te._cliente_sin_posiciones(1, "María Fernández | Moderado", {}) is True


def test_sin_posiciones_true_para_tickers_vacios(te, monkeypatch):
    df = pd.DataFrame({"TICKER": ["", "NAN"], "VALOR_ARS": [0, 0]})
    monkeypatch.setattr(te, "_cargar_cartera_cliente", lambda *a, **k: df)
    assert te._cliente_sin_posiciones(1, "X", {}) is True


def test_con_posiciones_false(te, monkeypatch):
    df = pd.DataFrame({"TICKER": ["AAPL", "PN43O"], "VALOR_ARS": [100, 200]})
    monkeypatch.setattr(te, "_cargar_cartera_cliente", lambda *a, **k: df)
    assert te._cliente_sin_posiciones(1, "X", {}) is False


def test_apertura_render_no_lanza(te, monkeypatch):
    # Sin modo elegido, la bifurcación renderiza los 2 botones sin explotar.
    monkeypatch.setattr(te, "_cargar_cartera_cliente", lambda *a, **k: pd.DataFrame())
    te._render_apertura_sin_posiciones(7, "María Fernández | Moderado", {"user_role": "estudio"})
