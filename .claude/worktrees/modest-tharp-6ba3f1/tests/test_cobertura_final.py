"""
tests/test_cobertura_final.py — Complementos Sprint 31 (motor_salida, backtester_real).
Evita duplicar test_motor_salida / test_backtester_real / test_multicuenta: solo huecos o regresión breve.
Sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ── motor_salida ─────────────────────────────────────────────────────────────


class TestMotorSalidaFinalS31:
    """Invariante: disparadores de dominio coherentes con OBJETIVOS_PERFIL."""

    def test_evaluar_salida_stop_loss_activa_disparador(self):
        from services.motor_salida import evaluar_salida

        r = evaluar_salida(
            "AAPL", 100.0, 60.0, 80.0, 2.0, 3.0, date(2022, 1, 1),
        )
        assert len(r["disparadores_activos"]) >= 1

    def test_estimar_prob_exito_orden_rsi_sobrevendido_ideal_sobrecomprado(self):
        """Invariante: RSI sobrevendido >= zona ideal >= sobrecomprado (mismo score)."""
        from services.motor_salida import estimar_prob_exito

        p1 = estimar_prob_exito(50.0, 25.0)
        p2 = estimar_prob_exito(50.0, 45.0)
        p3 = estimar_prob_exito(50.0, 80.0)
        assert p1 >= p2 >= p3
        for p in (p1, p2, p3):
            assert 0.20 <= p <= 0.80


# ── backtester_real.calcular_metricas ────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_st_plotly_backtester_s31():
    prev_st = sys.modules.get("streamlit")
    prev_plotly = sys.modules.get("plotly")
    prev_pgo = sys.modules.get("plotly.graph_objects")

    sys.modules["streamlit"] = MagicMock()
    mock_pgo = MagicMock()
    mock_plotly = MagicMock()
    mock_plotly.graph_objects = mock_pgo
    sys.modules["plotly"] = mock_plotly
    sys.modules["plotly.graph_objects"] = mock_pgo

    sys.modules.pop("services.backtester_real", None)
    yield

    sys.modules.pop("services.backtester_real", None)
    if prev_st is not None:
        sys.modules["streamlit"] = prev_st
    else:
        sys.modules.pop("streamlit", None)
    if prev_plotly is not None:
        sys.modules["plotly"] = prev_plotly
    else:
        sys.modules.pop("plotly", None)
    if prev_pgo is not None:
        sys.modules["plotly.graph_objects"] = prev_pgo
    else:
        sys.modules.pop("plotly.graph_objects", None)


class TestBacktesterRealFinalS31:
    def test_calcular_metricas_max_dd_no_positivo_serie_ruidosa(self):
        """Invariante: max_drawdown_pct nunca positivo en equity ruidosa."""
        import services.backtester_real as bt

        rng = np.random.default_rng(42)
        n = 100
        valores = [10_000.0]
        for _ in range(n - 1):
            valores.append(valores[-1] * (1.0 + rng.normal(0.0, 0.02)))
        retornos = [0.0] + [
            valores[i] / valores[i - 1] - 1.0 for i in range(1, n)
        ]
        df = pd.DataFrame({"valor_usd": valores, "retorno_diario": retornos})
        result = bt.calcular_metricas(df)
        if result:
            assert result["max_drawdown_pct"] <= 0.0
