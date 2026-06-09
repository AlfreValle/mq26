"""
core/db_clientes.py — Dominio: Clientes & Objetivos de Inversión
DB: 0_Data_Maestra/db_clientes.db

Tablas:
  clientes            — Perfil de cada inversor (tenant-aware)
  objetivos_inversion — Metas de inversión por cliente

Sin FK hacia otros dominios; referencia cross-domain solo por cliente_id (int).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Index,
    Integer, String, Text, UniqueConstraint,
)

from core.db_domains import CLIENTES

_B = CLIENTES.Base


# ─── Modelos ──────────────────────────────────────────────────────────────────

class Cliente(_B):
    __tablename__ = "clientes"
    __table_args__ = (
        Index("ix_cli_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", "nombre", name="uq_cli_tenant_nombre"),
    )

    id              = Column(Integer, primary_key=True, autoincrement=True)
    nombre          = Column(String(200), nullable=False)
    perfil_riesgo   = Column(String(50), default="Moderado", nullable=False)
    horizonte_label = Column(String(30), default="1 año")
    capital_usd     = Column(Float, default=0.0)
    tipo_cliente    = Column(String(50), default="Persona")
    activo          = Column(Boolean, default=True)
    notas_asesor    = Column(Text, default="")
    tenant_id       = Column(String(200), nullable=False, default="default")
    created_at      = Column(DateTime, default=dt.datetime.utcnow)
    updated_at      = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class ObjetivosInversion(_B):
    __tablename__ = "objetivos_inversion"
    __table_args__ = (
        Index("ix_obj_cliente", "cliente_id"),
        Index("ix_obj_tenant", "tenant_id"),
    )

    id                = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id        = Column(Integer, nullable=False, index=True)   # ref a clientes.id (mismo dominio)
    ticker            = Column(String(20), default="")
    monto_ars         = Column(Float, default=0.0)
    plazo_label       = Column(String(30), default="1 año")
    plazo_dias        = Column(Integer, default=365)
    motivo            = Column(Text, default="")
    fecha_creacion    = Column(Date, default=dt.date.today)
    fecha_vencimiento = Column(Date, nullable=True)
    target_pct        = Column(Float, nullable=True)
    stop_pct          = Column(Float, nullable=True)
    estado            = Column(String(20), default="ACTIVO")   # ACTIVO | VENCIDO | COMPLETADO
    tenant_id         = Column(String(200), nullable=False, default="default")
    created_at        = Column(DateTime, default=dt.datetime.utcnow)


# ─── Inicializar tablas ────────────────────────────────────────────────────────
CLIENTES.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def registrar_cliente(
    nombre: str,
    perfil: str,
    capital_usd: float = 0.0,
    tipo: str = "Persona",
    horizonte: str = "1 año",
    tenant_id: str = "default",
    notas: str = "",
) -> int:
    """Inserta un nuevo cliente y retorna su ID."""
    with CLIENTES.session() as s:
        cli = Cliente(
            nombre=nombre.strip()[:200],
            perfil_riesgo=perfil,
            capital_usd=capital_usd,
            tipo_cliente=tipo,
            horizonte_label=horizonte,
            tenant_id=tenant_id,
            notas_asesor=notas,
        )
        s.add(cli)
        s.flush()
        return cli.id


def obtener_clientes_df(tenant_id: str = "default") -> "pd.DataFrame":
    """Lista de clientes activos del tenant como DataFrame."""
    import pandas as pd

    with CLIENTES.session() as s:
        rows = (
            s.query(Cliente)
            .filter(Cliente.tenant_id == tenant_id, Cliente.activo == True)
            .order_by(Cliente.nombre)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["ID", "Nombre", "Perfil", "Horizonte", "Capital_USD"])
        return pd.DataFrame([
            {
                "ID": r.id,
                "Nombre": r.nombre,
                "Perfil": r.perfil_riesgo,
                "Horizonte": r.horizonte_label,
                "Capital_USD": r.capital_usd,
                "Tipo": r.tipo_cliente,
                "Notas": r.notas_asesor or "",
                "tenant_id": r.tenant_id,
            }
            for r in rows
        ])


def actualizar_cliente(cliente_id: int, **kwargs) -> bool:
    """Actualiza campos de un cliente. Retorna True si encontrado."""
    _ALLOWED = {"nombre", "perfil_riesgo", "capital_usd", "horizonte_label",
                "tipo_cliente", "activo", "notas_asesor"}
    updates = {k: v for k, v in kwargs.items() if k in _ALLOWED}
    if not updates:
        return False
    with CLIENTES.session() as s:
        row = s.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not row:
            return False
        for k, v in updates.items():
            setattr(row, k, v)
        return True


def eliminar_cliente(cliente_id: int) -> bool:
    """Soft-delete: marca activo=False."""
    return actualizar_cliente(cliente_id, activo=False)


def registrar_objetivo(
    cliente_id: int,
    monto_ars: float,
    plazo_label: str = "1 año",
    ticker: str = "",
    motivo: str = "",
    tenant_id: str = "default",
) -> int:
    """Inserta un objetivo de inversión y retorna su ID."""
    import datetime as dt

    plazo_map = {
        "1 mes": 30, "3 meses": 90, "6 meses": 180,
        "1 año": 365, "3 años": 1095, "+5 años": 1825,
    }
    dias = plazo_map.get(plazo_label, 365)
    with CLIENTES.session() as s:
        obj = ObjetivosInversion(
            cliente_id=cliente_id,
            ticker=ticker.upper().strip()[:20],
            monto_ars=monto_ars,
            plazo_label=plazo_label,
            plazo_dias=dias,
            motivo=motivo,
            fecha_vencimiento=dt.date.today() + dt.timedelta(days=dias),
            tenant_id=tenant_id,
        )
        s.add(obj)
        s.flush()
        return obj.id


def obtener_objetivos_cliente(cliente_id: int) -> "pd.DataFrame":
    """Objetivos activos de un cliente."""
    import pandas as pd

    with CLIENTES.session() as s:
        rows = (
            s.query(ObjetivosInversion)
            .filter(
                ObjetivosInversion.cliente_id == cliente_id,
                ObjetivosInversion.estado == "ACTIVO",
            )
            .order_by(ObjetivosInversion.fecha_vencimiento)
            .all()
        )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame([{
            "id": r.id,
            "cliente_id": r.cliente_id,
            "ticker": r.ticker,
            "monto_ars": r.monto_ars,
            "plazo_label": r.plazo_label,
            "plazo_dias": r.plazo_dias,
            "motivo": r.motivo,
            "fecha_vencimiento": r.fecha_vencimiento,
            "estado": r.estado,
        } for r in rows])
