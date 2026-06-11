"""
core/db_mercado.py — Dominio: Datos de Mercado
DB: 0_Data_Maestra/db_mercado.db

Tablas:
  precios_fallback   — Precios de rescate persistidos (sobreviven reinicios)
  scores_historicos  — Scores MOD-23 diarios por ticker

Sin FK hacia otros dominios.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from core.db_domains import MERCADO

_B: Any = MERCADO.Base  # mypy: alias dinámico SQLAlchemy
# ─── Modelos ──────────────────────────────────────────────────────────────────

class PrecioFallback(_B):
    """
    Precio ARS por unidad para tickers que no tienen cotización live.
    Persiste entre reinicios para evitar que P&L muestre -100%.
    """
    __tablename__ = "precios_fallback"
    __table_args__ = (
        Index("ix_pfb_ticker", "ticker"),
    )

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    ticker              = Column(String(20), nullable=False, unique=True)
    precio_ars          = Column(Float, nullable=False)
    fuente              = Column(String(50), default="manual")
    fecha_actualizacion = Column(Date, default=dt.date.today)
    updated_at          = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class ScoreHistorico(_B):
    """
    Score diario MOD-23 por ticker (técnico + fundamental + total).
    Un registro por ticker + fecha (upsert).
    """
    __tablename__ = "scores_historicos"
    __table_args__ = (
        UniqueConstraint("ticker", "fecha", name="uq_score_ticker_fecha"),
        Index("ix_score_ticker", "ticker"),
        Index("ix_score_fecha", "fecha"),
    )

    id                = Column(Integer, primary_key=True, autoincrement=True)
    ticker            = Column(String(20), nullable=False)
    fecha             = Column(Date, nullable=False)
    score_tecnico     = Column(Float)
    score_fundamental = Column(Float)
    score_total       = Column(Float)
    created_at        = Column(DateTime, default=dt.datetime.utcnow)


# ─── Inicializar ──────────────────────────────────────────────────────────────
MERCADO.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def guardar_precio_fallback(ticker: str, precio_ars: float, fuente: str = "live") -> None:
    """Persiste o actualiza el precio fallback de un ticker."""
    t = ticker.upper().strip()[:20]
    with MERCADO.session() as s:
        row = s.query(PrecioFallback).filter(PrecioFallback.ticker == t).first()
        if row:
            row.precio_ars = precio_ars
            row.fuente = fuente
            row.fecha_actualizacion = dt.date.today()
        else:
            s.add(PrecioFallback(ticker=t, precio_ars=precio_ars, fuente=fuente))


def obtener_precios_fallback() -> dict[str, float]:
    """Todos los precios fallback persistidos → {ticker: precio_ars}."""
    with MERCADO.session() as s:
        rows = s.query(PrecioFallback).all()
        return {r.ticker: r.precio_ars for r in rows}


def upsert_score(
    ticker: str,
    fecha: dt.date,
    score_tecnico: float,
    score_fundamental: float,
    score_total: float,
) -> None:
    """Inserta o actualiza el score del día para un ticker."""
    t = ticker.upper().strip()[:20]
    with MERCADO.session() as s:
        row = (
            s.query(ScoreHistorico)
            .filter(ScoreHistorico.ticker == t, ScoreHistorico.fecha == fecha)
            .first()
        )
        if row:
            row.score_tecnico = score_tecnico
            row.score_fundamental = score_fundamental
            row.score_total = score_total
        else:
            s.add(ScoreHistorico(
                ticker=t, fecha=fecha,
                score_tecnico=score_tecnico,
                score_fundamental=score_fundamental,
                score_total=score_total,
            ))


def obtener_scores_df(tickers: list[str] | None = None, dias: int = 30) -> pd.DataFrame:
    """Scores históricos de los últimos N días. Filtrar por tickers si se pasa lista."""
    desde = dt.date.today() - dt.timedelta(days=dias)
    with MERCADO.session() as s:
        q = s.query(ScoreHistorico).filter(ScoreHistorico.fecha >= desde)
        if tickers:
            tickers_up = [t.upper().strip() for t in tickers]
            q = q.filter(ScoreHistorico.ticker.in_(tickers_up))
        rows = q.order_by(ScoreHistorico.ticker, ScoreHistorico.fecha.desc()).all()
    if not rows:
        return pd.DataFrame(columns=["ticker", "fecha", "score_tecnico", "score_fundamental", "score_total"])
    return pd.DataFrame([{
        "ticker": r.ticker, "fecha": r.fecha,
        "score_tecnico": r.score_tecnico,
        "score_fundamental": r.score_fundamental,
        "score_total": r.score_total,
    } for r in rows])
