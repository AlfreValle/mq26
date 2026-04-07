"""
services/favoritos_mes.py — Lista convicción estudio (RF/RV) consumida por el recomendador.

Persistencia JSON bajo 0_Data_Maestra/ o ruta vía MQ26_FAVORITOS_MES_PATH (tests).
Incluye auditoría mínima: published_at (UTC ISO), published_by.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def favoritos_mes_path() -> Path:
    env = os.environ.get("MQ26_FAVORITOS_MES_PATH", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "0_Data_Maestra" / "mq26_favoritos_mes.json"


def _empty_doc() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "rf": [],
        "rv": [],
        "published_at": "",
        "published_by": "",
        "disclaimer": "",
    }


def _normalize_tickers(xs: Any) -> list[str]:
    if not isinstance(xs, list):
        return []
    out: list[str] = []
    for t in xs:
        u = str(t or "").strip().upper()
        if u:
            out.append(u)
    return out


def normalize_favoritos_doc(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw or not isinstance(raw, dict):
        return _empty_doc()
    base = _empty_doc()
    base["schema_version"] = int(raw.get("schema_version") or SCHEMA_VERSION)
    base["rf"] = _normalize_tickers(raw.get("rf"))
    base["rv"] = _normalize_tickers(raw.get("rv"))
    base["published_at"] = str(raw.get("published_at") or "").strip()
    base["published_by"] = str(raw.get("published_by") or "").strip()
    base["disclaimer"] = str(raw.get("disclaimer") or "").strip()
    return base


def load_favoritos_mes() -> dict[str, Any]:
    p = favoritos_mes_path()
    if not p.exists():
        return _empty_doc()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_doc()
    return normalize_favoritos_doc(raw if isinstance(raw, dict) else None)


def save_favoritos_mes(
    rf: list[str],
    rv: list[str],
    *,
    published_by: str,
    disclaimer: str = "",
) -> Path:
    """Escribe JSON y crea directorio padre si hace falta. Devuelve path usado."""
    p = favoritos_mes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "rf": _normalize_tickers(rf),
        "rv": _normalize_tickers(rv),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "published_by": (published_by or "").strip(),
        "disclaimer": (disclaimer or "").strip(),
    }
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def aplicar_prioridad_favoritos(ordenados: list[str], favoritos: list[str]) -> list[str]:
    """Mantiene el orden relativo dentro de cada bloque: primero los que están en favoritos."""
    fav_set = {str(t).strip().upper() for t in favoritos if str(t).strip()}
    primero = [t for t in ordenados if str(t).strip().upper() in fav_set]
    resto = [t for t in ordenados if str(t).strip().upper() not in fav_set]
    return primero + resto
