"""Tests para exportar_para_rrss() — Sprint 2 FIX-2"""
from __future__ import annotations

from unittest.mock import patch

import pytest

kaleido = pytest.importorskip("kaleido")


def test_exportar_instagram_dimensiones():
    from services.market_stress_map import exportar_para_rrss
    import plotly.graph_objects as go

    fig      = go.Figure(go.Scatter(x=[1, 2], y=[1, 2]))
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with patch.object(fig, "to_image", return_value=fake_png) as mock_img:
        result = exportar_para_rrss(fig, "instagram")
    mock_img.assert_called_once_with(format="png", width=1080, height=1080, scale=2)
    assert result == fake_png


def test_exportar_linkedin_dimensiones():
    from services.market_stress_map import exportar_para_rrss
    import plotly.graph_objects as go

    fig      = go.Figure()
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    with patch.object(fig, "to_image", return_value=fake_png) as mock_img:
        result = exportar_para_rrss(fig, "linkedin")
    mock_img.assert_called_once_with(format="png", width=1200, height=627, scale=2)
    assert result == fake_png
