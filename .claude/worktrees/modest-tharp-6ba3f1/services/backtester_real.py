"""
services/backtester_real.py — Backtesting Real de Cartera vs Benchmark
Mejora #6 de Estrategia

Conecta el historial real de operaciones (desde 2021) con precios históricos
para calcular la equity curve real vs SPY.

Métricas calculadas:
  - Retorno total y anualizado en USD
  - Sharpe ratio realizado
  - Máximo drawdown
  - Alfa vs SPY (cuánto ganaste de más)
  - Calmar ratio (retorno / max drawdown)
"""
from __future__ import annotations

import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RISK_FREE_RATE
from core.cache_manager import cache_yfinance_close_range


def calcular_equity_curve_real(
    df_operaciones: pd.DataFrame,
    ccl_historico:  dict[str, float],
    capital_inicial: float = 10_000.0,   # USD
) -> pd.DataFrame:
    """
    Reconstruye la equity curve real a partir del historial de operaciones.

    df_operaciones: columnas Ticker, Tipo_Op (COMPRA/VENTA), Cantidad,
                    Precio_ARS, FECHA_INICIAL
    ccl_historico: {AAAA-MM: ccl_float}

    Devuelve DataFrame con columnas: fecha, valor_usd, retorno_diario
    """
    if df_operaciones.empty:
        return pd.DataFrame()

    # Normalizar
    df = df_operaciones.copy()
    df["FECHA_INICIAL"] = pd.to_datetime(df.get("FECHA_INICIAL", df.get("Fecha")),
                                          errors="coerce")
    df = df.dropna(subset=["FECHA_INICIAL"])
    df = df.sort_values("FECHA_INICIAL")

    fecha_inicio = df["FECHA_INICIAL"].min().date()
    fecha_fin    = date.today()

    # Obtener precios históricos de todos los tickers
    tickers_unicos = df["Ticker"].str.upper().unique().tolist()
    mapa_yf = {"BRKB":"BRK-B","YPFD":"YPFD.BA","CEPU":"CEPU.BA",
               "TGNO4":"TGNO4.BA","PAMP":"PAMP.BA","GGAL":"GGAL.BA"}
    tickers_yf = [mapa_yf.get(t, t) for t in tickers_unicos]

    try:
        _start = (fecha_inicio - timedelta(days=5)).isoformat()
        _end = fecha_fin.isoformat()
        _syms = tuple(tickers_yf + ["SPY"])
        precios = cache_yfinance_close_range(_syms, _start, _end)
        if precios.empty:
            return pd.DataFrame(columns=["fecha", "valor_usd", "spy_usd"])
        # Renombrar columnas a tickers locales
        rename_map = {v: k for k, v in mapa_yf.items()}
        precios.rename(columns=rename_map, inplace=True)
    except Exception:
        return pd.DataFrame(columns=["fecha","valor_usd","spy_usd"])

    precios = precios.ffill()

    # Reconstruir CCL histórico por fecha
    def get_ccl_fecha(fecha):
        key = str(fecha)[:7]
        return float(ccl_historico.get(key, 1200.0))

    # Simular cartera día a día
    posiciones: dict[str, float] = {}   # {ticker: cantidad}
    fecha_range = pd.date_range(fecha_inicio, fecha_fin, freq="B")

    valores_cartera = []
    valores_spy     = []
    spy_cant_ref    = None
    spy_precio_ref  = None

    for fecha in fecha_range:
        fecha_d = fecha.date()

        # Procesar operaciones de este día
        ops_dia = df[df["FECHA_INICIAL"].dt.date == fecha_d]
        for _, op in ops_dia.iterrows():
            t    = str(op["Ticker"]).upper().strip()
            cant = float(op.get("Cantidad", 0))
            tipo = str(op.get("Tipo_Op", "")).upper()
            if tipo == "COMPRA":
                posiciones[t] = posiciones.get(t, 0) + cant
            elif tipo == "VENTA":
                posiciones[t] = max(0, posiciones.get(t, 0) - cant)

        # Calcular valor de la cartera en USD
        valor_usd = 0.0
        ccl_dia   = get_ccl_fecha(fecha_d)
        if fecha in precios.index:
            for ticker, cant in posiciones.items():
                if cant <= 0:
                    continue
                if ticker in precios.columns:
                    px = float(precios.loc[fecha, ticker])
                elif mapa_yf.get(ticker, ticker) in precios.columns:
                    px = float(precios.loc[fecha, mapa_yf.get(ticker, ticker)])
                else:
                    continue

                # Precio en USD del CEDEAR
                if ticker.endswith(".BA") or ticker in {"YPFD","CEPU","TGNO4","PAMP","GGAL"}:
                    px_usd = px / ccl_dia   # Acción local → ARS/CCL
                else:
                    px_usd = px              # Ya en USD

                valor_usd += cant * px_usd

        # SPY de referencia (inversión equivalente al capital_inicial)
        if "SPY" in precios.columns and fecha in precios.index:
            spy_px = float(precios.loc[fecha, "SPY"])
            if spy_cant_ref is None and spy_px > 0:
                spy_cant_ref  = capital_inicial / spy_px
                spy_precio_ref = spy_px
            spy_val = spy_cant_ref * spy_px if spy_cant_ref else 0

        valores_cartera.append({"fecha": fecha_d, "valor_usd": max(0, valor_usd)})
        valores_spy.append({"fecha": fecha_d, "spy_usd": spy_val if spy_cant_ref else 0})

    df_eq   = pd.DataFrame(valores_cartera)
    df_spy  = pd.DataFrame(valores_spy)
    df_out  = df_eq.merge(df_spy, on="fecha", how="left")
    df_out  = df_out[df_out["valor_usd"] > 0].reset_index(drop=True)

    if len(df_out) < 2:
        return df_out

    df_out["retorno_diario"]     = df_out["valor_usd"].pct_change()
    df_out["retorno_diario_spy"] = df_out["spy_usd"].pct_change()

    return df_out


