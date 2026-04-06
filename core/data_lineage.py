"""
core/data_lineage.py — Catálogo y validación de datos (Fase 0: C31–C33).

Sin I/O de red aquí: solo metadatos y funciones puras sobre DataFrames.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DatasetDescriptor:
    """C31: identidad mínima de un dataset usado en optimización/backtest."""
    id: str
    fuente: str
    frecuencia: str
    timezone: str
    descripcion: str
    ultima_revision_doc: str = "manual"


# Catálogo curado (ampliar según integraciones reales)
DATA_CATALOG: dict[str, DatasetDescriptor] = {
    "yfinance_eod": DatasetDescriptor(
        id="yfinance_eod",
        fuente="Yahoo Finance (no oficial, delay)",
        frecuencia="1d",
        timezone="America/New_York",
        descripcion="Cierres ajustados EOD para retornos de activos y benchmark",
        ultima_revision_doc="2026-03",
    ),
    "byma_ratios_interno": DatasetDescriptor(
        id="byma_ratios_interno",
        fuente="Universo Excel / config.RATIOS_CEDEAR / Supabase activos",
        frecuencia="ad_hoc",
        timezone="America/Argentina/Buenos_Aires",
        descripcion="Ratios CEDEAR para pasar de subyacente a certificado",
        ultima_revision_doc="2026-03",
    ),
}


def validate_returns_na(
    returns: pd.DataFrame,
    *,
    max_na_fraction_per_column: float = 0.05,
) -> tuple[bool, list[str]]:
    """
    C32: rechaza columnas con demasiados NA (después de dropna por fila según uso).
    """
    issues: list[str] = []
    for col in returns.columns:
        na_pct = float(returns[col].isna().mean())
        if na_pct > max_na_fraction_per_column:
            issues.append(f"{col}: {na_pct:.1%} NA > {max_na_fraction_per_column:.1%}")
    return (len(issues) == 0, issues)


def align_calendar_hint(df_ny: pd.DataFrame, df_local: pd.DataFrame) -> dict[str, Any]:
    """
    C33: documenta alineación NY vs BYMA — aquí solo compara índices (fechas).

    El caller debe decidir: inner join, ffill solo en fines de semana, etc.
    """
    idx_ny = pd.DatetimeIndex(pd.to_datetime(df_ny.index))
    idx_loc = pd.DatetimeIndex(pd.to_datetime(df_local.index))
    inter = idx_ny.intersection(idx_loc)
    return {
        "ny_rows": len(idx_ny),
        "local_rows": len(idx_loc),
        "intersection": len(inter),
        "ny_only": int(len(idx_ny.difference(idx_loc))),
        "local_only": int(len(idx_loc.difference(idx_ny))),
    }
