"""tests/test_favoritos_mes.py — Persistencia y prioridad favoritos estudio."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from types import SimpleNamespace

from services.favoritos_mes import (
    aplicar_prioridad_favoritos,
    load_favoritos_mes,
    save_favoritos_mes,
)
from services.recomendacion_capital import recomendar


def test_aplicar_prioridad_favoritos():
    assert aplicar_prioridad_favoritos(["AMZN", "MSFT", "KO"], ["MSFT"]) == ["MSFT", "AMZN", "KO"]
    assert aplicar_prioridad_favoritos(["A", "B"], []) == ["A", "B"]


def test_save_y_load_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "mq26_favoritos_mes.json"
    monkeypatch.setenv("MQ26_FAVORITOS_MES_PATH", str(p))
    save_favoritos_mes(["PN43O"], ["META", "MELI"], published_by="qa", disclaimer="convicción test")
    doc = load_favoritos_mes()
    assert doc["rf"] == ["PN43O"]
    assert doc["rv"] == ["META", "MELI"]
    assert doc["published_by"] == "qa"
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


@pytest.mark.parametrize("payload", [{}, "garbage"])
def test_load_sin_archivo_o_json_malo(tmp_path, monkeypatch, payload):
    p = tmp_path / "mq26_favoritos_mes.json"
    monkeypatch.setenv("MQ26_FAVORITOS_MES_PATH", str(p))
    if isinstance(payload, str):
        p.write_text(payload, encoding="utf-8")
    doc = load_favoritos_mes()
    assert doc["rf"] == [] and doc["rv"] == []


def test_recomendar_prioriza_favorito_rv_sobre_momentum(tmp_path, monkeypatch):
    fav_path = tmp_path / "mq26_favoritos_mes.json"
    monkeypatch.setenv("MQ26_FAVORITOS_MES_PATH", str(fav_path))
    save_favoritos_mes([], ["MSFT"], published_by="pytest")

    df = pd.DataFrame(
        [
            {"TICKER": "PN43O", "VALOR_ARS": 175_000, "TIPO": "ON_USD"},
            {"TICKER": "TLCTO", "VALOR_ARS": 175_000, "TIPO": "ON_USD"},
            {"TICKER": "SPY", "VALOR_ARS": 650_000, "TIPO": "CEDEAR"},
        ]
    )
    precios = {
        "PN43O": 10_000.0,
        "TLCTO": 10_000.0,
        "GLD": 10_000.0,
        "BRKB": 10_000.0,
        "SPY": 10_000.0,
        "MSFT": 10_000.0,
        "AMZN": 10_000.0,
        "NVDA": 10_000.0,
        "META": 10_000.0,
        "MELI": 10_000.0,
    }
    df_analisis = pd.DataFrame(
        [
            {"TICKER": "MSFT", "PUNTAJE_TECNICO": 0.1},
            {"TICKER": "AMZN", "PUNTAJE_TECNICO": 9.0},
        ]
    )
    r = recomendar(
        df_ag=df,
        perfil="Arriesgado",
        horizonte_label="1 año",
        capital_ars=5_000_000.0,
        ccl=1000.0,
        precios_dict=precios,
        diagnostico=SimpleNamespace(pct_defensivo_actual=0.35),
        df_analisis=df_analisis,
    )
    tickers = [c.ticker for c in r.compras_recomendadas]
    assert "MSFT" in tickers and "AMZN" in tickers
    assert tickers.index("MSFT") < tickers.index("AMZN")
