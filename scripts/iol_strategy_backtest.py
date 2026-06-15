#!/usr/bin/env python3
"""Compara estrategias de entrada/salida y entrena router por regimen de volatilidad (walk-forward)."""
from __future__ import annotations

import argparse
import json
import sys
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

from services.iol_api.backtest_lab import (
    compare_strategies,
    fit_regime_router_walk_forward,
    walk_forward_oos_grid,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest lab IOL — comparar estrategias y router por regimen.")
    p.add_argument("--csv", help="CSV con columna close (o ultima columna numerica como precio).")
    p.add_argument("--train-ratio", type=float, default=0.65)
    p.add_argument("--commission", type=float, default=0.001, help="Costo por cambio de posicion (aprox).")
    p.add_argument(
        "--walk-forward-ratios",
        default="",
        help="Opcional: varios train_ratio separados por coma (ej. 0.55,0.65,0.75) para grid OOS walk-forward.",
    )
    args = p.parse_args()

    if not args.csv:
        print("Uso: python scripts/iol_strategy_backtest.py --csv ruta/precios.csv", file=sys.stderr)
        return 2

    df = pd.read_csv(args.csv)
    close_col = "close" if "close" in df.columns else df.select_dtypes(include=["number"]).columns[-1]
    close = pd.to_numeric(df[close_col], errors="coerce").dropna()
    if isinstance(close.index, pd.RangeIndex):
        close.index = pd.date_range("2020-01-01", periods=len(close), freq="D")

    cmp_df = compare_strategies(close, commission_pct=args.commission, mode="long_flat")
    router = fit_regime_router_walk_forward(
        close, train_ratio=args.train_ratio, commission_pct=args.commission, mode="long_flat"
    )

    out: dict = {
        "comparacion_estrategias": cmp_df.to_dict(orient="records"),
        "router_regimen_vol": {str(k): v for k, v in router.regime_to_strategy.items()},
        "default_strategy": router.default_strategy,
        "train_sharpe_por_regimen": {
            str(k): v for k, v in router.train_sharpe_by_regime.items()
        },
        "oos_sharpe_router": router.oos_sharpe_router,
        "oos_mejor_estrategia_unica": router.oos_best_single_name,
        "oos_sharpe_mejor_unica": router.oos_sharpe_best_single,
    }
    wf = args.walk_forward_ratios.strip()
    if wf:
        ratios = [float(x.strip()) for x in wf.split(",") if x.strip()]
        if ratios:
            grid_df = walk_forward_oos_grid(
                close, train_ratios=ratios, commission_pct=args.commission, mode="long_flat"
            )
            out["walk_forward_oos_por_train_ratio"] = grid_df.to_dict(orient="records")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
