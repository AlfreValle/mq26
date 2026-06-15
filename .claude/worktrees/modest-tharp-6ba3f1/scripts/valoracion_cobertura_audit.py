"""
Imprime auditoría % valor live vs fallback por TIPO (misma lógica que run_mq26).

Uso (desde raíz del repo):
  python scripts/valoracion_cobertura_audit.py

Requiere sesión con cartera cargada vía transaccional, o adaptar el script a tu CSV.
Por defecto solo demuestra la API con DataFrames sintéticos.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core.price_engine import PriceRecord, PriceSource
from services.valoracion_audit import auditar_valoracion_por_tipo


def _demo() -> None:
    df = pd.DataFrame({
        "TICKER": ["GGAL", "AL30"],
        "TIPO": ["ACCION_LOCAL", "BONO_SOBERANO"],
        "VALOR_ARS": [80_000.0, 20_000.0],
    })
    rec = {
        "GGAL": PriceRecord(
            "GGAL", 5000.0, 1.0, 1000.0, 1.0, PriceSource.LIVE_BYMA, datetime.now(),
        ),
        "AL30": PriceRecord(
            "AL30", 70.0, 1.0, 1000.0, 1.0, PriceSource.FALLBACK_HARD, datetime.now(),
        ),
    }
    r = auditar_valoracion_por_tipo(df, rec)
    print("Demo auditar_valoracion_por_tipo:")
    for k in ("total_valor_ars", "pct_valor_live", "pct_valor_no_live"):
        print(f"  {k}: {r.get(k)}")
    print("  por_tipo:", r.get("por_tipo"))


if __name__ == "__main__":
    _demo()
