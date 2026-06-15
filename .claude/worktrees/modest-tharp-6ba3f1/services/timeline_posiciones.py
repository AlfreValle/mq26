"""
services/timeline_posiciones.py — Timeline Visual de Posiciones
Mejora #3 de Diseño

Línea de tiempo horizontal tipo Gantt donde cada barra es una posición.
Muestra: antigüedad, rentabilidad y concentración de un vistazo.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_timeline_posiciones(
    df_posiciones: pd.DataFrame,
    precios_actuales: dict[str, float],
    ccl: float,
    titulo: str = "Timeline de Posiciones",
):
    """
    Renderiza un Gantt chart de posiciones abiertas.

    df_posiciones debe tener: Ticker, Cantidad, PPC_USD, FECHA_INICIAL, Propietario, Cartera
    precios_actuales: {ticker: precio_ARS_actual}
    """
    st.markdown(f"### 📅 {titulo}")
    st.caption(
        "Cada barra = una posición. "
        "**Color**: verde = ganancia, rojo = pérdida, gris = neutral. "
        "**Ancho**: peso en cartera. "
        "**Longitud**: tiempo en cartera."
    )

    if df_posiciones.empty:
        st.info("Sin posiciones para mostrar.")
        return

    from config import RATIOS_CEDEAR

    today   = date.today()
    filas   = []
    val_tot = 0.0

    for _, row in df_posiciones.iterrows():
        ticker = str(row.get("Ticker", row.get("TICKER", ""))).upper().strip()
        cant   = float(row.get("Cantidad", row.get("CANTIDAD", 0)))
        if cant <= 0:
            continue

        ppc_usd = float(row.get("PPC_USD", row.get("PPC_USD_PROM", 0)) or 0)
        fecha_s = str(row.get("FECHA_INICIAL", row.get("Fecha", str(today))))
        try:
            fecha_ini = pd.to_datetime(fecha_s).date()
        except Exception:
            fecha_ini = today

        px_ars  = float(precios_actuales.get(ticker, 0))
        ratio   = float(RATIOS_CEDEAR.get(ticker, 1.0))
        px_usd_actual = (px_ars / ccl) * ratio if ccl > 0 and ratio > 0 else 0.0

        pnl_pct = ((px_usd_actual / ppc_usd) - 1) * 100 if ppc_usd > 0 and px_usd_actual > 0 else 0.0
        valor_ars = cant * px_ars
        val_tot  += valor_ars

        dias = max(1, (today - fecha_ini).days)

        filas.append({
            "ticker":    ticker,
            "fecha_ini": fecha_ini,
            "fecha_fin": today,
            "pnl_pct":   round(pnl_pct, 1),
            "valor_ars": valor_ars,
            "ppc_usd":   ppc_usd,
            "px_actual": round(px_usd_actual, 4),
            "cant":      int(cant),
            "dias":      dias,
        })

    if not filas:
        st.info("Sin posiciones abiertas.")
        return

    df = pd.DataFrame(filas)
    df["peso_pct"] = df["valor_ars"] / val_tot * 100 if val_tot > 0 else 0.0
    df = df.sort_values("fecha_ini")

    # ── Colores por P&L ───────────────────────────────────────────────
    def color_barra(pnl: float) -> str:
        if pnl >= 20:   return "#1a7a1a"
        elif pnl >= 5:  return "#28a745"
        elif pnl >= 0:  return "#5cb85c"
        elif pnl >= -5: return "#f0ad4e"
        elif pnl >= -15:return "#e67e22"
        else:           return "#cc0000"

    # ── Gantt chart ───────────────────────────────────────────────────
    fig = go.Figure()

    for i, row in df.iterrows():
        color  = color_barra(row["pnl_pct"])
        grosor = max(12, min(40, int(row["peso_pct"] * 1.5)))

        # Barra principal
        fig.add_trace(go.Bar(
            x    = [row["dias"]],
            y    = [row["ticker"]],
            base = [0],
            orientation = "h",
            marker = dict(color=color, opacity=0.85, line=dict(color="white", width=1)),
            width = 0.6,
            name  = row["ticker"],
            hovertemplate=(
                f"<b>{row['ticker']}</b><br>"
                f"Desde: {row['fecha_ini'].strftime('%d/%m/%Y')}<br>"
                f"Días en cartera: {row['dias']}<br>"
                f"Cant: {row['cant']} | PPC: USD {row['ppc_usd']:.4f}<br>"
                f"Precio actual: USD {row['px_actual']:.4f}<br>"
                f"P&L: <b>{'+'if row['pnl_pct']>=0 else ''}{row['pnl_pct']:.1f}%</b><br>"
                f"Peso en cartera: {row['peso_pct']:.1f}%<br>"
                f"Valor ARS: ${row['valor_ars']:,.0f}"
                "<extra></extra>"
            ),
            showlegend=False,
        ))

        # Etiqueta P&L sobre la barra
        fig.add_annotation(
            x    = row["dias"] / 2,
            y    = row["ticker"],
            text = f"{'+'if row['pnl_pct']>=0 else ''}{row['pnl_pct']:.0f}%  {row['peso_pct']:.0f}%↑",
            showarrow=False,
            font = dict(size=10, color="white"),
            xanchor="center",
        )

    fig.update_layout(
        title=dict(text=f"Timeline — {len(df)} posiciones · Total ${val_tot/1e6:.2f}M ARS", font=dict(size=13)),
        xaxis=dict(title="Días en cartera", gridcolor="#333"),
        yaxis=dict(title="", tickfont=dict(size=12)),
        height=max(300, len(df) * 52 + 80),
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        margin=dict(l=10, r=20, t=50, b=40),
        bargap=0.25,
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Leyenda de colores ────────────────────────────────────────────
    st.markdown("""
    <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;padding:8px">
        <span style="color:#1a7a1a">■ +20%+</span>
        <span style="color:#28a745">■ +5% a +20%</span>
        <span style="color:#5cb85c">■ 0% a +5%</span>
        <span style="color:#f0ad4e">■ 0% a -5%</span>
        <span style="color:#e67e22">■ -5% a -15%</span>
        <span style="color:#cc0000">■ -15%+</span>
    </div>
    """, unsafe_allow_html=True)
