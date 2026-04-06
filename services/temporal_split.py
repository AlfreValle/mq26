"""
Partición temporal train / test para optimización in-sample y backtest OOS (Fase 0).
Referencias de código: risk_engine en 1_Scripts_Motor/, backtest en services/backtester.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TemporalSplitMeta:
    train_frac: float
    n_rows: int
    n_train: int
    n_test: int
    train_end: pd.Timestamp | None
    test_start: pd.Timestamp | None


@dataclass(frozen=True)
class WalkForwardWindowMeta:
    """Metadatos de una ventana walk-forward (D05)."""

    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def walk_forward_splits(
    precios: pd.DataFrame,
    *,
    train_rows: int = 252,
    test_rows: int = 21,
    step_rows: int = 21,
) -> list[tuple[pd.DataFrame, pd.DataFrame, WalkForwardWindowMeta]]:
    """
    Genera ventanas walk-forward: train y test sin solapamiento temporal dentro de cada ventana.

    - train_rows / test_rows: longitud en filas (días de negocio típicos).
    - step_rows: desplazamiento del inicio de cada ventana respecto a la anterior.
    """
    df = precios.sort_index().copy()
    df = df.dropna(how="all")
    n = len(df)
    out: list[tuple[pd.DataFrame, pd.DataFrame, WalkForwardWindowMeta]] = []
    need = train_rows + test_rows
    if need > n or step_rows <= 0:
        return out

    start = 0
    w = 0
    while start + need <= n:
        train = df.iloc[start : start + train_rows]
        test = df.iloc[start + train_rows : start + train_rows + test_rows]
        if train.index[-1] >= test.index[0]:
            raise ValueError("walk_forward_splits: fuga train→test detectada")
        meta = WalkForwardWindowMeta(
            index=w,
            train_start=train.index[0],
            train_end=train.index[-1],
            test_start=test.index[0],
            test_end=test.index[-1],
        )
        out.append((train, test, meta))
        start += step_rows
        w += 1
    return out


def split_precios_train_test(
    precios: pd.DataFrame,
    *,
    train_frac: float = 0.7,
    min_train_rows: int = 60,
    min_test_rows: int = 20,
) -> tuple[pd.DataFrame, pd.DataFrame, TemporalSplitMeta]:
    """
    Divide precios ordenados por fecha en tramo de entrenamiento y prueba.

    - train_frac: fracción de filas (0–1) asignadas al entrenamiento.
    - Si no hay filas suficientes para min_train_rows + min_test_rows, se devuelve
      todo en train y test vacío (el caller debe desactivar OOS).
    """
    df = precios.sort_index().copy()
    df = df.dropna(how="all")
    n = len(df)
    if n < min_train_rows + min_test_rows:
        meta = TemporalSplitMeta(
            train_frac=train_frac,
            n_rows=n,
            n_train=n,
            n_test=0,
            train_end=df.index[-1] if n else None,
            test_start=None,
        )
        return df, pd.DataFrame(columns=df.columns), meta

    n_train = max(min_train_rows, int(np.floor(n * train_frac)))
    n_train = min(n_train, n - min_test_rows)
    train = df.iloc[:n_train]
    test = df.iloc[n_train:]
    meta = TemporalSplitMeta(
        train_frac=train_frac,
        n_rows=n,
        n_train=len(train),
        n_test=len(test),
        train_end=train.index[-1],
        test_start=test.index[0],
    )
    return train, test, meta
