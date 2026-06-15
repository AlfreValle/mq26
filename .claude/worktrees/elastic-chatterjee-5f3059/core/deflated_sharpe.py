"""
D08 — Sharpe deflado (ajuste por número de pruebas / sesgo de selección).

Implementación compacta basada en aproximación tipo Bailey–López de Prado:
SR_ajustado ≈ SR * sqrt((n_obs - 1) / (n_obs - 1 + n_trials * SR^2)) (toy).
"""
from __future__ import annotations

import math


def deflated_sharpe_ratio(
    sharpe_observed: float,
    *,
    n_observations: int,
    n_trials: int = 1,
) -> float:
    """
    Reduce el Sharpe observado cuando ``n_trials`` > 1 (múltiples especificaciones probadas).

    Si ``n_trials`` < 2, devuelve el Sharpe sin cambio.
    """
    if n_trials < 2 or n_observations < 3:
        return float(sharpe_observed)
    sr = float(sharpe_observed)
    # Penalización creciente con trials; acotada para evitar división por cero
    adj = math.sqrt(max(n_observations - 1, 1) / max(n_observations - 1 + n_trials * sr * sr, 1e-12))
    return sr * adj
