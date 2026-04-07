"""Tests batch scores diarios y reporte HTML (sin yfinance real)."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod_scores():
    return _load_script("actualizar_scores_diario_test", "actualizar_scores_diario.py")


@pytest.fixture
def mod_reporte():
    return _load_script("reporte_scores_html_test", "reporte_scores_html.py")


def test_run_scores_batch_upserts(monkeypatch, db_en_memoria, mod_scores):
    from core.db_manager import ScoreHistorico, get_session

    called: list[tuple] = []

    def fake_calc(ticker: str, tipo: str = "CEDEAR"):
        called.append((ticker, tipo))
        return {
            "Ticker": ticker,
            "Score_Tec": 55.0,
            "Score_Fund": 60.0,
            "Score_Total": 57.0,
        }

    monkeypatch.setattr("services.scoring_engine.calcular_score_total", fake_calc)

    fecha = date(2026, 4, 1)
    ok, err = mod_scores.run_scores_batch(
        fecha,
        [("TEST1", "CEDEAR"), ("TEST2", "CEDEAR")],
        dry_run=False,
    )
    assert ok == 2 and err == 0
    assert len(called) == 2

    with get_session() as s:
        rows = s.query(ScoreHistorico).filter(ScoreHistorico.fecha == fecha).all()
        tickers = sorted(r.ticker for r in rows)
        assert tickers == ["TEST1", "TEST2"]
        for r in rows:
            assert r.score_tecnico == 55.0
            assert r.score_fundamental == 60.0
            assert r.score_total == 57.0


def test_run_scores_batch_dry_run(monkeypatch, db_en_memoria, mod_scores):
    from core.db_manager import ScoreHistorico, get_session

    monkeypatch.setattr(
        "services.scoring_engine.calcular_score_total",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamarse")),
    )
    with get_session() as s:
        n_before = s.query(ScoreHistorico).count()
    fecha = date.today()
    ok, err = mod_scores.run_scores_batch(fecha, [("X", "CEDEAR")], dry_run=True)
    assert ok == 1 and err == 0
    with get_session() as s:
        n_after = s.query(ScoreHistorico).count()
    assert n_after == n_before


def test_reporte_html_contiene_filas(db_en_memoria, mod_reporte):
    from core.db_manager import upsert_score_historico

    upsert_score_historico("ZZZ", date(2026, 4, 2), 50.0, 51.0, 52.0)
    rows = mod_reporte._fetch_rows(7)
    assert any(r["ticker"] == "ZZZ" for r in rows)
    html = mod_reporte.build_html(rows)
    assert "ZZZ" in html
    assert ">52.0<" in html


def test_parse_tickers_arg(mod_scores):
    assert mod_scores._parse_tickers_arg("a, b") == [("A", "CEDEAR"), ("B", "CEDEAR")]
    assert mod_scores._parse_tickers_arg("") == []
