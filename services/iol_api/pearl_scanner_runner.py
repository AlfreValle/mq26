"""
Logica del escaner de perlas IOL (historial + score + estado). Usado por scripts/iol_pearl_scanner.py.
"""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from core.logging_config import get_logger
from services.alert_bot import enviar_telegram

logger = get_logger(__name__)
from services.iol_api.anomaly_scan import (
    PearlAnomalyConfig,
    PearlScoreResult,
    hist_meets_minimum,
    parse_iol_quote_price_volume,
    score_pearl_buy,
)
from services.iol_api.client import IOLApiClient
from services.iol_api.pearl_state import (
    PearlScannerState,
    advance_cooldown_if_due,
    can_scan_new_candidates,
    check_exit_event,
    enter_in_position,
    record_notify,
    save_pearl_state,
    should_skip_notify_dedupe,
)


def read_symbol_rows(path: Path) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "," in s:
            parts = [p.strip() for p in s.split(",", 1)]
            rows.append((parts[0], parts[1] if len(parts) > 1 else None))
        else:
            rows.append((s, None))
    return rows


def default_yahoo_ticker(iol_symbol: str, market: str) -> str:
    m = market.strip().lower()
    if "." in iol_symbol:
        return iol_symbol
    if m in {"argentina", "ar", "bcba"}:
        return f"{iol_symbol}.BA"
    return iol_symbol


def cache_path(cache_dir: Path, yahoo_ticker: str) -> Path:
    safe = yahoo_ticker.replace("/", "_").replace("\\", "_")
    return cache_dir / f"{safe}.csv"


def load_hist_from_cache(path: Path, ttl_sec: float) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl_sec:
        return None
    return pd.read_csv(path, parse_dates=["Date"])


