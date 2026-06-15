"""Regresión mínima: documento P2-BYMA-01 presente y con anclas esperadas."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "product" / "BYMA_CAMPOS_Y_ESCALAS_MQ26.md"


@pytest.mark.parametrize(
    "needle",
    [
        "open.bymadata.com.ar",
        "byma_market_data.py",
        "corporate-bonds",
        "MQ26_BYMA_API_URL",
        "_normalizar_lastprice_on_byma",
        "## 10. Semántica ficha RF (P2-RF-01): TIR de referencia vs TIR al precio",
        "tir_al_precio",
    ],
)
def test_byma_campos_doc_cubre_implementacion(needle: str):
    assert DOC.is_file(), f"Falta {DOC}"
    text = DOC.read_text(encoding="utf-8")
    assert needle in text
