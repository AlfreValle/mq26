"""
backtest_lab.py — Backtest de entradas/salidas y comparacion de estrategias (un activo).

Simula posiciones long/flat o long/short con retardo de 1 barra para evitar look-ahead
(posicion decidida en t-1 aplica al retorno close[t]/close[t-1]-1).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

PositionMode = Literal["long_flat", "long_short"]


@dataclass
class TradeLeg:
    bar: int
    action: str
    price: float


@dataclass
class BacktestLabResult:
    name: str
    sharpe: float
    sortino: float
    max_drawdown: float
    cum_return: float
    n_bars: int
    n_turns: float
    equity: pd.Series = field(repr=False)
    positions: pd.Series = field(repr=False)
    strategy_returns: pd.Series = field(repr=False)
    trades: list[TradeLeg] = field(default_factory=list, repr=False)
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0
    skew_net_returns: float = 0.0
    excess_kurtosis_net: float = 0.0
    cvar_95_daily: float = 0.0


def _sharpe(daily: pd.Series, rf_diario: float = 0.0) -> float:
    x = pd.to_numeric(daily, errors="coerce").dropna() - rf_diario
    s = float(x.std())
    return float((x.mean() / s) * np.sqrt(252)) if s > 0 else 0.0


def _sortino(daily: pd.Series, rf_diario: float = 0.0) -> float:
    x = pd.to_numeric(daily, errors="coerce").dropna() - rf_diario
    d = float(x[x < 0].std())
    return float((x.mean() / d) * np.sqrt(252)) if d > 0 else 0.0


def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.maximum(peak, 1e-12)
    return float(dd.min())


def _profit_factor_daily(net: pd.Series) -> float:
    """Suma retornos diarios positivos / abs(suma negativos). Sin negativos -> inf representado como 99.99."""
    x = pd.to_numeric(net, errors="coerce").dropna()
    if x.empty:
        return 0.0
    pos = float(x[x > 0].sum())
    neg = float(x[x < 0].sum())
    if neg >= 0.0:
        return 99.99 if pos > 0 else 0.0
    return pos / abs(neg)


def _annualized_return_from_equity(eq: np.ndarray) -> float:
    if eq.size < 2:
        return 0.0
    total = float(eq[-1] / max(eq[0], 1e-12) - 1.0)
    n = len(eq)
    return float((1.0 + total) ** (252.0 / max(n, 1)) - 1.0)


def _calmar_ratio(eq: np.ndarray, max_dd_frac: float) -> float:
    """Retorno anualizado / abs(max drawdown fraccion)."""
    if max_dd_frac >= -1e-9:
        return 0.0
    ret_a = _annualized_return_from_equity(eq)
    return float(ret_a / abs(max_dd_frac))


def _skew_excess_kurtosis(net: pd.Series) -> tuple[float, float]:
    x = pd.to_numeric(net, errors="coerce").dropna()
    if len(x) < 3:
        return 0.0, 0.0
    return float(x.skew()), float(x.kurtosis())


def _cvar_historical_daily(net: pd.Series, tail: float = 0.05) -> float:
    """Media del peor tail fraccion de retornos diarios netos (negativo = perdida esperada en cola)."""
    x = pd.to_numeric(net, errors="coerce").dropna().values
    if x.size < max(20, int(5.0 / max(tail, 0.01))):
        return 0.0
    k = max(1, int(np.ceil(tail * x.size)))
    worst = np.sort(x)[:k]
    return float(np.mean(worst))


def _positions_ma_cross(close: pd.Series, short: int, long: int) -> pd.Series:
    c = pd.to_numeric(close, errors="coerce")
    s_ma = c.rolling(short, min_periods=short).mean()
    l_ma = c.rolling(long, min_periods=long).mean()
    raw = np.where(s_ma > l_ma, 1.0, np.where(s_ma < l_ma, -1.0, 0.0))
    return pd.Series(raw, index=c.index, dtype=float)


def _positions_rsi_mean_reversion(
    close: pd.Series,
    period: int = 14,
    buy_level: float = 30.0,
    sell_level: float = 70.0,
) -> pd.Series:
    """Long solo en sobreventa; cierra en sobrecompra o salida neutral."""
    c = pd.to_numeric(close, errors="coerce")
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.rolling(period, min_periods=period).mean()
    al = loss.rolling(period, min_periods=period).mean()
    rs = ag / al.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    pos = np.zeros(len(c), dtype=float)
    hold = 0.0
    for i in range(len(c)):
        if np.isnan(rsi.iloc[i]):
            pos[i] = 0.0
            continue
        r = float(rsi.iloc[i])
        if hold == 0.0 and r < buy_level:
            hold = 1.0
        elif hold == 1.0 and r > sell_level:
            hold = 0.0
        pos[i] = hold
    return pd.Series(pos, index=c.index, dtype=float)


def _positions_breakout_channel(close: pd.Series, window: int = 20) -> pd.Series:
    """Long al romper maximo de window barras (Donchian simplificado a close)."""
    c = pd.to_numeric(close, errors="coerce")
    upper = c.rolling(window, min_periods=window).max().shift(1)
    pos = np.zeros(len(c), dtype=float)
    hold = 0.0
    for i in range(len(c)):
        if i == 0 or np.isnan(upper.iloc[i]):
            pos[i] = 0.0
            continue
        px = float(c.iloc[i])
        ub = float(upper.iloc[i])
        if hold == 0.0 and px > ub:
            hold = 1.0
        elif hold == 1.0 and px < ub * 0.98:
            hold = 0.0
        pos[i] = hold
    return pd.Series(pos, index=c.index, dtype=float)


def build_named_strategies(
    close: pd.Series,
) -> dict[str, pd.Series]:
    """Conjunto fijo de metodos de entrada/salida para comparar y enrutar."""
    return {
        "ma_cross_10_30": _positions_ma_cross(close, 10, 30),
        "ma_cross_5_20": _positions_ma_cross(close, 5, 20),
        "rsi_mr_14_30_70": _positions_rsi_mean_reversion(close, 14, 30.0, 70.0),
        "breakout_close_20": _positions_breakout_channel(close, 20),
    }


def simulate_positions(
    close: pd.Series,
    positions: pd.Series,
    *,
    commission_pct: float = 0.001,
    mode: PositionMode = "long_flat",
    rf_anual: float = 0.043,
) -> BacktestLabResult:
    """
    positions: -1, 0, 1 alineado al mismo indice que close.
    Retardo: la posicion en t-1 multiplica el retorno de t.
    """
    c = pd.to_numeric(close, errors="coerce").dropna()
    pos = pd.to_numeric(positions.reindex(c.index), errors="coerce").fillna(0.0)
    if mode == "long_flat":
        pos = pos.clip(lower=0.0, upper=1.0)
    else:
        pos = pos.clip(lower=-1.0, upper=1.0)

    pos_lag = pos.shift(1).fillna(0.0)
    chg = pos_lag.diff().abs().fillna(abs(pos_lag.iloc[0]))
    ret = c.pct_change().fillna(0.0)
    gross = pos_lag * ret
    costs = chg * float(commission_pct)
    net = gross - costs

    eq = (1.0 + net).cumprod()
    rf_d = rf_anual / 252.0
    sharpe = _sharpe(net, rf_d)
    sortino = _sortino(net, rf_d)
    mdd = _max_drawdown(eq.values)
    cum = float(eq.iloc[-1] - 1.0) if len(eq) else 0.0
    pf = _profit_factor_daily(net)
    calmar = _calmar_ratio(eq.values, mdd)
    sk, ku = _skew_excess_kurtosis(net)
    cvar95 = _cvar_historical_daily(net, tail=0.05)

    trades: list[TradeLeg] = []
    for i in range(1, len(pos)):
        if abs(float(pos.iloc[i]) - float(pos.iloc[i - 1])) > 1e-9:
            trades.append(TradeLeg(bar=i, action="rebalance", price=float(c.iloc[i])))

    return BacktestLabResult(
        name="custom",
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=mdd,
        cum_return=cum,
        n_bars=int(len(c)),
        n_turns=float(chg.sum()),
        equity=eq,
        positions=pos,
        strategy_returns=net,
        trades=trades,
        profit_factor=pf,
        calmar_ratio=calmar,
        skew_net_returns=sk,
        excess_kurtosis_net=ku,
        cvar_95_daily=cvar95,
    )


def compare_strategies(
    close: pd.Series,
    *,
    commission_pct: float = 0.001,
    mode: PositionMode = "long_flat",
    strategies: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    specs = strategies or build_named_strategies(close)
    rows = []
    for name, pos in specs.items():
        r = simulate_positions(close, pos, commission_pct=commission_pct, mode=mode)
        rows.append(
            {
                "estrategia": name,
                "sharpe": r.sharpe,
                "sortino": r.sortino,
                "max_dd": r.max_drawdown,
                "ret_acum": r.cum_return,
                "profit_factor": r.profit_factor,
                "calmar": r.calmar_ratio,
                "skew_net": r.skew_net_returns,
                "kurtosis_net": r.excess_kurtosis_net,
                "cvar95_daily": r.cvar_95_daily,
                "n_barras": r.n_bars,
                "turnover_1d_sum": r.n_turns,
            }
        )
    return pd.DataFrame(rows).sort_values("sharpe", ascending=False).reset_index(drop=True)


def regime_volatility_terciles(close: pd.Series, vol_window: int = 20, rank_window: int = 120) -> pd.Series:
    """
    Regimen por volatilidad relativa: 0=baja, 1=media, 2=alta segun terciles rolling.
    rank_window acotado para series cortas (min 40 barras).
    """
    c = pd.to_numeric(close, errors="coerce").dropna()
    vol = c.pct_change().rolling(vol_window, min_periods=vol_window).std()
    rw = max(40, min(rank_window, len(c) - 5))
    out = pd.Series(np.nan, index=c.index, dtype=float)
    for i in range(len(c)):
        if i < rw or np.isnan(vol.iloc[i]):
            continue
        w = vol.iloc[i - rw : i]
        w = w.dropna()
        if len(w) < 20:
            continue
        q1, q2 = np.quantile(w.values, [1.0 / 3.0, 2.0 / 3.0])
        v = float(vol.iloc[i])
        if v <= q1:
            out.iloc[i] = 0.0
        elif v <= q2:
            out.iloc[i] = 1.0
        else:
            out.iloc[i] = 2.0
    return out


StrategyBuilder = Callable[[pd.Series], dict[str, pd.Series]]


@dataclass
class RouterFitResult:
    """Mapa regimen -> mejor estrategia por Sharpe en train (sin look-ahead en etiqueta de regimen)."""
    regime_to_strategy: dict[int, str]
    default_strategy: str
    train_sharpe_by_regime: dict[int, dict[str, float]]
    oos_sharpe_router: float
    oos_sharpe_best_single: float
    oos_best_single_name: str


def fit_regime_router_walk_forward(
    close: pd.Series,
    *,
    train_ratio: float = 0.65,
    commission_pct: float = 0.001,
    mode: PositionMode = "long_flat",
    strategy_builder: StrategyBuilder | None = None,
) -> RouterFitResult:
    """
    Entrena: por cada regimen (vol terciles en t-1), elige la estrategia con mayor Sharpe
    sobre los dias de train donde ese regimen aplico al inicio del dia.
    OOS: retorno del dia t = estrategia elegida segun regimen en t-1.
    """
    c = pd.to_numeric(close, errors="coerce").dropna()
    n = len(c)
    if n < 80:
        return RouterFitResult({}, "", {}, 0.0, 0.0, "")

    split = int(n * train_ratio)
    train_idx = c.index[:split]
    test_idx = c.index[split:]

    builder = strategy_builder or build_named_strategies
    strat_all = builder(c)
    regimes = regime_volatility_terciles(c)

    # Precompute per-strategy daily returns (full series)
    strat_rets: dict[str, pd.Series] = {}
    for name, pos in strat_all.items():
        strat_rets[name] = simulate_positions(
            c, pos, commission_pct=commission_pct, mode=mode
        ).strategy_returns

    # Train: regime at t-1 -> pick best sharpe on train days
    regime_to_strategy: dict[int, str] = {}
    train_sharpe_by_regime: dict[int, dict[str, float]] = {}

    rlag = regimes.shift(1)
    for reg in (0.0, 1.0, 2.0):
        mask_train = train_idx.intersection(c.index)
        sub = rlag.reindex(mask_train)
        day_ok = sub == reg
        if int(day_ok.sum()) < 15:
            continue
        sharpe_by_s: dict[str, float] = {}
        for name, sr in strat_rets.items():
            chunk = sr.reindex(mask_train).loc[day_ok]
            sharpe_by_s[name] = _sharpe(chunk, 0.043 / 252.0)
        train_sharpe_by_regime[int(reg)] = sharpe_by_s
        best = max(sharpe_by_s, key=lambda k: sharpe_by_s[k])
        regime_to_strategy[int(reg)] = best

    default_strat = max(
        strat_rets,
        key=lambda k: _sharpe(strat_rets[k].reindex(train_idx), 0.043 / 252.0),
    )

    # OOS blended returns
    blended = []
    for t in test_idx:
        rp = rlag.loc[t] if t in rlag.index else np.nan
        if pd.isna(rp):
            pick = default_strat
        else:
            rk = int(float(rp))
            pick = regime_to_strategy.get(rk, default_strat)
        blended.append(float(strat_rets[pick].get(t, 0.0)))
    br = pd.Series(blended, index=test_idx, dtype=float)
    oos_sh_router = _sharpe(br, 0.043 / 252.0)

    best_single_name = ""
    best_single_sh = -1e9
    for name, sr in strat_rets.items():
        sh = _sharpe(sr.reindex(test_idx), 0.043 / 252.0)
        if sh > best_single_sh:
            best_single_sh = sh
            best_single_name = name

    return RouterFitResult(
        regime_to_strategy=regime_to_strategy,
        default_strategy=default_strat,
        train_sharpe_by_regime=train_sharpe_by_regime,
        oos_sharpe_router=oos_sh_router,
        oos_sharpe_best_single=best_single_sh,
        oos_best_single_name=best_single_name,
    )


def walk_forward_oos_grid(
    close: pd.Series,
    *,
    train_ratios: list[float],
    commission_pct: float = 0.001,
    mode: PositionMode = "long_flat",
) -> pd.DataFrame:
    """
    Evalua el router walk-forward con varios train_ratio (validacion OOS multi-particion).
    Cada fila es una corrida independiente sobre el mismo close.
    """
    rows: list[dict] = []
    for tr in train_ratios:
        tr_use = float(tr)
        tr_use = min(0.95, max(0.05, tr_use))
        r = fit_regime_router_walk_forward(
            close, train_ratio=tr_use, commission_pct=commission_pct, mode=mode
        )
        rows.append(
            {
                "train_ratio": tr_use,
                "oos_sharpe_router": r.oos_sharpe_router,
                "oos_sharpe_mejor_unica": r.oos_sharpe_best_single,
                "oos_mejor_unica": r.oos_best_single_name,
                "default_strategy": r.default_strategy,
                "n_regimenes_mapa": len(r.regime_to_strategy),
            }
        )
    return pd.DataFrame(rows)


def current_vol_regime(
    close: pd.Series,
    *,
    vol_window: int = 20,
    rank_window: int = 120,
) -> int | None:
    """Ultimo regimen de volatilidad (0/1/2) alineado a regime_volatility_terciles; None si aun no computable."""
    r = regime_volatility_terciles(close, vol_window=vol_window, rank_window=rank_window)
    rv = r.dropna()
    if rv.empty:
        return None
    return int(float(rv.iloc[-1]))


@dataclass
class CapitalWindowReport:
    """Resumen de una ventana: capital, operaciones cerradas y tasa de aciertos."""

    ventana_dias: int
    estrategia: str
    capital_inicial_ars: float
    capital_final_ars: float
    rendimiento_total_pct: float
    operaciones_cerradas: int
    operaciones_ganadoras: int
    tasa_aciertos_pct: float
    dias_en_mercado: int
    dias_ganadores: int
    tasa_aciertos_dias_pct: float
    sharpe: float
    max_drawdown: float
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0
    cvar_95_daily: float = 0.0
    skew_net_returns: float = 0.0
    excess_kurtosis_net: float = 0.0


def long_flat_roundtrip_stats(
    close: pd.Series,
    positions: pd.Series,
    *,
    commission_pct: float = 0.001,
) -> tuple[int, int, int, int]:
    """
    Long/flat: cuenta operaciones cerradas (0->1->0 o cierre al final si queda abierta).
    Retorna (n_cerradas, n_ganadoras, dias_expuesto, dias_ganadores_expuesto).
    """
    c = pd.to_numeric(close, errors="coerce").dropna()
    pos = pd.to_numeric(positions.reindex(c.index), errors="coerce").fillna(0.0).clip(0.0, 1.0)

    n_win = 0
    n_tr = 0
    entry_idx: int | None = None
    for t in range(1, len(c)):
        if float(pos.iloc[t - 1]) == 0.0 and float(pos.iloc[t]) == 1.0:
            entry_idx = t
        elif entry_idx is not None and float(pos.iloc[t - 1]) == 1.0 and float(pos.iloc[t]) == 0.0:
            gross = float(c.iloc[t] / c.iloc[entry_idx] - 1.0)
            pnl = gross - 2.0 * float(commission_pct)
            n_tr += 1
            if pnl > 0.0:
                n_win += 1
            entry_idx = None
    if entry_idx is not None and len(c) - 1 > entry_idx:
        gross = float(c.iloc[-1] / c.iloc[entry_idx] - 1.0)
        pnl = gross - float(commission_pct)
        n_tr += 1
        if pnl > 0.0:
            n_win += 1

    pos_lag = pos.shift(1).fillna(0.0)
    ret = c.pct_change().fillna(0.0)
    exp = pos_lag > 0.0
    dias_exp = int(exp.sum())
    dias_gan = int(((ret > 0.0) & exp).sum())

    return n_tr, n_win, dias_exp, dias_gan


def report_capital_window(
    close: pd.Series,
    positions: pd.Series,
    *,
    ventana_dias: int,
    estrategia: str,
    capital_inicial_ars: float = 100_000.0,
    commission_pct: float = 0.001,
    mode: PositionMode = "long_flat",
) -> CapitalWindowReport:
    sim = simulate_positions(close, positions, commission_pct=commission_pct, mode=mode)
    mult = float(sim.equity.iloc[-1]) if len(sim.equity) else 1.0
    cap_fin = capital_inicial_ars * mult
    ret_pct = (cap_fin / capital_inicial_ars - 1.0) * 100.0 if capital_inicial_ars > 0 else 0.0

    n_tr, n_win, d_exp, d_gan = long_flat_roundtrip_stats(close, positions, commission_pct=commission_pct)
    hit_tr = (100.0 * n_win / n_tr) if n_tr > 0 else 0.0
    hit_d = (100.0 * d_gan / d_exp) if d_exp > 0 else 0.0

    return CapitalWindowReport(
        ventana_dias=ventana_dias,
        estrategia=estrategia,
        capital_inicial_ars=float(capital_inicial_ars),
        capital_final_ars=float(cap_fin),
        rendimiento_total_pct=float(ret_pct),
        operaciones_cerradas=int(n_tr),
        operaciones_ganadoras=int(n_win),
        tasa_aciertos_pct=float(hit_tr),
        dias_en_mercado=int(d_exp),
        dias_ganadores=int(d_gan),
        tasa_aciertos_dias_pct=float(hit_d),
        sharpe=float(sim.sharpe),
        max_drawdown=float(sim.max_drawdown),
        profit_factor=float(sim.profit_factor),
        calmar_ratio=float(sim.calmar_ratio),
        cvar_95_daily=float(sim.cvar_95_daily),
        skew_net_returns=float(sim.skew_net_returns),
        excess_kurtosis_net=float(sim.excess_kurtosis_net),
    )


def pick_best_strategy_name(close: pd.Series, *, commission_pct: float = 0.001) -> str:
    df = compare_strategies(close, commission_pct=commission_pct, mode="long_flat")
    if df.empty:
        return "ma_cross_10_30"
    return str(df.iloc[0]["estrategia"])
