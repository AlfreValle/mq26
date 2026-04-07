"""
core/perfil_allocation.py — SSOT de targets RF/RV por perfil (Core & Satélite).

RF = renta fija argentina / instrumentos en TIPOS_RF y catálogo renta_fija_ar.
Versión publicada con cada diagnóstico para trazabilidad.
"""
from __future__ import annotations

RULESET_VERSION = "2026.04.3"

# Mismo conjunto que core/diagnostico_types.AJUSTE_HORIZONTE_CORTO (evita import circular).
_HORIZONTE_CORTO_RF: frozenset[str] = frozenset({"1 mes", "3 meses", "6 meses"})

# SSOT: (RF, RV) en fracción 0–1, suma 1. Conservador 60/40 (pedido “60/30”: 60% RF; RV = resto para cerrar 100%).
TARGET_RF_RV_BY_PERFIL: dict[str, tuple[float, float]] = {
    "Conservador": (0.60, 0.40),
    "Moderado": (0.50, 0.50),
    "Arriesgado": (0.35, 0.65),
    "Muy arriesgado": (0.30, 0.70),
}

# Fracción objetivo de Renta Fija por perfil (derivada de TARGET_RF_RV_BY_PERFIL).
TARGET_DF_FRACCION: dict[str, float] = {k: v[0] for k, v in TARGET_RF_RV_BY_PERFIL.items()}

PERFILES_TARGET_ORDER: tuple[str, ...] = tuple(TARGET_RF_RV_BY_PERFIL.keys())


def perfil_en_targets(perfil: str) -> bool:
    return (perfil or "").strip() in TARGET_DF_FRACCION


def target_rf_fraccion(perfil: str) -> float:
    """Target RF base (sin ajuste por horizonte)."""
    p = (perfil or "").strip()
    return float(TARGET_DF_FRACCION.get(p, TARGET_DF_FRACCION["Moderado"]))


def target_rv_fraccion(perfil: str) -> float:
    return max(0.0, min(1.0, 1.0 - target_rf_fraccion(perfil)))


def target_rf_efectivo(perfil: str, horizonte_label: str) -> float:
    """
    RF objetivo con +10 pp si el horizonte es corto (más sostén / liquidez).
    """
    rf = target_rf_fraccion(perfil)
    h = str(horizonte_label or "").strip()
    if h in _HORIZONTE_CORTO_RF:
        rf = min(1.0, rf + 0.10)
    return rf


def target_rv_efectivo(perfil: str, horizonte_label: str) -> float:
    return max(0.0, min(1.0, 1.0 - target_rf_efectivo(perfil, horizonte_label)))


def exceso_rv_muy_arriesgado(pct_rv_actual: float) -> str:
    """
    Bandas explícitas perfil Muy arriesgado (target RV 70%): amarillo >75%, rojo >85%.
    Retorna '', 'amarillo', 'rojo'.
    """
    if pct_rv_actual > 0.85 + 1e-9:
        return "rojo"
    if pct_rv_actual > 0.75 + 1e-9:
        return "amarillo"
    return ""
