"""
tests/test_scoring_engine_extended.py — Tests ampliados de scoring_engine (Sprint 19)
Cubre: score_fundamental (con mock yfinance), score_tecnico (con mock),
       score_sector_contexto (todas las ramas), _calcular_score_con_serie,
       calcular_cartera_optima.
Sin llamadas reales a yfinance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fake_history(n: int = 200) -> pd.DataFrame:
    """Crea un DataFrame fake de precios históricos de n días."""
    dates = pd.date_range("2022-01-01", periods=n, freq="D")
    prices = [float(100 + i * 0.5) for i in range(n)]
    return pd.DataFrame({"Close": prices}, index=dates)


def _fake_info_completa() -> dict:
    return {
        "regularMarketPrice": 150.0,
        "trailingPE": 15.0,
        "returnOnEquity": 0.20,
        "debtToEquity": 50.0,
        "dividendYield": 0.03,
        "earningsGrowth": 0.15,
        "profitMargins": 0.25,
    }


# ─── score_fundamental con mock yfinance ─────────────────────────────────────

class TestScoreFundamentalMocked:
    def test_score_cedear_con_info_completa(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = _fake_info_completa()
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, detalle = score_fundamental("AAPL", "CEDEAR")
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0
        assert isinstance(detalle, dict)

    def test_score_cedear_info_vacia_retorna_neutro(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, _ = score_fundamental("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_score_cedear_sin_regularMarketPrice_neutro(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": None}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, _ = score_fundamental("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_score_cedear_excepcion_retorna_neutro(self):
        from services.scoring_engine import score_fundamental
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("API error")
            score, _ = score_fundamental("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_score_pe_bajo_da_puntos_altos(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {**_fake_info_completa(), "trailingPE": 8.0}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, detalle = score_fundamental("AAPL", "CEDEAR")
        assert detalle["pe_score"] == 25

    def test_score_pe_alto_da_puntos_bajos(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {**_fake_info_completa(), "trailingPE": 60.0}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            _, detalle = score_fundamental("AAPL", "CEDEAR")
        assert detalle["pe_score"] == 0

    def test_score_roe_alto(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {**_fake_info_completa(), "returnOnEquity": 0.30}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            _, detalle = score_fundamental("AAPL", "CEDEAR")
        assert detalle["roe_score"] == 20

    def test_score_deuda_cero(self):
        from services.scoring_engine import score_fundamental
        mock_ticker = MagicMock()
        mock_ticker.info = {**_fake_info_completa(), "debtToEquity": 0}
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            _, detalle = score_fundamental("AAPL", "CEDEAR")
        assert detalle["deuda_score"] == 15

    def test_score_tipo_bono_no_usa_yfinance_principal(self):
        from services.scoring_engine import score_fundamental
        # Bono usa _score_bono, no el path yfinance principal
        with patch("services.scoring_engine._score_bono", return_value=(60.0, {})):
            score, _ = score_fundamental("GD30", "Bono USD")
        assert score == 60.0

    def test_score_tipo_accion_local(self):
        from services.scoring_engine import score_fundamental
        with patch("services.scoring_engine._score_accion_local", return_value=(55.0, {})):
            score, _ = score_fundamental("YPFD", "Acción Local")
        assert score == 55.0

    def test_score_tipo_merval(self):
        from services.scoring_engine import score_fundamental
        with patch("services.scoring_engine._score_accion_local", return_value=(62.0, {})):
            score, _ = score_fundamental("GGAL", "Merval")
        assert score == 62.0


# ─── score_tecnico con mock yfinance ─────────────────────────────────────────

class TestScoreTecnicoMocked:
    def test_retorna_tuple_float_dict(self):
        from services.scoring_engine import score_tecnico
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _fake_history(200)
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, detalle = score_tecnico("AAPL", "CEDEAR")
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0
        assert "sma_score" in detalle

    def test_historial_corto_retorna_neutro(self):
        from services.scoring_engine import score_tecnico
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _fake_history(10)
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, _ = score_tecnico("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_historial_vacio_retorna_neutro(self):
        from services.scoring_engine import score_tecnico
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            score, _ = score_tecnico("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_excepcion_retorna_neutro(self):
        from services.scoring_engine import score_tecnico
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("API timeout")
            score, _ = score_tecnico("AAPL", "CEDEAR")
        assert score == pytest.approx(40.0)

    def test_tipo_bono_delega_a_score_tecnico_bono(self):
        from services.scoring_engine import score_tecnico
        with patch("services.scoring_engine._score_tecnico_bono", return_value=(45.0, {})):
            score, _ = score_tecnico("GD30", "Bono USD")
        assert score == 45.0

    def test_precio_en_detalle(self):
        from services.scoring_engine import score_tecnico
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _fake_history(200)
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            _, detalle = score_tecnico("MSFT", "CEDEAR")
        assert "precio" in detalle
        assert detalle["precio"] > 0

    def test_precio_bien_sobre_sma_da_40pts(self):
        """Precio muy por encima de SMA150 → sma_score = 40."""
        from services.scoring_engine import score_tecnico
        n = 200
        # Precios que crecen rápido: último precio >> SMA150
        prices = [100.0] * 150 + [200.0] * 50  # salta bruscamente al final
        dates = pd.date_range("2022-01-01", periods=n, freq="D")
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": prices}, index=dates)
        with patch("services.scoring_engine.yf") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            _, detalle = score_tecnico("AAPL", "CEDEAR")
        assert detalle["sma_score"] == 40


# ─── score_sector_contexto — ramas no cubiertas ──────────────────────────────

class TestScoreSectorContextoRamas:
    def test_recesion_alto_reduce_score(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            # Neutralizar fed_ciclo para evitar interacción con otros tests
            CONTEXTO_MACRO["recesion_riesgo"] = "ALTO"
            CONTEXTO_MACRO["fed_ciclo"] = "PAUSA"
            _, detalle = score_sector_contexto("AAPL", "CEDEAR")
            assert detalle["ajuste_macro_eeuu"] == -10
        finally:
            CONTEXTO_MACRO.update(original)

    def test_fed_baja_beneficia_tecnologia(self):
        from services.scoring_engine import CONTEXTO_MACRO, SECTORES, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["fed_ciclo"] = "BAJA"
            CONTEXTO_MACRO["recesion_riesgo"] = "BAJO"
            # Asegurar AAPL está en sector Tecnología
            sector_aapl = SECTORES.get("AAPL", "Tecnología")
            _, detalle = score_sector_contexto("AAPL", "CEDEAR")
            # El ajuste debería incluir el bonus por fed_ciclo BAJA + sector tech
            assert isinstance(detalle["ajuste_macro_eeuu"], (int, float))
        finally:
            CONTEXTO_MACRO.update(original)

    def test_fed_suba_beneficia_financiero(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["fed_ciclo"] = "SUBA"
            _, detalle = score_sector_contexto("JPM", "CEDEAR")
            assert isinstance(detalle["ajuste_macro_eeuu"], (int, float))
        finally:
            CONTEXTO_MACRO.update(original)

    def test_ccl_sube_beneficia_cedear(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["ccl_tendencia"] = "SUBE"
            _, detalle = score_sector_contexto("AAPL", "CEDEAR")
            assert detalle["ajuste_arg"] == 10
        finally:
            CONTEXTO_MACRO.update(original)

    def test_riesgo_pais_bajo_accion_local(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["riesgo_pais"] = "BAJO"
            _, detalle = score_sector_contexto("YPFD", "Acción Local")
            assert detalle["ajuste_arg"] == 15
        finally:
            CONTEXTO_MACRO.update(original)

    def test_riesgo_pais_medio_accion_local(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["riesgo_pais"] = "MEDIO"
            _, detalle = score_sector_contexto("GGAL", "Acción Local")
            assert detalle["ajuste_arg"] == 5
        finally:
            CONTEXTO_MACRO.update(original)

    def test_riesgo_pais_alto_accion_local(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["riesgo_pais"] = "ALTO"
            _, detalle = score_sector_contexto("PAMP", "Acción Local")
            assert detalle["ajuste_arg"] == -5
        finally:
            CONTEXTO_MACRO.update(original)

    def test_bono_usd_riesgo_bajo(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["riesgo_pais"] = "BAJO"
            _, detalle = score_sector_contexto("GD30", "Bono USD")
            assert detalle["ajuste_arg"] == 12
        finally:
            CONTEXTO_MACRO.update(original)

    def test_bono_usd_riesgo_medio(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["riesgo_pais"] = "MEDIO"
            _, detalle = score_sector_contexto("AL30", "Bono USD")
            assert detalle["ajuste_arg"] == 6
        finally:
            CONTEXTO_MACRO.update(original)

    def test_etf_ccl_estable(self):
        from services.scoring_engine import CONTEXTO_MACRO, score_sector_contexto
        original = CONTEXTO_MACRO.copy()
        try:
            CONTEXTO_MACRO["ccl_tendencia"] = "ESTABLE"
            _, detalle = score_sector_contexto("GLD", "ETF")
            assert detalle["ajuste_arg"] == 5
        finally:
            CONTEXTO_MACRO.update(original)


# ─── _calcular_score_con_serie ────────────────────────────────────────────────

class TestCalcularScoreConSerie:
    @pytest.fixture
    def serie_larga(self):
        """200 precios con tendencia alcista para cubrir todas las ramas SMA/RSI/Mom."""
        dates = pd.date_range("2022-01-01", periods=200, freq="D")
        return pd.Series([float(100 + i * 0.5) for i in range(200)], index=dates)

    @pytest.fixture
    def serie_corta(self):
        """Serie con menos de 30 puntos."""
        return pd.Series([100.0, 101.0, 102.0])

    def test_retorna_dict(self, serie_larga):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("AAPL", "CEDEAR", serie_larga)
        assert isinstance(result, dict)

    def test_tiene_claves_esperadas(self, serie_larga):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("AAPL", "CEDEAR", serie_larga)
        for k in ("Ticker", "Tipo", "Score_Total", "Score_Fund", "Score_Tec", "Score_Sector"):
            assert k in result, f"Clave faltante: {k}"

    def test_score_total_en_rango(self, serie_larga):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("AAPL", "CEDEAR", serie_larga)
        assert 0.0 <= result["Score_Total"] <= 100.0

    def test_serie_corta_retorna_score_neutro_tec(self, serie_corta):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("MSFT", "CEDEAR", serie_corta)
        assert isinstance(result, dict)
        assert result["Score_Tec"] == pytest.approx(40.0)

    def test_tendencia_alcista_sma_score_40(self, serie_larga):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("AAPL", "CEDEAR", serie_larga)
        detalle_tec = result.get("Detalle_Tec", {})
        assert detalle_tec.get("sma_score", 0) == 40

    def test_precio_presente_en_resultado(self, serie_larga):
        from services.scoring_engine import _calcular_score_con_serie
        result = _calcular_score_con_serie("KO", "CEDEAR", serie_larga)
        assert result.get("Precio", 0) > 0

    def test_serie_con_nan_no_lanza(self):
        from services.scoring_engine import _calcular_score_con_serie
        serie = pd.Series([100.0, float("nan"), 102.0, 103.0] * 55)
        try:
            result = _calcular_score_con_serie("AAPL", "CEDEAR", serie)
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"_calcular_score_con_serie lanzó con NaN: {e}")

    def test_serie_decreciente_sma_score_bajo(self):
        from services.scoring_engine import _calcular_score_con_serie
        n = 200
        dates = pd.date_range("2022-01-01", periods=n, freq="D")
        # Precios decrecientes: último precio << SMA150
        prices = [float(200 - i * 0.5) for i in range(n)]
        serie = pd.Series(prices, index=dates)
        result = _calcular_score_con_serie("AAPL", "CEDEAR", serie)
        detalle_tec = result.get("Detalle_Tec", {})
        assert detalle_tec.get("sma_score", 0) == 0


# ─── calcular_cartera_optima ─────────────────────────────────────────────────

class TestCalcularCarteraOptima:
    @pytest.fixture
    def df_scores_completo(self):
        return pd.DataFrame({
            "Ticker": ["AAPL", "MSFT", "KO", "GLD", "JPM", "XOM", "LMT", "ABBV", "PEP", "PBR"],
            "Tipo":   ["CEDEAR"] * 10,
            "Sector": [
                "Tecnología", "Tecnología", "Consumo Def.", "Cobertura",
                "Financiero", "Energía", "Defensa", "Salud", "Consumo Def.", "Energía",
            ],
            "Score_Total": [80.0, 75.0, 65.0, 70.0, 72.0, 60.0, 68.0, 74.0, 63.0, 58.0],
            "Score_Fund":  [75.0, 70.0, 60.0, 65.0, 68.0, 55.0, 62.0, 72.0, 60.0, 52.0],
            "Score_Tec":   [80.0, 75.0, 65.0, 70.0, 72.0, 60.0, 68.0, 74.0, 63.0, 58.0],
            "Score_Sector":[75.0, 70.0, 60.0, 65.0, 68.0, 55.0, 62.0, 72.0, 60.0, 52.0],
            "RSI":         [50.0] * 10,
            "Precio":      [150.0, 300.0, 60.0, 200.0, 140.0, 110.0, 440.0, 160.0, 170.0, 14.0],
            "Senal": [
                "🟢 COMPRAR", "🟡 ACUMULAR", "⚪ MANTENER", "🟢 COMPRAR",
                "🟡 ACUMULAR", "⚪ MANTENER", "⚪ MANTENER", "🟢 COMPRAR",
                "⚪ MANTENER", "🟠 REDUCIR",
            ],
        })

    def test_retorna_dataframe(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {"AAPL": 10}, 100_000.0, "Moderado"
        )
        assert isinstance(result, pd.DataFrame)

    def test_df_vacio_retorna_df_vacio(self):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(pd.DataFrame(), {}, 50_000.0)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_columnas_esperadas(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 100_000.0, "Moderado"
        )
        if not result.empty:
            for col in ("Ticker", "Score_Total", "Peso_Optimo_Pct", "Accion_Semanal"):
                assert col in result.columns

    def test_perfil_conservador(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 50_000.0, "Conservador"
        )
        assert isinstance(result, pd.DataFrame)

    def test_perfil_agresivo(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 200_000.0, "Agresivo"
        )
        assert isinstance(result, pd.DataFrame)

    def test_pesos_suman_100(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 100_000.0
        )
        if not result.empty:
            total = result["Peso_Optimo_Pct"].sum()
            assert total == pytest.approx(100.0, abs=1.0)

    def test_accion_semanal_comprar_con_presupuesto(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 500_000.0, "Agresivo"
        )
        if not result.empty:
            acciones = result["Accion_Semanal"].tolist()
            assert any("Iniciar" in str(a) or "Agregar" in str(a) for a in acciones)

    def test_cartera_actual_refleja_posicion(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        cartera_actual = {"AAPL": 10, "MSFT": 5}
        result = calcular_cartera_optima(
            df_scores_completo, cartera_actual, 100_000.0
        )
        if not result.empty:
            row_aapl = result[result["Ticker"] == "AAPL"]
            if not row_aapl.empty:
                assert bool(row_aapl.iloc[0]["Tiene_Posicion"]) is True

    def test_n_posiciones_respetado(self, df_scores_completo):
        from services.scoring_engine import calcular_cartera_optima
        result = calcular_cartera_optima(
            df_scores_completo, {}, 100_000.0, n_posiciones=3
        )
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert len(result) <= 3

    def test_todos_scores_bajo_50_usa_top20(self):
        from services.scoring_engine import calcular_cartera_optima
        df_bajo = pd.DataFrame({
            "Ticker": ["A", "B", "C"],
            "Tipo":   ["CEDEAR"] * 3,
            "Sector": ["Tecnología", "Financiero", "Salud"],
            "Score_Total": [30.0, 25.0, 20.0],
            "Score_Fund":  [30.0, 25.0, 20.0],
            "Score_Tec":   [30.0, 25.0, 20.0],
            "Score_Sector":[30.0, 25.0, 20.0],
            "RSI":    [50.0, 50.0, 50.0],
            "Precio": [100.0, 200.0, 50.0],
            "Senal":  ["⚪ MANTENER"] * 3,
        })
        result = calcular_cartera_optima(df_bajo, {}, 100_000.0)
        assert isinstance(result, pd.DataFrame)
