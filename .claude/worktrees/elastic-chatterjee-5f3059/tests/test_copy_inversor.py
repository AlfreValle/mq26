"""Tests para textos de UI inversor (sin Streamlit)."""
from services.copy_inversor import (
    GLOSARIO_INVERSOR,
    antes_despues_defensivo,
    copy_rebalanceo_humano,
    defensivo_vs_perfil,
    participacion_txt,
    pasos_onboarding_hub,
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


def test_glosario_inversor_claves():
    assert "salud_score" in GLOSARIO_INVERSOR
    assert "0–100" in GLOSARIO_INVERSOR["salud_score"] or "0-100" in GLOSARIO_INVERSOR["salud_score"]


def test_copy_rebalanceo_humano_contiene_broker():
    s = copy_rebalanceo_humano()
    assert "MQ26" in s and "broker" in s.lower()


def test_pasos_onboarding_tres():
    pasos = pasos_onboarding_hub()
    assert len(pasos) == 3
    assert all(len(t) == 2 for t in pasos)
