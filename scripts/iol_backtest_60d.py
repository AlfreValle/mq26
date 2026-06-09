#!/usr/bin/env python3
"""
Backtesting de 60 dias para estrategias de iol_api/backtest_lab.
Entrega PnL final (ARS) por estrategia y mejor estrategia por ticker.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
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

from services.alert_bot import enviar_telegram
from services.iol_api.backtest_lab import build_named_strategies, report_capital_window
from services.iol_api.pearl_scanner_runner import default_yahoo_ticker, ensure_hist_cached, read_symbol_rows


def _series_for_symbol(
    symbol_iol: str,
    market: str,
    *,
    yahoo_override: str | None,
    hist_period: str,
    cache_dir: Path,
    cache_ttl_sec: float,
) -> tuple[str, pd.Series]:
    yh = yahoo_override or default_yahoo_ticker(symbol_iol, market)
    df = ensure_hist_cached(yh, hist_period, cache_dir, cache_ttl_sec)
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    close.name = "close"
    return yh, close


def _backtest_one(
    close: pd.Series,
    *,
    window_days: int,
    capital_ars: float,
    commission_pct: float,
) -> list[dict]:
    sl = close.tail(window_days).copy()
    strategies = build_named_strategies(sl)
    rows: list[dict] = []
    for name, pos in strategies.items():
        rep = report_capital_window(
            sl,
            pos,
            ventana_dias=window_days,
            estrategia=name,
            capital_inicial_ars=capital_ars,
            commission_pct=commission_pct,
            mode="long_flat",
        )
        pnl_ars = float(rep.capital_final_ars - rep.capital_inicial_ars)
        rows.append(
            {
                "estrategia": name,
                "capital_inicial_ars": round(rep.capital_inicial_ars, 2),
                "capital_final_ars": round(rep.capital_final_ars, 2),
                "pnl_final_ars": round(pnl_ars, 2),
                "rendimiento_total_pct": round(rep.rendimiento_total_pct, 2),
                "sharpe": round(rep.sharpe, 3),
                "max_drawdown_pct": round(rep.max_drawdown * 100, 2),
                "profit_factor": round(rep.profit_factor, 3),
                "operaciones_cerradas": rep.operaciones_cerradas,
                "operaciones_ganadoras": rep.operaciones_ganadoras,
                "hit_rate_operaciones_pct": round(rep.tasa_aciertos_pct, 2),
            }
        )
    rows.sort(key=lambda r: (r["pnl_final_ars"], r["sharpe"]), reverse=True)
    return rows


def _build_community_rows(results_by_symbol: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for r in results_by_symbol:
        if not isinstance(r, dict):
            continue
        if r.get("error"):
            continue
        best = None
        resultados = r.get("resultados")
        if isinstance(resultados, list) and resultados:
            b0 = resultados[0]
            if isinstance(b0, dict):
                best = b0
        if not best:
            continue
        rows.append(
            {
                "ticker": r.get("symbol_iol"),
                "mejor_estrategia": best.get("estrategia"),
                "pnl_60d_ars": best.get("pnl_final_ars"),
                "rend_60d_pct": best.get("rendimiento_total_pct"),
            }
        )
    rows.sort(
        key=lambda x: float(x.get("pnl_60d_ars") or 0.0),
        reverse=True,
    )
    return rows


def _build_whatsapp_backtest_message(
    community_rows: list[dict[str, object]],
    *,
    window_days: int,
    capital_ars: float,
) -> str:
    lines = [
        f"Backtest comunidad ({window_days} dias)",
        f"Capital base: ARS {capital_ars:,.0f}",
        "Ranking: Ticker | Mejor estrategia | PnL 60d | Rend%",
        "",
    ]
    if not community_rows:
        lines.append("Sin resultados validos para publicar.")
    for i, row in enumerate(community_rows[:10], start=1):
        tk = str(row.get("ticker", "N/D"))
        st = str(row.get("mejor_estrategia", "N/D"))
        pnl = float(row.get("pnl_60d_ars") or 0.0)
        rd = float(row.get("rend_60d_pct") or 0.0)
        lines.append(f"{i}) {tk} | {st} | ARS {pnl:,.0f} | {rd:+.2f}%")
    lines.extend(
        [
            "",
            f"Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "Aviso: simulacion historica, no garantiza resultados futuros.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Backtest 60 dias (PnL final por estrategia).")
    p.add_argument("--market", default="argentina")
    p.add_argument("--ticker", default="", help="Ticker IOL (ej. GGAL). Opcional si usas --symbols-file.")
    p.add_argument(
        "--symbols-file",
        default="",
        help="Archivo con tickers IOL o IOL,Yahoo (una linea por activo).",
    )
    p.add_argument("--window-days", type=int, default=60)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.001)
    p.add_argument("--hist-period", default="1y")
    p.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "pearl_hist_cache")
    p.add_argument("--cache-ttl-seconds", type=float, default=3600.0)
    p.add_argument("--top-n", type=int, default=10, help="Cantidad maxima de tickers a evaluar.")
    p.add_argument("--print-community", action="store_true", help="Imprime ranking simple para comunidad.")
    p.add_argument("--whatsapp", action="store_true", help="Genera y muestra mensaje para WhatsApp.")
    p.add_argument("--notify-telegram", action="store_true", help="Envia el mensaje WhatsApp a Telegram.")
    p.add_argument(
        "--whatsapp-file",
        type=Path,
        default=ROOT / "data" / "backtest_60d_whatsapp.txt",
        help="Archivo de salida del mensaje WhatsApp.",
    )
    args = p.parse_args()

    pairs: list[tuple[str, str | None]] = []
    if args.symbols_file.strip():
        pairs = read_symbol_rows(Path(args.symbols_file.strip()))
    elif args.ticker.strip():
        pairs = [(args.ticker.strip().upper(), None)]
    else:
        print("Debes indicar --ticker o --symbols-file.", file=sys.stderr)
        return 2

    pairs = pairs[: max(1, int(args.top_n))]
    out_symbols: list[dict] = []
    for sym, yov in pairs:
        try:
            yh, close = _series_for_symbol(
                sym,
                args.market,
                yahoo_override=yov,
                hist_period=args.hist_period,
                cache_dir=args.cache_dir,
                cache_ttl_sec=args.cache_ttl_seconds,
            )
            if len(close) < args.window_days:
                out_symbols.append(
                    {
                        "symbol_iol": sym,
                        "symbol_yahoo": yh,
                        "error": f"historial insuficiente ({len(close)} barras < {args.window_days})",
                    }
                )
                continue
            rows = _backtest_one(
                close,
                window_days=int(args.window_days),
                capital_ars=float(args.capital),
                commission_pct=float(args.commission),
            )
            out_symbols.append(
                {
                    "symbol_iol": sym,
                    "symbol_yahoo": yh,
                    "best_strategy": rows[0]["estrategia"] if rows else None,
                    "best_pnl_final_ars": rows[0]["pnl_final_ars"] if rows else None,
                    "resultados": rows,
                }
            )
        except Exception as exc:  # noqa: BLE001
            out_symbols.append({"symbol_iol": sym, "error": str(exc)})

    doc = {
        "ok": True,
        "window_days": int(args.window_days),
        "capital_ars": float(args.capital),
        "commission_pct": float(args.commission),
        "symbols_evaluados": len(pairs),
        "resultados_por_symbol": out_symbols,
    }
    print(json.dumps(doc, ensure_ascii=False))

    community_rows = _build_community_rows(out_symbols)
    if args.print_community and community_rows:
        print("\n--- COMMUNITY RANKING ---")
        print("Ticker | Mejor estrategia | PnL 60d (ARS) | Rend%")
        for row in community_rows:
            print(
                f"{row['ticker']} | {row['mejor_estrategia']} | "
                f"{float(row['pnl_60d_ars']):.2f} | {float(row['rend_60d_pct']):+.2f}%"
            )

    if args.whatsapp:
        msg = _build_whatsapp_backtest_message(
            community_rows,
            window_days=int(args.window_days),
            capital_ars=float(args.capital),
        )
        args.whatsapp_file.parent.mkdir(parents=True, exist_ok=True)
        args.whatsapp_file.write_text(msg, encoding="utf-8")
        print("\n--- WHATSAPP ---")
        print(msg)
        if args.notify_telegram and community_rows:
            enviar_telegram(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

