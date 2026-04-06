# services/comparador_instrumentos.py
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

# ── Tasas de plazo fijo AR históricas (TNA promedio anual, fuente BCRA) ─────
# Serie mantenida manualmente — actualizar cada año
_TASAS_PF: dict[int, float] = {
    2005: 0.06, 2006: 0.08, 2007: 0.10, 2008: 0.15, 2009: 0.14,
    2010: 0.12, 2011: 0.16, 2012: 0.14, 2013: 0.19, 2014: 0.24,
    2015: 0.27, 2016: 0.28, 2017: 0.24, 2018: 0.50, 2019: 0.63,
    2020: 0.34, 2021: 0.38, 2022: 0.75, 2023: 1.33, 2024: 0.90,
    2025: 0.48, 2026: 0.36,
}

# Tickers de la cartera conservadora benchmark
_TICKERS_CONSERVADORA = ["KO", "XOM", "GLD", "PG"]


def _serie_plazo_fijo(start: str = "2005-01-01", capital: float = 1000.0) -> pd.Series:
    """
    Simula el crecimiento de capital en plazo fijo AR usando tasas TNA históricas.
    Capitalización diaria: (1 + TNA/365)^días_en_año.
    """
    n_dias = 365 * 22
    idx = pd.date_range(start, periods=n_dias, freq="D")
    vals = np.empty(len(idx), dtype=float)
    cap = capital
    for i, fecha in enumerate(idx):
        tna = _TASAS_PF.get(fecha.year, 0.40)
        cap *= (1 + tna / 365)
        vals[i] = cap
    return pd.Series(vals, index=idx).resample("ME").last()


def _serie_dolar_ars(start: str = "2005-01-01", capital: float = 1000.0) -> pd.Series:
    """
    Simula mantener USD en efectivo: capital en pesos crece con el dólar informal.
    Proxy: ARS=X desde yfinance. Fallback: devaluación promedio sintética.
    """
    try:
        raw = yf.download(
            "ARS=X", start=start, progress=False, auto_adjust=True
        )["Close"].dropna()
        if hasattr(raw, "squeeze"):
            raw = raw.squeeze()
        if isinstance(raw, pd.DataFrame):
            raw = raw.iloc[:, 0]
        if raw.empty:
            raise ValueError("sin datos")
        raw = raw.resample("ME").last()
        px0 = float(raw.iloc[0])
        return (raw / px0 * capital).rename("Dolar ARS")
    except Exception:
        idx = pd.date_range(start, periods=264, freq="ME")
        vals = capital * np.cumprod(
            np.where(
                np.arange(len(idx)) == 0,
                1.0,
                1 + np.random.default_rng(seed=42).normal(0.035, 0.005, len(idx)),
            )
        )
        return pd.Series(vals, index=idx, name="Dolar ARS")


def _serie_spy(start: str = "2005-01-01", capital: float = 1000.0) -> pd.Series:
    """SPY total return indexado a capital inicial."""
    try:
        raw = yf.download(
            "SPY", start=start, progress=False, auto_adjust=True
        )["Close"].dropna()
        if hasattr(raw, "squeeze"):
            raw = raw.squeeze()
        if isinstance(raw, pd.DataFrame):
            raw = raw.iloc[:, 0]
        raw = raw.resample("ME").last()
        return (raw / float(raw.iloc[0]) * capital).rename("SPY")
    except Exception:
        idx = pd.date_range(start, periods=264, freq="ME")
        vals = capital * np.cumprod(
            1 + np.random.default_rng(seed=0).normal(0.009, 0.04, len(idx))
        )
        return pd.Series(vals, index=idx, name="SPY")


