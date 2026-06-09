"""Integracion de bot de trading con API IOL."""

from services.iol_api.backtest_lab import (
    RouterFitResult,
    build_named_strategies,
    compare_strategies,
    current_vol_regime,
    fit_regime_router_walk_forward,
    simulate_positions,
    walk_forward_oos_grid,
)
from services.iol_api.client import IOLApiClient
from services.iol_api.config import IOLBotSettings, load_iol_bot_settings
from services.iol_api.execution import IOLExecutionService, OrderIntent, RiskLimits
from services.iol_api.runner import RegimeRouterConfig, TradingBotRunner
from services.iol_api.strategy import MovingAverageSignalStrategy, SignalDecision

__all__ = [
    "IOLApiClient",
    "IOLBotSettings",
    "IOLExecutionService",
    "MovingAverageSignalStrategy",
    "OrderIntent",
    "RiskLimits",
    "RegimeRouterConfig",
    "RouterFitResult",
    "SignalDecision",
    "TradingBotRunner",
    "build_named_strategies",
    "compare_strategies",
    "current_vol_regime",
    "fit_regime_router_walk_forward",
    "load_iol_bot_settings",
    "simulate_positions",
    "walk_forward_oos_grid",
]
