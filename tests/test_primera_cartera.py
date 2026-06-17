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
    from services.primera_cartera import (
        PRESUPUESTO_MAX_ARS,
        PRESUPUESTO_MIN_ARS,
        presupuesto_semana,
    )

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
    from services.primera_cartera import (
        calcular_unidades,
        generar_narrativa_semana,
        seleccionar_recomendaciones,
    )

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
    from services.primera_cartera import (
        calcular_unidades,
        generar_narrativa_semana,
        seleccionar_recomendaciones,
    )
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


# ─── Tests para _ficha_fundamentals ──────────────────────────────────────────

def _fake_yf_info_cedear():
    return {
        "trailingPE": 24.5,
        "returnOnEquity": 0.32,
        "debtToEquity": 55.0,
        "dividendYield": 0.0085,
        "earningsGrowth": 0.12,
        "revenueGrowth": 0.08,
        "profitMargins": 0.235,
        "beta": 1.15,
        "marketCap": 3_000_000_000_000,
        "targetMeanPrice": 230.0,
        "numberOfAnalystOpinions": 40,
        "regularMarketPrice": 195.0,
        "sector": "Technology",
    }


def _make_mock_ticker(info_dict):
    mock_t = MagicMock()
    mock_t.info = info_dict
    return mock_t


@patch("services.primera_cartera._precio_ars_actual", return_value=38_000.0)
def test_ficha_fundamentals_cedear_consenso(mock_px):
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    with patch.object(yf, "Ticker", return_value=_make_mock_ticker(_fake_yf_info_cedear())):
        fund = _ficha_fundamentals("AAPL", "CEDEAR", 1200.0)

    assert fund["pe_ratio"] == pytest.approx(24.5)
    assert fund["roe_pct"] == pytest.approx(32.0, rel=0.01)
    assert fund["deuda_capital_pct"] == pytest.approx(55.0)
    assert fund["div_yield_pct"] == pytest.approx(0.85, rel=0.01)
    assert fund["eps_growth_pct"] == pytest.approx(12.0, rel=0.01)
    assert fund["profit_margin_pct"] == pytest.approx(23.5, rel=0.01)
    assert fund["beta"] == pytest.approx(1.15)
    assert fund["n_analistas"] == 40
    assert fund["fuente_objetivo"] == "consenso 40 analistas"
    assert fund["objetivo_salida_usd"] == pytest.approx(230.0)
    assert fund["horizonte_meses"] == 12
    # ARS = target_usd * ratio * ccl; AAPL ratio = 1 (from RATIOS_CEDEAR)
    assert fund["objetivo_salida_ars"] is not None and fund["objetivo_salida_ars"] > 0
    # upside computable porque precio_ars > 0
    assert fund["upside_pct"] is not None


@patch("services.primera_cartera._precio_ars_actual", return_value=0.0)
def test_ficha_fundamentals_sin_analistas_usa_eps(mock_px):
    """Con <3 analistas cae a proyeccion_eps."""
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    info = dict(_fake_yf_info_cedear())
    info["numberOfAnalystOpinions"] = 1
    info["targetMeanPrice"] = 250.0  # ignorado por <3 analistas

    with patch.object(yf, "Ticker", return_value=_make_mock_ticker(info)):
        fund = _ficha_fundamentals("AAPL", "CEDEAR", 1000.0)

    assert fund["fuente_objetivo"] == "proyeccion_eps"
    assert fund["objetivo_salida_usd"] is not None
    # Con eps_growth=12% + quality_mult > precio actual → target > precio
    assert fund["objetivo_salida_usd"] > info["regularMarketPrice"]


@patch("services.primera_cartera._precio_ars_actual", return_value=0.0)
def test_ficha_fundamentals_sin_eps_usa_flat8(mock_px):
    """Sin EPS growth ni analistas suficientes → flat+8%."""
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    info = {
        "regularMarketPrice": 100.0,
        "numberOfAnalystOpinions": 0,
        "targetMeanPrice": None,
    }

    with patch.object(yf, "Ticker", return_value=_make_mock_ticker(info)):
        fund = _ficha_fundamentals("SPY", "CEDEAR", 1000.0)

    assert fund["fuente_objetivo"] == "flat+8pct"
    assert fund["objetivo_salida_usd"] == pytest.approx(108.0)


@patch("services.primera_cartera._precio_ars_actual", return_value=0.0)
def test_ficha_fundamentals_sin_precio_no_target(mock_px):
    """Sin regularMarketPrice → objetivo_salida_ars es None."""
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    with patch.object(yf, "Ticker", return_value=_make_mock_ticker({})):
        fund = _ficha_fundamentals("AAPL", "CEDEAR", 1200.0)

    assert fund["objetivo_salida_usd"] is None
    assert fund["objetivo_salida_ars"] is None
    assert fund["upside_pct"] is None


