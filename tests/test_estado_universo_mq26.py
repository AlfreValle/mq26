"""Tests de services.estado_universo_mq26 con BYMA mockeado."""

from __future__ import annotations

import pandas as pd
import pytest

from services.estado_universo_mq26 import dataframe_estado_universo, resumen_estado_universo_mq26


def _fake_fetch_universo_rv_byma() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Tipo": ["CEDEAR", "CEDEAR", "ACCION_LOCAL", "ACCION_LOCAL", "ACCION_LOCAL"],
        }
    )


def _fake_fetch_tipo(ep: str) -> list[dict]:
    return [{"id": i} for i in range({"cedears": 10, "equities": 20}.get(ep, 5))]


def _fake_tickers_cedears(_seg: str, max_activos: int) -> list[str]:
    return [f"C{i}" for i in range(min(3, max_activos))]


def _fake_tickers_merval(_seg: str, max_activos: int) -> list[str]:
    return [f"M{i}" for i in range(min(2, max_activos))]


def test_resumen_estado_universo_mq26_monkeypatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.byma_market_data.fetch_universo_rv_byma",
        _fake_fetch_universo_rv_byma,
        raising=False,
    )
    monkeypatch.setattr(
        "services.byma_market_data._fetch_tipo",
        _fake_fetch_tipo,
        raising=False,
    )
    monkeypatch.setattr(
        "services.scoring_engine._tickers_rv_segmento_desde_byma",
        lambda seg, max_a: _fake_tickers_cedears(seg, max_a)
        if seg == "cedears"
        else _fake_tickers_merval(seg, max_a),
        raising=False,
    )
    monkeypatch.setattr(
        "services.scoring_engine.universo_ons_tickers",
        lambda: ["ON1", "ON2", "ON3"],
        raising=False,
    )
    monkeypatch.setattr(
        "services.scoring_engine.UNIVERSO_BONOS_USD",
        ["B1", "B2", "B3", "B4"],
        raising=False,
    )

    r = resumen_estado_universo_mq26(
        max_scan_cedears=80,
        max_scan_merval=40,
        max_scan_on=60,
        max_scan_bonos=30,
    )
    assert r["mq26_universo_cedears"] == 2
    assert r["mq26_universo_acciones"] == 3
    assert r["byma_filas_cedears"] == 10
    assert r["byma_filas_equities"] == 20
    assert r["scan_cedears_tickets"] == 3
    assert r["scan_merval_tickets"] == 2
    assert r["motor_catalogo_on"] == 3
    assert r["scan_on_tickets"] == 3
    assert r["motor_lista_bonos"] == 4
    assert r["scan_bonos_tickets"] == 4

    df = dataframe_estado_universo(r)
    assert not df.empty
    assert "Concepto" in df.columns and "Cantidad" in df.columns
