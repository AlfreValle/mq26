#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
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
from services.byma_market_data import _fetch_tipo
from services.iol_api.anomaly_scan import PearlAnomalyConfig, score_pearl_buy
from services.iol_api.client import IOLApiClient
from services.iol_api.config import load_iol_bot_settings
from services.iol_api.pearl_scanner_runner import (
    default_yahoo_ticker,
    ensure_hist_cached,
    parse_iol_quote_price_volume,
    read_symbol_rows,
)


def _risk_suggestion(close_hist: pd.Series) -> tuple[float, float]:
    """
    TP/SL sugerido en % basado en volatilidad reciente.
    Regla simple y robusta para screening diario.
    """
    c = pd.to_numeric(close_hist, errors="coerce").dropna()
    if len(c) < 25:
        return 3.0, 1.5
    rets = c.pct_change().dropna().tail(20)
    if rets.empty:
        return 3.0, 1.5
    vol = float(rets.std(ddof=1))
    if not np.isfinite(vol) or vol <= 0:
        return 3.0, 1.5
    tp = float(np.clip(vol * 2.5 * 100.0, 2.0, 8.0))
    sl = float(np.clip(vol * 1.5 * 100.0, 1.0, 5.0))
    return round(tp, 2), round(sl, 2)


def _abs_move_vs_prior_close_pct(close_for_model: pd.Series, live_px: float) -> float | None:
    """
    Diferencia de mercado (%%): |precio vivo - cierre previo| / cierre previo * 100.
    El cierre previo es la ultima barra de close_for_model (rueda anterior al live).
    """
    try:
        prev = float(pd.to_numeric(close_for_model, errors="coerce").dropna().iloc[-1])
        live = float(live_px)
    except Exception:
        return None
    if not np.isfinite(prev) or prev <= 0.0 or not np.isfinite(live):
        return None
    return float(abs(live / prev - 1.0) * 100.0)


def _occurrence_window(close_hist: pd.Series) -> tuple[int, str]:
    """
    Estima plazo de ocurrencia (ruedas) para resolver TP/SL.
    Regla heurística por volatilidad reciente.
    """
    c = pd.to_numeric(close_hist, errors="coerce").dropna()
    if len(c) < 25:
        return 5, "3-7 ruedas"
    rets = c.pct_change().dropna().tail(20)
    if rets.empty:
        return 5, "3-7 ruedas"
    vol = float(rets.std(ddof=1))
    if not np.isfinite(vol) or vol <= 0:
        return 5, "3-7 ruedas"
    if vol >= 0.04:
        return 2, "1-3 ruedas"
    if vol >= 0.025:
        return 3, "2-4 ruedas"
    if vol >= 0.015:
        return 5, "3-7 ruedas"
    return 8, "5-10 ruedas"


def _build_telegram_summary(items: list[dict[str, Any]], market: str) -> str:
    lines = [f"Top perlas del dia ({market})", f"Cantidad: {len(items)}"]
    for i, it in enumerate(items, start=1):
        mm = it.get("market_move_pct")
        mm_txt = f" Mov={mm:.2f}%%" if isinstance(mm, (int, float)) and np.isfinite(mm) else ""
        lines.append(
            f"{i}) {it['symbol']} score={it['score']:.3f} "
            f"TP={it['tp_pct']:.2f}% SL={it['sl_pct']:.2f}% "
            f"(ARS TP/SL={it['tp_ars']:.2f}/{it['sl_ars']:.2f}, "
            f"USD TP/SL={it['tp_usd']:.2f}/{it['sl_usd']:.2f}) "
            f"Plazo={it['occurrence_range']}{mm_txt}"
        )
    return "\n".join(lines)


def _build_whatsapp_message(items: list[dict[str, Any]], market: str, generated_at: str) -> str:
    lines = [
        "TOP PERLAS DEL DIA (corto plazo)",
        "",
        f"Universo: CEDEARs + Acciones | Mercado: {market}",
        "Metodo: anomalias + confirmacion tecnica",
        "Aviso: contenido educativo, no asesoramiento financiero.",
        "",
    ]
    if not items:
        lines.append("Sin senales que superen el umbral configurado hoy.")
    for i, it in enumerate(items, start=1):
        reason = "; ".join(it.get("reasons", [])[:2]) if it.get("reasons") else "Sin motivo adicional."
        mm = it.get("market_move_pct")
        mm_line = (
            f"Mov vs cierre previo: {float(mm):.2f}%"
            if isinstance(mm, (int, float)) and np.isfinite(float(mm))
            else "Mov vs cierre previo: n/d"
        )
        lines.extend(
            [
                f"{i}) {it['symbol']} | Score {it['score']:.3f}",
                f"Precio: ARS {it['price_ars']:.2f} | USD {it['price_usd']:.4f}",
                mm_line,
                f"TP +{it['tp_pct']:.2f}% -> ARS {it['tp_ars']:.2f} | USD {it['tp_usd']:.4f}",
                f"SL -{it['sl_pct']:.2f}% -> ARS {it['sl_ars']:.2f} | USD {it['sl_usd']:.4f}",
                f"Plazo estimado: {it['occurrence_range']}",
                f"Motivo: {reason}",
                "",
            ]
        )
    lines.append(f"Actualizado: {generated_at}")
    lines.append("#Trading #Cedears #CortoPlazo #RiskManagement")
    return "\n".join(lines)


