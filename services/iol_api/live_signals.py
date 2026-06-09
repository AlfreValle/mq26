"""
Motores de senal en vivo alineados a los nombres de build_named_strategies / regime router.
Cada instancia puede mantener estado (p. ej. RSI mean-reversion).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from services.iol_api.strategy import MovingAverageSignalStrategy, SignalDecision


class LiveSignalEngine(Protocol):
    name: str

    def decide(self, close: pd.Series) -> SignalDecision: ...


@dataclass
class MACrossLiveEngine:
    short: int
    long: int
    min_edge_pct: float = 0.001
    name: str = ""

    def __post_init__(self) -> None:
        self._inner = MovingAverageSignalStrategy(
            short_window=self.short,
            long_window=self.long,
            min_edge_pct=self.min_edge_pct,
        )
        if not self.name:
            self.name = f"ma_cross_{self.short}_{self.long}"

    def decide(self, close: pd.Series) -> SignalDecision:
        return self._inner.decide(close)


@dataclass
class RSIMRLiveEngine:
    period: int = 14
    buy_level: float = 30.0
    sell_level: float = 70.0
    name: str = "rsi_mr_14_30_70"
    _hold: bool = field(default=False, repr=False)

    def decide(self, close: pd.Series) -> SignalDecision:
        c = pd.to_numeric(close, errors="coerce").dropna()
        if len(c) < self.period + 2:
            return SignalDecision(side="HOLD", confidence=0.0, reason="RSI: datos insuficientes.")
        delta = c.diff()
        gain = delta.clip(lower=0.0)
        loss = (-delta).clip(lower=0.0)
        ag = gain.rolling(self.period, min_periods=self.period).mean()
        al = loss.rolling(self.period, min_periods=self.period).mean()
        rs = ag / al.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        r = float(rsi.iloc[-1])
        if np.isnan(r):
            return SignalDecision(side="HOLD", confidence=0.0, reason="RSI: nan.")
        if not self._hold and r < self.buy_level:
            self._hold = True
            return SignalDecision(
                side="BUY",
                confidence=min(1.0, (self.buy_level - r) / self.buy_level),
                reason=f"RSI sobreventa ({r:.1f}).",
            )
        if self._hold and r > self.sell_level:
            self._hold = False
            return SignalDecision(
                side="SELL",
                confidence=min(1.0, (r - self.sell_level) / (100.0 - self.sell_level)),
                reason=f"RSI sobrecompra ({r:.1f}).",
            )
        return SignalDecision(
            side="HOLD",
            confidence=0.25,
            reason=f"RSI en zona neutral ({r:.1f}), posicion={'long' if self._hold else 'flat'}.",
        )


@dataclass
class BreakoutLiveEngine:
    window: int = 20
    exit_frac: float = 0.98
    name: str = "breakout_close_20"
    _hold: bool = field(default=False, repr=False)

    def decide(self, close: pd.Series) -> SignalDecision:
        c = pd.to_numeric(close, errors="coerce").dropna()
        if len(c) < self.window + 2:
            return SignalDecision(side="HOLD", confidence=0.0, reason="Breakout: datos insuficientes.")
        upper = c.rolling(self.window, min_periods=self.window).max().shift(1)
        ub = float(upper.iloc[-1])
        px = float(c.iloc[-1])
        if np.isnan(ub):
            return SignalDecision(side="HOLD", confidence=0.0, reason="Breakout: sin techo.")
        if not self._hold and px > ub:
            self._hold = True
            return SignalDecision(side="BUY", confidence=0.7, reason=f"Rompimiento sobre {ub:.4f}.")
        if self._hold and px < ub * self.exit_frac:
            self._hold = False
            return SignalDecision(side="SELL", confidence=0.6, reason="Salida breakout.")
        return SignalDecision(
            side="HOLD",
            confidence=0.2,
            reason=f"Breakout sin senal (px={px:.4f}, techo_prev={ub:.4f}).",
        )


def build_live_engine(strategy_name: str) -> LiveSignalEngine:
    if strategy_name == "ma_cross_10_30":
        return MACrossLiveEngine(10, 30, name=strategy_name)
    if strategy_name == "ma_cross_5_20":
        return MACrossLiveEngine(5, 20, name=strategy_name)
    if strategy_name == "rsi_mr_14_30_70":
        return RSIMRLiveEngine(name=strategy_name)
    if strategy_name == "breakout_close_20":
        return BreakoutLiveEngine(20, name=strategy_name)
    raise ValueError(f"Estrategia desconocida para live: {strategy_name!r}")
