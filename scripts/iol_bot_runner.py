#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None  # type: ignore[assignment]

_env_path = ROOT / ".env"
if _load_dotenv and _env_path.is_file():
    _load_dotenv(_env_path)

from services.iol_api.client import IOLApiClient
from services.iol_api.config import load_iol_bot_settings
from services.iol_api.execution import IOLExecutionService, RiskLimits
from services.iol_api.runner import RegimeRouterConfig, RunnerInput, TradingBotRunner
from services.iol_api.strategy import MovingAverageSignalStrategy


def _load_regime_router_json(path: str) -> RegimeRouterConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    rmap = raw.get("router_regimen_vol") or raw.get("regime_to_strategy") or {}
    regime_to_strategy = {int(k): str(v) for k, v in rmap.items()}
    default = (raw.get("default_strategy") or raw.get("default") or "ma_cross_10_30").strip()
    vw = int(raw.get("vol_window", 20))
    rw = int(raw.get("rank_window", 120))
    return RegimeRouterConfig(
        regime_to_strategy=regime_to_strategy,
        default_strategy=default,
        vol_window=vw,
        rank_window=rw,
    )


def _load_prices(path: str) -> pd.Series:
    df = pd.read_csv(path)
    close_col = "close" if "close" in df.columns else df.columns[-1]
    return pd.to_numeric(df[close_col], errors="coerce").dropna()


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner operativo de bot IOL (demo/real segun entorno).")
    parser.add_argument("--market", default="argentina")
    parser.add_argument("--symbol", default="GGAL")
    parser.add_argument("--quantity", type=float, default=1.0)
    parser.add_argument("--price", type=float, default=1000.0)
    parser.add_argument("--prices-csv", required=True, help="CSV con columna close o ultima columna de precio.")
    parser.add_argument("--loop-seconds", type=int, default=0, help="Si >0 ejecuta en loop.")
    parser.add_argument(
        "--router-json",
        default="",
        help="Salida de iol_strategy_backtest (router_regimen_vol + default_strategy). Fuerza dry-run seguro.",
    )
    args = parser.parse_args()

    if args.router_json.strip():
        os.environ["IOL_DRY_RUN"] = "true"

    settings = load_iol_bot_settings()
    client = IOLApiClient(settings=settings)
    risk = RiskLimits(
        max_notional_ars=settings.max_notional_ars,
        max_daily_loss_ars=settings.max_daily_loss_ars,
        max_orders_per_day=settings.max_orders_per_day,
        kill_switch_file=settings.kill_switch_file,
    )
    execution = IOLExecutionService(client=client, settings=settings, risk_limits=risk)
    if args.router_json.strip():
        r_cfg = _load_regime_router_json(args.router_json.strip())
        runner = TradingBotRunner(execution=execution, regime_router=r_cfg)
    else:
        strategy = MovingAverageSignalStrategy()
        runner = TradingBotRunner(execution=execution, strategy=strategy)

    def _run_once() -> dict:
        prices = _load_prices(args.prices_csv)
        out = runner.run_once(
            RunnerInput(
                market=args.market,
                symbol=args.symbol,
                quantity=args.quantity,
                price_hint=args.price,
                price_series=prices,
            )
        )
        print(json.dumps(out, ensure_ascii=False))
        return out

    if args.loop_seconds > 0:
        while True:
            _run_once()
            time.sleep(args.loop_seconds)
    _run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
