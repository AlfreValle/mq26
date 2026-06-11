"""Tests services/reporte_pdf.py — generación de PDF profesional."""
from __future__ import annotations

from datetime import date

import pytest

# fpdf2 puede no estar instalado en CI; saltear graciosamente
fpdf2 = pytest.importorskip("fpdf", reason="fpdf2 no instalado")

from services.reporte_pdf import (
    FilaCartera,
    FilaEscenario,
    FilaRebalanceo,
    MetricasCartera,
    ReporteInput,
    generar_reporte_pdf,
    reporte_desde_cartera,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _input_basico() -> ReporteInput:
    return ReporteInput(
        nombre_cliente   = "Familia Test",
        capital_total_ars = 5_000_000.0,
        ccl              = 1_200.0,
        fecha_reporte    = date(2025, 6, 1),
        metricas         = MetricasCartera(
            retorno_esperado_pct = 35.0,
            vol_anual_pct        = 18.5,
            sharpe               = 1.45,
            sortino              = 2.10,
            max_drawdown_pct     = -12.5,
            cvar_95_pct          = 2.1,
        ),
        filas_cartera    = [
            FilaCartera("AAPL",  "Apple Inc.",         "Tecnología", "USD", 20.0, 12.0, 22.0, 0.55),
            FilaCartera("GGAL",  "Grupo Financiero G.", "Financiero", "ARS", 15.0, 35.0, 40.0, 0.88),
            FilaCartera("AL30",  "Bono AL30",           "Soberano",   "USD", 25.0,  9.0, 15.0, 0.60),
            FilaCartera("TSC2O", "ON Telecom",          "Corporativo","USD", 20.0,  8.5, 10.0, 0.85),
            FilaCartera("TX26",  "Bono CER TX26",       "CER",        "ARS", 20.0, 45.0,  8.0, 5.60),
        ],
        escenarios       = [
            FilaEscenario("Devaluación 30 %",  "Salto de TCO del 30%",   -12.5, -18.0),
            FilaEscenario("EMBI +300 bps",      "+300 bps en spreads EM",  -8.3, -11.0),
            FilaEscenario("Recesión sectorial", "PBI -3 % anual",          -5.1,  -7.5),
        ],
        ordenes_rebalanceo = [
            FilaRebalanceo("AAPL",  "COMPRA",  5.0, 250_000.0, 1),
            FilaRebalanceo("GGAL",  "VENTA",  -3.0, 150_000.0, 2),
            FilaRebalanceo("AL30",  "HOLD",    0.5,       0.0, 3),
        ],
        regimen_actual    = "NORMAL",
        vol_actual_ann_pct = 16.2,
        pct_dias_crisis   = 0.18,
        turnover_pct      = 8.0,
        costo_total_ars   = 12_000.0,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_genera_bytes_no_vacio():
    inp = _input_basico()
    pdf_bytes = generar_reporte_pdf(inp)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5_000


def test_pdf_tiene_header():
    """Los primeros bytes deben empezar con %PDF (magic PDF)."""
    pdf_bytes = generar_reporte_pdf(_input_basico())
    assert pdf_bytes[:4] == b"%PDF"


def test_sin_cartera_no_falla():
    inp = _input_basico()
    inp.filas_cartera = []
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_sin_escenarios_no_falla():
    inp = _input_basico()
    inp.escenarios = []
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_sin_ordenes_no_falla():
    inp = _input_basico()
    inp.ordenes_rebalanceo = []
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_regimen_crisis_no_falla():
    inp = _input_basico()
    inp.regimen_actual = "CRISIS"
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_regimen_low_vol_no_falla():
    inp = _input_basico()
    inp.regimen_actual = "LOW_VOL"
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_reporte_desde_cartera_helper():
    pdf_bytes = reporte_desde_cartera(
        nombre_cliente    = "Test SA",
        capital_total_ars = 2_000_000.0,
        ccl               = 1_100.0,
        pesos_dict        = {"AAPL": 40.0, "GGAL": 30.0, "AL30": 30.0},
        metricas_dict     = {"retorno_esperado_pct": 20.0, "vol_anual_pct": 15.0, "sharpe": 1.2},
        escenarios_dict   = [
            {"nombre": "Stress", "descripcion": "Test", "impacto_cartera_pct": -10.0}
        ],
        ordenes_dict      = [
            {"ticker": "AAPL", "tipo": "COMPRA", "delta_pct": 5.0, "monto_ars": 100_000.0, "prioridad": 1}
        ],
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"


def test_capital_grande_no_falla():
    inp = _input_basico()
    inp.capital_total_ars = 100_000_000_000.0
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_nombre_largo_no_falla():
    inp = _input_basico()
    inp.nombre_cliente = "A" * 200
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 1_000


def test_muchas_filas_cartera():
    inp = _input_basico()
    inp.filas_cartera = [
        FilaCartera(f"T{i}", f"Activo {i}", "Genérico", "ARS", 1.0 / 30 * 100, 10.0, 20.0, 0.5)
        for i in range(30)
    ]
    pdf_bytes = generar_reporte_pdf(inp)
    assert len(pdf_bytes) > 5_000
