"""tests/test_mq26_ux_design_system.py — P3-UX-02: helpers mq26_ux + tokens visuales."""
from ui.mq26_ux import (
    defensive_bar_html,
    hero_alignment_bar_html,
    plotly_chart_layout_base,
    semaforo_html,
)


def test_plotly_chart_layout_base_barlow_y_color_claro():
    d = plotly_chart_layout_base(light=True)
    assert d["font"]["family"] == "Barlow, sans-serif"
    assert d["font"]["color"] == "rgb(51, 65, 85)"


def test_plotly_chart_layout_base_color_oscuro():
    d = plotly_chart_layout_base(light=False)
    assert d["font"]["color"] == "rgb(168, 163, 154)"


def test_semaforo_html_clases_semanticas():
    h = semaforo_html("verde", 80, "")
    assert "mq-sem-label-text--verde" in h
    assert "mq-sem-score" in h
    assert "color:" not in h


def test_semaforo_neutro_clase():
    h = semaforo_html("otro", None, "X")
    assert "mq-sem-label-text--neutro" in h


def test_hero_alignment_bar_clases():
    h = hero_alignment_bar_html(42.0, "Test")
    assert "mq-hero-gauge__track" in h
    assert "mq-hero-number" in h
    assert "mq-label" in h


def test_defensive_bar_clases():
    h = defensive_bar_html(0.5, 0.4, label="Def")
    assert "mq-def-bar-wrap" in h
    assert "mq-def-bar-head" in h
