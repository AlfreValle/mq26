"""
core/evaluation_oos.py — Train/test temporal, benchmarks y backtesting rolling (D43–D46, A14).

No ejecuta backtest completo de broker: solo cortes temporales y métricas
sobre series de retornos ya calculadas.

Backtesting rolling walk-forward (A14):
  rolling_oos_backtest() implementa una ventana deslizante (sliding) o expandida
  (anchored). En cada paso:
    1. Estima μ y Σ en la ventana de entrenamiento.
    2. Optimiza pesos con optimizer_fn (cualquier solver de portfolio_optimization).
    3. Aplica los pesos al período OOS siguiente.
    4. Calcula métricas IS y OOS por ventana.
  Agrega métricas en RollingOOSResult + degeneración IS→OOS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

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


# ─── Rolling OOS backtest (A14) ───────────────────────────────────────────────

@dataclass
class VentanaOOS:
    """Resultado de una ventana individual del rolling backtest."""
    idx_ventana:        int
    fecha_inicio_train: Any   # pd.Timestamp
    fecha_fin_train:    Any
    fecha_inicio_oos:   Any
    fecha_fin_oos:      Any
    n_dias_train:       int
    n_dias_oos:         int
    weights:            dict[str, float]
    metricas_is:        dict[str, float]
    metricas_oos:       dict[str, float]
    optimizer_success:  bool
    optimizer_method:   str = ""


@dataclass
class RollingOOSResult:
    """
    Resultado agregado del rolling walk-forward backtest.

    ventanas                 : lista de VentanaOOS (una por paso)
    retornos_oos             : serie concatenada de retornos OOS reales
    metricas_agregadas       : métricas sobre toda la serie OOS
    degradacion_is_oos       : {metrica: IS_media - OOS_media}
                               positivo = IS > OOS (sobreajuste)
    n_ventanas_exitosas      : ventanas donde el optimizer convergió
    """
    ventanas:            list[VentanaOOS]
    retornos_oos:        pd.Series
    metricas_agregadas:  dict[str, float]
    degradacion_is_oos:  dict[str, float]
    n_ventanas_exitosas: int
    tickers:             list[str] = field(default_factory=list)
    params:              dict[str, Any] = field(default_factory=dict)


def rolling_oos_backtest(
    returns: pd.DataFrame,
    optimizer_fn: Callable,
    *,
    window_train: int = 252,
    window_oos: int = 63,
    step: int = 21,
    anchored: bool = False,
    rf_annual: float = 0.043,
    cvar_max: float | None = None,
    cvar_alpha: float = 0.05,
    annualization: int = 252,
    **optimizer_kwargs: Any,
) -> RollingOOSResult:
    """
    Walk-forward rolling backtest (A14).

    Parámetros
    ----------
    returns       : DataFrame (T×n) de retornos simples diarios, columnas = tickers.
    optimizer_fn  : callable que recibe OptimizationProblem → OptimizationResult.
                    Ejemplos: solve_max_sharpe, solve_minimum_variance, solve_equal_risk_contribution.
    window_train  : días de entrenamiento por ventana (default 252 = 1 año).
    window_oos    : días de evaluación OOS por ventana (default 63 = 1 trimestre).
    step          : días de avance entre ventanas (default 21 = mensual).
    anchored      : si True, la ventana de train crece (expanding); si False, ventana fija (sliding).
    rf_annual     : tasa libre de riesgo anual para métricas Sharpe/Sortino.
    cvar_max      : si se especifica, pasa restricción CVaR al OptimizationProblem.
    cvar_alpha    : nivel de cola para CVaR (default 0.05).
    annualization : factor de anualización de retornos (default 252).
    **optimizer_kwargs : kwargs adicionales pasados a optimizer_fn.

    Retorna
    -------
    RollingOOSResult con ventanas individuales, serie OOS y métricas agregadas.
    """
    from core.portfolio_optimization import OptimizationProblem, estimate_mu_sigma_mle  # noqa: PLC0415

    returns = returns.dropna(axis=0, how="any")
    tickers = list(returns.columns)
    T = len(returns)

    if T < window_train + window_oos:
        raise ValueError(
            f"Serie insuficiente: T={T} < window_train+window_oos={window_train + window_oos}"
        )

    ventanas: list[VentanaOOS] = []
    oos_series_parts: list[pd.Series] = []
    idx_ventana = 0

    start = 0
    while True:
        train_end = start + window_train
        oos_end   = train_end + window_oos
        if oos_end > T:
            break

        # ── Selección de ventanas ─────────────────────────────────────────────
        train_slice = returns.iloc[start:train_end] if not anchored else returns.iloc[0:train_end]
        oos_slice   = returns.iloc[train_end:oos_end]

        R_train = train_slice.values  # (T_train, n)

        # ── Estimación μ y Σ ─────────────────────────────────────────────────
        try:
            mu, Sigma = estimate_mu_sigma_mle(R_train, annualization=annualization)
        except Exception:
            # Fallback si Ledoit-Wolf falla (pocas obs)
            mu = R_train.mean(axis=0) * annualization
            Sigma = np.cov(R_train.T, bias=False) * annualization + 1e-6 * np.eye(len(tickers))

        prob = OptimizationProblem(
            mu=mu,
            Sigma=Sigma,
            rf=rf_annual,
            long_only=True,
            cvar_max=cvar_max,
            returns_history=R_train if cvar_max is not None else None,
            cvar_alpha=cvar_alpha,
        )

        # ── Optimización ─────────────────────────────────────────────────────
        try:
            opt_result = optimizer_fn(prob, **optimizer_kwargs)
            w = opt_result.weights
            success = bool(opt_result.success)
            method  = opt_result.method
        except Exception:
            w = naive_one_over_n_weights(len(tickers))
            success = False
            method  = "fallback_1n"

        weights_dict = {t: float(w[i]) for i, t in enumerate(tickers)}

        # ── Métricas IS (in-sample) ───────────────────────────────────────────
        r_is  = portfolio_return_series(train_slice, weights_dict, tickers)
        m_is  = metrics_from_returns(r_is, periods_per_year=annualization, rf_annual=rf_annual)

        # ── Métricas OOS (out-of-sample) ─────────────────────────────────────
        r_oos = portfolio_return_series(oos_slice, weights_dict, tickers)
        m_oos = metrics_from_returns(r_oos, periods_per_year=annualization, rf_annual=rf_annual)

        oos_series_parts.append(r_oos)

        ventanas.append(VentanaOOS(
            idx_ventana        = idx_ventana,
            fecha_inicio_train = train_slice.index[0],
            fecha_fin_train    = train_slice.index[-1],
            fecha_inicio_oos   = oos_slice.index[0],
            fecha_fin_oos      = oos_slice.index[-1],
            n_dias_train       = len(train_slice),
            n_dias_oos         = len(oos_slice),
            weights            = weights_dict,
            metricas_is        = m_is,
            metricas_oos       = m_oos,
            optimizer_success  = success,
            optimizer_method   = method,
        ))

        idx_ventana += 1
        start += step

    if not ventanas:
        raise ValueError("No se generó ninguna ventana. Revisa window_train, window_oos y step.")

    # ── Concatenar retornos OOS y calcular métricas globales ─────────────────
    retornos_oos = pd.concat(oos_series_parts).sort_index()
    metricas_agregadas = metrics_from_returns(
        retornos_oos, periods_per_year=annualization, rf_annual=rf_annual,
    )

    # ── Degradación IS→OOS (sobreajuste) ─────────────────────────────────────
    metricas_keys = list(ventanas[0].metricas_is.keys())
    degradacion: dict[str, float] = {}
    for k in metricas_keys:
        is_vals  = [v.metricas_is.get(k, 0.0)  for v in ventanas]
        oos_vals = [v.metricas_oos.get(k, 0.0) for v in ventanas]
        degradacion[k] = float(np.mean(is_vals) - np.mean(oos_vals))

    n_exitosas = sum(1 for v in ventanas if v.optimizer_success)

    return RollingOOSResult(
        ventanas            = ventanas,
        retornos_oos        = retornos_oos,
        metricas_agregadas  = metricas_agregadas,
        degradacion_is_oos  = degradacion,
        n_ventanas_exitosas = n_exitosas,
        tickers             = tickers,
        params              = {
            "window_train": window_train,
            "window_oos":   window_oos,
            "step":         step,
            "anchored":     anchored,
            "cvar_max":     cvar_max,
            "cvar_alpha":   cvar_alpha,
            "n_ventanas":   len(ventanas),
        },
    )


def resumen_rolling(result: RollingOOSResult) -> dict[str, Any]:
    """
    Tabla resumen del rolling backtest para mostrar en UI o logs.

    Retorna dict con métricas OOS globales + degradación IS→OOS +
    porcentaje de ventanas donde el optimizer convergió.
    """
    out: dict[str, Any] = {
        **{f"oos_{k}": v for k, v in result.metricas_agregadas.items()},
        **{f"deg_{k}": v for k, v in result.degradacion_is_oos.items()},
        "n_ventanas":          result.params.get("n_ventanas", len(result.ventanas)),
        "n_ventanas_exitosas": result.n_ventanas_exitosas,
        "pct_exitosas":        (
            result.n_ventanas_exitosas / max(len(result.ventanas), 1)
        ),
    }
    return out
