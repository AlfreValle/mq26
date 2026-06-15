from __future__ import annotations

from ui.privacy_display import maybe_mask_money_display, privacy_hide_amounts


def test_privacy_off_explicit_session():
    s: dict = {}
    assert privacy_hide_amounts(s) is False
    assert maybe_mask_money_display("USD 1.000", session_state=s) == "USD 1.000"


def test_privacy_on_masks():
    s = {"mq26_privacy_hide_amounts": True}
    assert privacy_hide_amounts(s) is True
    assert maybe_mask_money_display("USD 1.000", session_state=s) == "••••••"


def test_mask_respects_emdash():
    s = {"mq26_privacy_hide_amounts": True}
    assert maybe_mask_money_display("—", session_state=s) == "—"
