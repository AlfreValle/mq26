"""
services/guardrails.py — capa de validación explícita del plan recomendado (H1).

Antes de mostrar/adjuntar una recomendación, se la valida contra reglas duras de
negocio (concentración, alineación de perfil, capital, monto mínimo, precio).
Es defensa en profundidad + transparencia: NO bloquea ni re-decide (MQ26 es
recomendador, no ejecutor) — surfacea violaciones para que el humano decida.

Función pura, sin Streamlit. Reglas centralizadas acá (antes estaban dispersas:
tope overweight en el motor, monto chico en recomendador_explicable, mix por
perfil en cartera_optima).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.cartera_optima import PERFIL_CONSTRAINTS
from core.diagnostico_types import perfil_diagnostico_valido
from core.renta_fija_ar import es_renta_fija

# Umbral de monto chico (alineado con recomendador_explicable): por debajo, la
# comisión mínima del broker pesa de más.
UMBRAL_MONTO_CHICO_ARS = 20_000.0
# Concentración: por encima de esto en UN activo, advertir (no es error duro —
# con poco capital y pocos holdings la concentración sube por diseño).
CONCENTRACION_RV_MAX = 0.50   # un CEDEAR/acción solo no debería superar ~50%
CONCENTRACION_ANY_MAX = 0.60  # ningún activo (ni RF) debería superar ~60%
# Tolerancia para el rango RF del perfil (puntos de fracción).
TOL_MIX_RF = 0.10

SEV_ERROR = "ERROR"
SEV_ADVERTENCIA = "ADVERTENCIA"


@dataclass
class Violacion:
    """Una regla incumplida por el plan. severidad ERROR bloquea; ADVERTENCIA avisa."""

    regla: str
    severidad: str
    mensaje: str


def _items(rr: Any) -> list[Any]:
    return list(getattr(rr, "compras_recomendadas", None) or [])


def validar_recomendacion(
    rr: Any,
    *,
    perfil: str,
    capital_ars: float,
) -> list[Violacion]:
    """Valida el plan de compras contra las reglas. Devuelve la lista de
    violaciones (vacía = todo OK). No lanza: ante datos raros, no inventa errores.
    """
    out: list[Violacion] = []
    items = _items(rr)
    if not items or capital_ars <= 0:
        return out

    perfil_n = perfil_diagnostico_valido(perfil)
    c = PERFIL_CONSTRAINTS.get(perfil_n, PERFIL_CONSTRAINTS["Moderado"])

    montos = {}
    monto_total = 0.0
    for it in items:
        tk = str(getattr(it, "ticker", "") or "").upper()
        m = float(getattr(it, "monto_ars", 0) or 0)
        precio = float(getattr(it, "precio_ars_estimado", 0) or 0)
        if tk:
            montos[tk] = montos.get(tk, 0.0) + m
            monto_total += m
        # R-precio: no recomendar sin precio válido.
        if precio <= 0:
            out.append(Violacion(
                "precio", SEV_ERROR,
                f"{tk or 'Un activo'} no tiene precio válido — no se puede valuar la compra.",
            ))

    # R-capital: no exceder el capital disponible (tolerancia de redondeo).
    if monto_total > capital_ars * 1.005:
        out.append(Violacion(
            "capital", SEV_ERROR,
            f"El plan suma ${monto_total:,.0f} ARS, supera el capital disponible "
            f"(${capital_ars:,.0f}).",
        ))

    if monto_total <= 0:
        return out

    # R-concentración: ningún activo demasiado pesado.
    for tk, m in montos.items():
        frac = m / monto_total
        es_rf = es_renta_fija(tk)
        if frac > CONCENTRACION_ANY_MAX or (not es_rf and frac > CONCENTRACION_RV_MAX):
            out.append(Violacion(
                "concentracion", SEV_ADVERTENCIA,
                f"{tk} concentra {frac * 100:.0f}% del plan — alta concentración "
                "en un solo activo (mayor riesgo).",
            ))

    # R-mix de perfil: la renta fija debe caer en el rango del perfil (±tolerancia).
    rf_frac = sum(m for tk, m in montos.items() if es_renta_fija(tk)) / monto_total
    rf_min = float(c.get("rf_min", 0.0))
    rf_max = float(c.get("rf_max", 1.0))
    if rf_frac < rf_min - TOL_MIX_RF:
        out.append(Violacion(
            "mix_perfil", SEV_ADVERTENCIA,
            f"Renta fija {rf_frac * 100:.0f}% — por debajo del piso del perfil "
            f"{perfil_n} ({rf_min * 100:.0f}%). Cartera más agresiva que el perfil.",
        ))
    elif rf_frac > rf_max + TOL_MIX_RF:
        out.append(Violacion(
            "mix_perfil", SEV_ADVERTENCIA,
            f"Renta fija {rf_frac * 100:.0f}% — por encima del techo del perfil "
            f"{perfil_n} ({rf_max * 100:.0f}%). Cartera más conservadora que el perfil.",
        ))

    # R-monto chico: compras donde la comisión mínima pesa de más.
    chicas = [tk for tk, m in montos.items() if 0 < m < UMBRAL_MONTO_CHICO_ARS]
    if chicas:
        out.append(Violacion(
            "monto_chico", SEV_ADVERTENCIA,
            f"{len(chicas)} compra(s) por debajo de ${UMBRAL_MONTO_CHICO_ARS:,.0f} ARS "
            f"({', '.join(chicas[:4])}): la comisión mínima del broker pesa de más.",
        ))

    return out


def hay_errores(violaciones: list[Violacion]) -> bool:
    """True si hay alguna violación de severidad ERROR (debería frenar el adjuntar)."""
    return any(v.severidad == SEV_ERROR for v in violaciones)
