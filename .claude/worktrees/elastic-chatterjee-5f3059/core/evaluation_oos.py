"""
core/evaluation_oos.py — Train/test temporal y benchmarks (Fase 0: D43–D46).

No ejecuta backtest completo de broker: solo cortes temporales y métricas
sobre series de retornos ya calculadas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def temporal_train_test_split(
    returns: pd.DataFrame,
    train_fraction: float = 0.7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    D43–D44: separación temporal estricta (sin shuffle).
    returns: índice temporal ordenado.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction en (0,1)")
    n = len(returns)
    cut = max(int(n * train_fraction), 1)
    if cut >= n:
        cut = n - 1
    train = returns.iloc[:cut]
    test = returns.iloc[cut:]
    return train, test


def naive_one_over_n_weights(n: int) -> np.ndarray:
    """D46: benchmark 1/N."""
    if n <= 0:
        raise ValueError("n>0")
    return np.ones(n, dtype=float) / n


def portfolio_return_series(
    returns: pd.DataFrame,
    weights: dict[str, float] | np.ndarray,
    tickers: list[str] | None = None,
) -> pd.Series:
    """Retorno diario de cartera r_p = R @ w (mismas columnas ordenadas)."""
    if isinstance(weights, dict):
        tix = tickers or list(weights.keys())
        w = np.array([weights.get(t, 0.0) for t in tix], dtype=float)
    else:
        w = np.asarray(weights, dtype=float).ravel()
        tix = list(returns.columns[: len(w)])
    sub = returns[tix].dropna()
    if len(w) != len(tix):
        raise ValueError("len(weights) debe coincidir con tickers")
    s = w.sum()
    if s > 0:
        w = w / s
    r = sub.values @ w
    return pd.Series(r, index=sub.index)


def metrics_from_returns(
    r: pd.Series,
    *,
    periods_per_year: int = 252,
    rf_annual: float = 0.043,
) -> dict[str, float]:
    """
    D45: métricas estándar sobre retornos simples por periodo.
    """
    x = pd.to_numeric(r, errors="coerce").dropna()
    if len(x) < 2:
        return {
            "cagr": 0.0,
            "vol_ann": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_dd": 0.0,
            "skew": 0.0,
            "kurtosis_excess": 0.0,
        }
    rf_p = rf_annual / periods_per_year
    ex = x - rf_p
    vol = float(ex.std()) * np.sqrt(periods_per_year)
    mean_ann = float(x.mean()) * periods_per_year
    cagr = float((1 + x).prod() ** (periods_per_year / len(x)) - 1.0)
    sharpe = float(mean_ann - rf_annual) / vol if vol > 0 else 0.0
    downside = x[x < 0]
    dstd = float(downside.std()) * np.sqrt(periods_per_year) if len(downside) > 1 else 0.0
    sortino = float(mean_ann - rf_annual) / dstd if dstd > 0 else 0.0
    eq = (1 + x).cumprod()
    peak = eq.cummax()
    max_dd = float(((eq - peak) / peak).min())
    skew = float(x.skew())
    kurt = float(x.kurt())  # pandas: exceso
    return {
        "cagr": cagr,
        "vol_ann": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "skew": skew,
        "kurtosis_excess": kurt,
    }


def compare_to_naive_benchmark(
    returns: pd.DataFrame,
    w_opt: np.ndarray,
    tickers: list[str],
) -> dict[str, dict[str, float]]:
    """
    D46: compara métricas cartera optimizada vs 1/N en la misma ventana.
    """
    r_opt = portfolio_return_series(returns, w_opt, tickers)
    w_nv = naive_one_over_n_weights(len(tickers))
    r_nv = portfolio_return_series(returns, w_nv, tickers)
    return {
        "optimized": metrics_from_returns(r_opt),
        "naive_1n": metrics_from_returns(r_nv),
    }
