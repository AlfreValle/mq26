"""
decision_engine.py — Árbol de Decisión con Filtro de Alpha Neto
Master Quant 26 + DSS Unificado
Versión mejorada: integra costos de broker y filtra solo órdenes con alpha_neto > 0
"""

import pandas as pd


def calcular_costos_operacion(
    ticker: str,
    tipo_op: str,
    nominales: int,
    precio_ars: float,
    comision_pct: float = 0.006,   # IOL: 0.6%, BullMarket: ~0.5%
    derechos_mep: float = 0.0004,  # derechos de mercado ~0.04%
    spread_pct: float = 0.001,     # spread implícito estimado ~0.1%
) -> dict:
    valor_nocional = nominales * precio_ars
    costo_total = valor_nocional * (comision_pct + derechos_mep + spread_pct)
    return {
        "ticker": ticker,
        "tipo_op": tipo_op,
        "nominales": nominales,
        "precio_ars": precio_ars,
        "valor_nocional": round(valor_nocional, 2),
        "costo_total": round(costo_total, 2),
        "comision": round(valor_nocional * comision_pct, 2),
        "derechos": round(valor_nocional * derechos_mep, 2),
        "spread": round(valor_nocional * spread_pct, 2),
    }


def filtrar_por_alpha_neto(
    ordenes: list[dict],
    retornos_esperados: dict[str, float],  # retorno diario esperado por ticker
    horizonte_dias: int = 252,
    comision_pct: float = 0.006,
    derechos_mep: float = 0.0004,
    spread_pct: float = 0.001,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Filtra órdenes: solo ejecuta si alpha_neto > 0.
    alpha_esperado = ((1 + ret_diario)^horizonte - 1) * valor_nocional * signo
    alpha_neto = alpha_esperado - costos_totales

    Usa crecimiento compuesto (no lineal) para horizontes > 30 días.
    Devuelve: (ejecutables_df, bloqueadas_df)
    """
    if not ordenes:
        cols = ["ticker","tipo_op","nominales","precio_ars","valor_nocional",
                "costo_total","alpha_esperado","alpha_neto","decision"]
        return pd.DataFrame(columns=cols), pd.DataFrame(columns=cols)

    rows = []
    for orden in ordenes:
        ticker = orden["ticker"]
        tipo_op = orden.get("tipo_op", "COMPRA")
        nominales = orden.get("nominales", 0)
        precio = orden.get("precio_ars", 0.0)

        costos = calcular_costos_operacion(
            ticker, tipo_op, nominales, precio,
            comision_pct=comision_pct,
            derechos_mep=derechos_mep,
            spread_pct=spread_pct,
        )

        # Alpha esperado: crecimiento compuesto sobre el horizonte (no lineal)
        # Para COMPRAs: alpha = ganancia esperada del activo en el horizonte
        # Para VENTAs: alpha = capital liberado × (peso_actual - peso_optimo)
        #              es decir, el costo de oportunidad de MANTENER overweight vs vender
        ret_diario = retornos_esperados.get(ticker, 0.0)
        ret_compuesto = ((1.0 + ret_diario) ** horizonte_dias - 1.0)
        if tipo_op == "COMPRA":
            alpha_esperado = ret_compuesto * costos["valor_nocional"]
        else:
            # Para VENTAs: el alpha es positivo si el retorno esperado es NEGATIVO
            # (conviene vender) o si hay sobreweight que genera costo de oportunidad
            peso_actual = orden.get("peso_actual", 0.0)
            peso_optimo = orden.get("peso_optimo", 0.0)
            sobreweight = max(0.0, peso_actual - peso_optimo)
            alpha_esperado = (sobreweight * costos["valor_nocional"] -
                              ret_compuesto * costos["valor_nocional"])
        alpha_neto = alpha_esperado - costos["costo_total"]

        rows.append({
            **costos,
            "alpha_esperado": round(alpha_esperado, 2),
            "alpha_neto": round(alpha_neto, 2),
            "decision": "✅ EJECUTAR" if alpha_neto > 0 else "🚫 BLOQUEAR",
            "motivo": "" if alpha_neto > 0 else f"Alpha neto negativo (${alpha_neto:,.0f} ARS)",
        })

    df = pd.DataFrame(rows)
    ejecutables = df[df["alpha_neto"] > 0].copy()
    bloqueadas  = df[df["alpha_neto"] <= 0].copy()
    return ejecutables, bloqueadas


def generar_reporte_decision(ejecutables: pd.DataFrame, bloqueadas: pd.DataFrame) -> str:
    """Genera un resumen textual de las decisiones de ejecución."""
    total_ordenes = len(ejecutables) + len(bloqueadas)
    total_capital = ejecutables["valor_nocional"].sum() if not ejecutables.empty else 0.0
    total_costos  = ejecutables["costo_total"].sum() if not ejecutables.empty else 0.0
    total_alpha   = ejecutables["alpha_neto"].sum() if not ejecutables.empty else 0.0

    lines = [
        "📊 ÁRBOL DE DECISIÓN — Resumen",
        f"Total órdenes analizadas: {total_ordenes}",
        f"✅ Órdenes aprobadas: {len(ejecutables)}",
        f"🚫 Órdenes bloqueadas: {len(bloqueadas)}",
        "",
        f"💰 Capital a desplegar: ${total_capital:,.0f} ARS",
        f"💸 Costo total broker: ${total_costos:,.0f} ARS",
        f"📈 Alpha neto proyectado: ${total_alpha:,.0f} ARS",
    ]
    if not bloqueadas.empty:
        lines.append("\n🚫 Órdenes bloqueadas por alpha negativo:")
        for _, r in bloqueadas.iterrows():
            lines.append(f"  - {r['ticker']} ({r['tipo_op']}): {r['motivo']}")
    return "\n".join(lines)
