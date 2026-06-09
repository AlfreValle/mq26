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
    instrumentos_on_usd_proximos_vencer,
    monitor_on_usd_panel_df,
    monitor_on_usd_vencimientos_por_mes_df,
    resumen_alertas_vencimiento_on_usd,
)

_pn43 = get_meta("PN43O")
_tlcto = get_meta("TLCTO")
_mgcho = get_meta("MGCHO")


def test_bucket_pn43o_conservador():
    assert _pn43 is not None
    assert bucket_riesgo_on_hd(_pn43) == "conservador"


def test_bucket_tlcto_moderado():
    # TLCTO: calificacion AA + TIR 7.5% ≤ 7.6% → ahora clasifica "conservador"
    assert _tlcto is not None
    assert bucket_riesgo_on_hd(_tlcto) == "conservador"


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


# ── Alerta de vencimiento próximo (MRCAO / YCA6O) ────────────────────────────

class TestAlertasVencimientoProximo:
    """instrumentos_on_usd_proximos_vencer + resumen_alertas_vencimiento_on_usd."""

    def test_mrcao_yca6o_detectados_en_90_dias(self):
        """Ambos vencen 2026-07-01 (~35 días) → deben aparecer con ventana 90d."""
        proximos = instrumentos_on_usd_proximos_vencer(dias=90)
        tickers = {p["ticker"] for p in proximos}
        assert "MRCAO" in tickers, "MRCAO debe detectarse como próximo a vencer"
        assert "YCA6O" in tickers, "YCA6O debe detectarse como próximo a vencer"

    def test_nivel_alerta_critico_mrcao(self):
        """MRCAO vence en 35 días → nivel CRITICO (≤35d)."""
        proximos = instrumentos_on_usd_proximos_vencer(dias=90)
        mrcao = next((p for p in proximos if p["ticker"] == "MRCAO"), None)
        assert mrcao is not None
        assert mrcao["nivel_alerta"] == "CRITICO"
        assert mrcao["dias_al_vto"] <= 35

    def test_nivel_alerta_critico_yca6o(self):
        """YCA6O vence en 35 días → nivel CRITICO."""
        proximos = instrumentos_on_usd_proximos_vencer(dias=90)
        yca6o = next((p for p in proximos if p["ticker"] == "YCA6O"), None)
        assert yca6o is not None
        assert yca6o["nivel_alerta"] == "CRITICO"

    def test_resultado_ordenado_por_dias(self):
        """Lista ordenada ascendentemente por dias_al_vto."""
        proximos = instrumentos_on_usd_proximos_vencer(dias=365)
        dias = [p["dias_al_vto"] for p in proximos]
        assert dias == sorted(dias)

    def test_ventana_cero_dias_devuelve_lista_vacia(self):
        """Con ventana de 0 días no debe haber nada (nada vence hoy)."""
        proximos = instrumentos_on_usd_proximos_vencer(dias=0)
        assert proximos == []

    def test_campos_obligatorios_presentes(self):
        """Cada dict devuelto tiene los campos requeridos."""
        campos = {"ticker", "emisor", "descripcion", "vencimiento",
                  "dias_al_vto", "tir_ref", "calificacion", "lamina_min", "nivel_alerta"}
        proximos = instrumentos_on_usd_proximos_vencer(dias=365)
        for p in proximos:
            assert campos.issubset(p.keys()), f"Faltan campos en {p['ticker']}: {campos - p.keys()}"

    def test_instrumentos_inactivos_excluidos(self):
        """Instrumentos con activo=False no aparecen aunque su vencimiento esté próximo."""
        # CSO2O: activo=False, tipo ON_USD
        proximos = instrumentos_on_usd_proximos_vencer(dias=3650)
        tickers = {p["ticker"] for p in proximos}
        assert "CSO2O" not in tickers

    def test_resumen_texto_no_vacio_si_hay_alertas(self):
        """resumen_alertas_vencimiento_on_usd() devuelve texto con emoji cuando hay alertas."""
        texto = resumen_alertas_vencimiento_on_usd(dias=90)
        assert texto != ""
        assert "⚠️" in texto
        assert "MRCAO" in texto or "YCA6O" in texto

    def test_resumen_texto_vacio_si_ventana_cero(self):
        """Sin alertas devuelve string vacío."""
        texto = resumen_alertas_vencimiento_on_usd(dias=0)
        assert texto == ""

    def test_panel_df_tiene_columnas_dias_y_alerta(self):
        """monitor_on_usd_panel_df incluye 'Días al vto.' y '⚠️ Próx. vto.'."""
        df = monitor_on_usd_panel_df()
        assert "Días al vto." in df.columns, "Falta columna 'Días al vto.'"
        assert "⚠️ Próx. vto." in df.columns, "Falta columna '⚠️ Próx. vto.'"

    def test_panel_df_alerta_roja_en_mrcao(self):
        """Fila MRCAO del panel debe tener emoji 🔴 en '⚠️ Próx. vto.'."""
        df = monitor_on_usd_panel_df()
        row = df[df["Ticker"] == "MRCAO"]
        assert not row.empty
        alerta = str(row.iloc[0]["⚠️ Próx. vto."])
        assert "🔴" in alerta, f"Esperado 🔴 en MRCAO, obtenido: '{alerta}'"

    def test_panel_df_alerta_roja_en_yca6o(self):
        """Fila YCA6O del panel debe tener emoji 🔴 en '⚠️ Próx. vto.'."""
        df = monitor_on_usd_panel_df()
        row = df[df["Ticker"] == "YCA6O"]
        assert not row.empty
        alerta = str(row.iloc[0]["⚠️ Próx. vto."])
        assert "🔴" in alerta, f"Esperado 🔴 en YCA6O, obtenido: '{alerta}'"

    def test_panel_df_alerta_vacia_en_instrumento_largo_plazo(self):
        """Instrumento con vencimiento lejano (PN43O, 2037) → alerta vacía."""
        df = monitor_on_usd_panel_df()
        row = df[df["Ticker"] == "PN43O"]
        assert not row.empty
        alerta = str(row.iloc[0]["⚠️ Próx. vto."])
        assert alerta == "", f"PN43O no debe tener alerta, obtenido: '{alerta}'"
