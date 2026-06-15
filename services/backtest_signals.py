"""
services/backtest_signals.py — Backtest histórico de señales.

Mide el desempeño REAL de los criterios usados en perlas/scoring:
  - ¿Qué % de "Score ≥70 + RSI ≤45" subió en 3/6/12 meses?
  - ¿Cuál fue el retorno medio / mediano?
  - ¿Cuál es el Sharpe ratio?
  - ¿Outperforma a SPY (benchmark)?

Sin esto, la confianza del sistema está en "lógica plausible".
Con esto, está en "lógica + evidencia empírica".

API:
    from services.backtest_signals import backtest_setup
    r = backtest_setup(
        tickers=["AAPL","MSFT","KO","JNJ"],
        condicion="rsi_oversold",       # o "drawdown_recovery", "score_breakout"
        holding_meses=6,
        anios_historia=5,
    )
    print(r.win_rate)   # ej: 0.62 (62% subió)
    print(r.return_medio_pct)
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field, asdict
from statistics import mean, median, pstdev
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Resultado de backtest agregado para un setup."""
    setup_nombre: str
    holding_meses: int
    n_signals: int
    n_winners: int
    n_losers: int
    win_rate: float                # 0-1
    return_medio_pct: float        # promedio simple
    return_mediano_pct: float
    return_max_pct: float
    return_min_pct: float
    sharpe: float                  # anualizado (asume rf=4%)
    benchmark_return_medio_pct: float  # SPY en mismo horizonte
    alpha_pct: float               # return_medio - benchmark
    tickers_evaluados: list[str] = field(default_factory=list)
    detalle_signals: list[dict] = field(default_factory=list)
    fecha_inicio: str = ""
    fecha_fin: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── RSI y Drawdown sin yfinance pesado ───────────────────────────────────────

def _rsi_series(closes: pd.Series, ventana: int = 14) -> pd.Series:
    """RSI 14 estilo Wilder."""
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/ventana, min_periods=ventana, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/ventana, min_periods=ventana, adjust=False).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def _drawdown_series(closes: pd.Series, ventana_dias: int = 252) -> pd.Series:
    """Drawdown rolling vs máximo de los últimos N días."""
    rolling_max = closes.rolling(ventana_dias, min_periods=20).max()
    return (rolling_max - closes) / rolling_max   # 0 a 1 (positivo = drawdown)


# ─── Setups de detección (mismas reglas que perlas_service) ───────────────────