def _build_whatsapp_message_ars_only(items: list[dict[str, Any]], market: str, generated_at: str) -> str:
    lines = [
        "TOP PERLAS DEL DIA (ARS) - CORTO PLAZO",
        "",
        f"Universo: CEDEARs + Acciones | Mercado: {market}",
        "Metodo: anomalias + confirmacion tecnica",
        "Aviso: contenido educativo, no asesoramiento financiero.",
        "",
    ]
    if not items:
        lines.append("Sin senales que superen el umbral configurado hoy.")
    for i, it in enumerate(items, start=1):
        reason = "; ".join(it.get("reasons", [])[:2]) if it.get("reasons") else "Sin motivo adicional."
        mm = it.get("market_move_pct")
        mm_line = (
            f"Mov vs cierre previo: {float(mm):.2f}%"
            if isinstance(mm, (int, float)) and np.isfinite(float(mm))
            else "Mov vs cierre previo: n/d"
        )
        lines.extend(
            [
                f"{i}) {it['symbol']} | Score {it['score']:.3f}",
                f"Precio: ARS {it['price_ars']:.2f}",
                mm_line,
                f"TP +{it['tp_pct']:.2f}% -> ARS {it['tp_ars']:.2f}",
                f"SL -{it['sl_pct']:.2f}% -> ARS {it['sl_ars']:.2f}",
                f"Plazo estimado: {it['occurrence_range']}",
                f"Motivo: {reason}",
                "",
            ]
        )
    lines.append(f"Actualizado: {generated_at}")
    lines.append("#Trading #Cedears #CortoPlazo #GestionDeRiesgo")
    return "\n".join(lines)


def _is_yahoo_compatible_symbol(sym: str) -> bool:
    """
    Filtro conservador para evitar símbolos BYMA no listables en Yahoo.
    Acepta alfanuméricos (sin puntos/símbolos) de longitud razonable.
    """
    s = sym.strip().upper()
    if not s:
        return False
    if len(s) < 1 or len(s) > 8:
        return False
    return re.fullmatch(r"[A-Z0-9]+", s) is not None


