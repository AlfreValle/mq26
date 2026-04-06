from __future__ import annotations

import plotly.graph_objects as go
import yfinance as yf

from services.scoring_engine import score_fundamental, score_tecnico

RECOMENDACION_RULES: list[tuple[float, str]] = [
    (85, "Compra fuerte"),
    (70, "Compra"),
    (50, "Acumular"),
    (35, "Seguimiento"),
    (0,  "Venta parcial"),
]

DIMENSIONES = {"instagram": (1080, 1080), "linkedin": (1200, 627), "twitter": (1200, 675)}


def _generar_figura_velas(ticker: str) -> go.Figure:
    df = yf.download(ticker, period="6mo", progress=False, auto_adjust=True).dropna()
    if df.empty:
        return go.Figure()
    # Manejar MultiIndex si viene de yf con auto_adjust
    if hasattr(df.columns, "get_level_values"):
        ohlc = {c: df[c].squeeze() if hasattr(df[c], "squeeze") else df[c]
                for c in ["Open", "High", "Low", "Close"]}
    else:
        ohlc = {c: df[c] for c in ["Open", "High", "Low", "Close"]}
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=ohlc["Open"], high=ohlc["High"],
        low=ohlc["Low"],  close=ohlc["Close"],
        name=ticker,
    )])
    close = ohlc["Close"]
    fig.add_scatter(x=df.index, y=close.rolling(30).mean().values,
                    mode="lines", name="SMA30", line={"color": "#1F4E79", "width": 1.5})
    fig.update_layout(
        title=f"{ticker} — últimos 6 meses",
        xaxis_rangeslider_visible=False,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    return fig


def generar_ficha_activo(
    ticker: str,
    precio_entrada: float | None = None,
    fecha_entrada: str | None = None,
) -> dict:
    """
    Genera ficha completa de un activo: score MOD-23, gráfico de velas, recomendación.
    Retorna dict con keys: ticker, score_tecnico, score_fundamental, score_total,
    recomendacion, figura_velas, detalle_tecnico, detalle_fundamental.
    """
    _ = (precio_entrada, fecha_entrada)
    st, det_t = score_tecnico(ticker)
    sf, det_f = score_fundamental(ticker)
    score_total = float((st + sf) / 2.0)
    rec = next(r for umbral, r in RECOMENDACION_RULES if score_total >= umbral)
    return {
        "ticker":            ticker,
        "score_tecnico":     float(st),
        "score_fundamental": float(sf),
        "score_total":       score_total,
        "recomendacion":     rec,
        "figura_velas":      _generar_figura_velas(ticker),
        "detalle_tecnico":   det_t,
        "detalle_fundamental": det_f,
    }


def exportar_para_rrss(fig: go.Figure, formato: str = "instagram") -> bytes:
    """Exporta figura como PNG con dimensiones para redes sociales."""
    try:
        import kaleido  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "kaleido no instalado. Ejecutar: pip install kaleido==0.2.1"
        ) from None
    w, h = DIMENSIONES.get(formato, DIMENSIONES["instagram"])
    return fig.to_image(format="png", width=w, height=h, scale=2)

DIMENSIONES = {"instagram": (1080, 1080), "linkedin": (1200, 627), "twitter": (1200, 675)}


def exportar_ficha_para_rrss(fig: "go.Figure", formato: str = "instagram") -> bytes:
    """Exporta figura de velas como PNG para redes sociales. Requiere kaleido==0.2.1."""
    try:
        import kaleido  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "kaleido no instalado. Ejecutar: pip install kaleido==0.2.1"
        ) from None
    w, h = DIMENSIONES.get(formato, DIMENSIONES["instagram"])
    return fig.to_image(format="png", width=w, height=h, scale=2)
