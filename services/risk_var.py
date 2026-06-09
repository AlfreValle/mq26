"""
services/risk_var.py — Motor de Riesgo VaR / CVaR en Tiempo Real
Mejora #7 Profesional

Calcula el Value at Risk (VaR) y Conditional VaR (CVaR) de la cartera
usando simulación histórica de 252 días.

"Con 95% de probabilidad, tu cartera no pierde más de USD X esta semana."

Diferenciador clave: ninguna app de broker argentino ofrece esto.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RISK_FREE_RATE
from core.cache_manager import cache_yfinance_close_matrix
from core.pricing_utils import es_instrumento_local_ars


def calcular_var_cvar(
    tickers:          list[str],
    cantidades:       dict[str, float],    # {ticker: cantidad}
    precios_ars:      dict[str, float],    # {ticker: precio_ars_actual}
    ccl:              float,
    horizonte_dias:   int   = 5,           # horizonte en días hábiles
    nivel_confianza:  float = 0.95,        # 95% o 99%
    periodo_hist:     str   = "1y",
    ccl_series:       pd.Series | None = None,
) -> dict:
    """
    Calcula VaR y CVaR por simulación histórica.

    Metodología:
    1. Descarga retornos históricos de cada activo
    2. Calcula retornos del portafolio ponderados
    3. VaR = percentil (1-confianza) de la distribución de retornos
    4. CVaR = promedio de pérdidas peores que el VaR
    5. Escala al horizonte dado (√T rule)
    """
    mapa_yf = {"BRKB":"BRK-B","YPFD":"YPFD.BA","CEPU":"CEPU.BA",
               "TGNO4":"TGNO4.BA","PAMP":"PAMP.BA","GGAL":"GGAL.BA"}

    # Calcular pesos por valor de mercado
    valor_total = sum(cantidades.get(t, 0) * precios_ars.get(t, 0) for t in tickers)
    if valor_total <= 0:
        return {}

    pesos = {t: (cantidades.get(t, 0) * precios_ars.get(t, 0)) / valor_total
             for t in tickers}

    # Descargar retornos históricos (cacheado vía cache_manager)
    tickers_yf = [mapa_yf.get(t, t) for t in tickers]
    try:
        data = cache_yfinance_close_matrix(tuple(tickers_yf), periodo_hist)
        if data.empty:
            return {}
        rename_r = {v: k for k, v in mapa_yf.items()}
        data = data.rename(columns=rename_r)
    except Exception:
        return {}

    rets = data.pct_change().dropna()
    if rets.empty or len(rets) < 30:
        return {}

    # Retorno del portafolio = suma ponderada.
    # Para tickers no locales (USD/subyacente), se ajusta por retorno FX cuando hay serie de CCL.
    ret_port = pd.Series(0.0, index=rets.index)
    fx_adj = False
    fx_ret = None
    if ccl_series is not None and not ccl_series.empty:
        fx_ret = pd.to_numeric(ccl_series, errors="coerce").pct_change().reindex(rets.index).fillna(0.0)
    for ticker in tickers:
        if ticker in rets.columns:
            w = pesos.get(ticker, 0)
            r_t = rets[ticker]
            if fx_ret is not None and not es_instrumento_local_ars(ticker):
                r_t = (1.0 + r_t) * (1.0 + fx_ret) - 1.0
                fx_adj = True
            ret_port += r_t * w

    # VaR diario
    var_diario = float(np.percentile(ret_port, (1 - nivel_confianza) * 100))

    # CVaR (Expected Shortfall) = promedio de pérdidas peores que VaR
    peores = ret_port[ret_port <= var_diario]
    cvar_diario = float(peores.mean()) if len(peores) > 0 else var_diario

    # Escalar al horizonte (√T rule)
    factor_t    = math.sqrt(horizonte_dias)
    var_horizonte   = var_diario   * factor_t
    cvar_horizonte  = cvar_diario  * factor_t

    # Convertir a USD
    valor_usd   = valor_total / ccl if ccl > 0 else 0
    var_usd     = abs(var_horizonte)   * valor_usd
    cvar_usd    = abs(cvar_horizonte)  * valor_usd
    var_ars     = var_usd  * ccl
    cvar_ars    = cvar_usd * ccl

    # Volatilidad anual del portafolio
    vol_anual   = float(ret_port.std() * math.sqrt(252) * 100)

    # Sharpe del portafolio
    ret_anual   = float(ret_port.mean() * 252 * 100)
    sharpe      = (ret_anual - RISK_FREE_RATE * 100) / vol_anual if vol_anual > 0 else 0

    # Contribución al riesgo por activo
    contrib = {}
    for ticker in tickers:
        if ticker in rets.columns:
            cov     = float(rets[ticker].cov(ret_port))
            w       = pesos.get(ticker, 0)
            contrib[ticker] = round(w * cov / float(ret_port.var()) * 100, 1) if ret_port.var() > 0 else 0

    return {
        "var_pct":          round(var_horizonte   * 100, 2),
        "cvar_pct":         round(cvar_horizonte  * 100, 2),
        "var_usd":          round(var_usd,  0),
        "cvar_usd":         round(cvar_usd, 0),
        "var_ars":          round(var_ars,  0),
        "cvar_ars":         round(cvar_ars, 0),
        "valor_total_usd":  round(valor_usd, 0),
        "valor_total_ars":  round(valor_total, 0),
        "horizonte_dias":   horizonte_dias,
        "nivel_confianza":  nivel_confianza,
        "vol_anual_pct":    round(vol_anual, 1),
        "sharpe_portfolio": round(sharpe, 2),
        "contrib_riesgo":   contrib,
        "distribucion_rets": ret_port.tolist(),
        "fx_adjusted": fx_adj,
        "mensaje": (
            f"Con {nivel_confianza*100:.0f}% de confianza, "
            f"tu cartera NO pierde más de "
            f"USD {var_usd:,.0f} (ARS {var_ars:,.0f}) "
            f"en los próximos {horizonte_dias} días hábiles."
        ),
    }


def render_var_cvar(
    tickers:      list[str],
    cantidades:   dict[str, float],
    precios_ars:  dict[str, float],
    ccl:          float,
):
    """Renderiza el panel de riesgo VaR/CVaR."""
    st.markdown("## 🛡️ Motor de Riesgo — VaR & CVaR")
    st.caption(
        "Calculado por simulación histórica de 252 días. "
        "Metodología estándar de gestión de riesgo institucional."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        horizonte = st.selectbox("Horizonte", [1, 5, 10, 21], index=1,
                                  format_func=lambda x: f"{x} día{'s' if x>1 else ''}",
                                  key="var_horizonte")
    with c2:
        confianza = st.selectbox("Nivel confianza", [0.95, 0.99],
                                  format_func=lambda x: f"{x*100:.0f}%",
                                  key="var_confianza")
    with c3:
        periodo = st.selectbox("Datos históricos", ["6mo","1y","2y"], index=1,
                                key="var_periodo")

    with st.spinner("Calculando VaR/CVaR..."):
        resultado = calcular_var_cvar(
            tickers=tickers, cantidades=cantidades,
            precios_ars=precios_ars, ccl=ccl,
            horizonte_dias=horizonte,
            nivel_confianza=confianza,
            periodo_hist=periodo,
        )

    if not resultado:
        st.warning("Sin datos suficientes. Verificá conexión a internet.")
        return

    # ── Mensaje principal ─────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);
                border-radius:12px;padding:20px;margin:10px 0;
                border-left:5px solid #e74c3c">
      <h3 style="color:white;margin:0 0 8px">🛡️ Riesgo de la cartera</h3>
      <p style="color:#ccc;font-size:14px;margin:0">{resultado['mensaje']}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── 4 métricas clave ──────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"VaR {confianza*100:.0f}% ({horizonte}d)",
              f"USD {resultado['var_usd']:,.0f}",
              f"ARS {resultado['var_ars']/1e6:.2f}M",
              delta_color="inverse")
    m2.metric(f"CVaR ({horizonte}d)",
              f"USD {resultado['cvar_usd']:,.0f}",
              "Pérdida esperada si se supera VaR",
              delta_color="inverse")
    m3.metric("Volatilidad Anual", f"{resultado['vol_anual_pct']:.1f}%")
    m4.metric("Sharpe Portfolio",  f"{resultado['sharpe_portfolio']:.2f}")

    # ── Distribución de retornos ──────────────────────────────────────
    rets_arr = np.array(resultado["distribucion_rets"]) * 100
    var_line = resultado["var_pct"]
    cvar_line= resultado["cvar_pct"]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=rets_arr, nbinsx=50,
        marker_color="#00b4d8", opacity=0.7,
        name="Retornos diarios",
    ))
    # Zona de pérdida > VaR
    fig.add_vrect(
        x0=rets_arr.min(), x1=var_line,
        fillcolor="rgba(220,53,69,0.2)", layer="below",
        annotation_text=f"Zona VaR ({confianza*100:.0f}%)", annotation_position="top left",
        annotation_font_color="#dc3545",
    )
    fig.add_vline(x=var_line,  line_dash="dash", line_color="#dc3545",
                  annotation_text=f"VaR {var_line:.2f}%")
    fig.add_vline(x=cvar_line, line_dash="dot",  line_color="#e67e22",
                  annotation_text=f"CVaR {cvar_line:.2f}%")
    fig.add_vline(x=0, line_dash="solid", line_color="#666", line_width=1)

    fig.update_layout(
        title="Distribución de retornos históricos del portafolio",
        xaxis_title="Retorno diario (%)",
        yaxis_title="Frecuencia",
        height=350,
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#1a1a2e",
        font=dict(color="white"),
        margin=dict(l=10, r=10, t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Contribución al riesgo ────────────────────────────────────────
    st.markdown("#### ⚖️ Contribución al riesgo por activo")
    contrib = resultado.get("contrib_riesgo", {})
    if contrib:
        df_c = pd.DataFrame([
            {"Ticker": t, "Contribución al riesgo %": v,
             "Rol": "🔴 Mayor riesgo" if v > 20 else "🟡 Moderado" if v > 10 else "🟢 Bajo riesgo"}
            for t, v in sorted(contrib.items(), key=lambda x: -x[1])
        ])
        st.dataframe(df_c, use_container_width=True, hide_index=True)