def calcular_metricas(df_eq: pd.DataFrame, capital_inicial: float = 10_000.0) -> dict:
    """Calcula métricas de performance a partir de la equity curve."""
    if df_eq.empty or len(df_eq) < 10:
        return {}

    valor_final  = float(df_eq["valor_usd"].iloc[-1])
    valor_inicio = float(df_eq["valor_usd"][df_eq["valor_usd"] > 0].iloc[0])
    n_dias       = len(df_eq)
    n_años       = n_dias / 252

    # Retornos
    ret_total    = (valor_final / valor_inicio - 1) * 100 if valor_inicio > 0 else 0
    ret_anual    = ((valor_final / valor_inicio) ** (1 / n_años) - 1) * 100 if n_años > 0 and valor_inicio > 0 else 0

    # Sharpe
    rets = df_eq["retorno_diario"].dropna()
    vol_anual = float(rets.std() * math.sqrt(252) * 100) if len(rets) > 5 else 0
    sharpe    = (ret_anual - RISK_FREE_RATE * 100) / vol_anual if vol_anual > 0 else 0

    # Max Drawdown
    rolling_max = df_eq["valor_usd"].cummax()
    drawdown    = (df_eq["valor_usd"] / rolling_max - 1) * 100
    max_dd      = float(drawdown.min())
    calmar      = abs(ret_anual / max_dd) if max_dd < 0 else 0

    # Alfa vs SPY
    if "spy_usd" in df_eq.columns:
        spy_inicio = float(df_eq["spy_usd"][df_eq["spy_usd"] > 0].iloc[0])
        spy_final  = float(df_eq["spy_usd"].iloc[-1])
        ret_spy    = (spy_final / spy_inicio - 1) * 100 if spy_inicio > 0 else 0
        alfa       = ret_total - ret_spy
    else:
        ret_spy = 0
        alfa    = 0

    return {
        "valor_inicial_usd":  round(valor_inicio, 2),
        "valor_final_usd":    round(valor_final, 2),
        "retorno_total_pct":  round(ret_total, 1),
        "retorno_anual_pct":  round(ret_anual, 1),
        "volatilidad_anual":  round(vol_anual, 1),
        "sharpe_ratio":       round(sharpe, 2),
        "max_drawdown_pct":   round(max_dd, 1),
        "calmar_ratio":       round(calmar, 2),
        "retorno_spy_pct":    round(ret_spy, 1),
        "alfa_vs_spy_pct":    round(alfa, 1),
        "dias_activo":        n_dias,
        "años_activo":        round(n_años, 1),
    }


