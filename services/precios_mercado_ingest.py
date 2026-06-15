"""
Ingesta de precios hacia BD (`precios_fallback`) con escala alineada a brokers / feed BYMA.

P2-BYMA-02: opcional cuando se usa `DATABASE_URL` (o SQLite local): los jobs ETL o scripts
pueden volcar cotizaciones crudas y **normalizar ON USD** con la misma regla ÷100 que
`services/byma_market_data` antes de persistir, para que `PriceEngine` (FALLBACK_BD) y
`calcular_posicion_neta` vean **ARS por nominal** coherente.

Sin Streamlit.
"""
from __future__ import annotations

from typing import Any

from core.unit_contracts import es_instrumento_rf_usd_paridad


def precio_ars_canonico_para_persistencia(
    ticker: str,
    precio_raw_ars: float,
    ccl: float,
    tipo: str | None = None,
) -> float:
    """
    Devuelve el precio ARS a guardar en `precios_fallback` / motor.

    - Instrumentos **RF USD paridad** (ON/bono cable): aplica `normalizar_precio_ars_on_usd_desde_feed_o_broker`.
    - Resto: sin cambio de escala (CEDEAR, acción local, etc.).
    """
    if precio_raw_ars <= 0 or ccl <= 0:
        return float(precio_raw_ars)
    t = str(ticker).upper().strip()
    if not es_instrumento_rf_usd_paridad(t, tipo):
        return float(precio_raw_ars)
    from services.byma_market_data import normalizar_precio_ars_on_usd_desde_feed_o_broker

    return float(normalizar_precio_ars_on_usd_desde_feed_o_broker(float(precio_raw_ars), float(ccl)))


def ingestar_precios_fallback_desde_dict(
    precios_raw: dict[str, Any],
    ccl: float,
    fuente: str = "ingest_bd",
    tipos_por_ticker: dict[str, str] | None = None,
) -> dict[str, float]:
    """
    Persiste precios en `precios_fallback` aplicando escala RF USD cuando corresponde.

    Args:
        precios_raw: {ticker: precio_ars_crudo}
        ccl: tipo de cambio contado con liqui (mismo que usa el resto del motor)
        fuente: etiqueta en columna `fuente` (ej. ``ingest_bd``, ``etl_nightly``)
        tipos_por_ticker: opcional ``TICKER -> TIPO`` si el maestro trae tipo explícito

    Returns:
        {ticker: precio_ars persistido (canónico)}
    """
    from core.db_manager import guardar_precio_fallback

    tipos = {str(k).upper(): str(v) for k, v in (tipos_por_ticker or {}).items()}
    out: dict[str, float] = {}
    for tk_raw, px in precios_raw.items():
        if px is None:
            continue
        try:
            px_f = float(px)
        except (TypeError, ValueError):
            continue
        if px_f <= 0:
            continue
        tu = str(tk_raw).upper().strip()
        tipo = tipos.get(tu)
        canon = precio_ars_canonico_para_persistencia(tu, px_f, ccl, tipo)
        guardar_precio_fallback(tu, canon, fuente)
        out[tu] = canon
    return out
