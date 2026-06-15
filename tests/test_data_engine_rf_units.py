from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DE_PATH = ROOT / "1_Scripts_Motor" / "data_engine.py"


def _load_data_engine_module():
    spec = importlib.util.spec_from_file_location("data_engine_rf_test", DE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_agregar_cartera_normaliza_tipo_rf_si_vino_cedear():
    de = _load_data_engine_module()
    eng = de.DataEngine()
    df = pd.DataFrame(
        [
            {
                "CARTERA": "X",
                "FECHA_COMPRA": "2026-04-07",
                "TICKER": "TLCTO",
                "TIPO": "CEDEAR",  # carga incorrecta
                "CANTIDAD": 10,
                "PPC_USD": 100.0,
                "PPC_ARS": 150000.0,
            }
        ]
    )
    out = eng.agregar_cartera(df, "X")
    assert not out.empty
    assert str(out.iloc[0]["TIPO"]).upper() == "ON_USD"
    assert bool(out.iloc[0]["ES_LOCAL"]) is True


def test_obtener_precios_cartera_rf_no_depende_ticker_yahoo_equity(monkeypatch):
    de = _load_data_engine_module()
    eng = de.DataEngine()

    monkeypatch.setattr(de, "rf_get_meta", lambda _t: {"moneda": "USD", "paridad_ref": 100.0, "tipo": "ON_USD"})
    monkeypatch.setattr(
        de.yf,
        "download",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("yf_down_should_not_be_needed_for_rf")),
    )

    out = eng.obtener_precios_cartera(["TLCTO"], ccl=1500.0)
    assert out["TLCTO"] == 1500.0


def test_agregar_cartera_rf_normaliza_ppc_por_paridad(monkeypatch):
    de = _load_data_engine_module()
    eng = de.DataEngine()
    monkeypatch.setattr(de, "rf_get_meta", lambda _t: {"tipo": "ON_USD", "moneda": "USD", "paridad_ref": 100.0})
    monkeypatch.setattr(de, "ccl_historico_por_fecha", lambda *_a, **_k: 1464.9)

    df = pd.DataFrame(
        [
            {
                "CARTERA": "X",
                "FECHA_COMPRA": "2026-04-07",
                "TICKER": "TLCTO",
                "TIPO": "CEDEAR",
                "CANTIDAD": 10,
                "PPC_USD": 100.0,
                "PPC_ARS": 152040.0,  # inflado por factor 100 en carga fuente
            }
        ]
    )
    out = eng.agregar_cartera(df, "X")
    inv = float(out.iloc[0]["INV_ARS_HISTORICO"])
    assert inv == 14649.0


def test_agregar_cartera_fifo_rf_normaliza_ppc_por_paridad(monkeypatch):
    de = _load_data_engine_module()
    eng = de.DataEngine()
    monkeypatch.setattr(de, "rf_get_meta", lambda _t: {"tipo": "ON_USD", "moneda": "USD", "paridad_ref": 100.0})
    monkeypatch.setattr(de, "ccl_historico_por_fecha", lambda *_a, **_k: 1464.9)

    df = pd.DataFrame(
        [
            {
                "CARTERA": "X",
                "FECHA_COMPRA": "2026-04-07",
                "TICKER": "TLCTO",
                "TIPO": "CEDEAR",
                "CANTIDAD": 10,
                "PPC_USD": 100.0,
                "PPC_ARS": 152040.0,
            }
        ]
    )
    out = eng.agregar_cartera_fifo(df, "X")
    inv = float(out.iloc[0]["INV_ARS_HISTORICO"])
    assert inv == 14649.0
