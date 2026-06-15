"""
core/db_auditoria.py — Dominio: Auditoría, Alertas & Trazabilidad
DB: 0_Data_Maestra/db_auditoria.db

Tablas:
  alertas_log               — Eventos de alerta (VAR, drawdown, señales de venta)
  recomendaciones_auditoria — Log de simulaciones y ejecuciones de recomendación
  ordenes_calculadas        — Órdenes pre-aprobadas (optimización → ejecución)
  portfolio_snapshots       — Snapshot periódico de estado de cartera

Append-only por diseño. Sin FK externas; referencia por cliente_id (valor).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

import pandas as pd
from sqlalchemy import (
    Boolean, Column, DateTime, Float,
    Index, Integer, String, Text,
)

from core.db_domains import AUDITORIA

_B = AUDITORIA.Base


# ─── Modelos ──────────────────────────────────────────────────────────────────

class AlertaLog(_B):
    """
    Registro de alertas activas.
    tipo_alerta: VAR_BREACH | DRAWDOWN | SELL_SIGNAL | AUDITORIA | ON_VENCIMIENTO
    """
    __tablename__ = "alertas_log"
    __table_args__ = (
        Index("ix_alerta_cliente", "cliente_id"),
        Index("ix_alerta_tipo", "tipo_alerta"),
        Index("ix_alerta_ts", "created_at"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id  = Column(Integer, nullable=True)
    tipo_alerta = Column(String(50), nullable=False)
    ticker      = Column(String(20), default="")
    mensaje     = Column(Text, nullable=False)
    enviada     = Column(Boolean, default=False)
    usuario     = Column(String(100), default="")
    tenant_id   = Column(String(200), nullable=False, default="default")
    created_at  = Column(DateTime, default=dt.datetime.utcnow)


class RecomendacionAuditoria(_B):
    """
    Registro de cada simulación / ejecución de recomendación de capital.
    evento: SIMULACION_RECOMENDACION | EJECUCION_CONFIRMADA | ...
    """
    __tablename__ = "recomendaciones_auditoria"
    __table_args__ = (
        Index("ix_recom_cliente", "cliente_id"),
        Index("ix_recom_evento", "evento"),
        Index("ix_recom_ts", "created_at"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    evento       = Column(String(80), nullable=False)
    origen       = Column(String(80), default="")
    cliente_id   = Column(Integer, nullable=True)
    cliente_nombre = Column(String(200), default="")
    capital_ars  = Column(Float, nullable=True)
    ccl          = Column(Float, nullable=True)
    perfil       = Column(String(50), default="")
    tickers_json = Column(Text, default="[]")    # JSON list de tickers recomendados
    pesos_json   = Column(Text, default="{}")    # JSON dict ticker→peso
    resultado_json = Column(Text, default="{}")  # JSON resumen de resultado
    usuario      = Column(String(100), default="")
    tenant_id    = Column(String(200), nullable=False, default="default")
    created_at   = Column(DateTime, default=dt.datetime.utcnow)


class OrdenCalculada(_B):
    """
    Orden pre-aprobada generada por el optimizador.
    estado: PENDIENTE | APROBADA | RECHAZADA | EJECUTADA
    """
    __tablename__ = "ordenes_calculadas"
    __table_args__ = (
        Index("ix_orden_cliente", "cliente_id"),
        Index("ix_orden_estado", "estado"),
    )

    id            = Column(Integer, primary_key=True, autoincrement=True)
    tipo          = Column(String(10), nullable=False)    # COMPRA | VENTA
    ticker        = Column(String(20), nullable=False)
    cantidad      = Column(Float, nullable=False)
    precio_ref    = Column(Float, nullable=True)
    monto_ars     = Column(Float, nullable=True)
    cliente_id    = Column(Integer, nullable=True)
    cartera       = Column(String(300), default="")
    motivo        = Column(Text, default="")
    estado        = Column(String(20), default="PENDIENTE")
    aprobado_por  = Column(String(100), default="")
    tenant_id     = Column(String(200), nullable=False, default="default")
    created_at    = Column(DateTime, default=dt.datetime.utcnow)
    updated_at    = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class PortfolioSnapshot(_B):
    """
    Snapshot periódico del estado de una cartera (valor, P&L, composición).
    """
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_snap_cliente_fecha", "cliente_id", "fecha"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id   = Column(Integer, nullable=False)
    cartera      = Column(String(300), nullable=False)
    fecha        = Column(DateTime, default=dt.datetime.utcnow)
    modelo       = Column(String(50), default="")
    valor_ars    = Column(Float, nullable=True)
    pnl_pct      = Column(Float, nullable=True)
    ccl          = Column(Float, nullable=True)
    posiciones_json = Column(Text, default="{}")
    tenant_id    = Column(String(200), nullable=False, default="default")


# ─── Inicializar ──────────────────────────────────────────────────────────────
AUDITORIA.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def registrar_alerta(
    tipo_alerta: str,
    mensaje: str,
    cliente_id: int | None = None,
    ticker: str = "",
    usuario: str = "",
    tenant_id: str = "default",
) -> int:
    """Persiste una alerta. Retorna el ID generado."""
    with AUDITORIA.session() as s:
        a = AlertaLog(
            tipo_alerta=tipo_alerta[:50],
            mensaje=mensaje,
            cliente_id=cliente_id,
            ticker=(ticker or "").upper().strip()[:20],
            usuario=(usuario or "")[:100],
            tenant_id=tenant_id,
        )
        s.add(a)
        s.flush()
        return a.id


def registrar_recomendacion(
    evento: str,
    cliente_id: int | None = None,
    cliente_nombre: str = "",
    capital_ars: float | None = None,
    ccl: float | None = None,
    perfil: str = "",
    tickers: list[str] | None = None,
    pesos: dict[str, float] | None = None,
    resultado: dict[str, Any] | None = None,
    usuario: str = "",
    origen: str = "",
    tenant_id: str = "default",
) -> int:
    """Registra un evento de recomendación/simulación."""
    with AUDITORIA.session() as s:
        r = RecomendacionAuditoria(
            evento=evento[:80],
            origen=origen[:80],
            cliente_id=cliente_id,
            cliente_nombre=(cliente_nombre or "")[:200],
            capital_ars=capital_ars,
            ccl=ccl,
            perfil=perfil[:50],
            tickers_json=json.dumps(tickers or [], ensure_ascii=False),
            pesos_json=json.dumps(pesos or {}, ensure_ascii=False),
            resultado_json=json.dumps(resultado or {}, ensure_ascii=False),
            usuario=(usuario or "")[:100],
            tenant_id=tenant_id,
        )
        s.add(r)
        s.flush()
        return r.id


def obtener_alertas_df(
    cliente_id: int | None = None,
    tenant_id: str = "default",
    limit: int = 100,
) -> pd.DataFrame:
    """Alertas recientes."""
    with AUDITORIA.session() as s:
        q = s.query(AlertaLog).filter(AlertaLog.tenant_id == tenant_id)
        if cliente_id is not None:
            q = q.filter(AlertaLog.cliente_id == cliente_id)
        rows = q.order_by(AlertaLog.created_at.desc()).limit(limit).all()
    if not rows:
        return pd.DataFrame(columns=["id", "tipo_alerta", "ticker", "mensaje", "created_at"])
    return pd.DataFrame([{
        "id": r.id, "cliente_id": r.cliente_id,
        "tipo_alerta": r.tipo_alerta, "ticker": r.ticker,
        "mensaje": r.mensaje, "enviada": r.enviada,
        "usuario": r.usuario, "created_at": r.created_at,
    } for r in rows])


def guardar_snapshot(
    cliente_id: int,
    cartera: str,
    valor_ars: float,
    pnl_pct: float,
    ccl: float,
    posiciones: dict[str, Any] | None = None,
    modelo: str = "",
    tenant_id: str = "default",
) -> int:
    with AUDITORIA.session() as s:
        snap = PortfolioSnapshot(
            cliente_id=cliente_id,
            cartera=cartera[:300],
            valor_ars=valor_ars,
            pnl_pct=pnl_pct,
            ccl=ccl,
            modelo=modelo[:50],
            posiciones_json=json.dumps(posiciones or {}, ensure_ascii=False),
            tenant_id=tenant_id,
        )
        s.add(snap)
        s.flush()
        return snap.id
