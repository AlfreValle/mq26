"""Tests del resumen en lenguaje natural de la cartera (H1)."""
from __future__ import annotations

from types import SimpleNamespace

from services.resumen_natural import resumen_natural_cartera


def _obs(titulo):
    return SimpleNamespace(titulo=titulo, icono="⚠️")


def test_resumen_verde_con_ganancia():
    diag = SimpleNamespace(
        semaforo=SimpleNamespace(value="verde"),
        score_total=82,
        rendimiento_ytd_usd_pct=0.123,  # fracción → 12.3%
        valor_cartera_usd=15000,
        observaciones=[_obs("Buena diversificación")],
    )
    txt = resumen_natural_cartera(diag, {"total_valor": 0}, ccl=1500, nombre="Ana | Moderado")
    assert "Hola Ana." in txt
    assert "USD 15,000" in txt
    assert "ganó 12.3%" in txt
    assert "saludable" in txt and "82/100" in txt
    assert "Buena diversificación" in txt


def test_resumen_rojo_sugiere_accion():
    diag = SimpleNamespace(
        semaforo=SimpleNamespace(value="rojo"),
        score_total=35,
        rendimiento_ytd_usd_pct=-0.08,
        valor_cartera_usd=5000,
        observaciones=[],
    )
    txt = resumen_natural_cartera(diag, {}, ccl=1500)
    assert "perdió 8.0%" in txt
    assert "necesita atención" in txt
    assert "revis" in txt.lower()  # acción sugerida para rojo


def test_resumen_robusto_a_campos_faltantes():
    diag = SimpleNamespace()  # sin atributos
    txt = resumen_natural_cartera(diag, {})
    assert isinstance(txt, str)  # no explota


def test_resumen_deriva_valor_de_metricas_si_falta_en_diag():
    diag = SimpleNamespace(semaforo=SimpleNamespace(value="amarillo"), score_total=55)
    txt = resumen_natural_cartera(diag, {"total_valor": 3_000_000}, ccl=1500)
    assert "USD 2,000" in txt  # 3.000.000 / 1500
    assert "para revisar" in txt
