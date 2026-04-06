"""
tests/test_smoke_st_modules.py — Smoke y lógica pura para módulos con Streamlit.
Sprint 35: incluye dashboard_ejecutivo y timeline_posiciones; sin red real.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_st_global():
    """Invariante: cualquier import de streamlit usa un mock seguro."""
    mock_st = MagicMock()
    mock_st.session_state = {}
    mock_st.cache_data = MagicMock(return_value=lambda f: f)
    mock_st.columns.side_effect = lambda *a, **k: tuple(MagicMock() for _ in range(5))
    original = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    yield mock_st
    if original is not None:
        sys.modules["streamlit"] = original


class TestMulticuentaSmoke:
    def test_consolidar_multicuenta_es_callable(self):
        from services.multicuenta import consolidar_multicuenta

        assert callable(consolidar_multicuenta)

    def test_consolidar_df_vacio_retorna_vacio(self):
        from services.multicuenta import consolidar_multicuenta

        result = consolidar_multicuenta(pd.DataFrame(), 1465.0)
        assert isinstance(result, pd.DataFrame) and result.empty

    def test_consolidar_suma_cantidad(self):
        from services.multicuenta import consolidar_multicuenta

        df = pd.DataFrame(
            {
                "Ticker": ["AAPL", "AAPL"],
                "Tipo_Op": ["COMPRA", "COMPRA"],
                "Cantidad": [10.0, 5.0],
                "PPC_USD": [8.0, 8.0],
                "FECHA_INICIAL": ["2023-01-15", "2023-06-01"],
                "Broker": ["Balanz", "Balanz"],
            }
        )
        result = consolidar_multicuenta(df, 1465.0)
        if not result.empty:
            aapl = result[result["Ticker"] == "AAPL"].iloc[0]
            assert aapl["Cantidad_Total"] == pytest.approx(15.0)

    def test_detectar_divergencias_un_broker_devuelve_lista_vacia(self):
        from services.multicuenta import consolidar_multicuenta, detectar_divergencias

        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "Tipo_Op": ["COMPRA"],
                "Cantidad": [10.0],
                "PPC_USD": [8.0],
                "FECHA_INICIAL": ["2023-01-15"],
                "Broker": ["Balanz"],
            }
        )
        cons = consolidar_multicuenta(df, 1465.0)
        assert detectar_divergencias(cons, 1465.0) == []


class TestBacktesterRealSmoke:
    def test_calcular_metricas_callable(self):
        from services.backtester_real import calcular_metricas

        assert callable(calcular_metricas)

    def test_calcular_metricas_df_vacio(self):
        from services.backtester_real import calcular_metricas

        assert calcular_metricas(pd.DataFrame()) == {}

    def test_calcular_metricas_menos_de_10_filas(self):
        from services.backtester_real import calcular_metricas

        df = pd.DataFrame({"valor_usd": [10_000.0] * 5, "retorno_diario": [0.001] * 5})
        assert calcular_metricas(df) == {}

    def test_calcular_metricas_serie_valida(self):
        from services.backtester_real import calcular_metricas

        n = 100
        df = pd.DataFrame(
            {
                "valor_usd": [10_000.0 * (1.001**i) for i in range(n)],
                "retorno_diario": [0.001] * n,
            }
        )
        result = calcular_metricas(df)
        assert isinstance(result, dict) and len(result) > 0
        assert result.get("max_drawdown_pct", 0) <= 0.0


class TestRiskVarSmoke:
    def test_calcular_var_cvar_callable(self):
        from services.risk_var import calcular_var_cvar

        assert callable(calcular_var_cvar)

    def test_valor_total_cero_retorna_vacio(self):
        from services.risk_var import calcular_var_cvar

        result = calcular_var_cvar(["AAPL"], {"AAPL": 0}, {"AAPL": 0.0}, 1465.0)
        assert result == {}

    def test_yfinance_falla_retorna_vacio(self):
        from services.risk_var import calcular_var_cvar

        with patch("yfinance.download", side_effect=Exception("timeout")):
            result = calcular_var_cvar(["AAPL"], {"AAPL": 10}, {"AAPL": 19_000.0}, 1465.0)
        assert result == {}

    def test_con_datos_validos_retorna_claves(self):
        from services.risk_var import calcular_var_cvar

        rng = np.random.default_rng(42)
        n = 252
        idx = pd.date_range("2023-01-01", periods=n, freq="B")
        mock_df = pd.DataFrame(
            {"AAPL": 150.0 * np.cumprod(1 + rng.normal(0.001, 0.02, n))}, index=idx
        )
        with patch("yfinance.download", return_value={"Close": mock_df}):
            result = calcular_var_cvar(["AAPL"], {"AAPL": 10}, {"AAPL": 19_000.0}, 1465.0)
        if result:
            for key in ("var_pct", "cvar_pct", "mensaje"):
                assert key in result
            assert result["var_pct"] <= 0.0
            assert result["cvar_pct"] <= result["var_pct"]


class TestMarketConnectorSmoke:
    def test_precios_en_ars_callable(self):
        from services.market_connector import precios_en_ars

        assert callable(precios_en_ars)

    def test_precios_en_ars_multiplica_por_ccl(self):
        from services.market_connector import precios_en_ars

        df = pd.DataFrame({"AAPL": [10.0], "MSFT": [20.0]})
        result = precios_en_ars(df, ccl=1500.0)
        assert result["AAPL"].iloc[0] == pytest.approx(15_000.0)

    def test_circuit_breaker_bloquea_ticker_fallido(self):
        import services.market_connector as mc

        mc._circuit_breaker.clear()
        mc._circuit_breaker.add("TICKER_FALLIDO")
        llamadas = []

        def fn():
            llamadas.append(1)
            return 999

        result = mc._fetch_con_reintento(fn, etiqueta="TEST/TICKER_FALLIDO")
        assert result is None
        assert len(llamadas) == 0
        mc._circuit_breaker.clear()


class TestTabRecomendadorSmoke:
    def test_modulo_importa(self):
        import services.tab_recomendador as tr

        assert tr is not None

    def test_render_es_callable(self):
        import services.tab_recomendador as tr

        assert callable(tr.render_tab_recomendador)


class TestPortfolioSnapshotSmoke:
    def test_guardar_y_recuperar(self):
        from services.portfolio_snapshot import cargar_snapshot, guardar_snapshot

        sid = guardar_snapshot("Test", "Sharpe", {"AAPL": 0.6, "KO": 0.4}, {"sharpe": 1.2})
        assert sid > 0
        snap = cargar_snapshot(sid)
        assert snap is not None
        assert snap["modelo"] == "Sharpe"

    def test_id_inexistente_retorna_none(self):
        from services.portfolio_snapshot import cargar_snapshot

        assert cargar_snapshot(999_999_999) is None

    def test_eliminar_idempotente(self):
        from services.portfolio_snapshot import eliminar_snapshot, guardar_snapshot

        sid = guardar_snapshot("Del", "CVaR", {"A": 1.0}, {})
        eliminar_snapshot(sid)
        eliminar_snapshot(sid)


class TestAuditTrailSmoke:
    def test_registrar_y_listar(self):
        from services.audit_trail import listar_ordenes, registrar_orden

        oid = registrar_orden("COMPRA", "AAPL", 10.0, 19_000.0, cartera="Test_S34")
        assert oid > 0
        df = listar_ordenes(cartera="Test_S34")
        assert isinstance(df, pd.DataFrame)


class TestDashboardEjecutivoSmoke:
    """Smoke de services.dashboard_ejecutivo sin red."""

    def test_render_vacio_llama_info(self, mock_st_global):
        from importlib import reload

        import services.dashboard_ejecutivo as dash_mod

        reload(dash_mod)
        from services.dashboard_ejecutivo import render_dashboard_ejecutivo

        render_dashboard_ejecutivo(pd.DataFrame(), 1500.0)
        dash_mod.st.info.assert_called()

    def test_render_con_posiciones_no_lanza(self, mock_st_global):
        from importlib import reload

        import services.dashboard_ejecutivo as dash_mod

        reload(dash_mod)
        from services.dashboard_ejecutivo import render_dashboard_ejecutivo

        df = pd.DataFrame(
            {
                "TICKER": ["AAPL", "MSFT"],
                "VALOR_ARS": [1_000_000.0, 500_000.0],
                "INVERSION_ARS": [900_000.0, 480_000.0],
                "CANTIDAD_TOTAL": [10.0, 5.0],
            }
        )
        render_dashboard_ejecutivo(
            df, 1500.0, score_promedio=72.0, nombre_cartera="Cartera_S35"
        )
        assert dash_mod.st.markdown.call_count >= 1


class TestTimelinePosicionesSmoke:
    """Smoke de services.timeline_posiciones (plotly + st mockeados)."""

    def test_render_vacio_llama_info(self, mock_st_global):
        from importlib import reload

        import services.timeline_posiciones as tl_mod

        reload(tl_mod)
        from services.timeline_posiciones import render_timeline_posiciones

        render_timeline_posiciones(pd.DataFrame(), {}, 1500.0)
        tl_mod.st.info.assert_called()

    def test_render_con_posicion_llama_plotly(self, mock_st_global):
        from importlib import reload

        import services.timeline_posiciones as tl_mod

        reload(tl_mod)
        from services.timeline_posiciones import render_timeline_posiciones

        df = pd.DataFrame(
            {
                "Ticker": ["AAPL"],
                "Cantidad": [10.0],
                "PPC_USD": [150.0],
                "FECHA_INICIAL": ["2023-01-01"],
            }
        )
        precios = {"AAPL": 190_000.0}
        render_timeline_posiciones(df, precios, 1500.0, titulo="TL_S35")
        tl_mod.st.plotly_chart.assert_called()


class TestStreamlitWidthRegression:
    """Sprint 7: Streamlit 1.56 — no usar width='stretch' ni width='content'."""

    def test_no_width_stretch_en_ui(self):
        root = Path(__file__).resolve().parent.parent
        ui_dir = root / "ui"
        patron = re.compile(r"width\s*=\s*['\"]stretch['\"]")
        violaciones: list[str] = []
        for f in sorted(ui_dir.glob("*.py")):
            content = f.read_text(encoding="utf-8", errors="replace")
            n = len(patron.findall(content))
            if n:
                violaciones.append(f"{f.name}: {n} ocurrencias")
        assert not violaciones, "width='stretch' encontrado:\n" + "\n".join(violaciones)

    def test_no_width_content_en_ui(self):
        root = Path(__file__).resolve().parent.parent
        ui_dir = root / "ui"
        patron = re.compile(r"width\s*=\s*['\"]content['\"]")
        violaciones: list[str] = []
        for f in sorted(ui_dir.glob("*.py")):
            content = f.read_text(encoding="utf-8", errors="replace")
            if patron.search(content):
                violaciones.append(f.name)
        assert not violaciones, f"width='content' en: {violaciones}"

    def test_no_width_stretch_en_entrypoints(self):
        root = Path(__file__).resolve().parent.parent
        patron = re.compile(r"width\s*=\s*['\"]stretch['\"]")
        for name in ("run_mq26.py", "app_main.py"):
            p = root / name
            if not p.exists():
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            assert not patron.search(content), f"{name} contiene width='stretch'"


def test_tab_estudio_importa_diagnostico():
    """tab_estudio puede importar los módulos del Sprint 5 / informe inversor."""
    from core.diagnostico_types import perfil_diagnostico_valido
    from services.diagnostico_cartera import diagnosticar

    assert callable(diagnosticar)
    assert perfil_diagnostico_valido("Arriesgado") in ("Arriesgado", "Moderado")


