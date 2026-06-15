#!/usr/bin/env python3
"""
Backtest 30 / 60 / 90 dias (barras diarias) con capital inicial en ARS.
Elige en cada ventana la estrategia predefinida con mayor Sharpe (misma familia que build_named_strategies).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.iol_api.backtest_lab import (
    build_named_strategies,
    pick_best_strategy_name,
    report_capital_window,
)


def _download_close(ticker: str, period: str) -> pd.Series:
    raw = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if raw is None or raw.empty or "Close" not in raw.columns:
        raise RuntimeError(f"Sin datos para {ticker}")
    s = pd.to_numeric(raw["Close"], errors="coerce").dropna()
    s.name = "close"
    return s


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="GGAL.BA", help="Ticker Yahoo (ej. GGAL.BA en pesos).")
    p.add_argument("--period", default="1y", help="Periodo descarga yfinance (ej. 1y).")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.001, help="Costo por unidad de cambio de posicion.")
    p.add_argument("--windows", default="30,60,90", help="Ventanas en dias (barras), separadas por coma.")
    args = p.parse_args()

    close_full = _download_close(args.ticker.strip(), args.period.strip())
    wins = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    out_rows = []
    for w in wins:
        if len(close_full) < w:
            continue
        sl = close_full.iloc[-w:]
        name = pick_best_strategy_name(sl, commission_pct=args.commission)
        pos = build_named_strategies(sl)[name]
        rep = report_capital_window(
            sl,
            pos,
            ventana_dias=w,
            estrategia=name,
            capital_inicial_ars=args.capital,
            commission_pct=args.commission,
            mode="long_flat",
        )
        out_rows.append(
            {
                "ventana_dias": rep.ventana_dias,
                "estrategia_elegida": rep.estrategia,
                "capital_inicial_ars": rep.capital_inicial_ars,
                "capital_final_ars": round(rep.capital_final_ars, 2),
                "rendimiento_total_pct": round(rep.rendimiento_total_pct, 2),
                "operaciones_cerradas": rep.operaciones_cerradas,
                "operaciones_ganadoras": rep.operaciones_ganadoras,
                "tasa_aciertos_operaciones_pct": round(rep.tasa_aciertos_pct, 2),
                "dias_en_mercado": rep.dias_en_mercado,
                "dias_ganadores_en_mercado": rep.dias_ganadores,
                "tasa_aciertos_dias_expuesto_pct": round(rep.tasa_aciertos_dias_pct, 2),
                "sharpe": round(rep.sharpe, 3),
                "max_drawdown": round(rep.max_drawdown * 100, 2),
                "profit_factor": round(rep.profit_factor, 3),
                "calmar": round(rep.calmar_ratio, 3),
                "cvar95_daily_pct": round(rep.cvar_95_daily * 100, 4),
                "skew_net_returns": round(rep.skew_net_returns, 3),
                "excess_kurtosis_net": round(rep.excess_kurtosis_net, 3),
            }
        )

    doc = {
        "ticker": args.ticker,
        "period_descarga": args.period,
        "nota": (
            "Estrategia por ventana = mayor Sharpe entre las predefinidas en build_named_strategies. "
            "Precios yfinance; comision aproximada por cambio de posicion. No es simulacion IOL ni slippage real."
        ),
        "resultados": out_rows,
    }
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0 if out_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
