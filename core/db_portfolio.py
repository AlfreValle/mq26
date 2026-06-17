"""
core/db_portfolio.py — Dominio: Portfolio (Activos, Transacciones, Operaciones CSV)
DB: 0_Data_Maestra/db_portfolio.db

Tablas:
  activos                  — Universo de instrumentos (CEDEAR, ON, ETF, acción)
  transacciones            — Log de trades ORM (legacy + dss_master migrado)
  transaccional_operaciones — Espejo del CSV Maestra_Transaccional (fuente viva)

Esta es la tabla de datos más crítica del sistema. El CSV dual-write
queda deprecado: `transaccional_operaciones` es la fuente de verdad.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)

from core.db_domains import PORTFOLIO

# mypy: _B viene de SQLAlchemy declarative_base() (dinámico); Any lo hace válido como tipo base.
_B: Any = PORTFOLIO.Base


# ─── Modelos ──────────────────────────────────────────────────────────────────

class Activo(_B):
    """
    Universo de instrumentos. Uno por ticker_local.
    Mantiene ratio CEDEAR, metadata de renta fija, versión de universo.
    """
    __tablename__ = "activos"
    __table_args__ = (
        Index("ix_act_ticker", "ticker_local"),
        Index("ix_act_tipo", "tipo"),
    )

    id               = Column(Integer, primary_key=True, autoincrement=True)
    tipo             = Column(String(20), default="CEDEAR", nullable=False)
    ticker_local     = Column(String(20), nullable=False, unique=True)
    ticker_yf        = Column(String(30), nullable=False)
    nombre           = Column(String(200))
    ratio            = Column(Float, default=1.0)
    sector           = Column(String(100))
    pais             = Column(String(100), default="Estados Unidos")
    moneda           = Column(String(5), default="USD")
    activo           = Column(Boolean, default=True)
    universo_version = Column(Integer, default=1, nullable=False)
    # Renta fija (ON / bono)
    cupon_anual      = Column(Float, nullable=True)
    vencimiento      = Column(Date, nullable=True)
    valor_nominal    = Column(Float, nullable=True)
    calificacion     = Column(String(10), nullable=True)
    ley              = Column(String(20), nullable=True)
    lamina_min       = Column(Integer, nullable=True, default=1)
    updated_at       = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class Transaccion(_B):
    """
    Trade log ORM (formato dss_master legacy).
    Incluye FK lógicas (cliente_id, activo_id) sin FK SQL para aislamiento cross-domain.
    """
    __tablename__ = "transacciones"
    __table_args__ = (
        Index("ix_trans_cliente_fecha", "cliente_id", "fecha"),
        Index("ix_trans_ticker", "ticker_local"),
    )

    id                = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id        = Column(Integer, nullable=False)          # ref a db_clientes.clientes.id
    activo_id         = Column(Integer, nullable=True)           # ref a activos.id (mismo dominio)
    ticker_local      = Column(String(20), nullable=False)       # desnormalizado para queries directas
    cartera           = Column(String(300), nullable=False, default="")
    fecha             = Column(Date, nullable=False)
    tipo_op           = Column(String(10), nullable=False)       # COMPRA | VENTA
    nominales         = Column(Float, nullable=False)            # VN USD para ONs, unidades para CEDEAR
    precio_bruto_ars  = Column(Float, nullable=False)
    precio_usd        = Column(Float, default=0.0)              # PPC USD (paridad para ONs)
    comision_broker   = Column(Float, default=0.0)
    derechos_mercado  = Column(Float, default=0.0)
    iva               = Column(Float, default=0.0)
    total_neto_ars    = Column(Float, nullable=False)
    tipo_activo       = Column(String(40), default="CEDEAR")
    lamina_vn         = Column(Float, nullable=True)
    moneda_precio     = Column(String(20), default="ARS")
    notas             = Column(Text, default="")
    created_at        = Column(DateTime, default=dt.datetime.utcnow)


class TransaccionalOperacion(_B):
    """
    Fuente viva del portafolio — reemplaza al CSV Maestra_Transaccional.csv.
    Un registro por compra/venta en cartera.
    Convención de precio:
      - CEDEAR/Acción: precio_ars = ARS por 1 unidad CEDEAR
      - ON_USD       : precio_ars = ARS por 1 VN USD nominal
                       precio_usd = paridad% (ej. 1.025 = 102.5%)
    """
    __tablename__ = "transaccional_operaciones"
    __table_args__ = (
        Index("ix_transop_cartera_fecha", "cartera", "fecha_compra"),
        Index("ix_transop_ticker", "ticker"),
    )

    id            = Column(Integer, primary_key=True, autoincrement=True)
    cartera       = Column(String(300), nullable=False)
    fecha_compra  = Column(Date, nullable=False)
    ticker        = Column(String(30), nullable=False)
    cantidad      = Column(Float, nullable=False)           # unidades o VN USD
    ppc_usd       = Column(Float, nullable=False, default=0.0)
    ppc_ars       = Column(Float, nullable=False, default=0.0)
    tipo          = Column(String(40), nullable=False, default="CEDEAR")
    lamina_vn     = Column(Float, nullable=True)
    moneda_precio = Column(String(20), default="ARS")
    tenant_id     = Column(String(200), nullable=False, default="default")
    created_at    = Column(DateTime, default=dt.datetime.utcnow)


# ─── Inicializar ──────────────────────────────────────────────────────────────
PORTFOLIO.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def cargar_transaccional_df(cartera: str | None = None, tenant_id: str = "default") -> pd.DataFrame:
    """
    Carga transacciones desde `transaccional_operaciones`.
    Formato compatible con data_engine.cargar_transaccional().
    """
    with PORTFOLIO.session() as s:
        q = s.query(TransaccionalOperacion).filter(
            TransaccionalOperacion.tenant_id == tenant_id
        )
        if cartera:
            q = q.filter(TransaccionalOperacion.cartera == cartera)
        rows = q.order_by(TransaccionalOperacion.fecha_compra).all()

    if not rows:
        return pd.DataFrame(columns=[
            "CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD",
            "PPC_USD", "PPC_ARS", "TIPO", "LAMINA_VN", "MONEDA_PRECIO",
        ])
    return pd.DataFrame([{
        "CARTERA": r.cartera,
        "FECHA_COMPRA": str(r.fecha_compra),
        "TICKER": r.ticker.upper(),
        "CANTIDAD": r.cantidad,
        "PPC_USD": r.ppc_usd,
        "PPC_ARS": r.ppc_ars,
        "TIPO": r.tipo,
        "LAMINA_VN": r.lamina_vn,
        "MONEDA_PRECIO": r.moneda_precio or "",
    } for r in rows])


def registrar_operacion(
    cartera: str,
    fecha: dt.date,
    ticker: str,
    cantidad: float,
    ppc_ars: float,
    ppc_usd: float = 0.0,
    tipo: str = "CEDEAR",
    lamina_vn: float | None = None,
    moneda_precio: str = "ARS",
    tenant_id: str = "default",
) -> int:
    """Persiste una operación. Retorna el ID generado."""
    with PORTFOLIO.session() as s:
        op = TransaccionalOperacion(
            cartera=cartera.strip()[:300],
            fecha_compra=fecha,
            ticker=ticker.upper().strip()[:30],
            cantidad=cantidad,
            ppc_usd=ppc_usd,
            ppc_ars=ppc_ars,
            tipo=tipo,
            lamina_vn=lamina_vn,
            moneda_precio=moneda_precio,
            tenant_id=tenant_id,
        )
        s.add(op)
        s.flush()
        return op.id


def vaciar_cartera(cartera: str, tenant_id: str = "default") -> int:
    """Elimina todas las operaciones de una cartera. Retorna filas eliminadas."""
    with PORTFOLIO.session() as s:
        n = (
            s.query(TransaccionalOperacion)
            .filter(
                TransaccionalOperacion.cartera == cartera,
                TransaccionalOperacion.tenant_id == tenant_id,
            )
            .delete(synchronize_session=False)
        )
        return n


def upsert_activo(
    ticker_local: str,
    ticker_yf: str,
    tipo: str = "CEDEAR",
    nombre: str = "",
    ratio: float = 1.0,
    sector: str = "",
    pais: str = "Estados Unidos",
    moneda: str = "USD",
    lamina_min: int = 1,
    **extra: Any,
) -> int:
    """Inserta o actualiza un activo del universo. Retorna su ID."""
    tl = ticker_local.upper().strip()[:20]
    with PORTFOLIO.session() as s:
        row = s.query(Activo).filter(Activo.ticker_local == tl).first()
        if row:
            row.ticker_yf = ticker_yf
            row.tipo = tipo
            row.nombre = nombre or row.nombre
            row.ratio = ratio
            row.sector = sector or row.sector
            row.pais = pais
            row.moneda = moneda
            row.lamina_min = lamina_min
            row.universo_version = (row.universo_version or 0) + 1
            for k, v in extra.items():
                if hasattr(row, k):
                    setattr(row, k, v)
            s.flush()
            return row.id
        act = Activo(
            ticker_local=tl, ticker_yf=ticker_yf,
            tipo=tipo, nombre=nombre, ratio=ratio,
            sector=sector, pais=pais, moneda=moneda,
            lamina_min=lamina_min,
        )
        for k, v in extra.items():
            if hasattr(act, k):
                setattr(act, k, v)
        s.add(act)
        s.flush()
        return act.id


def obtener_activos_df() -> pd.DataFrame:
    """Universo completo de activos activos."""
    with PORTFOLIO.session() as s:
        rows = s.query(Activo).filter(Activo.activo == True).all()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "id": r.id, "tipo": r.tipo, "Ticker": r.ticker_local,
        "ticker_yf": r.ticker_yf, "Nombre": r.nombre,
        "Ratio": r.ratio, "Sector": r.sector,
        "Pais": r.pais, "Moneda": r.moneda,
        "lamina_min": r.lamina_min,
        "universo_version": r.universo_version,
    } for r in rows])


def importar_desde_csv(csv_path: str | Path, tenant_id: str = "default") -> int:
    """
    Importa operaciones desde Maestra_Transaccional.csv a transaccional_operaciones.
    Salta duplicados (misma cartera+fecha+ticker+cantidad+ppc_ars).
    Retorna número de filas importadas.
    """
    import datetime
    csv_p = Path(csv_path)
    if not csv_p.exists():
        return 0
    df = pd.read_csv(csv_p)
    required = {"CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD"}
    if not required.issubset(df.columns):
        return 0

    imported = 0
    with PORTFOLIO.session() as s:
        for _, row in df.iterrows():
            try:
                fecha_raw = str(row.get("FECHA_COMPRA", ""))
                fecha = datetime.date.fromisoformat(fecha_raw[:10])
                cartera = str(row.get("CARTERA", "")).strip()
                ticker = str(row.get("TICKER", "")).strip().upper()
                cantidad = float(row.get("CANTIDAD", 0) or 0)
                ppc_ars = float(row.get("PPC_ARS", 0) or 0)
                ppc_usd = float(row.get("PPC_USD", 0) or 0)
                tipo = str(row.get("TIPO", "CEDEAR") or "CEDEAR").strip()
                lamina = row.get("LAMINA_VN")
                lamina_vn = float(lamina) if lamina and str(lamina) not in ("nan","None","") else None
                moneda = str(row.get("MONEDA_PRECIO", "ARS") or "ARS").strip()
            except (ValueError, TypeError):
                continue

            # Dedup: buscar existente
            exists = (
                s.query(TransaccionalOperacion)
                .filter(
                    TransaccionalOperacion.cartera == cartera,
                    TransaccionalOperacion.fecha_compra == fecha,
                    TransaccionalOperacion.ticker == ticker,
                    TransaccionalOperacion.cantidad == cantidad,
                )
                .first()
            )
            if exists:
                continue

            s.add(TransaccionalOperacion(
                cartera=cartera, fecha_compra=fecha, ticker=ticker,
                cantidad=cantidad, ppc_usd=ppc_usd, ppc_ars=ppc_ars,
                tipo=tipo, lamina_vn=lamina_vn, moneda_precio=moneda,
                tenant_id=tenant_id,
            ))
            imported += 1

    return imported
