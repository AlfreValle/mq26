"""Monitor ON USD."""
from __future__ import annotations

from datetime import date

import pytest

from core.renta_fija_ar import (
    INSTRUMENTOS_RF,
    _meses_calendario_pago_cupon,
    bucket_riesgo_on_hd,
    ficha_rf_minima_bundle,
    get_meta,
    monitor_on_usd_panel_df,
    monitor_on_usd_vencimientos_por_mes_df,
)

_pn43 = get_meta("PN43O")
_tlcto = get_meta("TLCTO")
_mgcho = get_meta("MGCHO")


def test_bucket_pn43o_conservador():
    assert _pn43 is not None
    assert bucket_riesgo_on_hd(_pn43) == "conservador"


def test_bucket_tlcto_moderado():
    assert _tlcto is not None
    assert bucket_riesgo_on_hd(_tlcto) == "moderado"


def test_bucket_mgcho_moderado():
    assert _mgcho is not None
    assert bucket_riesgo_on_hd(_mgcho) == "moderado"


def test_monitor_df_includes_on_usd_only():
    df = monitor_on_usd_panel_df()
    assert not df.empty
    assert "GD30" not in set(df["Ticker"])
    assert "PN43O" in set(df["Ticker"])
    assert set(df["Tipo"].unique()) == {"Hard Dollar"}
    assert list(df.columns[:4]) == ["Banda", "Ticker", "Emisor", "Tipo"]


def test_monitor_df_con_ccl_incluye_ars_por_100_vn():
    df = monitor_on_usd_panel_df(ccl=1465.0)
    assert "ARS / 100 VN USD" in df.columns
    sub = df[df["Ticker"] == "PN43O"]
    assert not sub.empty
    assert float(sub.iloc[0]["ARS / 100 VN USD"]) > 0


def test_ficha_minima_bundle_desde_fila_panel_pn43o():
    """P2-RF-01 PR 3: mismo contrato que usa monitor_on_usd (fila → bundle)."""
    df = monitor_on_usd_panel_df(ccl=1500.0)
    row = df[df["Ticker"] == "PN43O"].iloc[0]
    meta = INSTRUMENTOS_RF.get("PN43O")
    assert meta is not None
    par = float(row["Paridad %"]) if row.get("Paridad %") is not None else None
    b = ficha_rf_minima_bundle(
        "PN43O",
        meta,
        paridad_pct=par,
        fuente_precio=str(row.get("Fuente") or ""),
    )
    assert b["ok"] is True
    assert b["ticker"] == "PN43O"
    assert b["tir_ref_pct"] == pytest.approx(float(meta["tir_ref"]), rel=0.01)


def test_monitor_df_marca_ajuste_x100_cuando_byma_indica_escala():
    """P2-RF-04: columna visible cuando el feed aplicó ÷100."""
    live = {
        "PN43O": {
            "paridad_ref": 100.0,
            "var_diaria_pct": 0.0,
            "precio_ars": 1500.0,
            "fecha_ref": "2026-01-01 12:00",
            "fuente": "BYMA_LIVE",
            "escala_div100": True,
        }
    }
    df = monitor_on_usd_panel_df(byma_live=live, ccl=1500.0)
    sub = df[df["Ticker"] == "PN43O"]
    assert not sub.empty
    assert sub.iloc[0]["Ajuste ×100 BYMA"] == "Sí"


def test_meses_cupon_semestral_y_trimestral():
    meta_s = {"cupon_anual": 0.08, "frecuencia": 2}
    s_s, lbl_s = _meses_calendario_pago_cupon(meta_s, date(2035, 7, 15))
    assert s_s == {1, 7}
    assert "Julio" in lbl_s and "Enero" in lbl_s
    meta_q = {"cupon_anual": 0.06, "frecuencia": 4}
    s_q, _ = _meses_calendario_pago_cupon(meta_q, date(2035, 7, 15))
    assert s_q == {1, 4, 7, 10}


def test_universo_ons_incluye_catalogo_activo():
    from services.scoring_engine import universo_ons_tickers

    assert "PN43O" in universo_ons_tickers()


def test_vencimientos_on_usd_por_mes_no_vacio_y_columnas():
    df = monitor_on_usd_vencimientos_por_mes_df()
    assert not df.empty
    for col in (
        "Mes",
        "Vencimiento",
        "Ticker",
        "Emisor",
        "TIR ref. %",
        "Frec. cupón",
        "Pagos en el año (cupón)",
    ):
        assert col in df.columns
    _meses_es = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    assert df.iloc[0]["Mes"] in _meses_es
    # Orden: meses calendario enero → diciembre, luego vencimiento
    _ord = {m: i for i, m in enumerate(_meses_es)}
    ords = [_ord[str(r["Mes"])] for _, r in df.iterrows()]
    assert ords == sorted(ords)
