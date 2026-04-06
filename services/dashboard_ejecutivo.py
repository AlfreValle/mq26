"""
services/dashboard_ejecutivo.py — Dashboard Ejecutivo en Tiempo Real
Mejora #1 de Diseño

Header de 5 métricas animadas con semáforo de color.
El usuario entra y en 3 segundos sabe si tiene que actuar o no.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st


def render_dashboard_ejecutivo(
    df_posiciones: pd.DataFrame,   # cartera activa con VALOR_ARS, INVERSION_ARS
    ccl: float,
    score_promedio: float = 0.0,
    nombre_cartera: str = "",
):
    """
    Renderiza el panel ejecutivo superior de la app.
    Reemplaza las métricas planas por un dashboard con semáforo.
    """
    if df_posiciones.empty:
        st.info("Sin posiciones cargadas.")
        return

    # ── Calcular métricas ─────────────────────────────────────────────
    valor_ars   = float(df_posiciones.get("VALOR_ARS",     pd.Series([0])).sum())
    inv_ars     = float(df_posiciones.get("INVERSION_ARS", pd.Series([0])).sum())
    pnl_ars     = valor_ars - inv_ars
    pnl_pct     = pnl_ars / inv_ars * 100 if inv_ars > 0 else 0.0
    valor_usd   = valor_ars / ccl if ccl > 0 else 0.0
    n_pos       = len(df_posiciones[df_posiciones.get("CANTIDAD_TOTAL", pd.Series([0])) > 0])

    # ── Semáforo de color ─────────────────────────────────────────────
    def color_pnl(pct: float) -> str:
        if pct >= 10:   return "#28a745"   # Verde fuerte
        elif pct >= 0:  return "#5cb85c"   # Verde suave
        elif pct >= -5: return "#f0ad4e"   # Naranja
        else:           return "#dc3545"   # Rojo

    def color_score(sc: float) -> str:
        if sc >= 70:    return "#28a745"
        elif sc >= 50:  return "#f0ad4e"
        else:           return "#dc3545"

    def icono_pnl(pct: float) -> str:
        if pct >= 5:    return "🚀"
        elif pct >= 0:  return "📈"
        elif pct >= -5: return "⚠️"
        else:           return "🔴"

    # ── CSS animaciones ───────────────────────────────────────────────
    st.markdown("""
    <style>
    .mq26-metric {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 16px 20px;
        text-align: center;
        border-left: 4px solid #0f3460;
        transition: transform 0.2s;
        margin: 4px;
    }
    .mq26-metric:hover { transform: translateY(-2px); }
    .mq26-label  { color: #aaa; font-size: 11px; text-transform: uppercase;
                   letter-spacing: 1px; margin-bottom: 6px; }
    .mq26-value  { font-size: 22px; font-weight: 700; margin: 4px 0; }
    .mq26-delta  { font-size: 12px; color: #aaa; }
    .mq26-banner {
        background: linear-gradient(90deg, #1a1a2e, #0f3460);
        color: white; padding: 10px 20px; border-radius: 8px 8px 0 0;
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Banner superior
    st.markdown(f"""
    <div class="mq26-banner">
        <span style="font-weight:700;font-size:16px">📊 {nombre_cartera or 'MQ26 Dashboard'}</span>
        <span style="color:#aaa;font-size:12px">📅 {date.today().strftime('%d/%m/%Y')} · CCL ${ccl:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

    # 5 métricas
    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""
        <div class="mq26-metric" style="border-left-color:#0066cc">
            <div class="mq26-label">💰 Valor ARS</div>
            <div class="mq26-value" style="color:#66b3ff">${valor_ars/1e6:.2f}M</div>
            <div class="mq26-delta">≈ USD {valor_usd:,.0f}</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        c_pnl = color_pnl(pnl_pct)
        st.markdown(f"""
        <div class="mq26-metric" style="border-left-color:{c_pnl}">
            <div class="mq26-label">{icono_pnl(pnl_pct)} P&L Total</div>
            <div class="mq26-value" style="color:{c_pnl}">
                {'+'if pnl_ars>=0 else ''}{pnl_ars/1e6:.2f}M
            </div>
            <div class="mq26-delta">{'+'if pnl_pct>=0 else ''}{pnl_pct:.1f}% desde entrada</div>
        </div>""", unsafe_allow_html=True)

    with c3:
        c_sc = color_score(score_promedio)
        st.markdown(f"""
        <div class="mq26-metric" style="border-left-color:{c_sc}">
            <div class="mq26-label">🎯 Score MOD-23</div>
            <div class="mq26-value" style="color:{c_sc}">{score_promedio:.0f}/100</div>
            <div class="mq26-delta">{'Excelente' if score_promedio>=70 else 'Bueno' if score_promedio>=55 else 'Revisar'}</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="mq26-metric" style="border-left-color:#9b59b6">
            <div class="mq26-label">📁 Posiciones</div>
            <div class="mq26-value" style="color:#c39bd3">{n_pos}</div>
            <div class="mq26-delta">activas</div>
        </div>""", unsafe_allow_html=True)

    with c5:
        # Concentración: peso del activo más grande
        if "VALOR_ARS" in df_posiciones.columns and valor_ars > 0:
            max_peso = float(df_posiciones["VALOR_ARS"].max() / valor_ars * 100)
            c_conc   = "#28a745" if max_peso < 20 else "#f0ad4e" if max_peso < 30 else "#dc3545"
            ticker_max = df_posiciones.loc[df_posiciones["VALOR_ARS"].idxmax(), "TICKER"] \
                         if "TICKER" in df_posiciones.columns else "—"
        else:
            max_peso, c_conc, ticker_max = 0, "#aaa", "—"

        st.markdown(f"""
        <div class="mq26-metric" style="border-left-color:{c_conc}">
            <div class="mq26-label">⚖️ Concentración</div>
            <div class="mq26-value" style="color:{c_conc}">{max_peso:.0f}%</div>
            <div class="mq26-delta">mayor pos: {ticker_max}</div>
        </div>""", unsafe_allow_html=True)
