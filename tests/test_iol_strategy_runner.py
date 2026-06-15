from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from services.iol_api.runner import RunnerInput, TradingBotRunner
from services.iol_api.strategy import MovingAverageSignalStrategy


def test_strategy_buy_signal():
    s = MovingAverageSignalStrategy(short_window=3, long_window=5, min_edge_pct=0.0001)
    prices = pd.Series([10, 10, 10, 11, 12, 13])
    out = s.decide(prices)
    assert out.side == "BUY"


def test_runner_hold_no_envia_orden():
    execution = MagicMock()
    strategy = MovingAverageSignalStrategy(short_window=3, long_window=5, min_edge_pct=0.5)
    runner = TradingBotRunner(execution=execution, strategy=strategy)
    out = runner.run_once(
        RunnerInput(
            market="argentina",
            symbol="GGAL",
            quantity=1.0,
            price_hint=1000.0,
            price_series=pd.Series([10, 10, 10, 10, 10, 10]),
        )
    )
    assert out["decision"] == "HOLD"
    execution.place_order.assert_not_called()
