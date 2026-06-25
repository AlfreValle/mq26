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
        observaciones=[SimpleNamespace(titulo="Buena diversificación", icono="✅")],
    )


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


def test_genera_pdf_sin_recomendacion_ni_diag():
    # Robusto: aun con datos mínimos produce un PDF válido.
    pdf = generar_informe_pdf(cliente_nombre="Cliente", perfil="Conservador")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 800