def _serie_conservadora(start: str = "2005-01-01", capital: float = 1000.0) -> pd.Series:
    """
    Cartera conservadora MQ26: KO + XOM + GLD + PG pesos igual-peso.
    Retorno mensual = promedio simple de los 4 retornos mensuales.
    """
    try:
        raw = yf.download(
            _TICKERS_CONSERVADORA, start=start, progress=False, auto_adjust=True
        )["Close"].dropna(axis=1, how="all").dropna()
        raw = raw.resample("ME").last()
        rets = raw.pct_change().dropna()
        ret_port = rets.mean(axis=1)
        cumret = (1 + ret_port).cumprod()
        return (cumret / float(cumret.iloc[0]) * capital).rename("Cartera MQ26 Conservadora")
    except Exception:
        idx = pd.date_range(start, periods=263, freq="ME")
        vals = capital * np.cumprod(
            1 + np.random.default_rng(seed=1).normal(0.007, 0.025, len(idx))
        )
        return pd.Series(vals, index=idx, name="Cartera MQ26 Conservadora")


def generar_comparador_instrumentos(
    start: str = "2005-01-01",
    capital: float = 1_000.0,
) -> go.Figure:
    """
    Gráfico logarítmico de capital invertido en 4 instrumentos desde `start`.
    Invariante: retorna go.Figure válida incluso si yfinance falla (fallback sintético).
    """
    spy = _serie_spy(start, capital)
    pf = _serie_plazo_fijo(start, capital)
    dolar = _serie_dolar_ars(start, capital)
    mq26 = _serie_conservadora(start, capital)

    idx_comun = (
        spy.index.intersection(pf.index)
        .intersection(dolar.index)
        .intersection(mq26.index)
    )
    if idx_comun.empty:
        n = min(len(spy), len(pf), len(dolar), len(mq26))
        idx_comun = spy.index[:n]

    colores = {
        "SPY (mercado USA)":         "#1A6B3C",
        "Cartera MQ26 Conservadora": "#1F4E79",
        "Dólar billete (ARS)":       "#B8860B",
        "Plazo fijo AR":             "#C00000",
    }

    series_plot = [
        (spy.reindex(idx_comun).ffill(),   "SPY (mercado USA)",         colores["SPY (mercado USA)"]),
        (mq26.reindex(idx_comun).ffill(),  "Cartera MQ26 Conservadora", colores["Cartera MQ26 Conservadora"]),
        (dolar.reindex(idx_comun).ffill(), "Dólar billete (ARS)",       colores["Dólar billete (ARS)"]),
        (pf.reindex(idx_comun).ffill(),    "Plazo fijo AR",             colores["Plazo fijo AR"]),
    ]

    fig = go.Figure()
    for serie, label, color in series_plot:
        fig.add_scatter(
            x=serie.index,
            y=serie.values,
            mode="lines",
            name=label,
            line={"color": color, "width": 2},
            hovertemplate=(
                f"<b>{label}</b><br>"
                "Fecha: %{x|%b %Y}<br>"
                "Valor: USD %{y:,.0f}<extra></extra>"
            ),
        )

    # Anotaciones de valor final
    for serie_orig, label, color in [
        (spy,   "SPY (mercado USA)",         colores["SPY (mercado USA)"]),
        (mq26,  "Cartera MQ26 Conservadora", colores["Cartera MQ26 Conservadora"]),
        (dolar, "Dólar billete (ARS)",       colores["Dólar billete (ARS)"]),
        (pf,    "Plazo fijo AR",             colores["Plazo fijo AR"]),
    ]:
        try:
            s_clean = serie_orig.dropna()
            val_final = float(s_clean.iloc[-1])
            fig.add_annotation(
                x=s_clean.index[-1],
                y=val_final,
                text=f"  USD {val_final:,.0f}",
                showarrow=False,
                font={"color": color, "size": 11},
                xanchor="left",
            )
        except Exception:
            pass

    fig.update_layout(
        title=f"USD {capital:,.0f} invertidos en {start[:4]} → hoy",
        xaxis_title="Año",
        yaxis_title="Valor final (USD)",
        yaxis_type="log",
        legend={"orientation": "h", "y": -0.18},
        margin={"l": 0, "r": 40, "t": 50, "b": 60},
        height=450,
        hovermode="x unified",
    )
    return fig
