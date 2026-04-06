"""
execution_engine.py — Motor de Ejecución y Órdenes
Master Quant 26 | Estrategia Capitales
Genera órdenes de rebalanceo con regla anti-churning configurable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def generar_ordenes(
    pesos_objetivo: dict[str, float],
    capital_actual: dict[str, float],
    capital_nuevo: float,
    precios_ars: dict[str, float],
    umbral_pct: float = 0.05,
) -> list[dict]:
    """
    Genera órdenes de rebalanceo. Solo actúa si la desviación >= umbral (anti-churning).
    Recibe pesos del optimizador como parámetro; nunca usa pesos hardcodeados.
    """
    ordenes = []
    cap_total_actual = sum(capital_actual.values())
    cap_total_target = cap_total_actual + capital_nuevo
    if cap_total_target <= 0:
        return ordenes

    todos_tickers = set(list(pesos_objetivo.keys()) + list(capital_actual.keys()))

    for t in todos_tickers:
        peso_ideal = pesos_objetivo.get(t, 0.0)
        val_actual = capital_actual.get(t, 0.0)
        val_target = cap_total_target * peso_ideal
        diferencia = val_target - val_actual

        # Regla del 5%: ignorar si la desviacion es menor al umbral
        if cap_total_target > 0:
            desviacion = abs(diferencia) / cap_total_target
            if desviacion < umbral_pct and capital_nuevo == 0:
                continue

        px = precios_ars.get(t, 0.0)
        if px <= 0:
            continue

        nominales = int(diferencia / px)
        if nominales == 0:
            continue

        accion = "COMPRAR" if nominales > 0 else "VENDER"
        # Solo comprar si hay capital nuevo
        if capital_nuevo == 0 and accion == "COMPRAR":
            pass  # Rebalanceo puro: permite compras y ventas

        ordenes.append({
            "TICKER":    t,
            "ACCION":    accion,
            "NOMINALES": abs(nominales),
            "PRECIO_ARS": round(px, 2),
            "TOTAL_ARS":  round(abs(nominales) * px, 0),
            "PESO_IDEAL": round(peso_ideal * 100, 1),
            "DESVIACION": round((diferencia / cap_total_target) * 100, 1) if cap_total_target > 0 else 0,
        })

    return sorted(ordenes, key=lambda x: abs(x["TOTAL_ARS"]), reverse=True)


def calcular_nominales_cedear(
    ticker: str,
    monto_usd: float,
    precio_usd: float,
    ratio: float
) -> int:
    """Formula exacta para nominales CEDEAR: Monto / (Precio_US / Ratio)"""
    if precio_usd <= 0 or ratio <= 0:
        return 0
    precio_cedear_usd = precio_usd / ratio
    return max(0, int(monto_usd / precio_cedear_usd))
