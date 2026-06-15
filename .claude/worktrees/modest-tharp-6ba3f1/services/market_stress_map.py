from __future__ import annotations

import plotly.graph_objects as go
import scipy.signal
import yfinance as yf

DIMENSIONES: dict[str, tuple[int, int]] = {
    "instagram": (1080, 1080),
    "linkedin":  (1200, 627),
    "twitter":   (1200, 675),
}


def generar_mapa_estres_spy(start: str = "1998-01-01") -> go.Figure:
    """SPY indexado base=100 desde start, con anotaciones de correcciones > 15%."""
    data = yf.download("SPY", start=start, progress=False, auto_adjust=True)["Close"].dropna()
    if isinstance(data.columns, object) and hasattr(data, "squeeze"):
        data = data.squeeze()
    base = data / float(data.iloc[0]) * 100.0
    draw = (base - base.cummax()) / base.cummax()
    peaks, _ = scipy.signal.find_peaks((-draw).values, height=0.15, distance=120)
    fig = go.Figure()
    fig.add_scatter(x=base.index, y=base.values, mode="lines",
                    name="SPY (base 100)", line={"color": "#1A6B3C", "width": 1.5})
    for i in peaks[:8]:
        fig.add_annotation(
            x=base.index[i], y=float(base.iloc[i]),
            text=f"{draw.iloc[i]:.1%}",
            showarrow=True, arrowhead=2, arrowsize=0.8,
            font={"size": 10}, bgcolor="rgba(255,255,255,0.8)",
        )
    fig.update_layout(
        title="Mapa de estrés — SPY histórico",
        xaxis_title="Fecha", yaxis_title="Índice (base 100)",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    return fig


def generar_vix_historico(start: str = "1998-01-01") -> go.Figure:
    """VIX histórico con línea umbral=20 y picos > 40 anotados automáticamente."""
    data = yf.download("^VIX", start=start, progress=False, auto_adjust=True)["Close"].dropna()
    if hasattr(data, "squeeze"):
        data = data.squeeze()
    peaks, _ = scipy.signal.find_peaks(data.values, height=40, distance=60)
    fig = go.Figure()
    fig.add_scatter(x=data.index, y=data.values, mode="lines",
                    name="VIX", line={"color": "#C00000", "width": 1.2})
    fig.add_hline(y=20, line_dash="dash", line_color="#888",
                  annotation_text="Umbral de estrés (20)")
    for i in peaks[:10]:
        fig.add_annotation(
            x=data.index[i], y=float(data.iloc[i]),
            text=f"{float(data.iloc[i]):.0f}",
            showarrow=True, arrowhead=2, arrowsize=0.8,
            font={"size": 10}, bgcolor="rgba(255,255,255,0.8)",
        )
    fig.update_layout(
        title="VIX histórico — índice de volatilidad S&P 500",
        xaxis_title="Fecha", yaxis_title="VIX",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
    )
    return fig


def exportar_para_rrss(fig: go.Figure, formato: str = "instagram") -> bytes:
    """
    Exporta figura Plotly como PNG con dimensiones para redes sociales.
    Requiere kaleido (pip install kaleido==0.2.1).
    """
    try:
        import kaleido  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "kaleido no instalado. Ejecutar: pip install kaleido==0.2.1"
        ) from None
    w, h = DIMENSIONES.get(formato, DIMENSIONES["instagram"])
    return fig.to_image(format="png", width=w, height=h, scale=2)
