"""
G04 — Registro mínimo de consentimiento informativo (Ley 25.326 AR, placeholder).

No sustituye asesoramiento legal; campos para trazabilidad en UI/API futura.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ConsentRecord25326:
    subject_id: str
    purpose: str
    accepted: bool
    recorded_at_utc: str
    version: str = "placeholder-v1"

    @classmethod
    def create(cls, subject_id: str, purpose: str, accepted: bool) -> ConsentRecord25326:
        return cls(
            subject_id=subject_id,
            purpose=purpose,
            accepted=accepted,
            recorded_at_utc=datetime.now(UTC).isoformat(),
        )
