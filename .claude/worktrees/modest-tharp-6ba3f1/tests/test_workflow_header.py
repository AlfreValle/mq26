"""
tests/test_workflow_header.py — Tests del workflow header v9 (markdown, sin success/warning).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.flow_manager import FlowManager


def _resumen(coverage=100.0, alertas=0, aprobada=False):
    """Helper: genera flow_resumen via FlowManager real."""
    fm = FlowManager()
    return fm.resumen({
        "price_coverage_pct":     coverage,
        "n_concentration_alerts": alertas,
        "optimizacion_aprobada":  aprobada,
    })


def _mock_cols():
    """5 columnas mockeadas con context manager."""
    cols = [MagicMock() for _ in range(5)]
    for c in cols:
        c.__enter__ = MagicMock(return_value=c)
        c.__exit__ = MagicMock(return_value=False)
    return cols


class TestImportYEstructura:
    def test_importa_sin_error(self):
        from ui.workflow_header import render_workflow_header
        assert callable(render_workflow_header)

    def test_paso_colores_existe(self):
        import ui.workflow_header as wh
        assert hasattr(wh, "_PASO_COLORES")
        assert "green" in wh._PASO_COLORES


class TestCompact:
    def test_compact_no_llama_a_columns(self):
        from ui.workflow_header import render_workflow_header
        resumen = _resumen(100.0)
        with patch("ui.workflow_header.st") as mock_st:
            mock_st.markdown = MagicMock()
            render_workflow_header(resumen, compact=True)
            mock_st.columns.assert_not_called()

    def test_compact_llama_markdown(self):
        from ui.workflow_header import render_workflow_header
        resumen = _resumen(100.0)
        with patch("ui.workflow_header.st") as mock_st:
            mock_st.markdown = MagicMock()
            render_workflow_header(resumen, compact=True)
            mock_st.markdown.assert_called()
            assert mock_st.markdown.call_count >= 1


class TestFull:
    def test_full_llama_a_columns_con_5(self):
        from ui.workflow_header import render_workflow_header
        resumen = _resumen(100.0)
        with patch("ui.workflow_header.st") as mock_st:
            mock_st.columns.return_value = _mock_cols()
            mock_st.markdown = MagicMock()
            render_workflow_header(resumen, compact=False)
            mock_st.columns.assert_called_once_with(5)

    def test_full_banner_markdown_incluye_siguiente(self):
        from ui.workflow_header import render_workflow_header
        resumen = _resumen(coverage=50.0)
        with patch("ui.workflow_header.st") as mock_st:
            mock_st.columns.return_value = _mock_cols()
            mock_st.markdown = MagicMock()
            render_workflow_header(resumen, compact=False)
            first_call = mock_st.markdown.call_args_list[0]
            html_arg = first_call[0][0]
            assert "Siguiente:" in html_arg


class TestCasosEdge:
    def test_dict_vacio_no_lanza_excepcion(self):
        from ui.workflow_header import render_workflow_header
        with patch("ui.workflow_header.st"):
            render_workflow_header({})

    def test_sin_siguiente_accion_no_lanza(self):
        from ui.workflow_header import render_workflow_header
        resumen = {1: {"color": "green", "icon": "✅", "name": "Datos", "label": "Completo"}}
        with patch("ui.workflow_header.st") as mock_st:
            mock_st.markdown = MagicMock()
            render_workflow_header(resumen, compact=True)
