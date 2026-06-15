"""
core/export_lineage.py — Lineage en exportaciones (C35, D52/D53, G lineage/hash).

Genera manifiestos reproducibles: hash de inputs, versión de modelo y parámetros,
sin almacenar secretos en texto plano.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

MODEL_VERSION_KEY = "mq26_model_version"
DEFAULT_MODEL_VERSION = "1.1.0-fase1"


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_inputs(**kwargs: Any) -> str:
    """Hash SHA-256 del JSON estable de argumentos nombrados (inputs cuant)."""
    return sha256_hex(stable_json_dumps(kwargs).encode("utf-8"))


def build_export_manifest(
    *,
    model_version: str = DEFAULT_MODEL_VERSION,
    optimization_method: str,
    inputs_digest: str,
    parameters: dict[str, Any],
    tickers: list[str] | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Manifiesto para adjuntar a CSV/JSON/ZIP exportados (C35)."""
    return {
        MODEL_VERSION_KEY: model_version,
        "optimization_method": optimization_method,
        "inputs_content_sha256": inputs_digest,
        "parameters": parameters,
        "tickers": list(tickers or []),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }


def wrap_payload_with_lineage(
    payload: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Envuelve resultados con bloque _lineage para auditoría."""
    lineage_digest = sha256_hex(stable_json_dumps(manifest).encode("utf-8"))
    out = dict(payload)
    out["_lineage"] = {"manifest": manifest, "manifest_sha256": lineage_digest}
    return out


def serialize_signed_bundle(
    results: dict[str, Any],
    manifest: dict[str, Any],
) -> str:
    """JSON completo (firma = hash del manifiesto embebido en _lineage)."""
    return stable_json_dumps(wrap_payload_with_lineage(results, manifest))
