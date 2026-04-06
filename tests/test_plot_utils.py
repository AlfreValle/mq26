"""
tests/test_plot_utils.py — Tests de plot_utils.py (Sprint 26)
Funciones puras que generan HTML o traces Plotly.
Sin streamlit ni red.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import plotly.graph_objects as go
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestConstantes:
    def test_mq26_colors_es_dict(self):
        from services.plot_utils import MQ26_COLORS

        assert isinstance(MQ26_COLORS, dict)
        assert len(MQ26_COLORS) > 0

    def test_mq26_colors_tiene_claves_clave(self):
        from services.plot_utils import MQ26_COLORS

        for k in ("accent", "success", "danger", "warning"):
            assert k in MQ26_COLORS

    def test_mq26_sequence_es_lista(self):
        from services.plot_utils import MQ26_SEQUENCE

        assert isinstance(MQ26_SEQUENCE, list)
        assert len(MQ26_SEQUENCE) >= 5

    def test_colores_son_hex_validos(self):
        from services.plot_utils import MQ26_COLORS

        patron = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for k, v in MQ26_COLORS.items():
            assert patron.match(v), f"Color inválido: {k}={v}"


class TestApplyMq26Layout:
    def test_retorna_figura(self):
        from services.plot_utils import apply_mq26_layout

        fig = go.Figure()
        result = apply_mq26_layout(fig, title="Test")
        assert isinstance(result, go.Figure)

    def test_es_mismo_objeto(self):
        """Modifica in-place y retorna el mismo objeto."""
        from services.plot_utils import apply_mq26_layout

        fig = go.Figure()
        result = apply_mq26_layout(fig)
        assert result is fig

    def test_titulo_se_aplica(self):
        from services.plot_utils import apply_mq26_layout

        fig = go.Figure()
        apply_mq26_layout(fig, title="Mi Título")
        title = fig.layout.title
        text = title.text if hasattr(title, "text") else str(title)
        assert "Mi Título" in str(text or "")

    def test_height_se_aplica(self):
        from services.plot_utils import apply_mq26_layout

        fig = go.Figure()
        apply_mq26_layout(fig, height=600)
        assert fig.layout.height == 600

    def test_figura_vacia_no_lanza(self):
        from services.plot_utils import apply_mq26_layout

        try:
            apply_mq26_layout(go.Figure())
        except Exception as e:
            pytest.fail(f"apply_mq26_layout lanzó con figura vacía: {e}")


class TestMq26Line:
    def test_retorna_scatter(self):
        from services.plot_utils import mq26_line

        trace = mq26_line([1, 2, 3], [10, 20, 30], name="Línea Test")
        assert isinstance(trace, go.Scatter)

    def test_name_asignado(self):
        from services.plot_utils import mq26_line

        trace = mq26_line([1], [1], name="Mi Serie")
        assert trace.name == "Mi Serie"

    def test_datos_x_e_y(self):
        from services.plot_utils import mq26_line

        x = [1, 2, 3]
        y = [10, 20, 30]
        trace = mq26_line(x, y)
        assert list(trace.x) == x
        assert list(trace.y) == y

    def test_color_personalizado(self):
        from services.plot_utils import mq26_line

        trace = mq26_line([1], [1], color="#FF0000")
        color_str = str(trace.line.color or "")
        assert "#FF0000" in color_str or "FF0000" in color_str.upper()


class TestMq26Bar:
    def test_retorna_bar(self):
        from services.plot_utils import mq26_bar

        trace = mq26_bar(["A", "B"], [10, 20])
        assert isinstance(trace, go.Bar)

    def test_name_asignado(self):
        from services.plot_utils import mq26_bar

        trace = mq26_bar(["A"], [1], name="Barras Test")
        assert trace.name == "Barras Test"

    def test_datos_x_e_y(self):
        from services.plot_utils import mq26_bar

        x = ["ENE", "FEB", "MAR"]
        y = [100, 200, 150]
        trace = mq26_bar(x, y)
        assert list(trace.x) == x
        assert list(trace.y) == y


class TestProgressBarHtml:
    def test_retorna_string(self):
        from services.plot_utils import progress_bar_html

        assert isinstance(progress_bar_html(50.0), str)

    def test_contiene_html(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(50.0)
        assert "<div" in result

    def test_cero_pct_width_cero(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(0.0, max_pct=100.0)
        assert "0.0%" in result or "width:0" in result

    def test_pct_sobre_max_usa_danger(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(120.0, max_pct=100.0)
        assert "danger" in result

    def test_pct_sobre_max_muestra_estrella(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(110.0, max_pct=100.0)
        assert "⭐" in result

    def test_pct_alto_pero_bajo_max_usa_yellow(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(85.0, max_pct=100.0)
        assert "yellow" in result

    def test_pct_bajo_usa_verde(self):
        from services.plot_utils import progress_bar_html

        result = progress_bar_html(50.0, max_pct=100.0)
        assert "verde" in result

    def test_pct_negativo_no_lanza(self):
        from services.plot_utils import progress_bar_html

        try:
            result = progress_bar_html(-10.0)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"progress_bar_html(-10.0) lanzó: {e}")


class TestMetricCardHtml:
    def test_retorna_string(self):
        from services.plot_utils import metric_card_html

        assert isinstance(metric_card_html("Valor", "$300K"), str)

    def test_contiene_label_y_value(self):
        from services.plot_utils import metric_card_html

        result = metric_card_html("Total ARS", "$300.000")
        assert "Total ARS" in result
        assert "$300.000" in result

    def test_delta_positivo_clase_pos(self):
        from services.plot_utils import metric_card_html

        result = metric_card_html("PnL", "+14%", delta="+14%", delta_positive=True)
        assert "delta-pos" in result
        assert "▲" in result

    def test_delta_negativo_clase_neg(self):
        from services.plot_utils import metric_card_html

        result = metric_card_html("PnL", "-5%", delta="-5%", delta_positive=False)
        assert "delta-neg" in result
        assert "▼" in result

    def test_delta_none_no_tiene_seccion_delta(self):
        from services.plot_utils import metric_card_html

        result = metric_card_html("Val", "100", delta=None)
        assert "▲" not in result
        assert "▼" not in result

    def test_delta_positivo_none_usa_neutro(self):
        from services.plot_utils import metric_card_html

        result = metric_card_html("Val", "100", delta="+1%", delta_positive=None)
        assert "delta-neu" in result
        assert "●" in result

    def test_sin_delta_sin_lanzar(self):
        from services.plot_utils import metric_card_html

        try:
            result = metric_card_html("Label", "Value")
            assert len(result) > 0
        except Exception as e:
            pytest.fail(f"metric_card_html sin delta lanzó: {e}")
