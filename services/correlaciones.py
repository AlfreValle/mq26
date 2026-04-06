"""
services/correlaciones.py — Mapa de Calor de Correlaciones
Mejora #2 de Diseño

Heatmap interactivo que muestra correlaciones entre activos de la cartera.
Identifica riesgo de concentración oculto y verdaderos diversificadores.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def obtener_retornos_historicos(
    tickers: list[str],
    periodo: str = "1y",
) -> pd.DataFrame:
    """Descarga retornos diarios para una lista de tickers."""
    mapa = {"BRKB":"BRK-B","YPFD":"YPFD.BA","CEPU":"CEPU.BA",
            "TGNO4":"TGNO4.BA","PAMP":"PAMP.BA","GGAL":"GGAL.BA"}
    tickers_yf = [mapa.get(t.upper(), t.upper()) for t in tickers]

    try:
        data = yf.download(tickers_yf, period=periodo,
                           auto_adjust=True, progress=False)["Close"]
        if isinstance(data, pd.Series):
            data = data.to_frame(tickers[0])
        data.columns = tickers[:len(data.columns)]
        retornos = data.pct_change().dropna()
        return retornos
    except Exception:
        return pd.DataFrame()


def calcular_matriz_correlacion(retornos: pd.DataFrame) -> pd.DataFrame:
    """Calcula la matriz de correlación de Pearson."""
    return retornos.corr(method="pearson")


def alertas_pares_correlacion(corr: pd.DataFrame, umbral: float = 0.75) -> pd.DataFrame:
    """
    Pares con |ρ| ≥ umbral (lógica pura para tests y orquestación UI).
    Columnas: Par, Correlación, Tipo, Riesgo.
    """
    if corr.empty or corr.shape[0] < 2:
        return pd.DataFrame(columns=["Par", "Correlación", "Tipo", "Riesgo"])
    u = float(umbral)
    pares: list[dict] = []
    cols = corr.columns
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c = float(corr.iloc[i, j])
            if abs(c) >= u:
                pares.append(
                    {
                        "Par": f"{cols[i]} ↔ {cols[j]}",
                        "Correlación": round(c, 3),
                        "Tipo": "🔴 Alta correlación" if c >= u else "🟢 Anticorrelado",
                        "Riesgo": "Concentración oculta" if c >= u else "Diversificador real",
                    }
                )
    if not pares:
        return pd.DataFrame(columns=["Par", "Correlación", "Tipo", "Riesgo"])
    return pd.DataFrame(pares).sort_values("Correlación", ascending=False)


def resumen_correlacion_promedio(corr: pd.DataFrame) -> pd.DataFrame:
    """Promedio de |ρ| por activo excluyendo diagonal (NaN en copia)."""
    if corr.empty:
        return pd.DataFrame(columns=["Ticker", "Corr. promedio", "Rol"])
    corr_sin_diag = corr.copy()
    _vals = corr_sin_diag.values.copy()
    np.fill_diagonal(_vals, np.nan)
    corr_sin_diag = corr_sin_diag.__class__(_vals, index=corr_sin_diag.index, columns=corr_sin_diag.columns)
    corr_prom = corr_sin_diag.mean().sort_values(ascending=True)
    df_prom = pd.DataFrame(
        {
            "Ticker": corr_prom.index,
            "Corr. promedio": corr_prom.values.round(3),
            "Rol": [
                "🟢 Diversificador" if v < 0.4 else "🟡 Neutral" if v < 0.65 else "🔴 Concentrador"
                for v in corr_prom.values
            ],
        }
    )
    return df_prom


def render_heatmap_correlaciones(
    tickers: list[str],
    pesos: dict[str, float] = None,    # {ticker: peso%} para mostrar contexto
    periodo: str = "1y",
):
    """
    Renderiza el heatmap interactivo de correlaciones en Streamlit.
    """
    st.markdown("### 🔥 Mapa de Correlaciones — Cartera")
    st.caption(
        "Correlación de Pearson sobre retornos diarios. "
        "**Verde oscuro** = sin correlación (diversifica). "
        "**Rojo** = alta correlación (riesgo oculto)."
    )

    col1, col2 = st.columns([3, 1])
    with col2:
        periodo_sel = st.selectbox(
            "Período", ["6mo", "1y", "2y", "3y"],
            index=1, key="corr_periodo"
        )

    with st.spinner("Calculando correlaciones..."):
        retornos = obtener_retornos_historicos(tickers, periodo_sel)

    if retornos.empty or len(retornos.columns) < 2:
        st.warning("Necesitás al menos 2 activos con datos para calcular correlaciones.")
        return

    corr = calcular_matriz_correlacion(retornos)

    # ── Heatmap principal ─────────────────────────────────────────────
    fig = go.Figure(data=go.Heatmap(
        z=corr.values,
        x=corr.columns.tolist(),
        y=corr.index.tolist(),
        colorscale=[
            [0.0,  "#1a6b1a"],   # -1 = verde oscuro (anticorrelación)
            [0.5,  "#f5f5f5"],   # 0  = blanco (sin correlación)
            [0.75, "#ff8c00"],   # 0.5 = naranja
            [1.0,  "#cc0000"],   # 1  = rojo (correlación perfecta)
        ],
        zmin=-1, zmax=1,
        text=np.round(corr.values, 2),
        texttemplate="%{text}",
        textfont={"size": 11},
        hoverongaps=False,
        hovertemplate="<b>%{x} vs %{y}</b><br>Correlación: %{z:.3f}<extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text=f"Correlaciones ({periodo_sel}) — {len(tickers)} activos",
            font=dict(size=14)
        ),
        height=max(400, len(tickers) * 45),
        xaxis=dict(side="bottom"),
        margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Alertas de concentración ──────────────────────────────────────
    st.markdown("#### ⚠️ Alertas de correlación")
    df_alertas = alertas_pares_correlacion(corr, umbral=0.75)
    if not df_alertas.empty:
        st.dataframe(df_alertas, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Sin pares con correlación > 0.75. Cartera bien diversificada.")

    # ── Resumen por clusters ──────────────────────────────────────────
    st.markdown("#### 📊 Correlación promedio por activo")
    df_prom = resumen_correlacion_promedio(corr)
    st.dataframe(df_prom, use_container_width=True, hide_index=True)

    return corr
