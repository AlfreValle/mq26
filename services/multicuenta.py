"""
services/multicuenta.py — Multi-Cuenta y Multi-Broker Unificado
Mejora #9 Profesional

Consolida posiciones de un mismo cliente a través de múltiples brokers:
Balanz, Bull Market, IOL, PPI, Cocos Capital.

Calcula posición neta consolidada con PPC promedio ponderado entre brokers.
Si Alfredo tiene AMZN en Balanz y AMZN en Bull Market, las une correctamente.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RATIOS_CEDEAR

# Brokers soportados con su parseo nativo
BROKERS_SOPORTADOS = {
    "Balanz":       {"color": "#e63946", "icono": "🔴", "comision_pct": 0.006},
    "Bull Market":  {"color": "#457b9d", "icono": "🔵", "comision_pct": 0.005},
    "IOL":          {"color": "#2ecc71", "icono": "🟢", "comision_pct": 0.007},
    "PPI":          {"color": "#f39c12", "icono": "🟡", "comision_pct": 0.006},
    "Cocos":        {"color": "#9b59b6", "icono": "🟣", "comision_pct": 0.005},
    "Manual":       {"color": "#95a5a6", "icono": "⚫", "comision_pct": 0.006},
}


def consolidar_multicuenta(
    df_todas_operaciones: pd.DataFrame,
    ccl: float,
) -> pd.DataFrame:
    """
    Consolida posiciones de múltiples brokers en una vista unificada.

    df_todas_operaciones debe tener: Ticker, Tipo_Op, Cantidad, PPC_USD,
                                     FECHA_INICIAL, Broker, Propietario, Cartera

    Retorna un DataFrame con posición neta consolidada por Ticker incluyendo:
    - PPC_USD promedio ponderado entre todos los brokers
    - Cantidad total
    - Desglose por broker
    - Fuente de cada lote
    """
    if df_todas_operaciones.empty:
        return pd.DataFrame()

    df = df_todas_operaciones.copy()
    df["Ticker"]  = df["Ticker"].astype(str).str.upper().str.strip()
    df["Broker"]  = df.get("Broker", pd.Series(["Manual"] * len(df))).fillna("Manual")
    df["Tipo_Op"] = df["Tipo_Op"].astype(str).str.upper()

    # Calcular posición neta por Ticker + Broker
    filas = []
    for (ticker, broker), g in df.groupby(["Ticker", "Broker"]):
        compras = g[g["Tipo_Op"] == "COMPRA"]
        ventas  = g[g["Tipo_Op"] == "VENTA"]
        cant_c  = float(compras["Cantidad"].sum())
        cant_v  = float(ventas["Cantidad"].sum())
        neto    = cant_c - cant_v
        if neto <= 0:
            continue

        # PPC ponderado por cantidad de compras
        if cant_c > 0:
            ppc_pond = float((compras["Cantidad"] * compras["PPC_USD"]).sum()) / cant_c
        else:
            ppc_pond = 0.0

        ratio = float(RATIOS_CEDEAR.get(ticker, 1.0))

        filas.append({
            "Ticker":     ticker,
            "Broker":     broker,
            "Cantidad":   neto,
            "PPC_USD":    round(ppc_pond, 4),
            "INV_USD":    round(neto * ppc_pond, 2),
            "Ratio":      ratio,
            "Fecha_primera_compra": str(compras["FECHA_INICIAL"].min())[:10] if not compras.empty else "",
        })

    if not filas:
        return pd.DataFrame()

    df_lotes = pd.DataFrame(filas)

    # Consolidar por ticker (sumar todos los brokers)
    filas_cons = []
    for ticker, g in df_lotes.groupby("Ticker"):
        cant_total = g["Cantidad"].sum()
        inv_total  = g["INV_USD"].sum()
        ppc_pond   = inv_total / cant_total if cant_total > 0 else 0

        # Desglose por broker
        desglose = {
            row["Broker"]: {"cantidad": row["Cantidad"], "ppc": row["PPC_USD"]}
            for _, row in g.iterrows()
        }
        brokers_activos = ", ".join(g["Broker"].tolist())

        filas_cons.append({
            "Ticker":          ticker,
            "Cantidad_Total":  round(cant_total, 0),
            "PPC_USD_Pond":    round(ppc_pond, 4),
            "INV_USD_Total":   round(inv_total, 2),
            "Brokers":         brokers_activos,
            "N_Brokers":       len(g),
            "Desglose":        desglose,
            "Ratio":           float(RATIOS_CEDEAR.get(ticker, 1.0)),
        })

    return pd.DataFrame(filas_cons).sort_values("INV_USD_Total", ascending=False).reset_index(drop=True)


def detectar_divergencias(df_consolidado: pd.DataFrame, ccl: float) -> list[dict]:
    """
    Detecta situaciones donde el mismo activo en dos brokers tiene
    precios de compra muy distintos (posible oportunidad de optimización).
    """
    divergencias = []
    for _, row in df_consolidado.iterrows():
        desglose = row.get("Desglose", {})
        if len(desglose) < 2:
            continue
        ppcs = [v["ppc"] for v in desglose.values() if v["ppc"] > 0]
        if len(ppcs) < 2:
            continue
        diff_pct = (max(ppcs) - min(ppcs)) / min(ppcs) * 100
        if diff_pct > 5:
            divergencias.append({
                "ticker":    row["Ticker"],
                "diff_pct":  round(diff_pct, 1),
                "ppc_min":   round(min(ppcs), 4),
                "ppc_max":   round(max(ppcs), 4),
                "brokers":   list(desglose.keys()),
                "nota":      f"PPC varía {diff_pct:.1f}% entre brokers — verificar timing de compras",
            })
    return divergencias


def render_multicuenta(
    df_operaciones_todos: pd.DataFrame,
    precios_actuales:     dict[str, float],
    ccl:                  float,
    cliente_filtro:       str | None = None,
):
    """Renderiza la vista multi-cuenta unificada."""
    st.markdown("## 🏦 Vista Multi-Broker Consolidada")
    st.caption(
        "Consolida todas tus posiciones de Balanz, Bull Market, IOL y otros brokers. "
        "PPC promedio ponderado entre todos los lotes de compra."
    )

    if df_operaciones_todos.empty:
        st.info("Sin operaciones cargadas.")
        return

    # Filtro por cliente
    if cliente_filtro:
        df_f = df_operaciones_todos[
            df_operaciones_todos.get("Propietario", pd.Series()).str.contains(
                cliente_filtro, case=False, na=False
            )
        ]
    else:
        df_f = df_operaciones_todos

    # Resumen por broker
    st.markdown("### 📊 Distribución por broker")
    brokers_en_datos = df_f.get("Broker", pd.Series(["Manual"] * len(df_f))).fillna("Manual")
    df_b = brokers_en_datos.value_counts().reset_index()
    df_b.columns = ["Broker", "Operaciones"]

    cols = st.columns(min(len(df_b), 5))
    for i, row in df_b.iterrows():
        broker = row["Broker"]
        info   = BROKERS_SOPORTADOS.get(broker, {"icono":"⚫","color":"#666"})
        if i < len(cols):
            cols[i].markdown(f"""
            <div style="background:#1a1a2e;border-radius:8px;padding:12px;
                        text-align:center;border-left:4px solid {info['color']}">
              <div style="font-size:20px">{info['icono']}</div>
              <div style="color:white;font-weight:700">{broker}</div>
              <div style="color:#aaa;font-size:11px">{row['Operaciones']} ops</div>
            </div>""", unsafe_allow_html=True)

    # Posición consolidada
    df_cons = consolidar_multicuenta(df_f, ccl)
    if df_cons.empty:
        st.info("Sin posiciones abiertas.")
        return

    # Calcular P&L con precios actuales
    df_cons["Px_ARS_actual"] = df_cons["Ticker"].map(precios_actuales).fillna(0)
    df_cons["Px_USD_actual"] = df_cons.apply(
        lambda r: r["Px_ARS_actual"] * r["Ratio"] / ccl if ccl > 0 else 0, axis=1
    )
    df_cons["Valor_USD"]     = df_cons["Cantidad_Total"] * df_cons["Px_USD_actual"]
    df_cons["PnL_USD"]       = df_cons["Valor_USD"] - df_cons["INV_USD_Total"]
    df_cons["PnL_pct"]       = (df_cons["PnL_USD"] / df_cons["INV_USD_Total"] * 100).round(1)

    st.markdown("### 💼 Posición neta consolidada")

    # Tabla con colores
    def color_pnl_celda(val):
        try:
            v = float(str(val).replace("+","").replace("%",""))
            if v >= 10:   return "color:#28a745;font-weight:bold"
            elif v >= 0:  return "color:#5cb85c"
            elif v >= -5: return "color:#f0ad4e"
            else:         return "color:#dc3545;font-weight:bold"
        except Exception:
            return ""

    cols_mostrar = ["Ticker","Cantidad_Total","PPC_USD_Pond","Px_USD_actual",
                    "Valor_USD","PnL_pct","Brokers","N_Brokers"]
    cols_existentes = [c for c in cols_mostrar if c in df_cons.columns]

    st.dataframe(
        df_cons[cols_existentes].style.format({
            "Cantidad_Total":  "{:.0f}",
            "PPC_USD_Pond":    "USD {:.4f}",
            "Px_USD_actual":   "USD {:.4f}",
            "Valor_USD":       "USD ${:,.0f}",
            "PnL_pct":         "{:+.1f}%",
        }).map(color_pnl_celda, subset=["PnL_pct"]), use_container_width=True,
        hide_index=True,
    )

    # Totales
    total_inv  = df_cons["INV_USD_Total"].sum()
    total_val  = df_cons["Valor_USD"].sum()
    total_pnl  = total_val - total_inv
    total_pct  = total_pnl / total_inv * 100 if total_inv > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Inversión total", f"USD ${total_inv:,.0f}")
    c2.metric("📈 Valor actual",    f"USD ${total_val:,.0f}",
              f"ARS ${total_val*ccl/1e6:.2f}M")
    c3.metric("🎯 P&L consolidado", f"USD ${total_pnl:+,.0f}",
              f"{total_pct:+.1f}%")

    # Divergencias entre brokers
    divs = detectar_divergencias(df_cons, ccl)
    if divs:
        st.markdown("### ⚠️ Divergencias de PPC entre brokers")
        for d in divs:
            st.warning(
                f"**{d['ticker']}** — PPC varía {d['diff_pct']:.1f}% "
                f"({', '.join(d['brokers'])}): "
                f"USD {d['ppc_min']:.4f} vs USD {d['ppc_max']:.4f}. "
                f"{d['nota']}"
            )

    # Gráfico donut por broker
    if "Brokers" in df_cons.columns:
        df_por_broker = df_cons.groupby("Brokers")["Valor_USD"].sum().reset_index()
        fig = px.pie(
            df_por_broker, names="Brokers", values="Valor_USD",
            title="Distribución de valor por broker",
            hole=0.4, height=320,
            color_discrete_sequence=["#e63946","#457b9d","#2ecc71","#f39c12","#9b59b6"],
        )
        st.plotly_chart(fig, use_container_width=True)
