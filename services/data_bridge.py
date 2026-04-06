"""
services/data_bridge.py — Almacenamiento de datos de configuración compartida.
Utiliza la tabla `configuracion` para persistir valores clave/valor entre sesiones.
"""
from __future__ import annotations


def _fallback_ccl_positivo() -> float:
    """Lee CCL_FALLBACK_OVERRIDE o 1500.0; Invariante: retorna siempre float > 0."""
    import os
    raw = os.environ.get("CCL_FALLBACK_OVERRIDE", "1500.0")
    try:
        v = float(raw)
        return v if v > 0 else 1500.0
    except (TypeError, ValueError):
        return 1500.0


def publicar_ccl(ccl: float) -> None:
    """
    Publica el CCL calculado por MQ26 para que DSS lo muestre como referencia.
    Invariante: no propaga excepciones.
    """
    try:
        import core.db_manager as dbm
        dbm.set_config("ccl_actual", str(round(ccl, 2)))
    except Exception:
        pass


def leer_ccl() -> float:
    """
    Lee el CCL publicado por MQ26. Devuelve el fallback si no existe o falla la BD.
    Invariante: siempre retorna float > 0.
    """
    import core.db_manager as dbm
    raw = None
    try:
        raw = dbm.get_config("ccl_actual")
    except Exception:
        return _fallback_ccl_positivo()
    if raw:
        try:
            v = float(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return _fallback_ccl_positivo()


def publicar_objetivo_completado(cliente_id: int, ticker: str, monto_ars: float) -> None:
    """
    Notifica a través de la BD que un objetivo fue alcanzado.
    Invariante: no propaga excepciones.
    """
    import datetime as dt

    try:
        import core.db_manager as dbm
        dbm.set_config(
            f"objetivo_completado_{cliente_id}_{ticker}",
            f"{monto_ars}|{dt.date.today().isoformat()}",
        )
    except Exception:
        pass
