"""
J03 / B09 — Ajuste neto de retornos por costos (v1 placeholders ley 25.326).

Parámetros documentados como orientativos; no constituyen asesoramiento fiscal.
"""
from __future__ import annotations

import numpy as np

# Placeholders documentados (fracción sobre retorno bruto por período)
DEFAULT_WITHHOLDING_EQ_PLACEHOLDER = 0.0
DEFAULT_COMMISSION_BPS_PER_REBALANCE = 10.0


def adjust_returns_net_of_costs(
    returns: np.ndarray,
    *,
    commission_bps: float = DEFAULT_COMMISSION_BPS_PER_REBALANCE,
    withholding_rate: float = DEFAULT_WITHHOLDING_EQ_PLACEHOLDER,
) -> np.ndarray:
    """
    Aplica comisión proporcional y retención placeholder sobre serie de retornos.

    ``commission_bps``: costo en puntos básicos por unidad de retorno bruto (toy v1).
    """
    r = np.asarray(returns, dtype=float)
    fee = (commission_bps / 10000.0) * np.abs(r)
    net = r - fee
    if withholding_rate > 0:
        net = net * (1.0 - withholding_rate)
    return net