_SETUPS = {
    "rsi_oversold": {
        "descripcion": "RSI ≤ 35 (sobrevendido)",
        "cumple": lambda close, rsi, dd: rsi.iloc[-1] <= 35,
    },
    "drawdown_recovery": {
        "descripcion": "Drawdown ≥ 25% desde máximo 52 sem",
        "cumple": lambda close, rsi, dd: dd.iloc[-1] >= 0.25,
    },
    "rsi_or_dd": {
        "descripcion": "RSI ≤ 45 O Drawdown ≥ 20% (criterio actual perlas)",
        "cumple": lambda close, rsi, dd: (rsi.iloc[-1] <= 45) or (dd.iloc[-1] >= 0.20),
    },
    "score_premium": {
        "descripcion": "Drawdown 20-40% (rebote esperado, sin sobrecompra extrema)",
        "cumple": lambda close, rsi, dd: 0.20 <= dd.iloc[-1] <= 0.40,
    },
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _descargar_historico(ticker: str, anios: int = 5) -> pd.Series | None:
    """Descarga histórico de cierres ajustados. Retorna None si falla."""
    try:
        import yfinance as yf
        period = f"{max(2, anios)}y"
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if df.empty or "Close" not in df.columns:
            return None
        return df["Close"].dropna()
    except Exception as e:
        logger.debug("backtest: no se pudo descargar %s: %s", ticker, e)
        return None


def _retorno_forward(closes: pd.Series, idx: int, dias_adelante: int) -> float | None:
    """Retorno % desde closes[idx] hasta closes[idx + dias_adelante]."""
    if idx + dias_adelante >= len(closes):
        return None
    p0 = closes.iloc[idx]
    p1 = closes.iloc[idx + dias_adelante]
    if p0 <= 0:
        return None
    return float((p1 / p0 - 1) * 100)


def _sharpe_anualizado(retornos: list[float], rf_anual_pct: float = 4.0,
                       periodos_por_anio: int = 12) -> float:
    """Sharpe simple anualizado (asume retornos en %)."""
    if len(retornos) < 2:
        return 0.0
    avg = mean(retornos)
    std = pstdev(retornos)
    if std == 0:
        return 0.0
    # Convertir mensual → anualizado (asumiendo retornos en período "holding")
    # Approx: si holding=6 meses, return/6 * 12 = return anualizado
    return round((avg - rf_anual_pct) / std, 2)


# ─── API principal ────────────────────────────────────────────────────────────

def backtest_setup(
    tickers: list[str],
    *,
    condicion: str = "rsi_or_dd",
    holding_meses: int = 6,
    anios_historia: int = 5,
    incluir_benchmark: bool = True,
    sampling_dias: int = 21,
) -> BacktestResult:
    """
    Ejecuta backtest histórico de un setup sobre un universo de tickers.

    Args:
        tickers: lista a evaluar.
        condicion: clave de _SETUPS (rsi_or_dd, rsi_oversold, drawdown_recovery, score_premium).
        holding_meses: cuántos meses adelante medir el retorno.
        anios_historia: años hacia atrás de datos.
        incluir_benchmark: si True, compara contra SPY.
        sampling_dias: cada cuántos días evaluar si el setup se cumple (default mensual).

    Returns:
        BacktestResult con estadísticas agregadas.
    """
    setup = _SETUPS.get(condicion)
    if setup is None:
        raise ValueError(f"Condición desconocida: {condicion}. Válidas: {list(_SETUPS.keys())}")

    holding_dias = holding_meses * 21   # ~21 días hábiles por mes
    fecha_hoy = dt.date.today()
    fecha_inicio = fecha_hoy - dt.timedelta(days=anios_historia * 365)

    # Descargar benchmark
    spy_closes = _descargar_historico("SPY", anios=anios_historia + 1) if incluir_benchmark else None

    todos_retornos: list[float] = []
    todos_bench_retornos: list[float] = []
    detalle: list[dict] = []
    tickers_validos: list[str] = []

    for ticker in tickers:
        closes = _descargar_historico(ticker, anios=anios_historia + 1)
        if closes is None or len(closes) < 252:
            continue
        tickers_validos.append(ticker)

        rsi = _rsi_series(closes, ventana=14)
        dd = _drawdown_series(closes, ventana_dias=252)

        # Iterar por la historia evaluando el setup cada `sampling_dias`
        idx = 252  # arrancar tras 1 año de warm-up
        while idx + holding_dias < len(closes):
            # Sub-series hasta el momento
            sub_close = closes.iloc[:idx+1]
            sub_rsi = rsi.iloc[:idx+1]
            sub_dd = dd.iloc[:idx+1]

            # Skip si NaN
            if pd.isna(sub_rsi.iloc[-1]) or pd.isna(sub_dd.iloc[-1]):
                idx += sampling_dias
                continue

            try:
                cumple = bool(setup["cumple"](sub_close, sub_rsi, sub_dd))
            except Exception:
                cumple = False

            if cumple:
                ret = _retorno_forward(closes, idx, holding_dias)
                if ret is not None:
                    todos_retornos.append(ret)
                    bench_ret = None
                    if spy_closes is not None:
                        # Match aproximado por fecha
                        fecha_signal = closes.index[idx]
                        bench_idx = spy_closes.index.get_indexer([fecha_signal], method="nearest")[0]
                        bench_ret = _retorno_forward(spy_closes, bench_idx, holding_dias)
                        if bench_ret is not None:
                            todos_bench_retornos.append(bench_ret)
                    detalle.append({
                        "ticker":         ticker,
                        "fecha_signal":   str(closes.index[idx].date()),
                        "rsi":            round(float(sub_rsi.iloc[-1]), 1),
                        "drawdown_pct":   round(float(sub_dd.iloc[-1]) * 100, 1),
                        "return_pct":     round(ret, 2),
                        "benchmark_pct":  round(bench_ret, 2) if bench_ret is not None else None,
                    })

            idx += sampling_dias

    n = len(todos_retornos)
    if n == 0:
        return BacktestResult(
            setup_nombre=condicion,
            holding_meses=holding_meses,
            n_signals=0, n_winners=0, n_losers=0,
            win_rate=0, return_medio_pct=0, return_mediano_pct=0,
            return_max_pct=0, return_min_pct=0,
            sharpe=0, benchmark_return_medio_pct=0, alpha_pct=0,
            tickers_evaluados=tickers_validos,
            fecha_inicio=fecha_inicio.isoformat(),
            fecha_fin=fecha_hoy.isoformat(),
        )

    n_winners = sum(1 for r in todos_retornos if r > 0)
    win_rate = n_winners / n
    return_medio = mean(todos_retornos)
    return_mediano = median(todos_retornos)
    bench_medio = mean(todos_bench_retornos) if todos_bench_retornos else 0.0

    return BacktestResult(
        setup_nombre=condicion,
        holding_meses=holding_meses,
        n_signals=n,
        n_winners=n_winners,
        n_losers=n - n_winners,
        win_rate=round(win_rate, 3),
        return_medio_pct=round(return_medio, 2),
        return_mediano_pct=round(return_mediano, 2),
        return_max_pct=round(max(todos_retornos), 2),
        return_min_pct=round(min(todos_retornos), 2),
        sharpe=_sharpe_anualizado(todos_retornos),
        benchmark_return_medio_pct=round(bench_medio, 2),
        alpha_pct=round(return_medio - bench_medio, 2),
        tickers_evaluados=tickers_validos,
        detalle_signals=detalle[:50],   # primeros 50 ejemplos
        fecha_inicio=fecha_inicio.isoformat(),
        fecha_fin=fecha_hoy.isoformat(),
    )


def comparar_setups(tickers: list[str], holding_meses: int = 6) -> dict[str, BacktestResult]:
    """Corre todos los setups en paralelo conceptual y devuelve comparativa."""
    return {
        nombre: backtest_setup(tickers, condicion=nombre, holding_meses=holding_meses)
        for nombre in _SETUPS.keys()
    }
