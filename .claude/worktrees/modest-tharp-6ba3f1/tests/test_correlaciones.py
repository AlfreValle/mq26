"""
tests/test_correlaciones.py — Tests de services/correlaciones.py (Sprint 19)
correlaciones.py importa streamlit; la descarga pasa por core.cache_manager (yfinance dentro).
- calcular_matriz_correlacion: función 100% pura (pandas), se testea directamente.
- obtener_retornos_historicos: mockea yfinance.download (invocado desde cache_manager).
Sin red. Sin Streamlit runtime (render_* mockea st).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── calcular_matriz_correlacion (función pura) ───────────────────────────────

class TestCalcularMatrizCorrelacion:
    @pytest.fixture
    def df_retornos(self):
        """DataFrame de retornos diarios simulados para 3 activos."""
        np.random.seed(42)
        n = 50
        data = {
            "AAPL": np.random.normal(0.001, 0.02, n),
            "MSFT": np.random.normal(0.001, 0.02, n),
            "KO":   np.random.normal(0.0005, 0.01, n),
        }
        return pd.DataFrame(data, index=pd.date_range("2024-01-01", periods=n))

    def test_importa_sin_error(self):
        from services.correlaciones import calcular_matriz_correlacion
        assert callable(calcular_matriz_correlacion)

    def test_retorna_dataframe(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        assert isinstance(result, pd.DataFrame)

    def test_dimension_cuadrada(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        n = len(df_retornos.columns)
        assert result.shape == (n, n)

    def test_diagonal_es_uno(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        for i in range(len(result)):
            assert result.iloc[i, i] == pytest.approx(1.0)

    def test_simetrica(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        assert result.equals(result.T)

    def test_valores_en_rango_menos1_a_1(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        assert result.values.min() >= -1.0 - 1e-9
        assert result.values.max() <= 1.0 + 1e-9

    def test_correlacion_perfecta_misma_serie(self):
        from services.correlaciones import calcular_matriz_correlacion
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        df = pd.DataFrame({"A": s, "B": s})
        result = calcular_matriz_correlacion(df)
        assert result.loc["A", "B"] == pytest.approx(1.0)

    def test_columnas_preservadas(self, df_retornos):
        from services.correlaciones import calcular_matriz_correlacion
        result = calcular_matriz_correlacion(df_retornos)
        assert list(result.columns) == list(df_retornos.columns)
        assert list(result.index) == list(df_retornos.columns)


# ─── obtener_retornos_historicos (mockea yfinance) ───────────────────────────

class TestObtenerRetornosHistoricos:
    def test_importa_sin_error(self):
        from services.correlaciones import obtener_retornos_historicos
        assert callable(obtener_retornos_historicos)

    def test_retorna_dataframe_vacio_si_yfinance_falla(self):
        from services.correlaciones import obtener_retornos_historicos
        with patch("yfinance.download", side_effect=Exception("timeout")):
            result = obtener_retornos_historicos(["AAPL", "MSFT"], "1y")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_retorna_dataframe_con_datos_mockeados(self):
        from services.correlaciones import obtener_retornos_historicos
        n = 20
        mock_data = pd.DataFrame(
            {
                "AAPL": 100.0 + np.random.randn(n).cumsum(),
                "MSFT": 200.0 + np.random.randn(n).cumsum(),
            },
            index=pd.date_range("2024-01-01", periods=n),
        )
        with patch("yfinance.download", return_value={"Close": mock_data}):
            result = obtener_retornos_historicos(["AAPL", "MSFT"], "1mo")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert list(result.columns) == ["AAPL", "MSFT"]

    def test_close_como_series_un_solo_activo(self):
        from services.correlaciones import obtener_retornos_historicos

        mock_close = pd.Series(
            [100.0, 101.0, 99.5, 102.0],
            index=pd.date_range("2024-01-01", periods=4, freq="B"),
        )
        with patch("yfinance.download", return_value={"Close": mock_close}):
            result = obtener_retornos_historicos(["GGAL"], "3mo")
        assert list(result.columns) == ["GGAL"]
        assert len(result) >= 1

    def test_mapeo_brkb_a_ticker_yahoo(self):
        from services.correlaciones import obtener_retornos_historicos

        mock_data = pd.DataFrame({"x": [1.0, 1.1]}, index=pd.date_range("2024-01-01", periods=2))
        with patch("yfinance.download") as dl:
            dl.return_value = {"Close": mock_data}
            obtener_retornos_historicos(["BRKB"], "1y")
        assert dl.call_args[0][0] == ["BRK-B"]

    def test_mapeo_cepu_ba(self):
        from services.correlaciones import obtener_retornos_historicos

        mock_data = pd.DataFrame({"x": [1.0, 1.1]}, index=pd.date_range("2024-01-01", periods=2))
        with patch("yfinance.download") as dl:
            dl.return_value = {"Close": mock_data}
            obtener_retornos_historicos(["CEPU"], "1y")
        assert dl.call_args[0][0] == ["CEPU.BA"]


class TestCorrelacionesFuncionesPuras:
    def test_alertas_detecta_alta_correlacion(self):
        from services.correlaciones import alertas_pares_correlacion

        corr = pd.DataFrame([[1.0, 0.9], [0.9, 1.0]], index=["A", "B"], columns=["A", "B"])
        df_a = alertas_pares_correlacion(corr, umbral=0.75)
        assert len(df_a) == 1
        assert "A" in df_a.iloc[0]["Par"] and "B" in df_a.iloc[0]["Par"]

    def test_resumen_promedio_roles(self):
        from services.correlaciones import resumen_correlacion_promedio

        corr = pd.DataFrame(
            [[1.0, 0.2, 0.85], [0.2, 1.0, 0.3], [0.85, 0.3, 1.0]],
            index=["L", "M", "H"],
            columns=["L", "M", "H"],
        )
        r = resumen_correlacion_promedio(corr)
        assert set(r["Ticker"]) == {"L", "M", "H"}
        assert "Rol" in r.columns

    def test_alertas_matriz_un_activo_vacia(self):
        from services.correlaciones import alertas_pares_correlacion

        corr = pd.DataFrame([[1.0]], index=["Solo"], columns=["Solo"])
        df_a = alertas_pares_correlacion(corr)
        assert df_a.empty
        assert list(df_a.columns) == ["Par", "Correlación", "Tipo", "Riesgo"]

    def test_alertas_sin_pares_sobre_umbral(self):
        from services.correlaciones import alertas_pares_correlacion

        corr = pd.DataFrame(
            [[1.0, 0.1, 0.2], [0.1, 1.0, 0.15], [0.2, 0.15, 1.0]],
            index=["a", "b", "c"],
            columns=["a", "b", "c"],
        )
        assert alertas_pares_correlacion(corr, umbral=0.75).empty

    def test_alertas_anticorrelacion_fuerte(self):
        from services.correlaciones import alertas_pares_correlacion

        corr = pd.DataFrame([[1.0, -0.82], [-0.82, 1.0]], index=["A", "B"], columns=["A", "B"])
        df_a = alertas_pares_correlacion(corr, umbral=0.75)
        assert len(df_a) == 1
        assert "Anticorrelado" in df_a.iloc[0]["Tipo"]

    def test_resumen_corr_vacia(self):
        from services.correlaciones import resumen_correlacion_promedio

        r = resumen_correlacion_promedio(pd.DataFrame())
        assert r.empty
        assert list(r.columns) == ["Ticker", "Corr. promedio", "Rol"]

    def test_resumen_roles_neutral_o_concentrador(self):
        from services.correlaciones import resumen_correlacion_promedio

        corr = pd.DataFrame(
            [[1.0, 0.5, 0.5], [0.5, 1.0, 0.5], [0.5, 0.5, 1.0]],
            index=["x", "y", "z"],
            columns=["x", "y", "z"],
        )
        roles = set(resumen_correlacion_promedio(corr)["Rol"])
        assert any("Neutral" in x or "Concentrador" in x for x in roles)


class TestRenderHeatmapCorrelaciones:
    @pytest.fixture
    def mock_st(self):
        col2 = MagicMock()
        col2.__enter__ = MagicMock(return_value=None)
        col2.__exit__ = MagicMock(return_value=False)
        spin = MagicMock()
        spin.__enter__ = MagicMock(return_value=None)
        spin.__exit__ = MagicMock(return_value=False)
        m = MagicMock()
        m.columns.return_value = (MagicMock(), col2)
        m.spinner.return_value = spin
        m.selectbox.return_value = "1y"
        return m

    @patch("services.correlaciones.go")
    @patch("services.correlaciones.obtener_retornos_historicos")
    def test_render_retorna_corr_y_plotly(self, mock_obt, mock_go, mock_st):
        from services.correlaciones import render_heatmap_correlaciones

        n, rng = 15, np.random.default_rng(0)
        ret = pd.DataFrame(
            {"T1": rng.normal(0, 0.01, n), "T2": rng.normal(0, 0.01, n)},
            index=pd.date_range("2024-01-01", periods=n, freq="B"),
        )
        mock_obt.return_value = ret
        mock_go.Figure.return_value = MagicMock()
        with patch("services.correlaciones.st", mock_st):
            out = render_heatmap_correlaciones(["T1", "T2"], pesos={"T1": 0.5, "T2": 0.5})
        assert out.shape == (2, 2)
        mock_st.plotly_chart.assert_called_once()
        mock_st.dataframe.assert_called()
        mock_go.Figure.assert_called_once()

    @patch("services.correlaciones.obtener_retornos_historicos")
    def test_render_vacio_warning(self, mock_obt, mock_st):
        from services.correlaciones import render_heatmap_correlaciones

        mock_obt.return_value = pd.DataFrame()
        with patch("services.correlaciones.st", mock_st):
            assert render_heatmap_correlaciones(["A", "B"]) is None
        mock_st.warning.assert_called_once()

    @patch("services.correlaciones.obtener_retornos_historicos")
    def test_render_una_columna_warning(self, mock_obt, mock_st):
        from services.correlaciones import render_heatmap_correlaciones

        mock_obt.return_value = pd.DataFrame({"Z": [0.01, -0.02]})
        with patch("services.correlaciones.st", mock_st):
            assert render_heatmap_correlaciones(["Z", "X"]) is None
        mock_st.warning.assert_called_once()

    @patch("services.correlaciones.go")
    @patch("services.correlaciones.obtener_retornos_historicos")
    def test_render_rama_success_diversificado(self, mock_obt, mock_go, mock_st):
        from services.correlaciones import render_heatmap_correlaciones

        n, rng = 40, np.random.default_rng(42)
        ret = pd.DataFrame(
            {"P": rng.normal(0, 0.02, n), "Q": rng.normal(0, 0.02, n)},
            index=pd.date_range("2024-01-01", periods=n, freq="B"),
        )
        mock_obt.return_value = ret
        mock_go.Figure.return_value = MagicMock()
        with patch("services.correlaciones.st", mock_st):
            out = render_heatmap_correlaciones(["P", "Q"])
        assert out is not None
        mock_st.success.assert_called()

    @patch("services.correlaciones.go")
    @patch("services.correlaciones.obtener_retornos_historicos")
    def test_render_con_alertas_muestra_dataframe(self, mock_obt, mock_go, mock_st):
        """Rama st.dataframe cuando hay pares con |rho| >= 0.75."""
        from services.correlaciones import render_heatmap_correlaciones

        n, rng = 25, np.random.default_rng(7)
        base = rng.normal(0, 0.008, n)
        ret = pd.DataFrame({"H1": base, "H2": base * 1.02 + rng.normal(0, 1e-5, n)})
        ret.index = pd.date_range("2024-01-01", periods=n, freq="B")
        mock_obt.return_value = ret
        mock_go.Figure.return_value = MagicMock()
        with patch("services.correlaciones.st", mock_st):
            render_heatmap_correlaciones(["H1", "H2"])
        assert mock_st.dataframe.call_count >= 2
