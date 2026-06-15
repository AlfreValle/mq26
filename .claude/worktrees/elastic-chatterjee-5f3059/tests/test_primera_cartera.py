"""Tests motor Primera Cartera (mocks yfinance/scoring)."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

def test_numero_semana_del_año():
    from services.primera_cartera import numero_semana_del_año

    assert numero_semana_del_año(date(2026, 1, 5)) == 2  # lunes
    assert numero_semana_del_año(date(2026, 12, 31)) >= 52


def test_presupuesto_semana_rango():
    from services.primera_cartera import PRESUPUESTO_MAX_ARS, PRESUPUESTO_MIN_ARS, presupuesto_semana

    for w in range(1, 60):
        p = presupuesto_semana(w)
        assert PRESUPUESTO_MIN_ARS <= p <= PRESUPUESTO_MAX_ARS + 0.01


def _fake_score(ticker: str, tipo: str):
    base = {"AAPL": 80, "KO": 70, "GLD": 65, "YPFD": 62, "CEPU": 60}.get(ticker, 55)
    return {
        "Ticker": ticker,
        "Tipo": tipo,
        "Sector": "Test",
        "Score_Total": float(base),
        "RSI": 38 if ticker == "AAPL" else 50,
        "Senal": "🟡 ACUMULAR",
        "Detalle_Tec": {},
        "Detalle_Fund": {},
        "Detalle_Sector": {},
    }


@patch("services.primera_cartera._variacion_30d", return_value=-2.5)
@patch("services.primera_cartera._precio_ars_actual", side_effect=lambda t, _tipo, _ccl: {"AAPL": 1000, "KO": 500, "GLD": 2000, "YPFD": 300}.get(t, 100))
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
def test_seleccionar_recomendaciones_diversifica_y_n(mock_score, _mock_px, _mock_var):
    from services import primera_cartera as pc

    recs = pc.seleccionar_recomendaciones(1450.0, n=3, min_score=45.0)
    assert len(recs) == 3
    cats = [r["categoria"] for r in recs]
    assert len(set(cats)) >= 2
    assert {r["ticker"] for r in recs} == {r["ticker"] for r in recs}  # únicos
    assert len({r["ticker"] for r in recs}) == 3


@patch("services.primera_cartera._variacion_30d", return_value=0.0)
@patch("services.primera_cartera._precio_ars_actual", return_value=2500.0)
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
def test_calcular_unidades(mock_score, _mock_px, _mock_var):
    from services.primera_cartera import calcular_unidades, seleccionar_recomendaciones

    recs = seleccionar_recomendaciones(1500.0, n=2, min_score=40.0)
    with_u = calcular_unidades(80_000.0, recs)
    assert len(with_u) == 2
    assert with_u[0]["unidades"] >= 1


@patch("services.primera_cartera._variacion_30d", return_value=-4.0)
@patch("services.primera_cartera._precio_ars_actual", return_value=1000.0)
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
def test_generar_narrativa_campos(mock_score, _mock_px, _mock_var):
    from services.primera_cartera import calcular_unidades, generar_narrativa_semana, seleccionar_recomendaciones

    recs = seleccionar_recomendaciones(1200.0, n=2, min_score=40.0)
    u = calcular_unidades(90_000.0, recs)
    narr = generar_narrativa_semana(u, 90_000.0, 1200.0, nota_admin="Ojo comisiones", fecha=date(2026, 4, 2))
    assert narr["anio"] == 2026
    assert narr["semana"] == int(date(2026, 4, 2).isocalendar()[1])
    assert "items" in narr and len(narr["items"]) == 2
    for it in narr["items"]:
        assert "var_txt" in it and "rsi_txt" in it
    assert "Ojo comisiones" in narr["resumen_ejecutivo"]


@patch("services.primera_cartera._variacion_30d", return_value=0.0)
@patch("services.primera_cartera._precio_ars_actual", return_value=500.0)
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
def test_generar_html_largo_y_escape(mock_score, _mock_px, _mock_var):
    from services.primera_cartera import calcular_unidades, generar_narrativa_semana, seleccionar_recomendaciones
    from services.reporte_primera_cartera import generar_html_semana

    recs = seleccionar_recomendaciones(1000.0, n=1, min_score=40.0)
    u = calcular_unidades(50_000.0, recs)
    narr = generar_narrativa_semana(u, 50_000.0, 1000.0, nota_admin='<script>x</script>', fecha=date(2026, 4, 2))
    html = generar_html_semana(narr)
    assert len(html) > 500
    assert "<script>" not in html
    assert "&lt;script&gt;" in html or "script" not in html.lower()


def test_guardar_y_cargar_recomendacion_fake():
    store: dict[str, str] = {}

    def fake_guardar(clave, valor, audit_user=""):
        store[clave] = valor if isinstance(valor, str) else json.dumps(valor)

    def fake_obtener(clave, default=None):
        if clave not in store:
            return default
        raw = store[clave]
        try:
            return json.loads(raw)
        except Exception:
            return raw

    payload = {
        "anio": 2026,
        "semana": 14,
        "fecha_generacion": "2026-04-02",
        "presupuesto_ars": 80000,
        "ccl": 1400.0,
        "nota": "",
        "items": [{"ticker": "X", "unidades": 1}],
        "resumen_ejecutivo": "test",
        "disclaimer": "d",
    }
    raw = json.dumps(payload, ensure_ascii=False)

    with patch("services.primera_cartera.dbm.guardar_config", side_effect=fake_guardar):
        with patch("services.primera_cartera.dbm.obtener_config", side_effect=fake_obtener):
            from services.primera_cartera import (
                CLAVE_ACTIVA,
                cargar_recomendacion_activa,
                guardar_recomendacion,
            )

            guardar_recomendacion(payload)
            assert CLAVE_ACTIVA in store
            got = cargar_recomendacion_activa()
            assert got is not None
            assert got["items"][0]["ticker"] == "X"


def test_historial_sql_parsea_filas():
    from services.primera_cartera import historial_recomendaciones

    row1 = (
        "primera_cartera_2026_s14",
        json.dumps({"anio": 2026, "semana": 14, "items": []}, ensure_ascii=False),
    )
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [row1]
    mock_s = MagicMock()
    mock_s.execute.return_value = mock_result
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_s
    mock_ctx.__exit__.return_value = None

    with patch("services.primera_cartera.dbm.get_session", return_value=mock_ctx):
        hist = historial_recomendaciones(2026)
    assert len(hist) == 1
    assert hist[0]["semana"] == 14
    assert hist[0]["_clave_config"] == "primera_cartera_2026_s14"


def test_construir_payload_completo_none_si_vacio():
    with patch("services.primera_cartera.seleccionar_recomendaciones", return_value=[]):
        from services.primera_cartera import construir_payload_completo

        assert construir_payload_completo(1000.0) is None


def test_import_seleccionar():
    from services.primera_cartera import seleccionar_recomendaciones

    assert callable(seleccionar_recomendaciones)
