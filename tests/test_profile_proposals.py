"""Tests para services/profile_proposals.py — Sprint 2 FIX-0"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


def _fake_prices(tickers, n=120):
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0003, 0.01, (n, len(tickers))), axis=0),
        index=idx, columns=tickers,
    )


def test_build_conservador_pesos_suman_1():
    from services.profile_proposals import UNIVERSOS
    tickers  = UNIVERSOS["conservador"]
    fake_raw = MagicMock()
    fake_raw.__getitem__ = lambda self, k: _fake_prices(tickers)

    with patch("services.profile_proposals.yf.download", return_value=fake_raw):
        with patch("services.profile_proposals.RiskEngine") as MockEng:
            inst = MockEng.return_value
            inst.optimizar.return_value = {t: 0.1 for t in tickers}
            inst.calcular_metricas.return_value = (0.08, 0.12, 0.5)
            from services.profile_proposals import build_profile_proposal
            result = build_profile_proposal("conservador")

    assert abs(sum(result["pesos"].values()) - 1.0) < 1e-4
    assert result["modelo"] == "min_var"


def test_build_perfil_desconocido_lanza_error():
    from services.profile_proposals import build_profile_proposal
    with pytest.raises(ValueError, match="Perfil desconocido"):
        build_profile_proposal("agresivo_extremo")


def test_fallback_igual_peso_si_yfinance_falla():
    with patch("services.profile_proposals.yf.download", side_effect=Exception("red")):
        from services.profile_proposals import build_profile_proposal
        result = build_profile_proposal("moderado")
    assert "error" in result
    assert abs(sum(result["pesos"].values()) - 1.0) < 1e-4