def render_backtester(
    df_operaciones: pd.DataFrame,
    ccl_historico:  dict[str, float],
    capital_inicial: float = 10_000.0,
):
    """Renderiza el backtester completo en Streamlit."""
    st.markdown("## 📈 Backtesting Real — Cartera vs SPY")
    st.caption(
        "Equity curve calculada a partir del historial real de operaciones desde 2021. "
        "Muestra el alfa real generado por la selección de activos vs comprar SPY y esperar."
    )

    with st.spinner("Calculando equity curve histórica..."):
        df_eq = calcular_equity_curve_real(df_operaciones, ccl_historico, capital_inicial)

    if df_eq.empty:
        st.warning("Sin datos históricos suficientes. Verificá que yfinance esté disponible.")
        return

    metricas = calcular_metricas(df_eq, capital_inicial)

    # ── Métricas principales ──────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📈 Retorno Total",   f"{metricas.get('retorno_total_pct',0):+.1f}%")
    c2.metric("⚡ Retorno Anual",   f"{metricas.get('retorno_anual_pct',0):+.1f}%",
              f"SPY: {metricas.get('retorno_spy_pct',0):+.1f}%")
    c3.metric("📊 Sharpe",          f"{metricas.get('sharpe_ratio',0):.2f}")
    c4.metric("📉 Max Drawdown",    f"{metricas.get('max_drawdown_pct',0):.1f}%")
    c5.metric("🏆 Alfa vs SPY",     f"{metricas.get('alfa_vs_spy_pct',0):+.1f}%",
              "ganancia extra vs índice")

    # ── Equity curve ──────────────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_eq["fecha"], y=df_eq["valor_usd"],
        name="Mi Cartera", line=dict(color="#00b4d8", width=2.5),
        fill="tozeroy", fillcolor="rgba(0,180,216,0.1)",
    ))

    if "spy_usd" in df_eq.columns and df_eq["spy_usd"].max() > 0:
        fig.add_trace(go.Scatter(
            x=df_eq["fecha"], y=df_eq["spy_usd"],
            name="SPY (benchmark)", line=dict(color="#f0ad4e", width=1.5, dash="dot"),
        ))

    # Drawdown overlay
    rolling_max = df_eq["valor_usd"].cummax()
    fig.add_trace(go.Scatter(
        x=df_eq["fecha"], y=rolling_max,
        name="Máximo histórico", line=dict(color="#666", width=1, dash="dot"),
        opacity=0.4,
    ))

    fig.update_layout(
        title="Equity Curve Real (USD)",
        xaxis_title="Fecha",
        yaxis_title="Valor USD",
        height=400,
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        legend=dict(bgcolor="#0f3460"),
        margin=dict(l=10, r=10, t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Drawdown chart ────────────────────────────────────────────────
    if len(df_eq) > 10:
        dd = (df_eq["valor_usd"] / df_eq["valor_usd"].cummax() - 1) * 100
        fig_dd = go.Figure(go.Scatter(
            x=df_eq["fecha"], y=dd,
            fill="tozeroy", fillcolor="rgba(220,53,69,0.3)",
            line=dict(color="#dc3545", width=1),
            name="Drawdown %",
        ))
        fig_dd.update_layout(
            title="Drawdown (%)", height=200,
            plot_bgcolor="#1a1a2e", paper_bgcolor="#1a1a2e",
            font=dict(color="white"),
            margin=dict(l=10, r=10, t=40, b=30),
            yaxis=dict(ticksuffix="%"),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

    # ── Resumen en tabla ─────────────────────────────────────────────
    st.markdown("#### 📋 Resumen de performance")
    df_res = pd.DataFrame([
        {"Métrica": "Retorno Total",       "Cartera": f"{metricas.get('retorno_total_pct',0):+.1f}%",   "SPY": f"{metricas.get('retorno_spy_pct',0):+.1f}%"},
        {"Métrica": "Retorno Anualizado",  "Cartera": f"{metricas.get('retorno_anual_pct',0):+.1f}%",  "SPY": "~12.5%"},
        {"Métrica": "Sharpe Ratio",        "Cartera": f"{metricas.get('sharpe_ratio',0):.2f}",         "SPY": "~0.85"},
        {"Métrica": "Volatilidad Anual",   "Cartera": f"{metricas.get('volatilidad_anual',0):.1f}%",   "SPY": "~18%"},
        {"Métrica": "Max Drawdown",        "Cartera": f"{metricas.get('max_drawdown_pct',0):.1f}%",    "SPY": "~-34%"},
        {"Métrica": "Calmar Ratio",        "Cartera": f"{metricas.get('calmar_ratio',0):.2f}",         "SPY": "~0.37"},
        {"Métrica": "Alfa vs SPY",         "Cartera": f"{metricas.get('alfa_vs_spy_pct',0):+.1f}%",   "SPY": "—"},
        {"Métrica": "Años activo",         "Cartera": f"{metricas.get('años_activo',0):.1f}",          "SPY": "—"},
    ])
    st.dataframe(df_res, use_container_width=True, hide_index=True)