@patch("services.primera_cartera._precio_ars_actual", return_value=0.0)
def test_ficha_fundamentals_yfinance_falla_devuelve_dict(mock_px):
    """Si yfinance lanza excepción → devuelve dict con Nones (no explota)."""
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    mock_t = MagicMock()
    mock_t.info = MagicMock(side_effect=Exception("timeout"))

    with patch.object(yf, "Ticker", return_value=mock_t):
        fund = _ficha_fundamentals("AAPL", "CEDEAR", 1000.0)

    assert isinstance(fund, dict)
    assert "pe_ratio" in fund
    assert "objetivo_salida_ars" in fund


@patch("services.primera_cartera._precio_ars_actual", return_value=999_999_999.0)
def test_ficha_fundamentals_upside_negativo_es_permitido(mock_px):
    """Si precio_ars_actual >> objetivo_ars → upside negativo es válido."""
    import yfinance as yf

    from services.primera_cartera import _ficha_fundamentals

    info = {
        "regularMarketPrice": 200.0,
        "numberOfAnalystOpinions": 5,
        "targetMeanPrice": 50.0,
        "sector": "Consumo",
    }

    with patch.object(yf, "Ticker", return_value=_make_mock_ticker(info)):
        fund = _ficha_fundamentals("KO", "CEDEAR", 100.0)

    assert fund["fuente_objetivo"] == "consenso 5 analistas"
    assert fund["upside_pct"] is not None
    assert fund["upside_pct"] < 0  # precio actual mucho mayor que objetivo


# ─── Tests para _tesis_inversion ─────────────────────────────────────────────

import pytest


def _sc(score=72, rsi=45, senal="ACUMULAR"):
    return {"Score_Total": score, "RSI": rsi, "Senal": senal}


def _fund(pe=18.0, roe=22.0, dce=40.0, div=1.5, eps_g=10.0, rev_g=8.0,
          margin=15.0, obj_ars=50_000.0, upside=15.0, horizonte=12,
          fuente="consenso 20 analistas"):
    return {
        "pe_ratio": pe,
        "roe_pct": roe,
        "deuda_capital_pct": dce,
        "div_yield_pct": div,
        "eps_growth_pct": eps_g,
        "rev_growth_pct": rev_g,
        "profit_margin_pct": margin,
        "objetivo_salida_ars": obj_ars,
        "upside_pct": upside,
        "horizonte_meses": horizonte,
        "fuente_objetivo": fuente,
    }


def test_tesis_es_string_no_vacio():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund())
    assert isinstance(t, str) and len(t) > 20


def test_tesis_menciona_pe():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(pe=10.0))
    assert "P/E" in t or "10" in t


def test_tesis_pe_atractivo():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(pe=9.0))
    assert "descuento" in t.lower() or "atractiv" in t.lower()


def test_tesis_pe_elevado():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(pe=50.0))
    assert "elevad" in t.lower() or "expectativas" in t.lower()


def test_tesis_roe_excepcional():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(roe=40.0))
    assert "excepcional" in t.lower() or "ventaja" in t.lower()


def test_tesis_deuda_alta():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(dce=120.0))
    assert "monitorear" in t.lower() or "vigilar" in t.lower() or "alto" in t.lower()


def test_tesis_rsi_sobrevendido():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(rsi=28), _fund())
    assert "sobrevendido" in t.lower() or "reversión" in t.lower()


def test_tesis_con_objetivo_positivo():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(), _fund(obj_ars=60_000.0, upside=25.0))
    assert "25" in t or "Objetivo" in t


def test_tesis_sin_datos_devuelve_fallback():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("AAPL", "CEDEAR", _sc(score=55), {})
    assert isinstance(t, str) and len(t) > 5
    assert "55" in t  # fallback menciona score


def test_tesis_dividendo_aparece():
    from services.primera_cartera import _tesis_inversion

    t = _tesis_inversion("KO", "CEDEAR", _sc(), _fund(div=3.5))
    assert "3.5" in t or "dividend" in t.lower() or "yield" in t.lower()


# ─── Tests narrativa enriquecida ──────────────────────────────────────────────

