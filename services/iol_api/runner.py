from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from core.logging_config import get_logger
from services.iol_api.backtest_lab import current_vol_regime
from services.iol_api.execution import IOLExecutionService, OrderIntent
from services.iol_api.live_signals import LiveSignalEngine, build_live_engine
from services.iol_api.strategy import MovingAverageSignalStrategy, SignalDecision

logger = get_logger(__name__)


@dataclass(frozen=True)
class RegimeRouterConfig:
    """Mapa entrenado regimen_vol -> nombre de estrategia (mismos nombres que build_named_strategies)."""

    regime_to_strategy: dict[int, str]
    default_strategy: str
    vol_window: int = 20
    rank_window: int = 120


@dataclass(frozen=True)
class RunnerInput:
    market: str
    symbol: str
    quantity: float
    price_hint: float
    price_series: pd.Series


class TradingBotRunner:
    """
    Modo simple: una sola MovingAverageSignalStrategy.
    Modo router: elige motor de senal segun regimen de volatilidad actual (current_vol_regime).

    Con router activo, las ordenes reales a broker estan bloqueadas hasta validar
    (solo dry-run / respuesta de seguridad), independientemente de IOL_DRY_RUN en .env.
    """

    def __init__(
        self,
        execution: IOLExecutionService,
        strategy: MovingAverageSignalStrategy | None = None,
        *,
        regime_router: RegimeRouterConfig | None = None,
    ) -> None:
        if strategy is None and regime_router is None:
            raise ValueError("Definir strategy o regime_router.")
        if strategy is not None and regime_router is not None:
            raise ValueError("Usar solo strategy o regime_router, no ambos.")
        self.execution = execution
        self._legacy_strategy = strategy
        self._regime_router = regime_router
        self._engines: dict[str, LiveSignalEngine] = {}

    def _engine(self, name: str) -> LiveSignalEngine:
        if name not in self._engines:
            self._engines[name] = build_live_engine(name)
        return self._engines[name]

    def _pick_strategy_name(self, regime: int | None) -> str:
        assert self._regime_router is not None
        if regime is None:
            return self._regime_router.default_strategy
        return self._regime_router.regime_to_strategy.get(regime, self._regime_router.default_strategy)

    def _run_once_router(self, inp: RunnerInput) -> dict[str, Any]:
        assert self._regime_router is not None
        regime = current_vol_regime(
            inp.price_series,
            vol_window=self._regime_router.vol_window,
            rank_window=self._regime_router.rank_window,
        )
        strat_name = self._pick_strategy_name(regime)
        engine = self._engine(strat_name)
        decision = engine.decide(inp.price_series)

        summary: dict[str, Any] = {
            "mode": "regime_router",
            "vol_regime": regime,
            "strategy_selected": strat_name,
            "decision": decision.side,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "market": inp.market,
            "symbol": inp.symbol,
            "router_safety": True,
            "dry_run_effective": True,
        }

        if decision.side == "HOLD":
            logger.info(
                "Bot router HOLD symbol=%s regime=%s strat=%s reason=%s",
                inp.symbol,
                regime,
                strat_name,
                decision.reason,
            )
            return summary

        order = OrderIntent(
            side=decision.side,
            market=inp.market,
            symbol=inp.symbol,
            quantity=inp.quantity,
            price=inp.price_hint,
        )

        if self.execution.settings.dry_run:
            summary["execution"] = self.execution.place_order(order)
            return summary

        logger.warning(
            "Router IOL: bloqueo de orden real hasta validar (IOL_DRY_RUN=%s). Simulando dry-run.",
            self.execution.settings.dry_run,
        )
        summary["execution"] = {
            "status": "router_safety_blocked",
            "message": "Orden real bloqueada con regime_router activo. Pone IOL_DRY_RUN=true y valida en sandbox.",
            "would_order": {
                "side": order.side,
                "market": order.market,
                "symbol": order.symbol,
                "quantity": order.quantity,
                "price": order.price,
            },
        }
        return summary

    def run_once(self, inp: RunnerInput) -> dict[str, Any]:
        if self._regime_router is not None:
            return self._run_once_router(inp)

        assert self._legacy_strategy is not None
        decision: SignalDecision = self._legacy_strategy.decide(inp.price_series)
        summary: dict[str, Any] = {
            "mode": "legacy_ma",
            "decision": decision.side,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "market": inp.market,
            "symbol": inp.symbol,
        }
        if decision.side == "HOLD":
            logger.info("Bot sin orden symbol=%s reason=%s", inp.symbol, decision.reason)
            return summary
        order = OrderIntent(
            side=decision.side,
            market=inp.market,
            symbol=inp.symbol,
            quantity=inp.quantity,
            price=inp.price_hint,
        )
        exec_result = self.execution.place_order(order)
        summary["execution"] = exec_result
        return summary
