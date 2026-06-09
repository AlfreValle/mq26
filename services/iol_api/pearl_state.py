"""
Estado del escaner de perlas: fase idle/in_position/cooldown, deduplicacion de alertas,
y seguimiento de objetivo / stop / tiempo maximo en posicion.
"""
from __future__ import annotations

import json
import time
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Phase = Literal["idle", "in_position", "cooldown"]


@dataclass
class PearlScannerState:
    phase: Phase = "idle"
    market: str = "argentina"
    active_symbol: str | None = None
    entry_price: float | None = None
    entry_epoch: float | None = None
    target_pct: float = 3.0
    stop_pct: float = 2.0
    max_hold_seconds: float = 86400.0 * 3
    cooldown_seconds: float = 300.0
    cooldown_until_epoch: float | None = None
    last_notify: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_json_dict(cls, raw: dict[str, Any]) -> PearlScannerState:
        ln = raw.get("last_notify") or {}
        if not isinstance(ln, dict):
            ln = {}
        cleaned: dict[str, dict[str, float]] = {}
        for k, v in ln.items():
            if isinstance(v, dict) and "epoch" in v and "score" in v:
                cleaned[str(k)] = {"epoch": float(v["epoch"]), "score": float(v["score"])}
        phase = raw.get("phase", "idle")
        if phase not in ("idle", "in_position", "cooldown"):
            phase = "idle"
        return cls(
            phase=phase,  # type: ignore[arg-type]
            market=str(raw.get("market", "argentina")),
            active_symbol=(str(raw["active_symbol"]) if raw.get("active_symbol") else None),
            entry_price=(float(raw["entry_price"]) if raw.get("entry_price") is not None else None),
            entry_epoch=(float(raw["entry_epoch"]) if raw.get("entry_epoch") is not None else None),
            target_pct=float(raw.get("target_pct", 3.0)),
            stop_pct=float(raw.get("stop_pct", 2.0)),
            max_hold_seconds=float(raw.get("max_hold_seconds", 86400.0 * 3)),
            cooldown_seconds=float(raw.get("cooldown_seconds", 300.0)),
            cooldown_until_epoch=(
                float(raw["cooldown_until_epoch"]) if raw.get("cooldown_until_epoch") is not None else None
            ),
            last_notify=cleaned,
        )


def load_pearl_state(path: Path) -> PearlScannerState:
    if not path.is_file():
        return PearlScannerState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return PearlScannerState()
        return PearlScannerState.from_json_dict(raw)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return PearlScannerState()


def save_pearl_state(path: Path, state: PearlScannerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_json_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> float:
    return time.time()


def advance_cooldown_if_due(state: PearlScannerState, now: float | None = None) -> PearlScannerState:
    t = now if now is not None else _now()
    if state.phase != "cooldown":
        return state
    until = state.cooldown_until_epoch
    if until is not None and t >= until:
        return PearlScannerState(
            phase="idle",
            market=state.market,
            active_symbol=None,
            entry_price=None,
            entry_epoch=None,
            target_pct=state.target_pct,
            stop_pct=state.stop_pct,
            max_hold_seconds=state.max_hold_seconds,
            cooldown_seconds=state.cooldown_seconds,
            cooldown_until_epoch=None,
            last_notify=state.last_notify,
        )
    return state


def can_scan_new_candidates(state: PearlScannerState, now: float | None = None) -> bool:
    s = advance_cooldown_if_due(state, now)
    return s.phase == "idle"


def should_skip_notify_dedupe(
    state: PearlScannerState,
    symbol: str,
    score: float,
    *,
    min_interval_sec: float,
    score_delta_renotify: float,
    now: float | None = None,
) -> bool:
    t = now if now is not None else _now()
    rec = state.last_notify.get(symbol)
    if not rec:
        return False
    last_t = float(rec.get("epoch", 0))
    last_s = float(rec.get("score", 0))
    if t - last_t < min_interval_sec and (score - last_s) < score_delta_renotify:
        return True
    return False


def record_notify(state: PearlScannerState, symbol: str, score: float, now: float | None = None) -> PearlScannerState:
    t = now if now is not None else _now()
    ln = dict(state.last_notify)
    ln[symbol] = {"epoch": t, "score": float(score)}
    return PearlScannerState(
        phase=state.phase,
        market=state.market,
        active_symbol=state.active_symbol,
        entry_price=state.entry_price,
        entry_epoch=state.entry_epoch,
        target_pct=state.target_pct,
        stop_pct=state.stop_pct,
        max_hold_seconds=state.max_hold_seconds,
        cooldown_seconds=state.cooldown_seconds,
        cooldown_until_epoch=state.cooldown_until_epoch,
        last_notify=ln,
    )


def enter_in_position(
    state: PearlScannerState,
    symbol: str,
    entry_price: float,
    *,
    market: str | None = None,
    now: float | None = None,
) -> PearlScannerState:
    t = now if now is not None else _now()
    return PearlScannerState(
        phase="in_position",
        market=market or state.market,
        active_symbol=symbol,
        entry_price=float(entry_price),
        entry_epoch=t,
        target_pct=state.target_pct,
        stop_pct=state.stop_pct,
        max_hold_seconds=state.max_hold_seconds,
        cooldown_seconds=state.cooldown_seconds,
        cooldown_until_epoch=None,
        last_notify=state.last_notify,
    )


def check_exit_event(
    state: PearlScannerState,
    current_price: float,
    *,
    now: float | None = None,
) -> tuple[PearlScannerState, str | None]:
    """
    Si phase=in_position, evalua TP / SL / tiempo. Devuelve (nuevo_estado, evento).
    evento: 'take_profit' | 'stop_loss' | 'time_exit' | None
    """
    s = advance_cooldown_if_due(state, now)
    t = now if now is not None else _now()
    if s.phase != "in_position" or s.active_symbol is None or s.entry_price is None:
        return s, None
    ep = float(s.entry_price)
    if ep <= 0 or not (math.isfinite(current_price) and current_price > 0):
        return s, None
    ret_pct = (current_price / ep - 1.0) * 100.0
    if ret_pct >= s.target_pct:
        return _to_cooldown_after_close(s, t), "take_profit"
    if ret_pct <= -abs(s.stop_pct):
        return _to_cooldown_after_close(s, t), "stop_loss"
    if s.entry_epoch is not None and (t - float(s.entry_epoch)) >= s.max_hold_seconds:
        return _to_cooldown_after_close(s, t), "time_exit"
    return s, None


def _to_cooldown_after_close(state: PearlScannerState, now: float) -> PearlScannerState:
    until = now + max(0.0, state.cooldown_seconds)
    return PearlScannerState(
        phase="cooldown",
        market=state.market,
        active_symbol=None,
        entry_price=None,
        entry_epoch=None,
        target_pct=state.target_pct,
        stop_pct=state.stop_pct,
        max_hold_seconds=state.max_hold_seconds,
        cooldown_seconds=state.cooldown_seconds,
        cooldown_until_epoch=until,
        last_notify=state.last_notify,
    )


def manual_close_to_cooldown(state: PearlScannerState, now: float | None = None) -> PearlScannerState:
    """Cierre manual (usuario opero fuera del bot): fuerza cooldown."""
    return _to_cooldown_after_close(state, now if now is not None else _now())