def _yf_history_to_df(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Normaliza salida de Ticker.history / download a Date, close, volume."""
    if raw is None or raw.empty or "Close" not in raw.columns:
        return None
    work = raw
    if isinstance(work.columns, pd.MultiIndex):
        if work.columns.nlevels > 1:
            work = work.droplevel(0, axis=1)
    # No alinear por indice de work (DatetimeIndex) vs out recien creado (RangeIndex):
    # usar arrays para evitar NaN en close.
    dates = pd.to_datetime(work.index, utc=True).tz_convert(None).normalize()
    out = pd.DataFrame(
        {
            "Date": dates.to_numpy(),
            "close": pd.to_numeric(work["Close"].to_numpy(), errors="coerce"),
        }
    )
    if "Volume" in work.columns:
        out["volume"] = pd.to_numeric(work["Volume"].to_numpy(), errors="coerce")
    out = out.dropna(subset=["close"])
    return out if not out.empty else None


def _yahoo_fetch_candidates(yahoo_ticker: str) -> list[str]:
    """Prioridad principal; si termina en .BA, reintenta sin sufijo (otro listing Yahoo)."""
    cands = [yahoo_ticker.strip()]
    y = cands[0]
    if y.endswith(".BA"):
        base = y[: -len(".BA")].strip()
        if base and base.upper() not in {c.upper() for c in cands}:
            cands.append(base)
    return cands


def download_yfinance_hist(yahoo_ticker: str, period: str) -> pd.DataFrame:
    """
    Descarga diaria vía yfinance. Usa Ticker.history (evita fallos de download()
    con un solo ticker, p. ej. TypeError NoneType en algunas versiones).
    """
    import yfinance as yf

    last_exc: BaseException | None = None
    for t in _yahoo_fetch_candidates(yahoo_ticker):
        try:
            raw = yf.Ticker(t).history(period=period, interval="1d", auto_adjust=True)
            out = _yf_history_to_df(raw)
            if out is not None:
                if t != yahoo_ticker:
                    logger.warning(
                        "yfinance: sin datos para %s; usando listing alternativo %s (puede diferir del activo IOL).",
                        yahoo_ticker,
                        t,
                    )
                return out
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            continue
        try:
            raw = yf.download(
                t,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if isinstance(raw.columns, pd.MultiIndex) and raw.columns.nlevels > 1:
                if t in raw.columns.get_level_values(0):
                    raw = raw[t]
                else:
                    raw = raw.droplevel(0, axis=1)
            out = _yf_history_to_df(raw)
            if out is not None:
                if t != yahoo_ticker:
                    logger.warning(
                        "yfinance (download): usando listing alternativo %s en lugar de %s.",
                        t,
                        yahoo_ticker,
                    )
                return out
        except BaseException as exc:  # noqa: BLE001
            last_exc = exc
            continue

    hint = (
        f" Sin datos yfinance para {yahoo_ticker!r}. "
        "Proba en el archivo de simbolos: TICKER_IOL,TICKER_YAHOO explicito "
        "(ej. GGAL,GGAL.BA o otro simbolo que Yahoo tenga activo)."
    )
    if last_exc is not None:
        raise RuntimeError(hint + f" Detalle: {last_exc!r}") from last_exc
    raise RuntimeError(hint)


def ensure_hist_cached(
    yahoo_ticker: str,
    period: str,
    cache_dir: Path,
    ttl_sec: float,
) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_path(cache_dir, yahoo_ticker)
    hit = load_hist_from_cache(p, ttl_sec)
    if hit is not None and not hit.empty:
        return hit
    df = download_yfinance_hist(yahoo_ticker, period)
    df.to_csv(p, index=False)
    return df


def telegram_body_pearl(
    market: str,
    iol_symbol: str,
    score: float,
    live_px: float,
    reasons: tuple[str, ...],
) -> str:
    lines = [
        "Perla IOL (candidato compra corto plazo)",
        f"Mercado: {market} | Ticker: {iol_symbol}",
        f"Score: {score:.3f} | Precio live IOL: {live_px:.4f}",
        "Motivos:",
    ]
    lines.extend(f" - {r}" for r in reasons[:6])
    return "\n".join(lines)


def telegram_body_exit(iol_symbol: str, event: str, px: float) -> str:
    labels = {
        "take_profit": "Objetivo (take profit)",
        "stop_loss": "Stop loss",
        "time_exit": "Salida por tiempo maximo",
    }
    return f"IOL pearl: {labels.get(event, event)} en {iol_symbol} @ {px:.4f}"


def candidate_row(res: PearlScoreResult, iol_sym: str, yh: str) -> dict[str, Any]:
    return {
        "iol": iol_sym,
        "yahoo": yh,
        "score": res.score,
        "z": res.z_return,
        "vol_ratio": res.vol_ratio,
        "reasons": list(res.reasons),
    }


def run_iteration(
    *,
    pairs: list[tuple[str, str | None]],
    market: str,
    cfg: PearlAnomalyConfig,
    min_score: float,
    state: PearlScannerState,
    state_path: Path,
    client: IOLApiClient | None,
    offline: bool,
    notify_telegram: bool,
    use_position_state: bool,
    dedupe_min_sec: float,
    dedupe_score_delta: float,
    cache_dir: Path,
    hist_period: str,
    cache_ttl_sec: float,
) -> tuple[PearlScannerState, dict[str, Any]]:
    state = replace(state, market=market)
    state = advance_cooldown_if_due(state)
    out: dict[str, Any] = {"phase": state.phase, "events": []}
    yahoo_by_iol = {iol: (y or default_yahoo_ticker(iol, market)) for iol, y in pairs}

    if use_position_state and state.phase == "in_position" and state.active_symbol:
        sym = state.active_symbol
        yh = yahoo_by_iol.get(sym)
        if not yh:
            out["events"].append({"type": "config_error", "symbol": sym, "detail": "sin_mapeo_yahoo"})
            save_pearl_state(state_path, state)
            return state, out
        if offline or client is None:
            df = ensure_hist_cached(yh, hist_period, cache_dir, cache_ttl_sec)
            px = float(df["close"].iloc[-1])
        else:
            q = client.get_quote(market, sym)
            px, _ = parse_iol_quote_price_volume(q)
            if px is None:
                out["events"].append({"type": "quote_error", "symbol": sym})
                save_pearl_state(state_path, state)
                return state, out
        new_state, ev = check_exit_event(state, px)
        state = new_state
        if ev:
            msg = telegram_body_exit(sym, ev, px)
            if notify_telegram:
                enviar_telegram(msg)
            out["events"].append({"type": "exit", "symbol": sym, "event": ev, "price": px})
        save_pearl_state(state_path, state)
        return state, out

    if not can_scan_new_candidates(state):
        save_pearl_state(state_path, state)
        out["note"] = "fase_no_idle"
        return state, out

    rows_out: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []
    for iol_sym, yahoo in pairs:
        yh = yahoo or default_yahoo_ticker(iol_sym, market)
        try:
            df = ensure_hist_cached(yh, hist_period, cache_dir, cache_ttl_sec)
        except Exception as exc:  # noqa: BLE001
            rows_out.append({"iol": iol_sym, "yahoo": yh, "error": str(exc)})
            continue
        close_s = pd.Series(df["close"].values, dtype="float64")
        vol_s = pd.Series(df["volume"].values, dtype="float64") if "volume" in df.columns else None
        if offline or client is None:
            if len(close_s) < cfg.min_hist_bars + 1:
                rows_out.append({"iol": iol_sym, "yahoo": yh, "skipped": "historial_corto_offline"})
                continue
            live_px = float(close_s.iloc[-1])
            close_for_model = close_s.iloc[:-1]
            vol_hist = vol_s.iloc[:-1] if vol_s is not None else None
            live_vol = float(vol_s.iloc[-1]) if vol_s is not None and len(vol_s) else None
            if not hist_meets_minimum(close_for_model, cfg):
                rows_out.append({"iol": iol_sym, "yahoo": yh, "skipped": "historial_corto"})
                continue
        else:
            close_for_model = close_s
            vol_hist = vol_s
            if not hist_meets_minimum(close_for_model, cfg):
                rows_out.append({"iol": iol_sym, "yahoo": yh, "skipped": "historial_corto"})
                continue
            q = client.get_quote(market, iol_sym)
            live_px, live_vol = parse_iol_quote_price_volume(q)
            if live_px is None:
                rows_out.append({"iol": iol_sym, "yahoo": yh, "error": "sin_precio_en_quote"})
                continue

        res = score_pearl_buy(
            close_for_model,
            live_px,
            cfg,
            volume_hist=vol_hist,
            live_volume=live_vol,
        )
        rows_out.append(candidate_row(res, iol_sym, yh))
        scored.append({"iol": iol_sym, "yahoo": yh, "live_px": live_px, "result": res})

    out["candidates"] = rows_out
    scored.sort(key=lambda x: float(x["result"].score), reverse=True)

    for row in scored:
        res = row["result"]
        if res.score < min_score:
            continue
        sym = str(row["iol"])
        live_px = float(row["live_px"])
        if should_skip_notify_dedupe(
            state,
            sym,
            res.score,
            min_interval_sec=dedupe_min_sec,
            score_delta_renotify=dedupe_score_delta,
        ):
            skipped = out.setdefault("dedupe_skipped", [])
            skipped.append({"symbol": sym, "score": res.score})
            continue

        msg = telegram_body_pearl(market, sym, res.score, live_px, res.reasons)
        if notify_telegram:
            enviar_telegram(msg)
        state = record_notify(state, sym, res.score)
        if use_position_state:
            state = enter_in_position(state, sym, live_px, market=market)
        out["picked"] = {"symbol": sym, "score": res.score, "price": live_px, "notified": notify_telegram}
        break

    save_pearl_state(state_path, state)
    return state, out
