"""P2-BYMA-02: ingesta a precios_fallback con escala ON USD alineada al feed BYMA."""
from __future__ import annotations

from services.precios_mercado_ingest import (
    ingestar_precios_fallback_desde_dict,
    precio_ars_canonico_para_persistencia,
)


def test_canonico_on_usd_div100_misma_heuristica_que_feed():
    ccl = 1500.0
    # 148500 → 1485 ARS/VN (test_byma_market_data mismo orden de magnitud)
    px = precio_ars_canonico_para_persistencia("TLCTO", 148_500.0, ccl, None)
    assert abs(px - 1485.0) < 0.05


def test_canonico_cedear_sin_tocar():
    ccl = 1500.0
    px = precio_ars_canonico_para_persistencia("GGAL", 5200.0, ccl, "CEDEAR")
    assert px == 5200.0


def test_ingestar_persiste_en_bd_normalizado(db_en_memoria):
    ccl = 1500.0
    out = ingestar_precios_fallback_desde_dict(
        {"TLCTO": 148_500.0, "GGAL": 5200.0},
        ccl=ccl,
        fuente="test_p2_byma02",
    )
    assert abs(out["TLCTO"] - 1485.0) < 0.05
    assert out["GGAL"] == 5200.0

    fb = db_en_memoria.obtener_precios_fallback()
    assert abs(fb["TLCTO"] - 1485.0) < 0.05
    assert fb["GGAL"] == 5200.0
