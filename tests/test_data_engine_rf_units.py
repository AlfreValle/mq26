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


# ── Regresión: escala de valuación RF por moneda ──────────────────────────────
# USD: nominal fijo (1 USD) → precio = paridad/100 × CCL.
# ARS/ARS_CER: la paridad es % del nominal AJUSTADO (CER/capitalización), no de
# 1 peso, así que paridad/100 NO es el precio en pesos (daba P&L -99% contra el
# costo, que es el precio peso real del broker). Se usa precio_ars_ref (pesos).

def test_precio_referencia_paridad_es_porcentaje_ars_y_usd():
    from core.renta_fija_ar import get_meta, precio_referencia_ars_desde_catalogo
    from core.renta_fija_catalogo import INSTRUMENTOS_RF

    ccl = 1500.0
    # Un ticker de cada moneda presente en el catálogo.
    por_moneda: dict[str, str] = {}
    for tk in INSTRUMENTOS_RF:
        mon = str(get_meta(tk).get("moneda", "")).upper()
        por_moneda.setdefault(mon, tk)
    assert por_moneda, "catálogo RF vacío"
    for mon, tk in por_moneda.items():
        m = get_meta(tk)
        px = precio_referencia_ars_desde_catalogo(tk, ccl, vn=1.0)
        if mon == "USD":
            par = float(m.get("paridad_ref", 0) or 0)
            if par <= 0:
                continue
            esperado = (par / 100.0) * ccl
            assert abs(px - esperado) < 1e-6, f"{tk} ({mon}): {px} != {esperado}"
        else:
            # ARS/ARS_CER: precio peso real (precio_ars_ref); independiente del CCL.
            precio_ref = float(m.get("precio_ars_ref", 0) or 0)
            assert abs(px - precio_ref) < 1e-6, f"{tk} ({mon}): {px} != precio_ars_ref {precio_ref}"
            assert px == precio_referencia_ars_desde_catalogo(tk, 0.0, vn=1.0), f"{tk}: ARS no debe usar CCL"


def test_familias_rf_clasifican_como_local_no_cedear():
    """BONCER/BOPREAL/DUAL/USD_LINKED deben reconstruir costo por convención RF,
    no por la rama CEDEAR (que ignora PPC_ARS e infla 100×)."""
    from core.pricing_utils import es_instrumento_local_ars

    # Por TIPO, independiente del prefijo del ticker (DICP no matchea prefijos).
    assert es_instrumento_local_ars("DICP", "BONCER") is True
    assert es_instrumento_local_ars("BPA27", "BOPREAL") is True
    assert es_instrumento_local_ars("XXX", "DUAL") is True
    assert es_instrumento_local_ars("YYY", "USD_LINKED") is True
