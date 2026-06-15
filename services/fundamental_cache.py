"""
services/fundamental_cache.py — Capa 1 del motor MQ26 (alias canónico).

Re-exporta toda la API de `services/fundamentals_cache.py` con el nombre
solicitado en la arquitectura definitiva (singular: "fundamental").

Uso recomendado:
    from services.fundamental_cache import obtener_fundamentales

Para mantener compatibilidad con código existente, ambos imports funcionan:
    from services.fundamentals_cache import obtener_fundamentales  # legacy
    from services.fundamental_cache  import obtener_fundamentales  # canónico
"""
from services.fundamentals_cache import (  # noqa: F401
    FundamentalsSnapshot,
    estadisticas_cache,
    listar_tickers_cacheados,
    obtener_fundamentales,
    precargar_fundamentales,
)


# ─── Helpers de normalización de escalas (críticos contra bug 1380%) ──────────

def pct_seguro(valor, decimals: int = 1) -> float | None:
    """
    Convierte un valor a porcentaje de manera SEGURA detectando la escala.

    Casos:
        valor = 0.2642  → fracción       → devuelve 26.42 (multiplica × 100)
        valor = 26.42   → ya en %         → devuelve 26.42 (no toca)
        valor = -52.86  → ya en % (signo) → devuelve -52.86
        valor = None    → None
        valor = 0       → 0.0

    Regla: si |valor| ≤ 1 asumimos fracción. Si > 1 asumimos porcentaje.

    Tope superior absoluto: 9999% (evita basura por errores extremos en feed).
    """
    if valor is None:
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return 0.0
    # Detectar escala
    if abs(v) <= 1:
        v = v * 100.0
    # Sanidad: ningún ratio razonable supera 10.000% en magnitud
    if abs(v) > 9999:
        return None
    return round(v, decimals)


def fraccion_segura(valor) -> float | None:
    """
    Convierte un valor a fracción de manera SEGURA detectando la escala.

    Inverso de pct_seguro: si valor > 1 asumimos porcentaje y dividimos.
    Útil para feeds que mezclan formatos.
    """
    if valor is None:
        return None
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return 0.0
    if abs(v) > 1:
        v = v / 100.0
    # Sanidad: ratios > 99 (en valor absoluto) son basura
    if abs(v) > 99:
        return None
    return v
