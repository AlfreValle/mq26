"""Smoke tests services/reporte_inversor.py"""
from core.diagnostico_types import DiagnosticoResult, RecomendacionResult, Semaforo


def _diag() -> DiagnosticoResult:
    return DiagnosticoResult(
        cliente_nombre="Test",
        perfil="Moderado",
        horizonte_label="3 años",
        fecha_diagnostico="2026-04-02",
        score_total=72.0,
        semaforo=Semaforo.AMARILLO,
        score_cobertura_defensiva=70.0,
        score_concentracion=80.0,
        score_rendimiento=65.0,
        score_senales_salida=75.0,
        titulo_semaforo="Buen estado general",
        resumen_ejecutivo="Resumen.",
        valor_cartera_usd=10_000.0,
        rendimiento_ytd_usd_pct=4.5,
    )


def test_generar_reporte_inversor_contiene_secciones():
    from services.reporte_inversor import generar_reporte_inversor

    html = generar_reporte_inversor(_diag(), None, {"total_valor": 15_000_000.0, "ccl": 1500.0})
    assert "MQ26" in html
    assert "Tu cartera vs referencias" in html
    assert "TIR ref" in html
    assert "TLCTO" in html or "DNC7O" in html
    assert "Ladder de vencimientos" in html
    assert "Diagnóstico" in html
    assert "informativo" in html
    assert "DOCTYPE html" in html


def test_generar_reporte_inversor_svg_cuando_hay_series():
    from services.reporte_inversor import generar_reporte_inversor

    ser = {
        "fechas": ["2026-01-01", "2026-02-01", "2026-03-01"],
        "cliente_norm": [100.0, 101.0, 102.0],
        "modelo_norm": [100.0, 100.5, 101.0],
        "spy_norm": [100.0, 100.2, 100.8],
    }
    html = generar_reporte_inversor(
        _diag(),
        None,
        {"total_valor": 1.0, "ccl": 1.0},
        bloque_competitivo={"series_comparacion": ser},
    )
    assert "<svg" in html
    assert "stroke=\"#1565c0\"" in html


def test_generar_reporte_estudio_tabla():
    from services.reporte_inversor import generar_reporte_estudio

    html = generar_reporte_estudio(
        [{"nombre": "A", "semaforo": "verde", "score": 80}],
        _diag(),
        None,
        {"total_valor": 1.0, "ccl": 1.0},
    )
    assert "Panel de estudio" in html
    assert "Metodología" in html


def test_generar_reporte_institucional_disclaimer():
    from services.reporte_inversor import generar_reporte_institucional

    rr = RecomendacionResult(
        cliente_nombre="Test",
        perfil="Moderado",
        capital_disponible_ars=0.0,
        capital_disponible_usd=0.0,
        ccl=1000.0,
        fecha_recomendacion="2026-04-02",
    )
    html = generar_reporte_institucional(
        _diag(), rr, {"total_valor": 1.0, "ccl": 1.0},
        asesor="Ana G.", matricula="999",
    )
    assert "regulatorio" in html or "exclusiva responsabilidad" in html
