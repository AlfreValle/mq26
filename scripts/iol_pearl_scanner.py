#!/usr/bin/env python3
"""
Escaneo multi-simbolo: historial (yfinance, cache en disco) + cotizacion IOL,
score de anomalia alcista, alertas Telegram y estado idle/in_position/cooldown.
No es asesoramiento financiero. Revisar IOL_BOT_MVP.md seccion Escaner de anomalias.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None  # type: ignore[assignment]

_env_path = ROOT / ".env"
if _load_dotenv and _env_path.is_file():
    _load_dotenv(_env_path)

from services.iol_api.anomaly_scan import PearlAnomalyConfig
from services.iol_api.client import IOLApiClient
from services.iol_api.config import load_iol_bot_settings
from services.iol_api.pearl_scanner_runner import read_symbol_rows, run_iteration
from services.iol_api.pearl_state import load_pearl_state


def main() -> int:
    p = argparse.ArgumentParser(description="Escaneo perlas IOL + anomalias (corto plazo).")
    p.add_argument("--symbols-file", required=True, type=Path, help="Texto: un ticker IOL por linea o IOL,Yahoo.")
    p.add_argument("--market", default="argentina")
    p.add_argument("--min-score", type=float, default=0.45)
    p.add_argument("--state-file", type=Path, default=Path(os.environ.get("TEMP", ".")) / "iol_pearl_state.json")
    p.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "pearl_hist_cache")
    p.add_argument("--hist-period", default="6mo", help="Periodo yfinance (ej. 3mo, 6mo, 1y).")
    p.add_argument("--cache-ttl-seconds", type=float, default=3600.0)
    p.add_argument("--loop-seconds", type=int, default=0)
    p.add_argument("--notify-telegram", action="store_true")
    p.add_argument("--no-position-state", action="store_true", help="No bloquear por trade activo ni TP/stop.")
    p.add_argument("--dedupe-min-seconds", type=float, default=900.0)
    p.add_argument("--dedupe-score-delta", type=float, default=0.12)
    p.add_argument("--offline", action="store_true", help="Sin IOL: usa ultimo cierre yfinance como precio live.")
    p.add_argument("--min-z", type=float, default=None, help="Override PearlAnomalyConfig.min_z_for_signal.")
    p.add_argument("--tech-strategy", default="breakout_close_20", help="Nombre motor live_signals o vacio=off.")
    p.add_argument("--target-pct", type=float, default=None, help="Take profit %% desde entrada (estado).")
    p.add_argument("--stop-pct", type=float, default=None, help="Stop loss %% desde entrada (estado).")
    p.add_argument("--max-hold-days", type=float, default=None, help="Dias max en posicion (estado).")
    p.add_argument("--cooldown-seconds", type=float, default=None, help="Cooldown tras cierre (estado).")
    args = p.parse_args()

    rows = read_symbol_rows(args.symbols_file)
    if not rows:
        print("Sin simbolos en archivo.", file=sys.stderr)
        return 2
    pairs = [(a, b) for a, b in rows]

    cfg = PearlAnomalyConfig()
    if args.min_z is not None:
        cfg = replace(cfg, min_z_for_signal=float(args.min_z))
    tech = (args.tech_strategy or "").strip()
    cfg = replace(cfg, tech_strategy_name=tech or None)

    state_path = args.state_file
    state = load_pearl_state(state_path)
    if args.target_pct is not None:
        state = replace(state, target_pct=float(args.target_pct))
    if args.stop_pct is not None:
        state = replace(state, stop_pct=float(args.stop_pct))
    if args.max_hold_days is not None:
        state = replace(state, max_hold_seconds=max(1.0, float(args.max_hold_days)) * 86400.0)
    if args.cooldown_seconds is not None:
        state = replace(state, cooldown_seconds=float(args.cooldown_seconds))
    state = replace(state, market=args.market)

    client: IOLApiClient | None = None
    if not args.offline:
        settings = load_iol_bot_settings()
        client = IOLApiClient(settings=settings)

    def _once() -> dict[str, Any]:
        nonlocal state
        state, summary = run_iteration(
            pairs=pairs,
            market=args.market,
            cfg=cfg,
            min_score=args.min_score,
            state=state,
            state_path=state_path,
            client=client,
            offline=args.offline,
            notify_telegram=args.notify_telegram,
            use_position_state=not args.no_position_state,
            dedupe_min_sec=args.dedupe_min_seconds,
            dedupe_score_delta=args.dedupe_score_delta,
            cache_dir=args.cache_dir,
            hist_period=args.hist_period,
            cache_ttl_sec=args.cache_ttl_seconds,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return summary

    if args.loop_seconds > 0:
        while True:
            _once()
            time.sleep(max(1, args.loop_seconds))
    _once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
