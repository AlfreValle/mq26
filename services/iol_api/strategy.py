from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SignalDecision:
    side: str
    confidence: float
    reason: str


class MovingAverageSignalStrategy:
    """Estrategia simple para MVP: cruce de media corta/larga."""

    def __init__(self, short_window: int = 10, long_window: int = 30, min_edge_pct: float = 0.001) -> None:
        if short_window >= long_window:
            raise ValueError("short_window debe ser menor a long_window.")
        self.short_window = short_window
        self.long_window = long_window
        self.min_edge_pct = min_edge_pct

    def decide(self, price_series: pd.Series) -> SignalDecision:
        prices = pd.to_numeric(price_series, errors="coerce").dropna()
        if len(prices) < self.long_window:
            return SignalDecision(side="HOLD", confidence=0.0, reason="Sin historial suficiente.")
        short_ma = float(prices.tail(self.short_window).mean())
        long_ma = float(prices.tail(self.long_window).mean())
        if long_ma <= 0:
            return SignalDecision(side="HOLD", confidence=0.0, reason="Serie invalida.")
        edge = (short_ma / long_ma) - 1.0
        if edge > self.min_edge_pct:
            return SignalDecision(
                side="BUY",
                confidence=min(1.0, abs(edge) * 10),
                reason=f"Cruce alcista corto/largo ({edge:.4%}).",
            )
        if edge < -self.min_edge_pct:
            return SignalDecision(
                side="SELL",
                confidence=min(1.0, abs(edge) * 10),
                reason=f"Cruce bajista corto/largo ({edge:.4%}).",
            )
        return SignalDecision(side="HOLD", confidence=0.2, reason="Sin ventaja estadistica.")
