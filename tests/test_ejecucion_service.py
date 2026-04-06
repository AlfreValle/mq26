"""
tests/test_ejecucion_service.py — Tests de ejecucion_service.py (Sprint 21)
Mockea risk_engine para errores controlados. Sin yfinance ni red.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "1_Scripts_Motor"
for _p in (_SCRIPTS, _ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


@pytest.fixture
def df_ag_simple():
    return pd.DataFrame({
        "TICKER":          ["AAPL", "MSFT"],
        "CANTIDAD_TOTAL":  [10.0, 5.0],
        "VALOR_ARS":       [190_000.0, 110_000.0],
        "PESO_PCT":        [63.3, 36.7],
    })


@pytest.fixture
def hist_precios_sinteticos():
    rng = np.random.default_rng(42)
    n = 252
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "AAPL": 150.0 * np.cumprod(1 + rng.normal(0.001, 0.02, n)),
        "MSFT": 250.0 * np.cumprod(1 + rng.normal(0.001, 0.018, n)),
    }, index=idx)


class TestGenerarPlanRebalanceoGuards:
    def test_tickers_vacios_retorna_error(self):
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo(
            tickers_cartera=[],
            df_ag=pd.DataFrame(),
            hist_precios=pd.DataFrame(),
            precios_ars={},
        )
        assert result["error"] is not None
        assert len(result["error"]) > 0

    def test_df_ag_vacio_retorna_error(self):
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo(
            tickers_cartera=["AAPL", "MSFT"],
            df_ag=pd.DataFrame(),
            hist_precios=pd.DataFrame(),
            precios_ars={},
        )
        assert result["error"] is not None

    def test_menos_de_2_tickers_en_hist_retorna_error(self, df_ag_simple):
        from services.ejecucion_service import generar_plan_rebalanceo
        hist_solo_uno = pd.DataFrame({"AAPL": [150.0, 155.0, 148.0]})
        result = generar_plan_rebalanceo(
            tickers_cartera=["AAPL", "MSFT"],
            df_ag=df_ag_simple,
            hist_precios=hist_solo_uno,
            precios_ars={"AAPL": 19_000.0, "MSFT": 22_000.0},
        )
        assert result["error"] is not None
        err = result["error"].lower()
        assert "insuficientes" in err

    def test_retorna_estructura_completa_siempre(self):
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo(
            tickers_cartera=[],
            df_ag=pd.DataFrame(),
            hist_precios=pd.DataFrame(),
            precios_ars={},
        )
        for k in (
            "pesos_optimos", "ejecutables", "bloqueadas",
            "reporte", "metricas", "error",
        ):
            assert k in result, f"Clave faltante en resultado: {k}"

    def test_ejecutables_es_dataframe(self):
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo([], pd.DataFrame(), pd.DataFrame(), {})
        assert isinstance(result["ejecutables"], pd.DataFrame)

    def test_bloqueadas_es_dataframe(self):
        from services.ejecucion_service import generar_plan_rebalanceo
        result = generar_plan_rebalanceo([], pd.DataFrame(), pd.DataFrame(), {})
        assert isinstance(result["bloqueadas"], pd.DataFrame)

    def test_excepcion_interna_no_propaga(self, df_ag_simple, hist_precios_sinteticos):
        """Si RiskEngine falla, el error queda en el dict, no se propaga."""
        from services.ejecucion_service import generar_plan_rebalanceo
        with patch("risk_engine.RiskEngine", side_effect=RuntimeError("fallo simulado")):
            try:
                result = generar_plan_rebalanceo(
                    tickers_cartera=["AAPL", "MSFT"],
                    df_ag=df_ag_simple,
                    hist_precios=hist_precios_sinteticos,
                    precios_ars={"AAPL": 19_000.0, "MSFT": 22_000.0},
                )
                assert isinstance(result, dict)
                assert result["error"] is not None
            except Exception as e:
                pytest.fail(f"generar_plan_rebalanceo propagó excepción: {e}")


class TestEnviarAlertaRebalanceo:
    def test_importa_sin_error(self):
        from services.ejecucion_service import enviar_alerta_rebalanceo
        assert callable(enviar_alerta_rebalanceo)

    def test_df_vacio_no_llama_alert_bot(self):
        from services.ejecucion_service import enviar_alerta_rebalanceo
        with patch("alert_bot.alerta_rebalanceo") as mock_alerta:
            enviar_alerta_rebalanceo(pd.DataFrame(), "Test Cartera")
            mock_alerta.assert_not_called()

    def test_no_lanza_con_alert_bot_fallido(self):
        from services.ejecucion_service import enviar_alerta_rebalanceo
        df_ej = pd.DataFrame({
            "ticker":    ["AAPL"],
            "tipo_op":   ["COMPRA"],
            "nominales": [10],
        })
        with patch(
            "alert_bot.alerta_rebalanceo",
            side_effect=Exception("Telegram caído"),
        ):
            try:
                enviar_alerta_rebalanceo(df_ej, "Retiro")
            except Exception as e:
                pytest.fail(f"enviar_alerta_rebalanceo propagó: {e}")

    def test_no_lanza_con_entradas_nulas_o_vacias(self):
        from services.ejecucion_service import enviar_alerta_rebalanceo
        try:
            enviar_alerta_rebalanceo(None, "")
            enviar_alerta_rebalanceo(pd.DataFrame(), None)
        except Exception as e:
            pytest.fail(f"enviar_alerta_rebalanceo lanzó: {e}")
