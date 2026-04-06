"""
services/copy_inversor.py — Textos en lenguaje coloquial para UI inversor.

Sin Streamlit. Sin reglas de negocio: solo formateo y frases fijas.
"""
from __future__ import annotations


def participacion_txt(pct: float) -> str:
    """pct en 0–100."""
    return f"{pct:.1f}% de tu cartera"


def defensivo_vs_perfil(pct_actual_pct: float, pct_objetivo_pct: float, perfil: str) -> str:
    """pct_* en escala 0–100."""
    p = (perfil or "Moderado").strip()
    if pct_actual_pct + 0.5 >= pct_objetivo_pct:
        return (
            f"Tu parte **defensiva** está en **{pct_actual_pct:.0f}%** "
            f"— en línea con lo que buscá un perfil **{p}** (objetivo ~{pct_objetivo_pct:.0f}%)."
        )
    falt = pct_objetivo_pct - pct_actual_pct
    return (
        f"Tu parte **defensiva** está en **{pct_actual_pct:.0f}%**; "
        f"para tu perfil **{p}** conviene acercarte a **{pct_objetivo_pct:.0f}%** "
        f"(faltan ~{falt:.0f} puntos)."
    )


def patrimonio_dual_line(valor_usd: float, valor_ars: float, ccl: float) -> str:
    """Una línea para caption o métrica secundaria."""
    c = max(float(ccl or 0.0), 1e-9)
    return (
        f"Patrimonio: **USD {valor_usd:,.0f}** · **ARS {valor_ars:,.0f}** "
        f"(CCL hoy {c:,.0f})"
    )


def antes_despues_defensivo(antes_pct: float, despues_pct: float) -> str:
    """Mensaje tras una carga exitosa. Escala 0–100."""
    return (
        f"Tras esta operación, tu parte defensiva pasó de **{antes_pct:.0f}%** "
        f"a **{despues_pct:.0f}%**."
    )


def titulo_seccion_resumen(nombre: str) -> str:
    return f"Tu cartera — {nombre.strip() or 'Inversor'}"


def ayuda_precio_cedear() -> str:
    return "Precio en **dólares** por acción/ETF, como en el boleto del broker. Nosotros convertimos a pesos con el CCL."


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