def _byma_ranked_universe(
    limit_cedears: int | None = None,
    limit_equities: int | None = None,
    *,
    yahoo_compatible_only: bool = True,
) -> list[tuple[str, str | None]]:
    """
    Universo BYMA: CEDEARs y acciones ordenados por volumen nominal del día (desc).
    Devuelve pares (ticker_iol, yahoo_override=None).
    """
    def _sym(row: dict[str, Any]) -> str:
        return str(row.get("symbol") or row.get("ticker") or "").strip().upper()

    def _vol(row: dict[str, Any]) -> float:
        for k in ("volumeAmount", "nominalVolume", "tradedVolume", "volume"):
            v = row.get(k)
            try:
                if v is not None and str(v).strip() != "":
                    return float(v)
            except Exception:
                pass
        return 0.0

    ced_raw = [r for r in _fetch_tipo("cedears") if isinstance(r, dict)]
    eq_raw = [r for r in _fetch_tipo("equities") if isinstance(r, dict)]

    ced_rank = sorted(
        [( _sym(r), _vol(r)) for r in ced_raw if _sym(r)],
        key=lambda x: (-x[1], x[0]),
    )
    eq_rank = sorted(
        [(_sym(r), _vol(r)) for r in eq_raw if _sym(r)],
        key=lambda x: (-x[1], x[0]),
    )
    if limit_cedears is not None and limit_cedears > 0:
        ced_rank = ced_rank[:limit_cedears]
    if limit_equities is not None and limit_equities > 0:
        eq_rank = eq_rank[:limit_equities]

    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for s, _ in ced_rank + eq_rank:
        if yahoo_compatible_only and not _is_yahoo_compatible_symbol(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append((s, None))
    return out


def _load_broken(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_broken(path: Path, data: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_temporarily_excluded(rec: dict[str, Any], now: datetime) -> bool:
    cnt = int(rec.get("count", 0) or 0)
    if cnt < 3:
        return False
    ts = str(rec.get("last_failure", "") or "").strip()
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return False
    return now - dt <= timedelta(days=7)


def main() -> int:
    p = argparse.ArgumentParser(description="Top N perlas del dia (screening corto plazo).")
    p.add_argument("--symbols-file", required=True, type=Path, help="Texto: ticker IOL por linea o IOL,Yahoo.")
    p.add_argument("--market", default="argentina")
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-score", type=float, default=0.20)
    p.add_argument("--use-byma-universe", action="store_true", help="Usa universo BYMA + ranking por volumen.")
    p.add_argument("--limit-cedears", type=int, default=0, help="Tope CEDEARs BYMA (0=todos).")
    p.add_argument("--limit-equities", type=int, default=0, help="Tope acciones BYMA (0=todas).")
    p.add_argument(
        "--allow-non-yahoo-symbols",
        action="store_true",
        help="Si se activa, incluye símbolos BYMA no compatibles con Yahoo (puede generar muchos errores).",
    )
    p.add_argument("--offline", action="store_true")
    p.add_argument("--hist-period", default="6mo")
    p.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "pearl_hist_cache")
    p.add_argument("--cache-ttl-seconds", type=float, default=3600.0)
    p.add_argument("--notify-telegram", action="store_true")
    p.add_argument("--print-whatsapp", action="store_true", help="Imprime mensaje listo para WhatsApp.")
    p.add_argument("--whatsapp-ars-only", action="store_true", help="Mensaje WhatsApp solo en ARS.")
    p.add_argument(
        "--whatsapp-file",
        type=Path,
        default=ROOT / "data" / "top5_perlas_whatsapp.txt",
        help="Archivo de salida para mensaje WhatsApp.",
    )
    p.add_argument(
        "--broken-cache-file",
        type=Path,
        default=ROOT / "data" / "top5_broken_symbols.json",
        help="Cache de simbolos con fallos repetidos (auto-exclusion temporal).",
    )
    p.add_argument("--tech-strategy", default="breakout_close_20")
    p.add_argument("--min-z", type=float, default=0.80)
    p.add_argument(
        "--min-market-move-pct",
        type=float,
        default=10.0,
        help="Solo tickers con |precio - cierre previo|/cierre previo mayor a este umbral (porcentaje). 0 desactiva.",
    )
    p.add_argument(
        "--ccl",
        type=float,
        default=float(os.environ.get("CCL_FALLBACK_OVERRIDE", "1500.0")),
        help="CCL de referencia para conversion ARS<->USD.",
    )
    args = p.parse_args()

    if args.use_byma_universe:
        lim_ced = args.limit_cedears if args.limit_cedears > 0 else None
        lim_eq = args.limit_equities if args.limit_equities > 0 else None
        rows = _byma_ranked_universe(
            limit_cedears=lim_ced,
            limit_equities=lim_eq,
            yahoo_compatible_only=not args.allow_non_yahoo_symbols,
        )
    else:
        rows = read_symbol_rows(args.symbols_file)
    if not rows:
        print("Sin simbolos en archivo.", file=sys.stderr)
        return 2

    cfg = PearlAnomalyConfig()
    if args.min_z is not None:
        cfg = replace(cfg, min_z_for_signal=float(args.min_z))
    tech = (args.tech_strategy or "").strip()
    cfg = replace(cfg, tech_strategy_name=tech or None)

    client: IOLApiClient | None = None
    if not args.offline:
        settings = load_iol_bot_settings()
        client = IOLApiClient(settings=settings)
    ccl = float(args.ccl) if float(args.ccl) > 0 else 1500.0
    now = datetime.now()
    broken = _load_broken(args.broken_cache_file)
    skipped_broken: list[str] = []

    out_rows: list[dict[str, Any]] = []
    for iol_sym, yahoo in rows:
        rec = broken.get(iol_sym, {})
        if _is_temporarily_excluded(rec, now):
            skipped_broken.append(iol_sym)
            continue
        yh = yahoo or default_yahoo_ticker(iol_sym, args.market)
        try:
            df = ensure_hist_cached(yh, args.hist_period, args.cache_dir, args.cache_ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            out_rows.append({"symbol": iol_sym, "error": f"hist: {exc}"})
            broken[iol_sym] = {
                "count": int(rec.get("count", 0) or 0) + 1,
                "last_failure": now.isoformat(timespec="seconds"),
                "last_error": f"hist: {exc}",
            }
            continue

        close_s = pd.Series(df["close"].values, dtype="float64")
        vol_s = pd.Series(df["volume"].values, dtype="float64") if "volume" in df.columns else None
        if args.offline:
            if len(close_s) < cfg.min_hist_bars + 1:
                continue
            live_px = float(close_s.iloc[-1])
            close_for_model = close_s.iloc[:-1]
            vol_hist = vol_s.iloc[:-1] if vol_s is not None else None
            live_vol = float(vol_s.iloc[-1]) if vol_s is not None and len(vol_s) else None
        else:
            close_for_model = close_s
            vol_hist = vol_s
            try:
                quote = client.get_quote(args.market, iol_sym) if client is not None else {}
                live_px, live_vol = parse_iol_quote_price_volume(quote)
                if live_px is None:
                    out_rows.append({"symbol": iol_sym, "error": "sin precio en quote IOL"})
                    broken[iol_sym] = {
                        "count": int(rec.get("count", 0) or 0) + 1,
                        "last_failure": now.isoformat(timespec="seconds"),
                        "last_error": "sin precio en quote IOL",
                    }
                    continue
            except Exception as exc:  # noqa: BLE001
                out_rows.append({"symbol": iol_sym, "error": f"iol: {exc}"})
                broken[iol_sym] = {
                    "count": int(rec.get("count", 0) or 0) + 1,
                    "last_failure": now.isoformat(timespec="seconds"),
                    "last_error": f"iol: {exc}",
                }
                continue

        move_pct = _abs_move_vs_prior_close_pct(close_for_model, float(live_px))
        thr_move = float(args.min_market_move_pct)
        if thr_move > 0.0:
            if move_pct is None:
                continue
            if move_pct <= thr_move:
                continue

        res = score_pearl_buy(
            close_for_model,
            float(live_px),
            cfg,
            volume_hist=vol_hist,
            live_volume=live_vol,
        )
        if res.score < args.min_score:
            continue
        tp_pct, sl_pct = _risk_suggestion(close_for_model)
        occ_days, occ_range = _occurrence_window(close_for_model)
        tp_mult = 1.0 + tp_pct / 100.0
        sl_mult = 1.0 - sl_pct / 100.0
        # Regla simple de moneda: *.BA suele cotizar en ARS; resto en USD.
        is_ars_quote = yh.upper().endswith(".BA")
        px = float(live_px)
        if is_ars_quote:
            price_ars = px
            price_usd = px / ccl
        else:
            price_usd = px
            price_ars = px * ccl
        tp_ars = price_ars * tp_mult
        sl_ars = price_ars * sl_mult
        tp_usd = price_usd * tp_mult
        sl_usd = price_usd * sl_mult
        out_rows.append(
            {
                "symbol": iol_sym,
                "yahoo": yh,
                "score": float(res.score),
                "z": res.z_return,
                "price": px,
                "quote_ccy": "ARS" if is_ars_quote else "USD",
                "ccl_used": ccl,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "price_ars": round(price_ars, 2),
                "price_usd": round(price_usd, 4),
                "tp_ars": round(tp_ars, 2),
                "sl_ars": round(sl_ars, 2),
                "tp_usd": round(tp_usd, 4),
                "sl_usd": round(sl_usd, 4),
                "occurrence_days": occ_days,
                "occurrence_range": occ_range,
                "market_move_pct": None if move_pct is None else round(float(move_pct), 2),
                "reasons": list(res.reasons)[:3],
            }
        )
        if iol_sym in broken:
            broken.pop(iol_sym, None)

    ranked = [r for r in out_rows if "score" in r]
    ranked.sort(key=lambda x: x["score"], reverse=True)
    top_n = max(1, int(args.top_n))
    top = ranked[:top_n]

    result = {
        "ok": True,
        "market": args.market,
        "offline": bool(args.offline),
        "min_score": float(args.min_score),
        "min_market_move_pct": float(args.min_market_move_pct),
        "top_n": top_n,
        "universe_mode": "byma_volume_ranked" if args.use_byma_universe else "file",
        "results": top,
        "errors": [r for r in out_rows if "error" in r][:30],
        "excluded_temporarily": skipped_broken[:200],
    }
    print(json.dumps(result, ensure_ascii=False))
    _save_broken(args.broken_cache_file, broken)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    whatsapp_msg = (
        _build_whatsapp_message_ars_only(top, args.market, generated_at)
        if args.whatsapp_ars_only
        else _build_whatsapp_message(top, args.market, generated_at)
    )
    args.whatsapp_file.parent.mkdir(parents=True, exist_ok=True)
    args.whatsapp_file.write_text(whatsapp_msg, encoding="utf-8")
    if args.print_whatsapp:
        print("\n--- WHATSAPP ---")
        print(whatsapp_msg)

    if args.notify_telegram and top:
        enviar_telegram(_build_telegram_summary(top, args.market))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

