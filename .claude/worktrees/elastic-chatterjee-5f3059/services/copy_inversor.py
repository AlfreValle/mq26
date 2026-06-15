"""
services/copy_inversor.py — Textos en lenguaje coloquial para UI inversor.

Sin Streamlit. Sin reglas de negocio: solo formateo y frases fijas.
"""
from __future__ import annotations


def participacion_txt(pct: float) -> str:
    """pct en 0–100."""
    return f"{pct:.1f}% de tu cartera"


def defensivo_vs_perfil(pct_actual_pct: float, pct_objetivo_pct: float, perfil: str) -> str:
    """pct_* en escala 0–100. Copy alineado a RF (antes “defensivo” en UI legacy)."""
    p = (perfil or "Moderado").strip()
    if pct_actual_pct + 0.5 >= pct_objetivo_pct:
        return (
            f"Tu **renta fija** está en **{pct_actual_pct:.0f}%** del patrimonio "
            f"— en línea con el target de un perfil **{p}** (~{pct_objetivo_pct:.0f}% RF)."
        )
    falt = pct_objetivo_pct - pct_actual_pct
    return (
        f"Tu **renta fija** está en **{pct_actual_pct:.0f}%**; "
        f"para un perfil **{p}** conviene acercarte a ~**{pct_objetivo_pct:.0f}%** RF "
        f"(faltan ~{falt:.0f} puntos; el resto es renta variable u otros activos)."
    )


def patrimonio_dual_line(valor_usd: float, valor_ars: float, ccl: float) -> str:
    """Una línea para caption: primero pesos (cotización local), USD como referencia."""
    c = max(float(ccl or 0.0), 1e-9)
    return (
        f"Patrimonio: **ARS {valor_ars:,.0f}** (~ **USD {valor_usd:,.0f}**) "
        f"· CCL {c:,.0f}"
    )


def antes_despues_defensivo(antes_pct: float, despues_pct: float) -> str:
    """Mensaje tras una carga exitosa. Escala 0–100 (participación RF)."""
    return (
        f"Tras esta operación, tu **renta fija** pasó de **{antes_pct:.0f}%** "
        f"a **{despues_pct:.0f}%** del patrimonio."
    )


def titulo_seccion_resumen(nombre: str) -> str:
    return f"Tu cartera — {nombre.strip() or 'Inversor'}"


def ayuda_precio_cedear() -> str:
    return (
        "En Argentina operás en **pesos**: el precio de cada CEDEAR es el de la bolsa local "
        "(ARS por cuotaparte). Mostramos también una **referencia en USD** cuando ayuda a comparar."
    )


def historial_meses_copy() -> str:
    return "Acá están todas las compras que cargaste. Si algo no coincide con el broker, corregilo con tu asesor."


def broker_tarjeta_sub(broker: str) -> str:
    b = broker.strip()
    hints = {
        "Balanz": "Exportá tu estado de cuenta o boletos en Excel/CSV.",
        "IOL": "Subí el Excel o CSV que exporte tu broker (formato compatible).",
        "BMB": "Usá la exportación de operaciones en Excel/CSV de Bull Market.",
    }
    return hints.get(b, "Subí el archivo que te dé tu broker.")


# ── Fase C hub inversor: glosario corto (tooltips / expander) ─────────────────
GLOSARIO_INVERSOR: dict[str, str] = {
    "salud_score": (
        "Un solo número del motor (0–100): mezcla concentración, cuánta renta fija tenés "
        "vs tu perfil, señales del universo y otras reglas. No es una promesa de ganancia."
    ),
    "semaforo": (
        "Verde / amarillo / rojo es una lectura rápida del mismo diagnóstico: "
        "si hay mucho rojo en el puntaje o en riesgos, el semáforo lo refleja."
    ),
    "rf_rv": (
        "**Renta fija:** instrumentos que pagan cupón o devuelven capital en fechas conocidas (bonos, ON, letras). "
        "**Renta variable:** acciones y CEDEARs: el precio fluctúa más."
    ),
    "rebalanceo": (
        "Rebalancear es volver a acercar la cartera a los pesos que querés (perfil + objetivos). "
        "Acá ves sugerencias y precios de referencia; las órdenes las das vos en el broker."
    ),
    "target_stop": (
        "**Target:** precio orientativo donde el motor considera razonable tomar ganancia. "
        "**Stop:** nivel de alerta si la posición se mueve en tu contra. No ejecutan solos."
    ),
    "ccl": (
        "Tipo de cambio de referencia ARS por USD que usa la app para convertir y comparar. "
        "Tu broker puede cotizar distinto."
    ),
}


def copy_rebalanceo_humano() -> str:
    """Intro de la pestaña Rebalanceo: tono claro, sin jerga innecesaria."""
    return (
        "**Qué podés hacer acá**  \n"
        "• Ver **objetivos por posición** (target, stop, señal) según tu perfil y el motor.  \n"
        "• Si tenés **plata nueva**, pedir una sugerencia de **qué comprar** alineada a lo que ya tenés.  \n"
        "• **Importar** compras o registrar ventas para que los números reflejen la realidad.  \n\n"
        "**Qué hace MQ26**  \n"
        "Te ordena la información y sugiere precios y alertas. **No manda órdenes** al broker: "
        "operás vos cuando quieras. Si usás stops automáticos en otra app, replicá ahí los niveles sugeridos."
    )


def pasos_onboarding_hub() -> list[tuple[str, str]]:
    """Tres pasos tipo ‘recorrido’ (onboarding ligero, no bloquea la UI)."""
    return [
        (
            "1 · Resumen",
            "Mirá cuánto vale todo y cómo vienen tus posiciones.",
        ),
        (
            "2 · Salud y alineación",
            "Acá está el **puntaje único** del motor y el semáforo: te dice si la cartera "
            "va en línea con tu perfil.",
        ),
        (
            "3 · Rebalanceo",
            "Objetivos por ticker, plata nueva e importaciones: próximos pasos concretos.",
        ),
    ]
