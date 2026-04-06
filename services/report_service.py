"""
services/report_service.py — Generador de Reporte HTML para el Cliente
MQ26-DSS | Sin dependencias de Streamlit ni de librerías de PDF.

Genera un HTML autocontenido con CSS inline + @media print, listo para
abrir en el navegador e imprimir como PDF con Ctrl+P → Guardar como PDF.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

# ─── PALETA Y ESTILOS ─────────────────────────────────────────────────────────
_AZUL_OSCURO  = "#1A2D4F"
_AZUL_MEDIO   = "#2E5FA3"
_AZUL_CLARO   = "#EBF2FF"
_GRIS_TABLA   = "#F5F7FA"
_GRIS_BORDE   = "#D0D7E3"
_ROJO         = "#C0392B"
_VERDE        = "#1A7E3A"
_NARANJA      = "#E67E22"
_TEXTO        = "#1C1C2E"
_BLANCO       = "#FFFFFF"


# ─── CSS ──────────────────────────────────────────────────────────────────────
_CSS = f"""
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 11px;
    color: {_TEXTO};
    background: {_BLANCO};
    padding: 24px 32px;
    max-width: 960px;
    margin: 0 auto;
}}

/* ENCABEZADO */
.header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    border-bottom: 3px solid {_AZUL_OSCURO};
    padding-bottom: 12px;
    margin-bottom: 20px;
}}
.header-title {{ font-size: 20px; font-weight: 700; color: {_AZUL_OSCURO}; letter-spacing: 0.5px; }}
.header-sub   {{ font-size: 11px; color: #666; margin-top: 2px; }}
.header-meta  {{ text-align: right; font-size: 10px; color: #555; line-height: 1.6; }}

/* SECCIONES */
.section {{
    margin-bottom: 22px;
    page-break-inside: avoid;
}}
.section-title {{
    font-size: 13px;
    font-weight: 700;
    color: {_AZUL_OSCURO};
    background: {_AZUL_CLARO};
    border-left: 4px solid {_AZUL_MEDIO};
    padding: 5px 10px;
    margin-bottom: 10px;
    letter-spacing: 0.3px;
}}

/* KPI CARDS */
.kpi-grid {{
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 8px;
}}
.kpi-card {{
    flex: 1;
    min-width: 130px;
    background: {_AZUL_CLARO};
    border: 1px solid {_GRIS_BORDE};
    border-radius: 6px;
    padding: 10px 12px;
    text-align: center;
}}
.kpi-label  {{ font-size: 9px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }}
.kpi-value  {{ font-size: 17px; font-weight: 700; color: {_AZUL_OSCURO}; margin-top: 3px; }}
.kpi-sub    {{ font-size: 9px; color: #666; margin-top: 2px; }}
.kpi-pos    {{ color: {_VERDE}; }}
.kpi-neg    {{ color: {_ROJO}; }}

/* TABLAS */
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
    margin-bottom: 6px;
}}
th {{
    background: {_AZUL_OSCURO};
    color: {_BLANCO};
    padding: 6px 8px;
    text-align: left;
    font-weight: 600;
    letter-spacing: 0.2px;
}}
th.num, td.num {{ text-align: right; }}
tr:nth-child(even) td {{ background: {_GRIS_TABLA}; }}
td {{
    padding: 5px 8px;
    border-bottom: 1px solid {_GRIS_BORDE};
    color: {_TEXTO};
}}
tr.total-row td {{
    background: {_AZUL_CLARO} !important;
    font-weight: 700;
    border-top: 2px solid {_AZUL_MEDIO};
}}
.pos {{ color: {_VERDE}; font-weight: 600; }}
.neg {{ color: {_ROJO};  font-weight: 600; }}
.badge-elite   {{ background:#1A7E3A; color:#fff; border-radius:3px; padding:1px 5px; font-size:9px; font-weight:700; }}
.badge-alcista {{ background:#2E5FA3; color:#fff; border-radius:3px; padding:1px 5px; font-size:9px; font-weight:700; }}
.badge-alerta  {{ background:#C0392B; color:#fff; border-radius:3px; padding:1px 5px; font-size:9px; font-weight:700; }}
.badge-opt     {{ background:#E67E22; color:#fff; border-radius:3px; padding:1px 5px; font-size:9px; font-weight:700; }}

/* RIESGO */
.risk-grid {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.risk-card {{
    flex: 1;
    min-width: 140px;
    border: 1px solid {_GRIS_BORDE};
    border-radius: 6px;
    padding: 8px 12px;
    background: {_BLANCO};
}}
.risk-title {{ font-size: 9px; font-weight: 700; text-transform: uppercase; color: #777; margin-bottom: 5px; }}
.risk-item  {{ font-size: 10px; padding: 2px 0; border-bottom: 1px solid #f0f0f0; }}

/* PASOS */
ol.pasos {{ padding-left: 18px; }}
ol.pasos li {{
    font-size: 10.5px;
    padding: 4px 0;
    border-bottom: 1px dashed {_GRIS_BORDE};
    line-height: 1.5;
}}
ol.pasos li:last-child {{ border-bottom: none; }}

/* NOTAS DEL ASESOR */
.notas-box {{
    background: #FFFBEA;
    border-left: 3px solid {_NARANJA};
    padding: 8px 12px;
    font-size: 10px;
    line-height: 1.6;
    margin-top: 6px;
}}

/* DISCLAIMER */
.disclaimer {{
    margin-top: 20px;
    border-top: 1px solid {_GRIS_BORDE};
    padding-top: 8px;
    font-size: 9px;
    color: #888;
    line-height: 1.5;
}}

/* PRINT */
@media print {{
    body {{ padding: 0; font-size: 10px; }}
    .no-print {{ display: none !important; }}
    .section {{ page-break-inside: avoid; }}
    .kpi-card {{ border: 1px solid #ccc; }}
    a {{ text-decoration: none; color: inherit; }}
}}
"""


# ─── HELPERS INTERNOS ─────────────────────────────────────────────────────────

def _fmt_ars(v: float, millones: bool = False) -> str:
    if millones and abs(v) >= 1_000_000:
        return f"${v/1_000_000:,.2f}M"
    return f"${v:,.0f}"


def _fmt_pct(v: float) -> str:
    return f"{v:+.1f}%" if isinstance(v, (int, float)) else str(v)


def _cls_pnl(v: float) -> str:
    """Retorna clase CSS para P&L: 'pos' si positivo, 'neg' si negativo, '' si cero."""
    if v > 0:
        return "pos"
    if v < 0:
        return "neg"
    return ""


def _badge_estado(estado: str) -> str:
    e = str(estado).upper()
    if e in ("ELITE", "ALCISTA"):
        cls = "badge-elite" if e == "ELITE" else "badge-alcista"
    elif e == "ALERTA":
        cls = "badge-alerta"
    else:
        cls = "badge-alerta"
    return f'<span class="{cls}">{e}</span>'


# ─── BLOQUES HTML ─────────────────────────────────────────────────────────────

def _html_header(nombre_cliente: str, nombre_asesor: str, fecha: str) -> str:
    return f"""
<div class="header">
  <div>
    <div class="header-title">INFORME DE CARTERA</div>
    <div class="header-sub">Master Quant 26 — Estrategia Capitales</div>
  </div>
  <div class="header-meta">
    <strong>Cliente:</strong> {nombre_cliente}<br>
    <strong>Asesor:</strong> {nombre_asesor}<br>
    <strong>Fecha:</strong> {fecha}
  </div>
</div>
"""


def _html_resumen(metricas: dict, ccl: float, horizonte_dias: int) -> str:
    tv    = metricas.get("total_valor", 0)
    ti    = metricas.get("total_inversion", 0)
    pnl   = metricas.get("total_pnl", 0)
    pnl_p = metricas.get("pnl_pct_total", 0)
    n_pos = metricas.get("n_posiciones", 0)
    tv_usd = tv / ccl if ccl > 0 else 0

    pnl_cls   = "kpi-pos" if pnl >= 0 else "kpi-neg"
    pnl_label = f"{_fmt_ars(pnl)}" + f" ({_fmt_pct(pnl_p * 100 if abs(pnl_p) < 1 else pnl_p)})"

    cards = [
        ("Valor de la Cartera", _fmt_ars(tv, millones=True), "ARS"),
        ("Equivalente USD",     f"USD {tv_usd:,.0f}",        f"CCL: {_fmt_ars(ccl)}"),
        ("P&amp;L Acumulado",   _fmt_ars(pnl, millones=True),
         f"{pnl_p*100:+.1f}%" if abs(pnl_p) < 1 else f"{pnl_p:+.1f}%"),
        ("Posiciones Activas",  str(n_pos),                  "activos"),
        ("Horizonte de análisis", f"{horizonte_dias} días",  "configurado"),
    ]

    html = '<div class="section"><div class="section-title">1. Resumen Ejecutivo</div>'
    html += '<div class="kpi-grid">'
    for i, (lbl, val, sub) in enumerate(cards):
        cls = ""
        if i == 2:
            cls = f' style="color:{"#1A7E3A" if pnl >= 0 else "#C0392B"}"'
        html += f"""
  <div class="kpi-card">
    <div class="kpi-label">{lbl}</div>
    <div class="kpi-value"{cls}>{val}</div>
    <div class="kpi-sub">{sub}</div>
  </div>"""
    html += "</div></div>\n"
    return html


def _html_posiciones(df_pos: pd.DataFrame) -> str:
    if df_pos.empty:
        return '<div class="section"><div class="section-title">2. Posiciones Actuales</div><p><em>Sin datos de posiciones.</em></p></div>\n'

    cols_map = {
        "TICKER":        "Ticker",
        "TIPO":          "Tipo",
        "CANTIDAD_TOTAL":"Cant.",
        "PPC_ARS":       "PPC (ARS)",
        "PRECIO_ARS":    "Precio actual",
        "VALOR_ARS":     "Valor ARS",
        "PNL_ARS":       "P&amp;L ARS",
        "PNL_PCT":       "P&amp;L %",
        "PESO_PCT":      "Peso %",
    }
    # Solo columnas presentes
    present = {k: v for k, v in cols_map.items() if k in df_pos.columns}

    header = "".join(f'<th class="num">{h}</th>' if h not in ("Ticker", "Tipo") else f'<th>{h}</th>'
                     for h in present.values())

    total_valor = df_pos["VALOR_ARS"].sum() if "VALOR_ARS" in df_pos.columns else 0
    total_pnl   = df_pos["PNL_ARS"].sum()   if "PNL_ARS"  in df_pos.columns else 0

    # Guard: reemplazar NaN numéricos con 0 antes de formatear para evitar ValueError
    df_pos = df_pos.fillna({
        col: 0.0 for col in df_pos.select_dtypes(include="number").columns
    })

    rows_html = ""
    for _, r in df_pos.iterrows():
        cells = ""
        for col, label in present.items():
            val = r.get(col, "")
            td_cls = 'class="num"' if label not in ("Ticker", "Tipo") else ""
            if col == "VALOR_ARS":
                cells += f'<td {td_cls}>{_fmt_ars(float(val))}</td>'
            elif col == "PNL_ARS":
                pnl_c = _cls_pnl(float(val))
                cells += f'<td {td_cls} class="{pnl_c}">{_fmt_ars(float(val))}</td>'
            elif col == "PNL_PCT":
                v = float(val)
                pct = v * 100 if abs(v) < 1 else v
                pnl_c = _cls_pnl(v)
                cells += f'<td {td_cls} class="{pnl_c}">{pct:+.1f}%</td>'
            elif col == "PESO_PCT":
                v = float(val)
                pct = v * 100 if abs(v) < 1 else v
                cells += f'<td {td_cls}>{pct:.1f}%</td>'
            elif col in ("PPC_ARS", "PRECIO_ARS"):
                cells += f'<td {td_cls}>{_fmt_ars(float(val) if val else 0)}</td>'
            elif col == "CANTIDAD_TOTAL":
                cells += f'<td {td_cls}>{float(val):,.0f}</td>'
            else:
                cells += f'<td {td_cls}>{val}</td>'
        rows_html += f"<tr>{cells}</tr>\n"

    # Fila de totales
    total_cls = _cls_pnl(total_pnl)
    total_row = '<tr class="total-row">'
    for col, label in present.items():
        if col == "TICKER":
            total_row += "<td><strong>TOTAL</strong></td>"
        elif col == "VALOR_ARS":
            total_row += f'<td class="num"><strong>{_fmt_ars(total_valor, millones=True)}</strong></td>'
        elif col == "PNL_ARS":
            total_row += f'<td class="num {total_cls}"><strong>{_fmt_ars(total_pnl, millones=True)}</strong></td>'
        elif col == "PESO_PCT":
            total_row += '<td class="num">100.0%</td>'
        else:
            total_row += "<td></td>"
    total_row += "</tr>"

    html = f"""
<div class="section">
  <div class="section-title">2. Posiciones Actuales</div>
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{rows_html}{total_row}</tbody>
  </table>
</div>
"""
    return html


def _html_riesgo(df_pos: pd.DataFrame, df_analisis: pd.DataFrame) -> str:
    html = '<div class="section"><div class="section-title">3. Diagnóstico de Riesgo</div>'
    html += '<div class="risk-grid">'

    # --- Concentración ---
    html += '<div class="risk-card"><div class="risk-title">Concentración</div>'
    if not df_pos.empty and "PESO_PCT" in df_pos.columns and "VALOR_ARS" in df_pos.columns:
        top = df_pos.nlargest(3, "VALOR_ARS")[["TICKER", "PESO_PCT"]].copy()
        for _, r in top.iterrows():
            p = float(r["PESO_PCT"])
            pct = p * 100 if abs(p) < 1 else p
            alerta = " ⚠️" if pct > 18 else ""
            html += f'<div class="risk-item"><strong>{r["TICKER"]}</strong>: {pct:.1f}%{alerta}</div>'
        top3_sum = float(top["PESO_PCT"].sum())
        top3_pct = top3_sum * 100 if abs(top3_sum) < 1 else top3_sum
        html += f'<div class="risk-item" style="margin-top:4px;font-size:9px;color:#555;">Top 3 = {top3_pct:.1f}% del total</div>'
    else:
        html += '<div class="risk-item"><em>Sin datos</em></div>'
    html += '</div>'

    # --- Alertas MOD-23 ---
    html += '<div class="risk-card"><div class="risk-title">Alertas de Venta (score &lt; 4)</div>'
    alertas_html = ""
    if not df_analisis.empty and "PUNTAJE_TECNICO" in df_analisis.columns:
        alertas = df_analisis[df_analisis["PUNTAJE_TECNICO"] < 4]
        tickers_cartera = df_pos["TICKER"].str.upper().tolist() if not df_pos.empty else []
        alertas_cart = alertas[alertas["TICKER"].isin(tickers_cartera)] if tickers_cartera else alertas
        if alertas_cart.empty:
            html += '<div class="risk-item pos">Sin alertas de venta en cartera</div>'
        else:
            for _, r in alertas_cart.iterrows():
                html += f'<div class="risk-item">{_badge_estado("ALERTA")} <strong>{r["TICKER"]}</strong> — score {r["PUNTAJE_TECNICO"]:.1f}</div>'
    else:
        html += '<div class="risk-item"><em>MOD-23 no ejecutado aún</em></div>'
    html += '</div>'

    # --- Activos ELITE ---
    html += '<div class="risk-card"><div class="risk-title">Activos de Alta Calidad (score ≥ 7)</div>'
    if not df_analisis.empty and "PUNTAJE_TECNICO" in df_analisis.columns:
        tickers_cartera = df_pos["TICKER"].str.upper().tolist() if not df_pos.empty else []
        elite = df_analisis[(df_analisis["PUNTAJE_TECNICO"] >= 7) & (df_analisis["TICKER"].isin(tickers_cartera))]
        if elite.empty:
            html += '<div class="risk-item" style="color:#888;">Ninguno en cartera actualmente</div>'
        else:
            for _, r in elite.head(6).iterrows():
                html += f'<div class="risk-item">{_badge_estado("ELITE")} <strong>{r["TICKER"]}</strong> — score {r["PUNTAJE_TECNICO"]:.1f}</div>'
    else:
        html += '<div class="risk-item"><em>Sin datos MOD-23</em></div>'
    html += '</div>'

    # ── Tabla de scores MOD-23 de la cartera activa (S7) ──────────────────────
    html += '<div class="risk-card" style="grid-column:1/-1">'
    html += '<div class="risk-title">Scores MOD-23 — Cartera activa</div>'
    if not df_analisis.empty and not df_pos.empty and "PUNTAJE_TECNICO" in df_analisis.columns:
        tickers_cart = df_pos["TICKER"].str.upper().tolist()
        df_sc = df_analisis[df_analisis["TICKER"].isin(tickers_cart)].copy()
        df_sc = df_sc.sort_values("PUNTAJE_TECNICO", ascending=False)
        if df_sc.empty:
            html += '<div class="risk-item"><em>Sin scores disponibles para la cartera</em></div>'
        else:
            html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:6px">'
            html += '<tr style="background:#2E75B6;color:#fff">'
            html += '<th style="padding:4px 8px;text-align:left">Ticker</th>'
            html += '<th style="padding:4px 8px;text-align:center">Score</th>'
            html += '<th style="padding:4px 8px;text-align:center">Estado</th>'
            html += '</tr>'
            COLOR_SCORE = {
                'ELITE': ('#1A6B3C', '#E2EFDA'),
                'FUERTE': ('#1A6B3C', '#E2EFDA'),
                'NEUTRO': ('#595959', '#F2F2F2'),
                'BAJISTA': ('#C55A11', '#FCE4D6'),
                'ALERTA': ('#C00000', '#FDECEA'),
            }
            for _, r in df_sc.iterrows():
                estado = str(r.get('ESTADO', 'NEUTRO'))
                fcolor, bgcolor = COLOR_SCORE.get(estado.upper(), ('#595959', '#F2F2F2'))
                html += (
                    f'<tr style="border-bottom:1px solid #eee">'
                    f'<td style="padding:4px 8px;font-weight:bold">{r["TICKER"]}</td>'
                    f'<td style="padding:4px 8px;text-align:center">{r["PUNTAJE_TECNICO"]:.1f}</td>'
                    f'<td style="padding:4px 8px;text-align:center;background:{bgcolor};'
                    f'color:{fcolor};font-weight:bold">{estado}</td>'
                    f'</tr>'
                )
            html += '</table>'
    else:
        html += '<div class="risk-item"><em>MOD-23 no ejecutado o cartera vacía</em></div>'
    html += '</div>'

    html += '</div></div>\n'
    return html


def _html_lab_quant(lab_resultados: dict, modelo_opt: str | None) -> str:
    if not lab_resultados:
        return ""

    html = '<div class="section"><div class="section-title">4. Laboratorio Cuantitativo — Comparativa de Modelos</div>'

    # Tabla comparativa de métricas
    metricas_cols = [
        ("ret_a",    "Retorno Anual", lambda v: f"{v*100:+.1f}%"),
        ("vol_a",    "Volatilidad",   lambda v: f"{v*100:.1f}%"),
        ("sharpe",   "Sharpe",        lambda v: f"{v:.2f}"),
        ("sortino",  "Sortino",       lambda v: f"{v:.2f}"),
        ("max_dd",   "Max Drawdown",  lambda v: f"{v*100:.1f}%"),
        ("var95",    "VaR 95%",       lambda v: f"{v:.2f}%"),
    ]

    html += """
<table>
  <thead>
    <tr>
      <th>Modelo</th>
      <th class="num">Retorno Anual</th>
      <th class="num">Volatilidad</th>
      <th class="num">Sharpe</th>
      <th class="num">Sortino</th>
      <th class="num">Max Drawdown</th>
      <th class="num">VaR 95%</th>
    </tr>
  </thead>
  <tbody>"""

    for modelo, data in lab_resultados.items():
        es_opt = (modelo == modelo_opt)
        highlight = ' style="background:#FFF8E7; font-weight:700;"' if es_opt else ""
        opt_badge = ' <span class="badge-opt">RECOMENDADO</span>' if es_opt else ""
        cells = f'<td><strong>{modelo}</strong>{opt_badge}</td>'
        for key, _, fmt in metricas_cols:
            v = data.get(key, 0) or 0
            cells += f'<td class="num">{fmt(float(v))}</td>'
        html += f"<tr{highlight}>{cells}</tr>\n"

    html += "  </tbody>\n</table>\n"

    # Tabla de pesos del modelo óptimo
    if modelo_opt and modelo_opt in lab_resultados:
        pesos = lab_resultados[modelo_opt].get("pesos", {})
        if pesos:
            html += f'<p style="font-size:10px;margin-top:8px;"><strong>Pesos sugeridos — Modelo {modelo_opt}:</strong></p>'
            html += "<table><thead><tr><th>Activo</th><th class=\"num\">Peso Óptimo</th></tr></thead><tbody>"
            for ticker, peso in sorted(pesos.items(), key=lambda x: -x[1]):
                html += f"<tr><td><strong>{ticker}</strong></td><td class=\"num\">{peso*100:.1f}%</td></tr>"
            html += "</tbody></table>"

    html += "</div>\n"
    return html


def _html_backtest(backtest) -> str:
    if backtest is None:
        return ""

    try:
        ret_e   = float(backtest.retorno_anual_estrategia)
        ret_b   = float(backtest.retorno_anual_benchmark)
        sh_e    = float(backtest.sharpe_estrategia)
        sh_b    = float(backtest.sharpe_benchmark)
        dd_e    = float(backtest.max_dd_estrategia)
        dd_b    = float(backtest.max_dd_benchmark)
        calmar  = float(backtest.calmar_estrategia)
        modelo  = backtest.modelo
        periodo = backtest.periodo
    except Exception:
        return ""

    alpha = ret_e - ret_b

    def _row(label, est_val, bench_val, fmt_fn, invert=False):
        cls_e = _cls_pnl(est_val if not invert else -est_val)
        cls_b = _cls_pnl(bench_val if not invert else -bench_val)
        return (f'<tr><td>{label}</td>'
                f'<td class="num {cls_e}"><strong>{fmt_fn(est_val)}</strong></td>'
                f'<td class="num {cls_b}">{fmt_fn(bench_val)}</td></tr>')

    alpha_cls = _cls_pnl(alpha)
    html = f"""
<div class="section">
  <div class="section-title">5. Backtest Histórico vs SPY — Modelo {modelo} ({periodo})</div>
  <table>
    <thead>
      <tr>
        <th>Métrica</th>
        <th class="num">Estrategia ({modelo})</th>
        <th class="num">Benchmark (SPY)</th>
      </tr>
    </thead>
    <tbody>
      {_row("Retorno Anual (CAGR)",   ret_e, ret_b, lambda v: f"{v*100:+.1f}%")}
      {_row("Sharpe Ratio",           sh_e,  sh_b,  lambda v: f"{v:.2f}")}
      {_row("Máximo Drawdown",        dd_e,  dd_b,  lambda v: f"{v*100:.1f}%", invert=True)}
      <tr><td>Calmar Ratio</td>
          <td class="num"><strong>{calmar:.2f}</strong></td><td class="num">—</td></tr>
      <tr><td><strong>Alpha acumulado vs SPY</strong></td>
          <td class="num {alpha_cls}" colspan="2"><strong>{alpha*100:+.1f}%</strong></td>
      </tr>
    </tbody>
  </table>
  <p style="font-size:9px;color:#666;margin-top:4px;">
    Backtest sobre datos históricos del período {periodo}. El rendimiento pasado no garantiza resultados futuros.
  </p>
</div>
"""
    return html


def _html_plan_accion(
    df_pos: pd.DataFrame,
    ejecutables: pd.DataFrame | None,
    pesos_opt: dict | None,
    modelo_opt: str | None,
) -> str:
    html = '<div class="section"><div class="section-title">6. Plan de Acción Recomendado</div>'

    # Órdenes concretas (si vienen de la mesa de ejecución)
    if ejecutables is not None and not ejecutables.empty:
        html += '<p style="font-size:10px;margin-bottom:6px;">Las siguientes operaciones están aprobadas por el árbol de decisión (desviación ≥ 5% y alpha neto positivo):</p>'
        html += """<table>
  <thead>
    <tr>
      <th>Activo</th>
      <th>Acción</th>
      <th class="num">Precio ARS</th>
      <th class="num">Valor Nocional</th>
      <th class="num">Alpha Neto</th>
    </tr>
  </thead>
  <tbody>"""
        for _, r in ejecutables.iterrows():
            tipo_op = str(r.get("tipo_op", "")).upper()
            color   = "#1A7E3A" if tipo_op == "COMPRA" else "#C0392B"
            html += (f'<tr>'
                     f'<td><strong>{r.get("ticker","")}</strong></td>'
                     f'<td style="color:{color};font-weight:700;">{tipo_op}</td>'
                     f'<td class="num">{_fmt_ars(float(r.get("precio_ars",0)))}</td>'
                     f'<td class="num">{_fmt_ars(float(r.get("valor_nocional",0)))}</td>'
                     f'<td class="num pos">{_fmt_ars(float(r.get("alpha_neto",0)))}</td>'
                     f'</tr>')
        html += "  </tbody>\n</table>\n"
    else:
        html += '<p style="font-size:10px;color:#666;margin-bottom:8px;">No se generaron órdenes automáticas en esta sesión (ir a la pestaña "Mesa de Ejecución" para calcularlas).</p>'

    # Pasos a seguir
    paso_modelo = f"el modelo <strong>{modelo_opt}</strong>" if modelo_opt else "el modelo cuantitativo"
    pasos = [
        "<strong>Revisar las alertas de venta MOD-23</strong>: evaluar los activos con score técnico inferior a 4; considerar reducir o liquidar esas posiciones si el análisis fundamental lo confirma.",
        f"<strong>Ejecutar el plan de rebalanceo</strong>: implementar las órdenes detalladas arriba de acuerdo a {paso_modelo}, respetando el límite máximo de 25% por activo.",
        "<strong>Mantener posiciones de alta calidad</strong>: los activos con score ELITE (≥ 7) pueden conservarse o incrementarse dentro de los límites de peso.",
        "<strong>Incorporar liquidez nueva</strong>: si dispone de capital fresco, utilizarlo para aumentar las posiciones sub-ponderadas según los pesos óptimos, reduciendo costos de transacción.",
        "<strong>Monitoreo mensual</strong>: recalcular el Motor MOD-23 y el laboratorio cuantitativo una vez por mes para detectar cambios en las tendencias técnicas del mercado.",
        "<strong>Gestión del tipo de cambio</strong>: el CCL es un factor clave en la valuación de CEDEARs. Actualice el precio fallback si el tipo de cambio se mueve más de un 5% en el mes.",
    ]

    html += '<ol class="pasos">'
    for p in pasos:
        html += f"<li>{p}</li>"
    html += "</ol>\n"
    html += "</div>\n"
    return html


def _html_attribution(attribution: dict | None) -> str:
    """S4: Sección BHB (Brinson-Hood-Beebower) para el PDF."""
    if not attribution or not isinstance(attribution, dict):
        return ""
    active = attribution.get("active_total")
    if active is None:
        return ""
    alloc = attribution.get("allocation_sum", 0)
    sel   = attribution.get("selection_sum", 0)
    inter = attribution.get("interaction_sum", 0)

    def _pct_val(v) -> str:
        if isinstance(v, (int, float)):
            return _fmt_pct(v * 100 if abs(v) <= 2 else v)
        return str(v)

    rows = [
        ("Retorno activo total", _pct_val(active)),
        ("Efecto asignación",    _pct_val(alloc)),
        ("Efecto selección",     _pct_val(sel)),
        ("Efecto interacción",   _pct_val(inter)),
    ]
    trs = "".join(
        f"<tr><td>{lbl}</td><td style='text-align:right'>{val}</td></tr>"
        for lbl, val in rows
    )
    return f"""
<div class="section">
  <div class="section-title">Attribution de performance (BHB)</div>
  <table>
    <thead><tr><th>Componente</th><th>Contribución</th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>
"""


def _html_stress(stress_df: pd.DataFrame | None) -> str:
    """S4: Tabla de escenarios de stress para el PDF."""
    if stress_df is None or (hasattr(stress_df, "empty") and stress_df.empty):
        return ""
    try:
        df = stress_df if isinstance(stress_df, pd.DataFrame) else pd.DataFrame(stress_df)
        if df.empty or "escenario" not in df.columns:
            return ""
    except Exception:
        return ""
    trs = []
    for _, row in df.iterrows():
        esc = str(row.get("escenario", ""))
        v_orig = row.get("valor_original", 0)
        v_stress = row.get("valor_stress", 0)
        pct = row.get("pct_perdida", 0)
        if isinstance(v_orig, (int, float)) and isinstance(v_stress, (int, float)):
            v_orig_s = _fmt_ars(v_orig, millones=True)
            v_stress_s = _fmt_ars(v_stress, millones=True)
        else:
            v_orig_s = str(v_orig)
            v_stress_s = str(v_stress)
        pct_s = f"{pct:.1f}%" if isinstance(pct, (int, float)) else str(pct)
        trs.append(f"<tr><td>{esc}</td><td>{v_orig_s}</td><td>{v_stress_s}</td><td>{pct_s}</td></tr>")
    thead = "<thead><tr><th>Escenario</th><th>Valor original</th><th>Valor bajo estrés</th><th>Pérdida %</th></tr></thead>"
    return f"""
<div class="section">
  <div class="section-title">Stress test — Escenarios históricos</div>
  <table>
    {thead}
    <tbody>{"".join(trs)}</tbody>
  </table>
</div>
"""


def _html_notas(notas: str) -> str:
    if not notas.strip():
        return ""
    return f"""
<div class="section">
  <div class="section-title">Notas del Asesor</div>
  <div class="notas-box">{notas.replace(chr(10), "<br>")}</div>
</div>
"""


def _html_disclaimer(nombre_asesor: str, fecha: str) -> str:
    return f"""
<div class="disclaimer">
  <strong>AVISO LEGAL:</strong> Este informe es de carácter exclusivamente informativo y no constituye una oferta,
  recomendación ni asesoramiento de inversión con garantía de rendimiento. Los datos de mercado son obtenidos de
  fuentes públicas (yfinance / BYMA) y pueden presentar diferencias respecto a los precios operables.
  El rendimiento histórico no garantiza resultados futuros. Los modelos cuantitativos utilizan datos históricos
  y están sujetos a riesgo de modelo. El inversor debe evaluar su propio perfil de riesgo antes de operar.<br><br>
  Elaborado por <strong>{nombre_asesor}</strong> | {fecha} | Sistema MQ26-DSS — Estrategia Capitales.
</div>
"""


# ─── FUNCIÓN PRINCIPAL ────────────────────────────────────────────────────────

def generar_reporte_html(
    nombre_cliente: str,
    nombre_asesor: str,
    df_pos: pd.DataFrame,
    metricas: dict,
    ccl: float,
    df_analisis: pd.DataFrame,
    lab_resultados: dict | None = None,
    modelo_opt: str | None = None,
    backtest=None,
    ejecutables: pd.DataFrame | None = None,
    notas_asesor: str = "",
    horizonte_dias: int = 252,
    attribution: dict | None = None,
    stress: pd.DataFrame | None = None,
) -> str:
    """
    Genera un HTML autocontenido listo para imprimir como PDF.

    Parámetros
    ----------
    nombre_cliente  : Nombre completo del cliente.
    nombre_asesor   : Nombre del asesor que firma el informe.
    df_pos          : DataFrame de posiciones (resultado de cs.calcular_posicion_neta).
    metricas        : Dict de cs.metricas_resumen(df_pos).
    ccl             : CCL del día.
    df_analisis     : DataFrame de scores MOD-23 (TICKER, PUNTAJE_TECNICO, ESTADO).
    lab_resultados  : Dict de resultados del Laboratorio Cuantitativo, o None.
    modelo_opt      : Nombre del modelo cuantitativo activo, o None.
    backtest        : Objeto BacktestResult de backtester.run_backtest(), o None.
    ejecutables     : DataFrame de órdenes aprobadas por ejecucion_service, o None.
    notas_asesor    : Texto libre del asesor para incluir en el informe.
    horizonte_dias  : Horizonte de análisis configurado en la app.
    attribution     : (S4) Dict BHB: active_total, allocation_sum, selection_sum, interaction_sum.
    stress          : (S4) DataFrame de StressTestEngine.todos_los_escenarios(), o None.

    Retorna
    -------
    str : Documento HTML completo como string.
    """
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    body = ""
    body += _html_header(nombre_cliente, nombre_asesor, fecha)
    body += _html_resumen(metricas, ccl, horizonte_dias)
    body += _html_posiciones(df_pos)
    body += _html_riesgo(df_pos, df_analisis)
    body += _html_lab_quant(lab_resultados, modelo_opt)
    body += _html_backtest(backtest)
    body += _html_plan_accion(df_pos, ejecutables, lab_resultados, modelo_opt)
    body += _html_attribution(attribution)
    body += _html_stress(stress)
    body += _html_notas(notas_asesor)
    body += _html_disclaimer(nombre_asesor, fecha)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Informe de Cartera — {nombre_cliente}</title>
  <style>{_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""
