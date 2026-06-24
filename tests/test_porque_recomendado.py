"""Tests del 'por qué' en lenguaje simple (H1 explicabilidad)."""
from __future__ import annotations

from services.recomendador_explicable import porque_recomendado


def test_porque_rv_traduce_score_a_palabras():
    row = {"Score_Total": 78, "Score_Fund": 80, "Score_Tec": 70, "Score_Sector": 60}
    txt = porque_recomendado("AAPL", score_row=row)
    assert "78/100" in txt
    assert "fundamentales sólidos" in txt   # 80 >= 65
    assert "momento técnico favorable" in txt  # 70 >= 65
    assert "sector neutral" in txt          # 60 en [50,65)


def test_porque_rv_score_bajo():
    row = {"Score_Total": 40, "Score_Fund": 45, "Score_Tec": 30, "Score_Sector": 40}
    txt = porque_recomendado("XYZ", score_row=row)
    assert "fundamentales flojos" in txt
    assert "técnico débil" in txt
    assert "sector en contra" in txt


def test_porque_renta_fija_usa_justificacion():
    txt = porque_recomendado(
        "PN43O", es_renta_fija=True, justificacion="ON USD 7% TIR, calificación AA+"
    )
    assert "TIR" in txt and "score" not in txt.lower()


def test_porque_sin_score_ni_justificacion_no_vacio():
    assert porque_recomendado("FOO").strip() != ""
    assert porque_recomendado("FOO", score_row={}).strip() != ""


def test_porque_rv_no_explota_con_score_invalido():
    # score_row con valores no numéricos no debe romper.
    txt = porque_recomendado("BAR", score_row={"Score_Total": "x", "Score_Fund": None})
    assert isinstance(txt, str) and txt.strip() != ""
