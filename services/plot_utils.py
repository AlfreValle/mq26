"""
services/plot_utils.py — Template Gráfico Institucional MQ26-DSS
Aplica tema oscuro, fuente Inter, colores de acento y watermark consistentes.
"""
from __future__ import annotations

import plotly.graph_objects as go

# ─── PALETA INSTITUCIONAL ────────────────────────────────────────────────────
MQ26_COLORS = {
    "accent":  "#2E86AB",
    "accent2": "#1A6A8A",
    "success": "#27AE60",
    "warning": "#F39C12",
    "danger":  "#E74C3C",
    "purple":  "#8E44AD",
    "teal":    "#1ABC9C",
    "orange":  "#E67E22",
    "gray":    "#7F8C8D",
    "white":   "#E8E8F0",
}

MQ26_SEQUENCE = [
    "#2E86AB", "#27AE60", "#E74C3C", "#F39C12",
    "#8E44AD", "#1ABC9C", "#E67E22", "#C0392B",
    "#3498DB", "#2ECC71",
]


def apply_mq26_layout(
    fig: go.Figure,
    title: str = "",
    height: int = 400,
    show_legend: bool = True,
    legend_bottom: bool = False,
    x_title: str = "",
    y_title: str = "",
) -> go.Figure:
    """
    Aplica el template institucional MQ26 a cualquier figura Plotly.
    Incluye fondo oscuro, fuente Inter, watermark y colores de acento.
    """
    legend_cfg = dict(
        font=dict(color="#E8E8F0", size=11),
        bgcolor="rgba(18,18,30,0.8)",
        bordercolor="rgba(46,134,171,0.3)",
        borderwidth=1,
    )
    if legend_bottom:
        legend_cfg.update(dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(family="Inter, sans-serif", size=16, color="#E8E8F0"),
            x=0,
        ),
        height=height,
        template="plotly_dark",
        paper_bgcolor="#0A0A14",
        plot_bgcolor="#12121E",
        font=dict(family="Inter, sans-serif", color="#E8E8F0"),
        xaxis=dict(
            title=x_title,
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(46,134,171,0.3)",
            title_font=dict(size=11, color="#A0A0B8"),
        ),
        yaxis=dict(
            title=y_title,
            gridcolor="rgba(255,255,255,0.06)",
            linecolor="rgba(46,134,171,0.3)",
            title_font=dict(size=11, color="#A0A0B8"),
        ),
        legend=legend_cfg if show_legend else dict(visible=False),
        margin=dict(l=50, r=20, t=50, b=40),
        # Watermark MQ26
        annotations=[
            dict(
                text="MQ26-DSS",
                xref="paper", yref="paper",
                x=0.98, y=0.02,
                xanchor="right", yanchor="bottom",
                font=dict(size=9, color="rgba(255,255,255,0.08)"),
                showarrow=False,
            )
        ],
    )
    return fig


def mq26_line(
    x, y,
    name: str = "",
    color: str = "#2E86AB",
    dash: str = "solid",
    width: int = 2,
) -> go.Scatter:
    """Traza de línea con estilo institucional."""
    return go.Scatter(
        x=x, y=y, name=name, mode="lines",
        line=dict(color=color, width=width, dash=dash),
    )


def mq26_bar(
    x, y,
    name: str = "",
    color: str = "#2E86AB",
    opacity: float = 0.85,
) -> go.Bar:
    """Traza de barras con estilo institucional."""
    return go.Bar(
        x=x, y=y, name=name,
        marker=dict(color=color, opacity=opacity,
                    line=dict(color="rgba(0,0,0,0.2)", width=0.5)),
    )


def progress_bar_html(pct: float, max_pct: float = 100.0) -> str:
    """
    Genera HTML de barra de progreso coloreada para usar en st.markdown().
    Verde 0-79%, Amarillo 80-99%, Rojo/estrella 100%+.
    """
    ratio = min(1.0, max(0.0, pct / max_pct)) if max_pct > 0 else 0.0
    width = ratio * 100
    if pct >= max_pct:
        cls = "mq26-progress-danger"
        label = f"⭐ {pct:.0f}%"
    elif pct >= max_pct * 0.8:
        cls = "mq26-progress-yellow"
        label = f"{pct:.0f}%"
    else:
        cls = "mq26-progress-verde"
        label = f"{pct:.0f}%"

    return (
        f'<div style="display:flex;align-items:center;gap:8px;">'
        f'<div class="mq26-progress-bar-container" style="flex:1;">'
        f'<div class="mq26-progress-bar {cls}" style="width:{width:.1f}%;"></div>'
        f'</div>'
        f'<span style="font-size:0.8rem;color:#E8E8F0;min-width:42px;">{label}</span>'
        f'</div>'
    )


def metric_card_html(
    label: str,
    value: str,
    delta: str | None = None,
    delta_positive: bool | None = None,
) -> str:
    """
    Genera HTML de una metric card institucional con delta colorizado.
    delta_positive=True → verde, False → rojo, None → gris.
    """
    delta_html = ""
    if delta:
        cls = "delta-pos" if delta_positive is True else (
              "delta-neg" if delta_positive is False else "delta-neu")
        icon = "▲" if delta_positive is True else ("▼" if delta_positive is False else "●")
        delta_html = f'<div class="delta {cls}">{icon} {delta}</div>'

    return (
        f'<div class="mq26-metric-card">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )
