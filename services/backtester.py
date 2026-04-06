"""
backtester.py — Backtesting Vectorizado vs Benchmark
MQ26 + DSS Unificado
Genera equity curve, alpha acumulado, métricas Sharpe/Sortino/Max DD
"""
import datetime as _dt_bt
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

_CACHE_DIR = Path(__file__).resolve().parent.parent / "0_Data_Maestra" / ".bench_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _bench_cache_path(ticker: str, period: str) -> Path:
    return _CACHE_DIR / f"{ticker}_{period}.pkl"


def _load_bench_cache(ticker: str, period: str) -> pd.Series | None:
    """D3: Carga caché de benchmark con invalidación por fecha (expira cada día)."""
    p = _bench_cache_path(ticker, period)
    if p.exists():
        try:
            # D3: Verificar que el cache es de hoy
            mtime = _dt_bt.datetime.fromtimestamp(p.stat().st_mtime).date()
            if mtime < _dt_bt.date.today():
                p.unlink(missing_ok=True)  # Expirado: eliminar
                return None
            with open(p, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return None


def _save_bench_cache(ticker: str, period: str, serie: pd.Series) -> None:
    try:
        with open(_bench_cache_path(ticker, period), "wb") as f:
            pickle.dump(serie, f)
    except Exception:
        pass


@dataclass
class BacktestResult:
    fechas:                   list
    equity_strategy:          np.ndarray
    equity_benchmark:         np.ndarray
    alpha_acumulado:          np.ndarray
    retorno_anual_estrategia: float
    retorno_anual_benchmark:  float
    sharpe_estrategia:        float
    sharpe_benchmark:         float
    sortino_estrategia:       float
    max_dd_estrategia:        float
    max_dd_benchmark:         float
    calmar_estrategia:        float
    information_ratio:        float = field(default=0.0)
    beta_vs_benchmark:        float = field(default=1.0)
    correlacion_benchmark:    float = field(default=1.0)
    tickers_usados:           list[str] = field(default_factory=list)
    modelo:                   str = field(default="")
    periodo:                  str = field(default="")
    bench_fallback_usado:     bool = field(default=False)
    volatilidad_anual_estrategia: float = field(default=0.0)
    skew_retornos_estrategia: float = field(default=0.0)
    kurtosis_retornos_estrategia: float = field(default=0.0)
    sharpe_1n: float = field(default=0.0)
    retorno_anual_1n: float = field(default=0.0)
    sharpe_spy: float = field(default=0.0)
    alpha_vs_spy: float = field(default=0.0)

    def oos_report(self) -> dict[str, float]:
        """D03: métricas OOS comparables en un solo dict."""
        return {
            "cagr_estrategia": float(self.retorno_anual_estrategia),
            "vol_anual_estrategia": float(self.volatilidad_anual_estrategia),
            "sharpe_estrategia": float(self.sharpe_estrategia),
            "sortino_estrategia": float(self.sortino_estrategia),
            "max_dd_estrategia": float(self.max_dd_estrategia),
            "skew_retornos_estrategia": float(self.skew_retornos_estrategia),
            "kurtosis_retornos_estrategia": float(self.kurtosis_retornos_estrategia),
            "sharpe_spy": float(self.sharpe_spy),
            "sharpe_1n": float(self.sharpe_1n),
            "alpha_vs_spy": float(self.alpha_vs_spy),
            "retorno_anual_benchmark": float(self.retorno_anual_benchmark),
        }


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min())


def _to_series(x) -> pd.Series:
    """Normaliza cualquier entrada a pd.Series 1D."""
    if isinstance(x, pd.DataFrame):
        return x.iloc[:, 0]
    return pd.Series(x) if not isinstance(x, pd.Series) else x


def _sharpe(retornos_diarios, rf_diario: float = 0.0) -> float:
    s = _to_series(retornos_diarios)
    exceso = s - rf_diario
    std = float(exceso.std())
    return float((exceso.mean() / std) * np.sqrt(252)) if std > 0 else 0.0


def _sortino(retornos_diarios, rf_diario: float = 0.0) -> float:
    s = _to_series(retornos_diarios)
    exceso = s - rf_diario
    downside = float(exceso[exceso < 0].std())
    return float((exceso.mean() / downside) * np.sqrt(252)) if downside > 0 else 0.0


def _rebalanced_portfolio_returns(
    retornos: pd.DataFrame,
    w: np.ndarray,
    *,
    rebalanceo_mensual: bool,
    costo_rebalanceo_pct: float,
) -> pd.Series:
    """Retornos diarios de cartera con pesos objetivo w (rebalanceo mensual opcional)."""
    w = np.asarray(w, dtype=float)
    if w.size == 0:
        return pd.Series(dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(w)) / len(w)
    else:
        w = w / w.sum()

    if not rebalanceo_mensual:
        return (retornos @ w).dropna()

    meses = retornos.resample("MS").first().index
    ret_strat_series = pd.Series(index=retornos.index, dtype=float)
    w_actual = w.copy()

    for i, inicio_mes in enumerate(meses):
        fin_mes = meses[i + 1] if i + 1 < len(meses) else retornos.index[-1]
        mask = (retornos.index >= inicio_mes) & (retornos.index <= fin_mes)
        ret_mes = retornos.loc[mask]
        ret_dia = ret_mes.values @ w

        if len(ret_dia) > 0 and i > 0:
            turnover = float(np.sum(np.abs(w - w_actual)) / 2.0)
            costo_real = turnover * costo_rebalanceo_pct
            ret_dia = ret_dia.copy()
            ret_dia[0] -= costo_real

        ret_strat_series.loc[mask] = ret_dia

        if len(ret_mes) > 0:
            ret_mes_vals = ret_mes.values
            cum_ret = np.prod(1 + ret_mes_vals, axis=0)
            w_derivado = w * cum_ret
            total_d = w_derivado.sum()
            w_actual = w_derivado / total_d if total_d > 0 else w.copy()

    return ret_strat_series.dropna()


def run_backtest(
    precios: pd.DataFrame,
    pesos: dict,
    benchmark_ticker: str = "SPY",
    rf_anual: float = 0.043,
    periodo_label: str = "1y",
    modelo: str = "Sharpe",
    rebalanceo_mensual: bool = True,
    costo_rebalanceo_pct: float = 0.006,
) -> BacktestResult | None:
    """
    Backtest vectorizado con rebalanceo mensual opcional.
    - precios: DataFrame de precios ajustados (columnas = tickers)
    - pesos: dict {ticker: peso} normalizado
    - benchmark: SPY por defecto
    - costo_rebalanceo_pct: costo total estimado por rebalanceo (comisión + spread).
      Se aplica como reducción del retorno en cada inicio de mes donde se rebalancea.
    """
    if precios.empty or not pesos:
        return None

    tickers = [t for t in pesos if t in precios.columns]
    if not tickers:
        return None

    precios_strat = precios[tickers].dropna(how="all").ffill().bfill()
    retornos = precios_strat.pct_change().dropna()

    w = np.array([pesos.get(t, 0.0) for t in tickers])
    w = w / w.sum() if w.sum() > 0 else np.ones(len(tickers)) / len(tickers)
    w_1n = np.ones(len(tickers)) / len(tickers)

    rf_diario = rf_anual / 252

    ret_strat_series = _rebalanced_portfolio_returns(
        retornos, w,
        rebalanceo_mensual=rebalanceo_mensual,
        costo_rebalanceo_pct=costo_rebalanceo_pct,
    )
    ret_1n_series = _rebalanced_portfolio_returns(
        retornos, w_1n,
        rebalanceo_mensual=rebalanceo_mensual,
        costo_rebalanceo_pct=costo_rebalanceo_pct,
    )

    # ── Benchmark ──────────────────────────────────────────────────────────────
    bench_fallback_usado = False
    try:
        raw_bench = yf.download(benchmark_ticker, period=periodo_label,
                                 auto_adjust=True, progress=False)
        close_col = raw_bench["Close"]
        if isinstance(close_col, pd.DataFrame):
            close_col = close_col.squeeze()
        bench_ret = close_col.pct_change().dropna()
        if isinstance(bench_ret, pd.DataFrame):
            bench_ret = bench_ret.iloc[:, 0]
        idx_comun = ret_strat_series.index.intersection(bench_ret.index)
        if len(idx_comun) < 10:
            raise ValueError("Pocos datos en benchmark")
        ret_strat_series = ret_strat_series.loc[idx_comun]
        ret_1n_series = ret_1n_series.loc[idx_comun]
        bench_ret = bench_ret.loc[idx_comun]
        _save_bench_cache(benchmark_ticker, periodo_label, bench_ret)
    except Exception:
        cached = _load_bench_cache(benchmark_ticker, periodo_label)
        if cached is not None:
            idx_comun = ret_strat_series.index.intersection(cached.index)
            if len(idx_comun) >= 10:
                ret_strat_series = ret_strat_series.loc[idx_comun]
                ret_1n_series = ret_1n_series.loc[idx_comun]
                bench_ret = cached.loc[idx_comun]
                bench_fallback_usado = True
            else:
                bench_ret = pd.Series(0.0, index=ret_strat_series.index)
                bench_fallback_usado = True
        else:
            bench_ret = pd.Series(0.0, index=ret_strat_series.index)
            bench_fallback_usado = True

    idx_ok = (
        ret_strat_series.index.intersection(ret_1n_series.index).intersection(bench_ret.index)
    )
    if len(idx_ok) == 0:
        return None
    ret_strat_series = ret_strat_series.loc[idx_ok]
    ret_1n_series = ret_1n_series.loc[idx_ok]
    bench_ret = bench_ret.loc[idx_ok]

    # ── Equity curves ──────────────────────────────────────────────────────────
    eq_strat = np.cumprod(1 + ret_strat_series.values)
    eq_bench = np.cumprod(1 + bench_ret.values)
    # Alpha relativo estándar GIPS (B5): eq_strat/eq_bench - 1
    alpha_ac = eq_strat / np.maximum(eq_bench, 1e-10) - 1.0

    n_dias = len(eq_strat)
    ret_anual_strat  = (eq_strat[-1] ** (252 / n_dias) - 1) if n_dias > 0 else 0.0
    ret_anual_bench  = (eq_bench[-1] ** (252 / n_dias) - 1) if n_dias > 0 else 0.0

    eq_1n = np.cumprod(1 + ret_1n_series.values)
    ret_anual_1n = (eq_1n[-1] ** (252 / n_dias) - 1) if n_dias > 0 else 0.0
    sharpe_1n = _sharpe(ret_1n_series, rf_diario)

    vol_ann = float(ret_strat_series.std() * np.sqrt(252)) if n_dias > 1 else 0.0
    skew_s = float(ret_strat_series.skew()) if n_dias > 2 else 0.0
    kurt_s = float(ret_strat_series.kurtosis()) if n_dias > 3 else 0.0

    max_dd_s = _max_drawdown(eq_strat)
    max_dd_b = _max_drawdown(eq_bench)
    sharpe_s = _sharpe(ret_strat_series, rf_diario)
    sharpe_b = _sharpe(bench_ret, rf_diario)
    sortino_s = _sortino(ret_strat_series, rf_diario)
    calmar_s = ret_anual_strat / abs(max_dd_s) if max_dd_s != 0 else 0.0

    # Information Ratio y Beta (B4)
    diff_ret = ret_strat_series.values - bench_ret.values
    tracking_error = float(diff_ret.std() * np.sqrt(252))
    alpha_anualizado = ret_anual_strat - ret_anual_bench
    ir = alpha_anualizado / tracking_error if tracking_error > 0 else 0.0

    bench_var = float(bench_ret.var())
    beta = float(np.cov(ret_strat_series.values, bench_ret.values)[0, 1] / bench_var) if bench_var > 0 else 1.0

    rs = ret_strat_series.values
    rb = bench_ret.values
    corr = float(np.corrcoef(rs, rb)[0, 1]) if len(rs) > 2 else 0.0

    return BacktestResult(
        fechas=ret_strat_series.index.tolist(),
        equity_strategy=eq_strat,
        equity_benchmark=eq_bench,
        alpha_acumulado=alpha_ac,
        retorno_anual_estrategia=ret_anual_strat,
        retorno_anual_benchmark=ret_anual_bench,
        sharpe_estrategia=sharpe_s,
        sharpe_benchmark=sharpe_b,
        sortino_estrategia=sortino_s,
        max_dd_estrategia=max_dd_s,
        max_dd_benchmark=max_dd_b,
        calmar_estrategia=calmar_s,
        information_ratio=round(ir, 3),
        beta_vs_benchmark=round(beta, 3),
        correlacion_benchmark=round(corr, 3),
        tickers_usados=tickers,
        modelo=modelo,
        periodo=periodo_label,
        bench_fallback_usado=bench_fallback_usado,
        volatilidad_anual_estrategia=vol_ann,
        skew_retornos_estrategia=skew_s,
        kurtosis_retornos_estrategia=kurt_s,
        sharpe_1n=sharpe_1n,
        retorno_anual_1n=ret_anual_1n,
        sharpe_spy=sharpe_b,
        alpha_vs_spy=alpha_anualizado,
    )


MODELOS_DISPONIBLES = [
    "min_var", "max_sharpe", "sortino", "cvar", "kelly", "paridad_riesgo", "hrp", "erc",
]


def run_backtest_multimodelo(
    precios: pd.DataFrame,
    modelos_pesos: dict[str, dict[str, float]],
    *,
    period: str = "2y",
    train_frac: float = 0.7,
) -> dict[str, BacktestResult]:
    """
    Ejecuta backtest para múltiples modelos usando pesos ya calculados.

    Nota: `train_frac` se conserva por contrato para integraciones UI.
    """
    _ = train_frac
    out: dict[str, BacktestResult] = {}
    for modelo, pesos in modelos_pesos.items():
        try:
            res = run_backtest(precios, pesos, periodo_label=period, modelo=modelo)
            if res is not None:
                out[modelo] = res
        except Exception:
            continue
    return out
