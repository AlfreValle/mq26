from __future__ import annotations

import numpy as np


def calcular_aporte_necesario(
    capital_actual: float,
    objetivo_usd: float,
    n_años: int,
    rendimiento_anual: float,
) -> float:
    """
    Aporte mensual necesario para alcanzar objetivo_usd en n_años.
    Fórmula: despeja PMT de FV = PV*(1+rm)^n + PMT*((1+rm)^n - 1)/rm
    """
    rm  = (1.0 + float(rendimiento_anual)) ** (1.0 / 12.0) - 1.0
    n   = int(n_años * 12)
    fv  = float(capital_actual) * (1.0 + rm) ** n
    if objetivo_usd <= fv:
        return 0.0
    den = (1.0 + rm) ** n - 1.0
    return float((objetivo_usd - fv) * rm / den) if abs(den) > 1e-12 else 0.0


def _daily_to_monthly(r_diarios: np.ndarray) -> np.ndarray:
    """
    Agrupa retornos diarios en retornos mensuales compuestos
    usando ventanas de 21 días de trading.
    """
    r       = np.asarray(r_diarios, dtype=float)
    ventana = 21
    n_meses = len(r) // ventana
    if n_meses == 0:
        return np.array([(1.0 + r).prod() - 1.0]) if r.size else np.array([0.005])
    meses = []
    for i in range(n_meses):
        bloque = r[i * ventana:(i + 1) * ventana]
        meses.append((1.0 + bloque).prod() - 1.0)
    return np.array(meses, dtype=float)


def simulate_retirement(
    aporte_mensual: float,
    n_meses_acum: int,
    retiro_mensual: float,
    n_meses_desacum: int,
    retornos_diarios: np.ndarray,
    n_sim: int = 5000,
) -> dict:
    """
    Simulación Montecarlo de retiro.
    p10/p50/p90 = patrimonio final al terminar la fase de desacumulación.
    prob_no_agotar = fracción de simulaciones con capital final > 0.
    Bootstrap sobre retornos MENSUALES (convertidos desde diarios con ventanas de 21 días).
    """
    rng = np.random.default_rng(seed=42)
    r_mensual = _daily_to_monthly(np.asarray(retornos_diarios, dtype=float))
    if r_mensual.size == 0:
        r_mensual = np.array([0.005])

    total_meses = n_meses_acum + n_meses_desacum
    vals = np.empty(n_sim, dtype=float)

    for i in range(n_sim):
        idx   = rng.integers(0, len(r_mensual), size=total_meses)
        draws = r_mensual[idx]
        cap   = 0.0
        for t in range(n_meses_acum):
            cap = (cap + aporte_mensual) * (1.0 + draws[t])
        for t in range(n_meses_desacum):
            cap = (cap - retiro_mensual) * (1.0 + draws[n_meses_acum + t])
        vals[i] = cap

    return {
        "p10":            float(np.percentile(vals, 10)),
        "p50":            float(np.percentile(vals, 50)),
        "p90":            float(np.percentile(vals, 90)),
        "prob_no_agotar": float(np.mean(vals > 0)),
    }