@patch("services.primera_cartera._variacion_30d", return_value=5.0)
@patch("services.primera_cartera._precio_ars_actual", return_value=1500.0)
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
@patch("services.primera_cartera._ficha_fundamentals")
@patch("services.primera_cartera._tesis_inversion", return_value="Tesis de ejemplo.")
def test_narrativa_incluye_fundamentals_y_tesis(
    mock_tesis, mock_fund, mock_score, _mock_px, _mock_var
):
    """Items en la narrativa deben tener las claves 'fundamentals' y 'tesis'."""
    mock_fund.return_value = {
        "pe_ratio": 20.0, "roe_pct": 18.0, "objetivo_salida_ars": 55_000.0,
        "upside_pct": 12.0, "horizonte_meses": 12, "fuente_objetivo": "proyeccion_eps",
    }
    from services.primera_cartera import (
        calcular_unidades,
        generar_narrativa_semana,
        seleccionar_recomendaciones,
    )

    recs = seleccionar_recomendaciones(1000.0, n=2, min_score=40.0)
    u = calcular_unidades(80_000.0, recs)
    narr = generar_narrativa_semana(u, 80_000.0, 1000.0, fecha=date(2026, 4, 7))

    for it in narr["items"]:
        assert "fundamentals" in it, "falta clave 'fundamentals'"
        assert isinstance(it["fundamentals"], dict)
        assert "tesis" in it, "falta clave 'tesis'"
        assert isinstance(it["tesis"], str)


@patch("services.primera_cartera._variacion_30d", return_value=0.0)
@patch("services.primera_cartera._precio_ars_actual", return_value=1000.0)
@patch("services.scoring_engine.calcular_score_total", side_effect=_fake_score)
@patch("services.primera_cartera._ficha_fundamentals", side_effect=Exception("yf timeout"))
def test_narrativa_fundamentals_falla_gracioso(mock_fund, mock_score, _px, _var):
    """Si _ficha_fundamentals lanza → item igual incluye 'fundamentals': {} y 'tesis': ''."""
    from services.primera_cartera import (
        calcular_unidades,
        generar_narrativa_semana,
        seleccionar_recomendaciones,
    )

    recs = seleccionar_recomendaciones(1000.0, n=1, min_score=40.0)
    u = calcular_unidades(50_000.0, recs)
    narr = generar_narrativa_semana(u, 50_000.0, 1000.0, fecha=date(2026, 4, 7))

    for it in narr["items"]:
        assert "fundamentals" in it
        assert it["fundamentals"] == {}
        assert it["tesis"] == ""


# ─── Tests para generar_primera_cartera() ─────────────────────────────────────

# Precios mínimos que permiten comprar al menos 1 unidad de cada ticker
_PRECIOS_TEST: dict[str, float] = {
    "PN43O":  1_500.0,
    "TLCTO":  1_500.0,
    "GLD":   12_800.0,
    "BRKB":  31_000.0,
    "SPY":   48_000.0,
    "MSFT":  18_500.0,
    "NVDA":  15_000.0,
    "META":  37_000.0,
    "AMZN":   2_750.0,
    "GOOGL": 22_000.0,
    "AAPL":  18_500.0,
    "MELI":  22_000.0,
    "KO":    22_540.0,
    "GGAL":   3_500.0,
    "YPFD":  55_000.0,
    "VIST":  28_740.0,
    "JNJ":   15_200.0,
    "VZ":     9_800.0,
    "PG":    18_400.0,
    "PLTR":   8_500.0,
    "IVW":   32_000.0,
}


def _gpc(capital=1_000_000.0, perfil="Moderado", ccl=1_200.0, precios=None):
    """Shortcut para llamar generar_primera_cartera en tests."""
    from services.recomendacion_capital import generar_primera_cartera

    return generar_primera_cartera(
        capital_ars=capital,
        perfil=perfil,
        ccl=ccl,
        precios_dict=precios if precios is not None else dict(_PRECIOS_TEST),
    )


def test_gpc_retorna_recomendacion_result():
    from core.diagnostico_types import RecomendacionResult

    rr = _gpc()
    assert isinstance(rr, RecomendacionResult)


def test_gpc_tiene_compras():
    rr = _gpc()
    assert len(rr.compras_recomendadas) >= 1


def test_gpc_no_critica_prioridad():
    """Primera cartera: ningún ítem debe tener prioridad CRITICA."""
    from core.diagnostico_types import PrioridadAccion

    rr = _gpc()
    for item in rr.compras_recomendadas:
        assert item.prioridad != PrioridadAccion.CRITICA, (
            f"Ticker {item.ticker} tiene prioridad CRITICA — no debería en primera cartera"
        )


def test_gpc_todos_activos_nuevos():
    """Primera cartera: es_activo_nuevo debe ser True para todos."""
    rr = _gpc()
    for item in rr.compras_recomendadas:
        assert item.es_activo_nuevo is True


def test_gpc_pct_defensivo_pre_cero():
    """Cartera nueva: pct_defensivo_pre siempre 0."""
    rr = _gpc()
    assert rr.pct_defensivo_pre == pytest.approx(0.0)


def test_gpc_capital_no_excede_disponible():
    """Total comprado ≤ capital aportado."""
    capital = 500_000.0
    rr = _gpc(capital=capital)
    total_gastado = sum(i.monto_ars for i in rr.compras_recomendadas)
    assert total_gastado <= capital + 1.0  # tolerancia 1 ARS por redondeo entero


