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
