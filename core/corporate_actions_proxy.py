"""
C08 — Corporate Actions: detección proxy + registro confirmado de splits CEDEAR.

Dos funciones principales:
  1. SPLIT_REGISTRY      — registro histórico de splits CEDEAR confirmados (CNV/BYMA).
  2. detect_price_jumps() — detección heurística de saltos no confirmados (proxy).

Cuando CNV/BYMA publica un cambio de ratio, agregar una entrada a SPLIT_REGISTRY
y ejecutar el ajuste de posiciones con `ajustar_posiciones_por_split()`.

Convención de ratio: X CEDEARs = 1 acción subyacente.
  ratio=20  → necesitás 20 CEDEARs para tener 1 SPY
  ratio=0.2 → necesitás 0.2 CEDEARs para tener 1 HUT (1 CEDEAR = 5 HUT)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ─── Registro de splits confirmados ───────────────────────────────────────────

@dataclass(frozen=True)
class SplitEvent:
    """Un split / ajuste de ratio de CEDEAR confirmado por CNV/BYMA."""
    ticker:        str
    fecha:         dt.date       # fecha efectiva del ajuste
    ratio_viejo:   float         # ratio antes del split
    ratio_nuevo:   float         # ratio después del split
    fuente:        str = "CNV/BYMA"
    notas:         str = ""

    @property
    def factor(self) -> float:
        """Factor de ajuste de cantidad (ratio_nuevo / ratio_viejo)."""
        return self.ratio_nuevo / self.ratio_viejo if self.ratio_viejo else 1.0

    @property
    def tipo(self) -> str:
        if self.factor > 1:
            return f"SPLIT {self.factor:.0f}x"
        elif self.factor < 1:
            return f"CONSOLIDACIÓN 1:{1/self.factor:.0f}"
        return "SIN CAMBIO"


# ── Historial completo de splits CEDEAR confirmados ──────────────────────────
# Agregar una fila por cada evento. NO modificar filas existentes.
SPLIT_REGISTRY: list[SplitEvent] = [
    # ── Junio 2026 ──────────────────────────────────────────────────────────
    SplitEvent(
        ticker="SPY",
        fecha=dt.date(2026, 6, 1),
        ratio_viejo=20.0,
        ratio_nuevo=60.0,
        notas="Split 3x: ratio CEDEAR ajustado de 20:1 a 60:1 por CNV",
    ),
    SplitEvent(
        ticker="HUT",
        fecha=dt.date(2026, 6, 1),
        ratio_viejo=0.2,
        ratio_nuevo=5.0,
        notas="Split 25x: ratio CEDEAR ajustado de 0.2 a 5 por CNV",
    ),
    # ── Agregar splits futuros aquí ─────────────────────────────────────────
]


def splits_para_ticker(ticker: str) -> list[SplitEvent]:
    """Todos los splits de un ticker, ordenados por fecha ASC."""
    t = ticker.upper().strip()
    return sorted([s for s in SPLIT_REGISTRY if s.ticker == t], key=lambda s: s.fecha)


def factor_acumulado(ticker: str, desde: dt.date, hasta: dt.date | None = None) -> float:
    """
    Factor acumulado de ajuste de cantidad para un ticker entre dos fechas.

    Útil para ajustar retroactivamente precios históricos en gráficos.
    factor > 1 → más CEDEARs por el split (precio histórico debe dividirse).
    """
    t = ticker.upper().strip()
    hasta = hasta or dt.date.today()
    factor = 1.0
    for ev in splits_para_ticker(t):
        if desde <= ev.fecha <= hasta:
            factor *= ev.factor
    return factor


def resumen_splits_df() -> pd.DataFrame:
    """DataFrame con todos los splits registrados, ordenado por fecha desc."""
    if not SPLIT_REGISTRY:
        return pd.DataFrame(columns=["ticker", "fecha", "ratio_viejo", "ratio_nuevo", "factor", "tipo"])
    return pd.DataFrame([{
        "ticker":      ev.ticker,
        "fecha":       ev.fecha,
        "ratio_viejo": ev.ratio_viejo,
        "ratio_nuevo": ev.ratio_nuevo,
        "factor":      round(ev.factor, 4),
        "tipo":        ev.tipo,
        "fuente":      ev.fuente,
        "notas":       ev.notas,
    } for ev in sorted(SPLIT_REGISTRY, key=lambda e: e.fecha, reverse=True)])


@dataclass
class JumpReport:
    flagged_dates: list[pd.Timestamp] = field(default_factory=list)
    max_abs_move: float = 0.0
    threshold: float = 0.25


def detect_price_jumps(
    close: pd.Series,
    *,
    threshold: float = 0.25,
) -> JumpReport:
    """
    Marca días con |r_t| > threshold en retornos simples.

    ``threshold`` en decimal (0.25 = 25%).
    """
    s = close.astype(float).dropna()
    if len(s) < 2:
        return JumpReport(threshold=threshold)
    r = s.pct_change().dropna()
    flagged = r.index[np.abs(r.values) > threshold].tolist()
    mx = float(np.max(np.abs(r.values))) if len(r) else 0.0
    return JumpReport(
        flagged_dates=list(flagged),
        max_abs_move=mx,
        threshold=threshold,
    )