def test_gpc_remanente_coherente():
    """
    Coherencia: capital_remanente_ars + capital_usado_ars == capital_disponible_ars.
    El pool de perlas (20%) está incluido en capital_remanente_ars (es cash reservado).
    """
    rr = _gpc(capital=800_000.0)
    total = rr.capital_remanente_ars + rr.capital_usado_ars
    assert total == pytest.approx(rr.capital_disponible_ars, abs=1.0)


def test_gpc_sin_tickers_bloqueados():
    """ADM, GIS, CMCSA nunca deben aparecer en primera cartera."""
    from config import TICKERS_NO_CEDEAR_BYMA

    rr = _gpc(capital=5_000_000.0)
    tickers_comprados = {i.ticker for i in rr.compras_recomendadas}
    bloqueados_presentes = tickers_comprados & TICKERS_NO_CEDEAR_BYMA
    assert not bloqueados_presentes, (
        f"Tickers bloqueados en primera cartera: {bloqueados_presentes}"
    )


def test_gpc_incluye_rf_cuando_hay_precio():
    """Con precios válidos para PN43O/TLCTO, al menos uno debe aparecer en compras."""
    from core.renta_fija_ar import es_renta_fija

    rr = _gpc(capital=1_000_000.0, perfil="Conservador")
    tickers_rf = [i.ticker for i in rr.compras_recomendadas if es_renta_fija(i.ticker)]
    assert len(tickers_rf) >= 1, (
        "Primera cartera (Conservador) debería incluir renta fija cotizable cuando hay precio"
    )


def test_gpc_rf_pendiente_cuando_sin_precio():
    """Sin precios para PN43O/TLCTO (ni en dict ni en fallback) → RF va a pendientes."""
    precios_sin_rf = {k: v for k, v in _PRECIOS_TEST.items() if k not in ("PN43O", "TLCTO")}
    # Patch _enriquecer_precios_recomendacion para devolver exactamente el dict sin RF,
    # evitando que el fallback ARS llene automáticamente PN43O/TLCTO.
    with patch(
        "services.recomendacion_capital._enriquecer_precios_recomendacion",
        return_value=dict(precios_sin_rf),
    ):
        from services.recomendacion_capital import generar_primera_cartera

        rr = generar_primera_cartera(
            capital_ars=1_000_000.0,
            perfil="Conservador",
            ccl=1_200.0,
            precios_dict=dict(precios_sin_rf),
        )
    tickers_pendientes = [p["ticker"] for p in rr.pendientes_proxima_inyeccion]
    # Debe aparecer _RENTA_AR o alguno de los RF como pendiente
    tiene_rf_pendiente = any(
        t in ("_RENTA_AR", "PN43O", "TLCTO") for t in tickers_pendientes
    )
    assert tiene_rf_pendiente


def test_gpc_capital_cero_devuelve_vacio():
    rr = _gpc(capital=0.0)
    assert rr.compras_recomendadas == []
    assert rr.capital_disponible_ars == pytest.approx(0.0)


def test_gpc_ccl_invalido_retorna_alerta():
    rr = _gpc(ccl=0.0)
    assert rr.alerta_mercado is True
    assert rr.compras_recomendadas == []


def test_gpc_justificaciones_no_usan_deficit_lenguaje():
    """Ninguna justificación debe contener lenguaje de 'deficit' / 'peso objetivo +X pp'."""
    rr = _gpc(capital=2_000_000.0)
    for item in rr.compras_recomendadas:
        jus = (item.justificacion or "").lower()
        assert "peso objetivo" not in jus, (
            f"Ticker {item.ticker}: justificación usa lenguaje de déficit: '{item.justificacion}'"
        )
        assert "pp en " not in jus, (
            f"Ticker {item.ticker}: justificación usa '+X pp': '{item.justificacion}'"
        )


def test_gpc_perfil_muy_arriesgado_incluye_tecnologia():
    """Perfil Muy arriesgado debe incluir al menos un ticker de tecnología (NVDA/META/MSFT/etc.)."""
    TECH = {"NVDA", "META", "MSFT", "GOOGL", "AAPL", "AMZN", "PLTR"}
    rr = _gpc(capital=3_000_000.0, perfil="Muy arriesgado")
    tickers = {i.ticker for i in rr.compras_recomendadas}
    assert tickers & TECH, f"Sin tecnología en Muy arriesgado: {tickers}"


def test_gpc_unidades_enteras():
    """Todas las unidades deben ser enteros >= 1."""
    rr = _gpc()
    for item in rr.compras_recomendadas:
        assert isinstance(item.unidades, int)
        assert item.unidades >= 1
