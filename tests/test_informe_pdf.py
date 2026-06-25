"""Tests del informe de cartera en PDF (entregable)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("reportlab", reason="instalar con: pip install reportlab")

from services.informe_pdf import generar_informe_pdf


def _diag():
    return SimpleNamespace(
        semaforo=SimpleNamespace(value="verde"),
        score_total=78,
        rendimiento_ytd_usd_pct=0.12,
        valor_cartera_usd=15000,
        pct_defensivo_actual=0.30,
        pct_defensivo_requerido=0.35,
        titulo_semaforo="Cartera saludable",
        observaciones=[
            SimpleNamespace(titulo="Buena diversificación", icono="✅", detalle="8 activos en 4 sectores"),
            SimpleNamespace(titulo="Falta renta fija", icono="⚠️", detalle="30% vs 35% objetivo"),
        ],
    )


def _posiciones():
    import pandas as pd

    return pd.DataFrame([
        {"TICKER": "AAPL", "TIPO": "CEDEAR", "VALOR_ARS": 5_000_000, "PESO_PCT": 0.45, "PNL_PCT": 0.12},
        {"TICKER": "PN43O", "TIPO": "ON_USD", "VALOR_ARS": 3_000_000, "PESO_PCT": 0.27, "PNL_PCT": 0.03},
        {"TICKER": "KO", "TIPO": "CEDEAR", "VALOR_ARS": 3_100_000, "PESO_PCT": 0.28, "PNL_PCT": -0.04},
    ])


def _rr():
    items = [
        SimpleNamespace(ticker="AAPL", unidades=3, monto_ars=300_000, justificacion="Núcleo tech"),
        SimpleNamespace(ticker="PN43O", unidades=200, monto_ars=200_000, justificacion="ON USD 7% TIR"),
    ]
    return SimpleNamespace(compras_recomendadas=items)


def test_genera_pdf_valido_con_recomendacion():
    pdf = generar_informe_pdf(
        cliente_nombre="Ana Gómez | Moderado", perfil="Moderado",
        diag=_diag(), recomendacion=_rr(), metricas={"total_valor": 22_500_000}, ccl=1500,
    )
    assert isinstance(pdf, bytes)
    assert pdf[:5] == b"%PDF-"      # header de PDF válido
    assert len(pdf) > 1500          # tiene contenido real


def test_pdf_rico_con_posiciones_y_contexto():
    # El informe enriquecido (cartera actual + diagnóstico + contexto) pesa más.
    pdf_min = generar_informe_pdf(cliente_nombre="X", perfil="Moderado", diag=_diag())
    pdf_rico = generar_informe_pdf(
        cliente_nombre="Ana | Moderado", perfil="Moderado", diag=_diag(),
        recomendacion=_rr(), metricas={"total_valor": 11_100_000}, ccl=1500,
        posiciones=_posiciones(), contexto_mercado="El mercado viene alcista. Mantener el plan.",
    )
    assert pdf_rico[:5] == b"%PDF-"
    # Más secciones → más bytes que el mínimo.
    assert len(pdf_rico) > len(pdf_min)


def test_genera_pdf_sin_recomendacion_ni_diag():
    # Robusto: aun con datos mínimos produce un PDF válido.
    pdf = generar_informe_pdf(cliente_nombre="Cliente", perfil="Conservador")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 800
