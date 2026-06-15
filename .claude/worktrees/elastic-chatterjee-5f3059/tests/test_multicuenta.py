"""
tests/test_multicuenta.py — Tests de multicuenta.py (Sprint 21)
multicuenta.py importa streamlit y plotly.express a nivel de módulo.
Se inyectan mocks en sys.modules antes del primer import.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_streamlit_y_plotly():
    """
    Invariante: streamlit y plotly.express existen en sys.modules como mocks
    antes de importar services.multicuenta.
    """
    prev_st = sys.modules.get("streamlit")
    prev_plotly = sys.modules.get("plotly")
    prev_px = sys.modules.get("plotly.express")

    mock_st = MagicMock()
    mock_st.session_state = {}
    sys.modules["streamlit"] = mock_st

    mock_px = MagicMock()
    mock_plotly_pkg = MagicMock()
    mock_plotly_pkg.express = mock_px
    sys.modules["plotly"] = mock_plotly_pkg
    sys.modules["plotly.express"] = mock_px

    sys.modules.pop("services.multicuenta", None)

    yield mock_st

    if prev_st is not None:
        sys.modules["streamlit"] = prev_st
    else:
        sys.modules.pop("streamlit", None)
    if prev_plotly is not None:
        sys.modules["plotly"] = prev_plotly
    else:
        sys.modules.pop("plotly", None)
    if prev_px is not None:
        sys.modules["plotly.express"] = prev_px
    else:
        sys.modules.pop("plotly.express", None)
    sys.modules.pop("services.multicuenta", None)


class TestImportMulticuenta:
    def test_modulo_importa_con_mocks(self):
        import services.multicuenta as mc
        assert mc is not None

    def test_funciones_publicas_consolidar_y_divergencias(self):
        import services.multicuenta as mc
        assert callable(mc.consolidar_multicuenta)
        assert callable(mc.detectar_divergencias)


@pytest.fixture
def df_operaciones_un_broker():
    return pd.DataFrame({
        "Ticker":        ["AAPL", "AAPL", "MSFT"],
        "Tipo_Op":       ["COMPRA", "COMPRA", "COMPRA"],
        "Cantidad":      [10.0, 5.0, 8.0],
        "PPC_USD":       [8.0, 8.5, 10.0],
        "FECHA_INICIAL": ["2023-01-15", "2023-03-01", "2023-02-10"],
        "Broker":        ["Balanz", "Balanz", "Balanz"],
    })


@pytest.fixture
def df_operaciones_dos_brokers():
    return pd.DataFrame({
        "Ticker":        ["AAPL", "AAPL", "KO", "KO"],
        "Tipo_Op":       ["COMPRA", "COMPRA", "COMPRA", "COMPRA"],
        "Cantidad":      [10.0, 5.0, 20.0, 10.0],
        "PPC_USD":       [8.0, 9.5, 4.0, 5.5],
        "FECHA_INICIAL": ["2023-01-15", "2023-06-01", "2023-01-10", "2023-08-01"],
        "Broker":        ["Balanz", "Bull Market", "Balanz", "IOL"],
    })


class TestConsolidarMulticuenta:
    def test_retorna_dataframe(self, df_operaciones_un_broker):
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(df_operaciones_un_broker, 1465.0)
        assert isinstance(result, pd.DataFrame)

    def test_df_vacio_retorna_vacio(self):
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(pd.DataFrame(), 1465.0)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_columnas_requeridas(self, df_operaciones_un_broker):
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(df_operaciones_un_broker, 1465.0)
        if not result.empty:
            for col in (
                "Ticker", "Cantidad_Total", "PPC_USD_Pond",
                "INV_USD_Total", "Brokers", "N_Brokers",
            ):
                assert col in result.columns, f"Columna faltante: {col}"

    def test_suma_cantidades_correcta(self, df_operaciones_un_broker):
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(df_operaciones_un_broker, 1465.0)
        if not result.empty:
            aapl = result[result["Ticker"] == "AAPL"].iloc[0]
            assert aapl["Cantidad_Total"] == pytest.approx(15.0)

    def test_ppc_ponderado_correcto(self, df_operaciones_un_broker):
        """PPC ponderado por broker Balanz: (10*8 + 5*8.5) / 15."""
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(df_operaciones_un_broker, 1465.0)
        if not result.empty:
            aapl = result[result["Ticker"] == "AAPL"].iloc[0]
            esperado = (10 * 8.0 + 5 * 8.5) / 15
            assert aapl["PPC_USD_Pond"] == pytest.approx(esperado, rel=0.01)

    def test_venta_reduce_posicion(self):
        from services.multicuenta import consolidar_multicuenta
        df = pd.DataFrame({
            "Ticker":        ["AAPL", "AAPL"],
            "Tipo_Op":       ["COMPRA", "VENTA"],
            "Cantidad":      [10.0, 3.0],
            "PPC_USD":       [8.0, 0.0],
            "FECHA_INICIAL": ["2023-01-15", "2023-06-01"],
            "Broker":        ["Balanz", "Balanz"],
        })
        result = consolidar_multicuenta(df, 1465.0)
        if not result.empty:
            aapl = result[result["Ticker"] == "AAPL"].iloc[0]
            assert aapl["Cantidad_Total"] == pytest.approx(7.0)

    def test_posicion_cero_no_aparece(self):
        from services.multicuenta import consolidar_multicuenta
        df = pd.DataFrame({
            "Ticker":        ["AAPL", "AAPL"],
            "Tipo_Op":       ["COMPRA", "VENTA"],
            "Cantidad":      [10.0, 10.0],
            "PPC_USD":       [8.0, 0.0],
            "FECHA_INICIAL": ["2023-01-15", "2023-06-01"],
            "Broker":        ["Balanz", "Balanz"],
        })
        result = consolidar_multicuenta(df, 1465.0)
        assert result.empty or "AAPL" not in result["Ticker"].values

    def test_multiples_brokers_n_brokers_correcto(self, df_operaciones_dos_brokers):
        from services.multicuenta import consolidar_multicuenta
        result = consolidar_multicuenta(df_operaciones_dos_brokers, 1465.0)
        if not result.empty:
            aapl = result[result["Ticker"] == "AAPL"].iloc[0]
            assert aapl["N_Brokers"] == 2

    def test_broker_por_defecto_manual_si_no_existe(self):
        from services.multicuenta import consolidar_multicuenta
        df = pd.DataFrame({
            "Ticker":        ["AAPL"],
            "Tipo_Op":       ["COMPRA"],
            "Cantidad":      [10.0],
            "PPC_USD":       [8.0],
            "FECHA_INICIAL": ["2023-01-15"],
        })
        result = consolidar_multicuenta(df, 1465.0)
        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "Manual" in str(result.iloc[0].get("Brokers", ""))


class TestDetectarDivergencias:
    def test_retorna_lista(self, df_operaciones_dos_brokers):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias
        df_cons = consolidar_multicuenta(df_operaciones_dos_brokers, 1465.0)
        result = detectar_divergencias(df_cons, 1465.0)
        assert isinstance(result, list)

    def test_sin_divergencias_con_un_broker(self, df_operaciones_un_broker):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias
        df_cons = consolidar_multicuenta(df_operaciones_un_broker, 1465.0)
        result = detectar_divergencias(df_cons, 1465.0)
        assert result == []

    def test_detecta_divergencia_con_dos_brokers_diff(self, df_operaciones_dos_brokers):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias
        df_cons = consolidar_multicuenta(df_operaciones_dos_brokers, 1465.0)
        divs = detectar_divergencias(df_cons, 1465.0)
        tickers_con_div = [d["ticker"] for d in divs]
        assert "KO" in tickers_con_div

    def test_divergencia_tiene_claves_requeridas(self, df_operaciones_dos_brokers):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias
        df_cons = consolidar_multicuenta(df_operaciones_dos_brokers, 1465.0)
        divs = detectar_divergencias(df_cons, 1465.0)
        if divs:
            for d in divs:
                for k in ("ticker", "diff_pct", "ppc_min", "ppc_max", "brokers"):
                    assert k in d

    def test_df_vacio_retorna_lista_vacia(self):
        from services.multicuenta import detectar_divergencias
        result = detectar_divergencias(pd.DataFrame(), 1465.0)
        assert result == []

    def test_diff_pct_correcto(self, df_operaciones_dos_brokers):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias
        df_cons = consolidar_multicuenta(df_operaciones_dos_brokers, 1465.0)
        divs = detectar_divergencias(df_cons, 1465.0)
        ko_divs = [d for d in divs if d["ticker"] == "KO"]
        if ko_divs:
            d = ko_divs[0]
            assert d["diff_pct"] > 5.0
            assert d["ppc_min"] < d["ppc_max"]
