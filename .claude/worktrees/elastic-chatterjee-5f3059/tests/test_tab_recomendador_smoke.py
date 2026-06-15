"""
tests/test_tab_recomendador_smoke.py — Smoke tests tab_recomendador (Sprint 31).
Solo import y API pública; no se ejecuta render Streamlit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


def _identity_dec(f):
    """Invariante: decorador cache_data no altera la función bajo test."""
    return f


@pytest.fixture(autouse=True)
def mock_st_y_plotly_tab():
    """Invariante: streamlit y plotly.express mockeados antes del import del tab."""
    prev_st = sys.modules.get("streamlit")
    prev_plotly = sys.modules.get("plotly")
    prev_px = sys.modules.get("plotly.express")

    mock_st = MagicMock()
    mock_st.session_state = {}
    mock_st.cache_data = MagicMock(return_value=_identity_dec)
    sys.modules["streamlit"] = mock_st

    mock_px = MagicMock()
    mock_plotly_pkg = MagicMock()
    mock_plotly_pkg.express = mock_px
    sys.modules["plotly"] = mock_plotly_pkg
    sys.modules["plotly.express"] = mock_px

    sys.modules.pop("services.tab_recomendador", None)
    yield mock_st

    sys.modules.pop("services.tab_recomendador", None)
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


class TestTabRecomendadorImporta:
    def test_modulo_importa_sin_error(self):
        try:
            import services.tab_recomendador as tr
            assert tr is not None
        except Exception as e:
            pytest.fail(f"tab_recomendador no importó: {e}")

    def test_render_tab_recomendador_es_callable(self):
        import services.tab_recomendador as tr

        assert callable(tr.render_tab_recomendador)

    def test_scan_cacheado_existe(self):
        import services.tab_recomendador as tr

        assert hasattr(tr, "_scan_cacheado")

    def test_enviar_reporte_email_existe(self):
        import services.tab_recomendador as tr

        assert hasattr(tr, "_enviar_reporte_email")

    def test_render_email_widget_existe(self):
        import services.tab_recomendador as tr

        assert hasattr(tr, "_render_email_widget")
