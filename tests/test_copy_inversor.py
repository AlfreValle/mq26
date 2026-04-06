"""Tests para textos de UI inversor (sin Streamlit)."""
from services.copy_inversor import (
    antes_despues_defensivo,
    defensivo_vs_perfil,
    participacion_txt,
    patrimonio_dual_line,
)


def test_participacion_txt():
    assert "25.0%" in participacion_txt(25.0)


def test_defensivo_vs_perfil():
    s = defensivo_vs_perfil(30.0, 40.0, "Moderado")
    assert "30%" in s and "40%" in s and "Moderado" in s


def test_antes_despues():
    s = antes_despues_defensivo(18.0, 26.0)
    assert "18%" in s and "26%" in s


def test_patrimonio_dual():
    s = patrimonio_dual_line(10_000.0, 15_000_000.0, 1500.0)
    assert "USD" in s and "ARS" in s
