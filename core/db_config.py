"""
core/db_config.py — Dominio: Configuración & Auditoría de Parámetros
DB: 0_Data_Maestra/db_config.db

Tablas:
  configuracion      — Store clave-valor JSON para parámetros runtime
  global_param_audit — Ledger append-only de cambios a parámetros críticos

Parámetros auditados: RISK_FREE_RATE, PESO_MAX_CARTERA, PESO_MAX_OPT, PESO_MAX.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from core.db_domains import CONFIG

if TYPE_CHECKING:
    import pandas as pd

_B: Any = CONFIG.Base  # mypy: alias dinámico SQLAlchemy
# Claves que generan fila de auditoría al modificarse
PARAM_AUDIT_KEYS = frozenset({
    "RISK_FREE_RATE",
    "PESO_MAX_OPT",
    "PESO_MAX_CARTERA",
    "PESO_MAX",
})


# ─── Modelos ──────────────────────────────────────────────────────────────────

class Configuracion(_B):
    """
    Store clave-valor genérico para parámetros runtime.
    Valor almacenado como JSON (str, int, float, dict, list).
    """
    __tablename__ = "configuracion"

    clave      = Column(String(100), primary_key=True)
    valor      = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class GlobalParamAudit(_B):
    """
    Ledger append-only de cambios a parámetros críticos.
    Solo INSERT; nunca UPDATE/DELETE.
    """
    __tablename__ = "global_param_audit"
    __table_args__ = (Index("ix_gpa_param_key", "param_key"),)

    id         = Column(Integer, primary_key=True, autoincrement=True)
    param_key  = Column(String(100), nullable=False)
    old_value  = Column(Text, nullable=True)
    new_value  = Column(Text, nullable=False)
    changed_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    changed_by = Column(String(200), default="")
    context    = Column(Text, default="")   # JSON extra context


# ─── Inicializar ──────────────────────────────────────────────────────────────
CONFIG.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def guardar_config(clave: str, valor: Any, changed_by: str = "", context: str = "") -> None:
    """
    Persiste un parámetro. Si la clave está en PARAM_AUDIT_KEYS, registra auditoría.
    """
    clave = clave.strip()[:100]
    valor_json = json.dumps(valor, ensure_ascii=False)

    with CONFIG.session() as s:
        old_row = s.query(Configuracion).filter(Configuracion.clave == clave).first()
        old_json = old_row.valor if old_row else None

        if old_row:
            old_row.valor = valor_json
            old_row.updated_at = dt.datetime.utcnow()
        else:
            s.add(Configuracion(clave=clave, valor=valor_json))

        # Auditoría para parámetros críticos
        if clave in PARAM_AUDIT_KEYS and old_json != valor_json:
            s.add(GlobalParamAudit(
                param_key=clave,
                old_value=old_json,
                new_value=valor_json,
                changed_by=changed_by or "",
                context=context or "",
            ))


def obtener_config(clave: str, default: Any = None) -> Any:
    """Lee un parámetro. Deserializa desde JSON. Retorna default si no existe."""
    with CONFIG.session() as s:
        row = s.query(Configuracion).filter(Configuracion.clave == clave).first()
        if not row:
            return default
        try:
            return json.loads(row.valor)
        except (json.JSONDecodeError, TypeError):
            return row.valor   # devuelve string crudo si no es JSON válido


def listar_config() -> dict[str, Any]:
    """Todos los parámetros persistidos {clave: valor_deserializado}."""
    with CONFIG.session() as s:
        rows = s.query(Configuracion).all()
        result = {}
        for r in rows:
            try:
                result[r.clave] = json.loads(r.valor)
            except (json.JSONDecodeError, TypeError):
                result[r.clave] = r.valor
        return result


def registrar_evento_admin(
    param_key: str,
    new_value: Any,
    old_value: Any = None,
    changed_by: str = "",
    context: str = "",
) -> None:
    """Fuerza un registro de auditoría (sin modificar la configuracion)."""
    with CONFIG.session() as s:
        s.add(GlobalParamAudit(
            param_key=str(param_key)[:100],
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value),
            changed_by=changed_by or "",
            context=context or "",
        ))


def historial_param(clave: str, limit: int = 50) -> pd.DataFrame:
    """Historial de cambios de un parámetro auditado."""
    import pandas as pd

    with CONFIG.session() as s:
        rows = (
            s.query(GlobalParamAudit)
            .filter(GlobalParamAudit.param_key == clave)
            .order_by(GlobalParamAudit.changed_at.desc())
            .limit(limit)
            .all()
        )
    if not rows:
        return pd.DataFrame(columns=["param_key", "old_value", "new_value", "changed_at", "changed_by"])
    return pd.DataFrame([{
        "param_key": r.param_key,
        "old_value": r.old_value,
        "new_value": r.new_value,
        "changed_at": r.changed_at,
        "changed_by": r.changed_by,
        "context": r.context,
    } for r in rows])
