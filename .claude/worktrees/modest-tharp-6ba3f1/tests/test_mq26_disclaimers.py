"""Smoke: textos legales disponibles para login."""
from __future__ import annotations

from core.mq26_disclaimers import LOGIN_LEGAL_DISCLAIMER_ES


def test_login_disclaimer_no_vacio():
    assert len(LOGIN_LEGAL_DISCLAIMER_ES) > 40
    assert "CNV" in LOGIN_LEGAL_DISCLAIMER_ES
