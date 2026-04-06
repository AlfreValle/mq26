"""
G07 — Export SOX-light: checklist y manifiesto mínimo para auditoría interna.
"""
from __future__ import annotations

from typing import Any

SOX_CHECKLIST_KEYS = (
    "lineage_manifest_present",
    "model_version_recorded",
    "parameters_hashed",
    "user_tenant_recorded",
)


def build_sox_light_bundle(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Genera bloque checklist + manifest embebido (sin I/O)."""
    m = manifest or {}
    checks = {
        "lineage_manifest_present": bool(m),
        "model_version_recorded": "mq26_model_version" in m or "optimization_method" in m,
        "parameters_hashed": "inputs_content_sha256" in m,
        "user_tenant_recorded": m.get("user_id") is not None or m.get("tenant_id") is not None,
    }
    return {
        "sox_light_version": "1.0",
        "checklist": checks,
        "checklist_all_true": all(checks[k] for k in SOX_CHECKLIST_KEYS),
        "manifest": m,
    }
