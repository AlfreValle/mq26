from __future__ import annotations

from pathlib import Path

from services.iol_api.pearl_state import (
    PearlScannerState,
    advance_cooldown_if_due,
    can_scan_new_candidates,
    check_exit_event,
    enter_in_position,
    load_pearl_state,
    manual_close_to_cooldown,
    record_notify,
    save_pearl_state,
    should_skip_notify_dedupe,
)


def test_load_save_roundtrip(tmp_path: Path):
    p = tmp_path / "st.json"
    s = PearlScannerState(phase="idle", target_pct=4.0, last_notify={"GGAL": {"epoch": 1.0, "score": 0.8}})
    save_pearl_state(p, s)
    s2 = load_pearl_state(p)
    assert s2.target_pct == 4.0
    assert s2.last_notify["GGAL"]["score"] == 0.8


def test_dedupe_skip():
    s = PearlScannerState(last_notify={"A": {"epoch": 1000.0, "score": 0.7}})
    assert should_skip_notify_dedupe(s, "A", 0.72, min_interval_sec=600, score_delta_renotify=0.2, now=1100.0)
    assert not should_skip_notify_dedupe(s, "A", 0.95, min_interval_sec=600, score_delta_renotify=0.2, now=1100.0)


def test_take_profit_transition():
    s = enter_in_position(PearlScannerState(target_pct=3.0, stop_pct=2.0), "GGAL", 100.0, now=0.0)
    assert s.phase == "in_position"
    s2, ev = check_exit_event(s, 104.0, now=10.0)
    assert ev == "take_profit"
    assert s2.phase == "cooldown"
    assert s2.cooldown_until_epoch is not None


def test_stop_loss():
    s = enter_in_position(PearlScannerState(target_pct=5.0, stop_pct=2.0), "X", 100.0)
    s2, ev = check_exit_event(s, 97.0)
    assert ev == "stop_loss"
    assert s2.phase == "cooldown"


def test_time_exit():
    s = enter_in_position(
        PearlScannerState(target_pct=99.0, stop_pct=50.0, max_hold_seconds=60.0),
        "X",
        100.0,
        now=0.0,
    )
    s2, ev = check_exit_event(s, 100.5, now=120.0)
    assert ev == "time_exit"


def test_cooldown_to_idle():
    s = PearlScannerState(phase="cooldown", cooldown_until_epoch=50.0)
    s2 = advance_cooldown_if_due(s, now=60.0)
    assert s2.phase == "idle"


def test_can_scan_after_cooldown():
    s = PearlScannerState(phase="cooldown", cooldown_until_epoch=10.0)
    assert can_scan_new_candidates(s, now=5.0) is False
    assert can_scan_new_candidates(s, now=15.0) is True


def test_record_notify_updates():
    s = PearlScannerState()
    s2 = record_notify(s, "GGAL", 0.66, now=123.0)
    assert s2.last_notify["GGAL"]["epoch"] == 123.0


def test_manual_close():
    s = enter_in_position(PearlScannerState(), "Z", 10.0)
    s2 = manual_close_to_cooldown(s, now=1.0)
    assert s2.phase == "cooldown"
