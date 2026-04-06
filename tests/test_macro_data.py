"""Tests para services/macro_data_ar.py — Sprint 2 T-2.0"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FAKE_RIPTE_JSON = {"data": [["2024-01-01", 500000.0], ["2024-02-01", 520000.0]]}
FAKE_HABER_JSON = {"data": [["2024-01-01", 90000.0], ["2024-02-01", 95000.0]]}


def _mock_get(url, timeout=10):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = FAKE_HABER_JSON if "11.3_CF" in url else FAKE_RIPTE_JSON
    return resp


def test_fetch_ripte_retorna_serie():
    import services.macro_data_ar as m
    m._CACHE.clear()
    with patch("services.macro_data_ar.requests.get", side_effect=_mock_get):
        s = m.fetch_ripte()
    assert isinstance(s, pd.Series)
    assert len(s) == 2
    assert s.iloc[0] == pytest.approx(500_000.0)


def test_fetch_haber_minimo_retorna_serie():
    import services.macro_data_ar as m
    m._CACHE.clear()
    with patch("services.macro_data_ar.requests.get", side_effect=_mock_get):
        s = m.fetch_haber_minimo()
    assert isinstance(s, pd.Series)
    assert len(s) == 2
    assert s.iloc[0] == pytest.approx(90_000.0)


def test_fetch_haber_fallback_si_api_falla():
    import services.macro_data_ar as m
    m._CACHE.clear()
    with patch("services.macro_data_ar.requests.get", side_effect=Exception("timeout")):
        s = m.fetch_haber_minimo()
    assert isinstance(s, pd.Series)
    assert len(s) >= 1


def test_cache_no_llama_api_dos_veces():
    import services.macro_data_ar as m
    m._CACHE.clear()
    call_count = {"n": 0}

    def counting_mock(url, timeout=10):
        call_count["n"] += 1
        return _mock_get(url, timeout)

    with patch("services.macro_data_ar.requests.get", side_effect=counting_mock):
        m.fetch_ripte()
        m.fetch_ripte()
    assert call_count["n"] == 1, "Segunda llamada debe usar cache"
