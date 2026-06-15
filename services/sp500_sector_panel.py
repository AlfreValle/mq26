"""
Panel de referencia S&P 500 por sector (ETFs SPDR sectoriales + SPY).
Datos vía yfinance: rendimientos, beta vs SPY, P/E forward y dividend yield cuando existan.
Los pesos sectoriales son aproximación educativa del índice (no tiempo real).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

import pandas as pd

# Pesos orientativos del índice (misma magnitud que reportes públicos tipo “Sector weight” S&P 500).
# Se renorman a 100% al armar la tabla.
_SPX_SECTOR_WEIGHT_HINT: dict[str, float] = {
    "XLE": 4.0,
    "XLB": 2.5,
    "XLF": 13.0,
    "XLI": 8.5,
    "XLY": 10.5,
    "XLK": 32.0,
    "XLC": 11.0,
    "XLRE": 2.5,
    "XLV": 12.5,
    "XLP": 6.0,
    "XLU": 2.5,
}

# Orden de columnas (etiqueta corta UI, ticker)
SP500_SECTOR_COLS: tuple[tuple[str, str], ...] = (
    ("Energía", "XLE"),
    ("Materiales", "XLB"),
    ("Financiero", "XLF"),
    ("Industrial", "XLI"),
    ("Cons. discr.", "XLY"),
    ("Tecnología", "XLK"),
    ("Com. serv.", "XLC"),
    ("Real estate", "XLRE"),
    ("Salud", "XLV"),
    ("Cons. básico", "XLP"),
    ("Serv. públicos", "XLU"),
)

BENCHMARK_TICKER = "SPY"
_DISCLAIMER = (
    "Referencia educativa. Pesos sectoriales aproximados (no composición oficial en vivo). "
    "Métricas de ETF sectorial ≠ agregado exacto del índice. Datos vía Yahoo Finance; pueden demorar o fallar."
)


def _nyc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="America/New_York")


def _ytd_start(now: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=now.year, month=1, day=1, tzinfo=now.tz)


def _qtd_start(now: pd.Timestamp) -> pd.Timestamp:
    q0 = ((now.month - 1) // 3) * 3 + 1
    return pd.Timestamp(year=now.year, month=q0, day=1, tzinfo=now.tz)


def _normalize_weights(raw: dict[str, float]) -> dict[str, float]:
    s = sum(max(0.0, v) for v in raw.values())
    if s <= 0:
        n = len(raw)
        return {k: round(100.0 / n, 1) for k in raw}
    return {k: round(100.0 * max(0.0, v) / s, 1) for k, v in raw.items()}


def _hist_close(
    ticker: str,
    *,
    period: str = "400d",
    download_fn: Callable[..., Any] | None = None,
) -> pd.Series:
    import yfinance as yf  # lazy

    fn = download_fn or yf.download
    df = fn(ticker, period=period, progress=False, auto_adjust=True)
    if df is None or getattr(df, "empty", True):
        return pd.Series(dtype=float)
    close = df["Close"] if "Close" in df.columns else df
    if getattr(close, "ndim", 1) > 1:
        close = close.squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return pd.Series(close, dtype=float).dropna()


def _total_return_pct(close: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    if close is None or close.empty:
        return None
    ix = pd.to_datetime(close.index)
    if getattr(ix, "tz", None) is not None:
        ix = ix.tz_convert("UTC").tz_localize(None)
    ser = pd.Series(close.values, index=ix.normalize()).sort_index().astype(float).dropna()
    sd = pd.Timestamp(start)
    if getattr(sd, "tz", None) is not None:
        sd = sd.tz_convert("UTC").tz_localize(None)
    sd = sd.normalize()
    ed = pd.Timestamp(end)
    if getattr(ed, "tz", None) is not None:
        ed = ed.tz_convert("UTC").tz_localize(None)
    ed = ed.normalize()
    sub = ser.loc[ser.index >= sd]
    sub = sub.loc[sub.index <= ed]
    if sub.size < 2:
        return None
    a, b = float(sub.iloc[0]), float(sub.iloc[-1])
    if a == 0:
        return None
    return round((b / a - 1.0) * 100.0, 2)


def _beta_vs_spy(asset: pd.Series, spy: pd.Series, min_days: int = 60) -> float | None:
    if asset is None or spy is None or asset.empty or spy.empty:
        return None
    a = asset.pct_change().dropna()
    b = spy.pct_change().dropna()
    j = a.align(b, join="inner")
    if j[0].shape[0] < min_days:
        return None
    var = float(j[1].var())
    if var <= 0:
        return None
    return round(float(j[0].cov(j[1])) / var, 2)


def _info_metrics(
    ticker: str,
    *,
    ticker_fn: Any | None = None,
) -> tuple[float | None, float | None]:
    import yfinance as yf  # lazy

    T = ticker_fn or yf.Ticker
    try:
        info = T(ticker).info or {}
    except Exception:
        return None, None
    pe = info.get("forwardPE") or info.get("trailingPE")
    try:
        pe_f = float(pe) if pe is not None else None
    except (TypeError, ValueError):
        pe_f = None
    if pe_f is not None:
        pe_f = round(pe_f, 1)
    dy = info.get("dividendYield")
    try:
        dy_f = float(dy) if dy is not None else None
    except (TypeError, ValueError):
        dy_f = None
    if dy_f is not None and dy_f <= 1.0:
        dy_f *= 100.0
    if dy_f is not None:
        dy_f = round(dy_f, 2)
    return pe_f, dy_f


@dataclass
class Sp500SectorPanelResult:
    table: pd.DataFrame
    as_of: str
    disclaimer: str
    errors: list[str]


def build_sp500_sector_panel(
    *,
    download_fn: Callable[..., Any] | None = None,
    ticker_fn: Any | None = None,
) -> Sp500SectorPanelResult:
    """
    Arma matriz métrica × sectores + columna S&P 500 (SPY).
    """
    now = _nyc_now()
    t_ytd = _ytd_start(now)
    t_qtd = _qtd_start(now)
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M")

    weights = _normalize_weights(_SPX_SECTOR_WEIGHT_HINT)
    tickers = [t for _, t in SP500_SECTOR_COLS] + [BENCHMARK_TICKER]

    closes: dict[str, pd.Series] = {}
    errors: list[str] = []
    for tk in tickers:
        try:
            s = _hist_close(tk, download_fn=download_fn)
            if s.empty:
                errors.append(f"{tk}: sin serie de precios")
            else:
                closes[tk] = s
        except Exception as ex:  # pragma: no cover - red
            errors.append(f"{tk}: {ex}")

    spy_s = closes.get(BENCHMARK_TICKER)
    rows: dict[str, list[Any]] = {
        "Peso en S&P 500 (%)": [],
        "Retorno QTD (%)": [],
        "Retorno YTD (%)": [],
        "Beta vs SPY": [],
        "P/E forward (x)": [],
        "Dividend yield (%)": [],
    }
    col_order: list[str] = [lbl for lbl, _ in SP500_SECTOR_COLS] + ["S&P 500"]

    for _, tk in SP500_SECTOR_COLS:
        w = weights.get(tk)
        rows["Peso en S&P 500 (%)"].append(w)
        c = closes.get(tk)
        if c is not None and spy_s is not None:
            rows["Retorno QTD (%)"].append(_total_return_pct(c, t_qtd, now))
            rows["Retorno YTD (%)"].append(_total_return_pct(c, t_ytd, now))
            rows["Beta vs SPY"].append(_beta_vs_spy(c, spy_s))
        else:
            rows["Retorno QTD (%)"].append(None)
            rows["Retorno YTD (%)"].append(None)
            rows["Beta vs SPY"].append(None)
        pe, dy = _info_metrics(tk, ticker_fn=ticker_fn)
        rows["P/E forward (x)"].append(pe)
        rows["Dividend yield (%)"].append(dy)

    # Columna SPY
    rows["Peso en S&P 500 (%)"].append(100.0)
    if spy_s is not None:
        rows["Retorno QTD (%)"].append(_total_return_pct(spy_s, t_qtd, now))
        rows["Retorno YTD (%)"].append(_total_return_pct(spy_s, t_ytd, now))
        rows["Beta vs SPY"].append(1.0)
    else:
        rows["Retorno QTD (%)"].append(None)
        rows["Retorno YTD (%)"].append(None)
        rows["Beta vs SPY"].append(None)
    pe_s, dy_s = _info_metrics(BENCHMARK_TICKER, ticker_fn=ticker_fn)
    rows["P/E forward (x)"].append(pe_s)
    rows["Dividend yield (%)"].append(dy_s)

    df = pd.DataFrame(rows, index=col_order).T
    return Sp500SectorPanelResult(
        table=df,
        as_of=as_of,
        disclaimer=_DISCLAIMER,
        errors=errors,
    )
