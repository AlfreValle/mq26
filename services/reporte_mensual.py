"""
services/reporte_mensual.py — Reporte PDF Mensual Automatizado
Mejora #8 Profesional

El día 1 de cada mes genera automáticamente un PDF de 4 páginas
y lo envía por email a cada cliente.

Contenido:
  Página 1: Portada + resumen ejecutivo
  Página 2: Posiciones, P&L y movimientos del mes
  Página 3: Evolución de cartera + gráficos
  Página 4: Recomendaciones para el próximo mes

Se genera como HTML optimizado para imprimir como PDF (Ctrl+P).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def generar_reporte_mensual_html(
    cliente:        str,
    cartera:        str,
    perfil:         str,
    df_posiciones:  pd.DataFrame,       # posiciones abiertas con P&L
    df_operaciones_mes: pd.DataFrame,   # operaciones del mes
    metricas:       dict,               # valor, pnl, sharpe, etc.
    recomendaciones: list[dict],        # lista de recomendaciones para el mes
    ccl:            float,
    mes_año:        str = "",           # "Febrero 2026"
) -> str:
    """
    Genera el HTML completo del reporte mensual.
    Optimizado para Ctrl+P → Guardar como PDF desde el navegador.
    """
    if not mes_año:
        meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        hoy = date.today()
        mes_año = f"{meses[hoy.month-2]} {hoy.year}" if hoy.month > 1 else f"Diciembre {hoy.year-1}"

    valor_ars     = metricas.get("valor_ars", 0)
    valor_usd     = metricas.get("valor_usd", valor_ars / ccl if ccl > 0 else 0)
    pnl_ars       = metricas.get("pnl_ars", 0)
    pnl_pct       = metricas.get("pnl_pct", 0)
    pnl_mes       = metricas.get("pnl_mes_pct", 0)
    sharpe        = metricas.get("sharpe", 0)
    n_pos         = len(df_posiciones) if not df_posiciones.empty else 0
    n_ops         = len(df_operaciones_mes) if not df_operaciones_mes.empty else 0

    color_pnl  = "#1a7a1a" if pnl_pct  >= 0 else "#cc0000"
    color_mes  = "#1a7a1a" if pnl_mes  >= 0 else "#cc0000"
    signo_pnl  = "+" if pnl_pct >= 0 else ""
    signo_mes  = "+" if pnl_mes >= 0 else ""

    # ── Tabla de posiciones ───────────────────────────────────────────
    filas_pos = ""
    if not df_posiciones.empty:
        for i, row in df_posiciones.iterrows():
            ticker  = str(row.get("Ticker", row.get("TICKER", "")))
            cant    = row.get("Cantidad", row.get("CANTIDAD_TOTAL", 0))
            ppc     = row.get("PPC_USD", row.get("PPC_USD_PROM", 0))
            px_act  = row.get("Px_USD_actual", 0)
            val_ars = row.get("Valor_ARS", row.get("VALOR_ARS", 0))
            pnl_r   = row.get("PnL_pct", row.get("PNL_PCT", 0))
            peso    = row.get("Peso_pct", 0)
            sector  = row.get("Sector", "—")

            c_fila  = "#f9f9f9" if i % 2 == 0 else "white"
            c_pnl   = "#1a7a1a" if float(pnl_r or 0) >= 0 else "#cc0000"
            filas_pos += f"""
            <tr style="background:{c_fila}">
              <td style="padding:7px 10px;font-weight:600">{ticker}</td>
              <td style="padding:7px;text-align:center">{sector}</td>
              <td style="padding:7px;text-align:center">{int(cant or 0)}</td>
              <td style="padding:7px;text-align:right">USD {float(ppc or 0):.4f}</td>
              <td style="padding:7px;text-align:right">USD {float(px_act or 0):.4f}</td>
              <td style="padding:7px;text-align:right">ARS ${float(val_ars or 0):,.0f}</td>
              <td style="padding:7px;text-align:center;color:{c_pnl};font-weight:600">
                {'+' if float(pnl_r or 0)>=0 else ''}{float(pnl_r or 0):.1f}%
              </td>
              <td style="padding:7px;text-align:center">{float(peso or 0):.1f}%</td>
            </tr>"""

    # ── Tabla de operaciones del mes ──────────────────────────────────
    filas_ops = ""
    if not df_operaciones_mes.empty:
        for i, row in df_operaciones_mes.iterrows():
            ticker = str(row.get("Ticker", ""))
            tipo   = str(row.get("Tipo_Op", ""))
            cant   = row.get("Cantidad", 0)
            px     = row.get("Precio_ARS", 0)
            neto   = row.get("Neto_ARS", float(cant or 0) * float(px or 0))
            fecha  = str(row.get("FECHA_INICIAL", ""))[:10]
            c_tipo = "#28a745" if tipo == "COMPRA" else "#dc3545"
            c_fila = "#f9f9f9" if i % 2 == 0 else "white"
            filas_ops += f"""
            <tr style="background:{c_fila}">
              <td style="padding:6px 10px">{fecha}</td>
              <td style="padding:6px;font-weight:600">{ticker}</td>
              <td style="padding:6px;text-align:center;color:{c_tipo};font-weight:600">{tipo}</td>
              <td style="padding:6px;text-align:center">{int(cant or 0)}</td>
              <td style="padding:6px;text-align:right">ARS ${float(px or 0):,.2f}</td>
              <td style="padding:6px;text-align:right">ARS ${float(neto or 0):,.0f}</td>
            </tr>"""
    else:
        filas_ops = '<tr><td colspan="6" style="padding:12px;text-align:center;color:#666">Sin operaciones este mes</td></tr>'

    # ── Recomendaciones próximo mes ────────────────────────────────────
    filas_rec = ""
    for r in recomendaciones[:5]:
        ticker = r.get("ticker","")
        accion = r.get("accion","")
        motivo = r.get("motivo","")
        score  = r.get("score", 0)
        c_ac   = "#28a745" if "Comprar" in accion or "Iniciar" in accion else "#f0ad4e"
        filas_rec += f"""
        <tr>
          <td style="padding:8px 10px;font-weight:700;color:#1a1a2e">{ticker}</td>
          <td style="padding:8px;color:{c_ac};font-weight:600">{accion}</td>
          <td style="padding:8px;text-align:center">{score:.0f}/100</td>
          <td style="padding:8px;color:#555;font-size:11px">{motivo}</td>
        </tr>"""

    if not filas_rec:
        filas_rec = '<tr><td colspan="4" style="padding:12px;text-align:center;color:#666">Cartera alineada con el modelo — sin cambios urgentes</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>MQ26 — Reporte Mensual {mes_año}</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:'Segoe UI',Arial,sans-serif; font-size:11px;
            color:#1c1c2e; background:white; padding:20px 30px;
            max-width:900px; margin:0 auto; }}
    @media print {{
      body {{ padding:0; }}
      .no-print {{ display:none; }}
      .page-break {{ page-break-after:always; }}
    }}
    .header {{ background:linear-gradient(135deg,#1a1a2e 0%,#0f3460 100%);
               color:white; padding:28px 32px; border-radius:8px; margin-bottom:20px; }}
    .header h1 {{ font-size:22px; margin-bottom:4px; }}
    .header p  {{ color:#aaa; font-size:12px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:16px 0; }}
    .metric {{ background:#f0f4ff; border-radius:8px; padding:14px;
               border-left:4px solid #1a1a2e; text-align:center; }}
    .metric .label {{ color:#666; font-size:10px; text-transform:uppercase;
                      letter-spacing:0.5px; margin-bottom:4px; }}
    .metric .value {{ font-size:18px; font-weight:700; color:#1a1a2e; }}
    .metric .sub   {{ font-size:10px; color:#888; margin-top:2px; }}
    .section {{ margin:20px 0; }}
    .section h2 {{ color:#1a1a2e; font-size:14px; border-bottom:2px solid #1a1a2e;
                   padding-bottom:6px; margin-bottom:12px; }}
    table {{ width:100%; border-collapse:collapse; font-size:11px; }}
    th {{ background:#1a1a2e; color:white; padding:8px 10px; text-align:left; }}
    th.center {{ text-align:center; }}
    th.right  {{ text-align:right;  }}
    .footer {{ background:#1a1a2e; color:#aaa; padding:12px 20px;
               border-radius:8px; text-align:center; font-size:10px;
               margin-top:20px; }}
    .disclaimer {{ background:#fff3cd; border:1px solid #ffc107;
                   border-radius:6px; padding:10px 14px; margin:12px 0;
                   font-size:10px; color:#856404; }}
    .btn-print {{ background:#1a1a2e; color:white; border:none; padding:10px 20px;
                  border-radius:6px; cursor:pointer; font-size:12px; margin:10px 0; }}
  </style>
</head>
<body>

<!-- BOTÓN IMPRIMIR (no se imprime) -->
<div class="no-print" style="text-align:right;margin-bottom:10px">
  <button class="btn-print" onclick="window.print()">🖨️ Guardar como PDF</button>
</div>

<!-- PÁGINA 1: PORTADA + RESUMEN -->
<div class="header">
  <div style="display:flex;justify-content:space-between;align-items:flex-start">
    <div>
      <h1>📊 Reporte Mensual de Inversiones</h1>
      <p style="font-size:16px;color:#ccc;margin-top:6px">{mes_año}</p>
    </div>
    <div style="text-align:right">
      <div style="font-size:13px;color:#ccc">Master Quant 26</div>
      <div style="font-size:11px;color:#888">Sistema DSS Unificado</div>
    </div>
  </div>
  <div style="margin-top:16px;border-top:1px solid #333;padding-top:12px">
    <span style="color:#aaa;font-size:12px">Cliente: </span>
    <span style="color:white;font-size:13px;font-weight:600">{cliente}</span>
    &nbsp;&nbsp;
    <span style="color:#aaa;font-size:12px">Cartera: </span>
    <span style="color:white;font-size:13px">{cartera}</span>
    &nbsp;&nbsp;
    <span style="color:#aaa;font-size:12px">Perfil: </span>
    <span style="color:white;font-size:13px">{perfil}</span>
  </div>
</div>

<!-- Métricas ejecutivas -->
<div class="metric-grid">
  <div class="metric">
    <div class="label">💰 Valor Cartera</div>
    <div class="value">ARS {valor_ars/1e6:.2f}M</div>
    <div class="sub">≈ USD {valor_usd:,.0f}</div>
  </div>
  <div class="metric" style="border-left-color:{color_pnl}">
    <div class="label">📈 P&L Total</div>
    <div class="value" style="color:{color_pnl}">{signo_pnl}{pnl_pct:.1f}%</div>
    <div class="sub">ARS {'+' if pnl_ars>=0 else ''}{pnl_ars/1e6:.2f}M</div>
  </div>
  <div class="metric" style="border-left-color:{color_mes}">
    <div class="label">📅 P&L del Mes</div>
    <div class="value" style="color:{color_mes}">{signo_mes}{pnl_mes:.1f}%</div>
    <div class="sub">{mes_año}</div>
  </div>
  <div class="metric">
    <div class="label">📁 Posiciones</div>
    <div class="value">{n_pos}</div>
    <div class="sub">{n_ops} operaciones el mes</div>
  </div>
</div>

<div class="page-break"></div>

<!-- PÁGINA 2: POSICIONES -->
<div class="section">
  <h2>📋 Posiciones al cierre del mes</h2>
  <table>
    <tr>
      <th>Ticker</th>
      <th class="center">Sector</th>
      <th class="center">Cant.</th>
      <th class="right">PPC USD</th>
      <th class="right">Precio actual</th>
      <th class="right">Valor ARS</th>
      <th class="center">P&L %</th>
      <th class="center">Peso</th>
    </tr>
    {filas_pos if filas_pos else '<tr><td colspan="8" style="padding:12px;text-align:center">Sin posiciones</td></tr>'}
    <tr style="background:#1a1a2e;color:white;font-weight:700">
      <td colspan="5" style="padding:8px 10px">TOTAL CARTERA</td>
      <td style="padding:8px;text-align:right">ARS ${valor_ars:,.0f}</td>
      <td style="padding:8px;text-align:center;color:{'#90ee90' if pnl_pct>=0 else '#ff9999'}">{signo_pnl}{pnl_pct:.1f}%</td>
      <td style="padding:8px;text-align:center">100%</td>
    </tr>
  </table>
</div>

<!-- Operaciones del mes -->
<div class="section">
  <h2>🔄 Operaciones realizadas en {mes_año}</h2>
  <table>
    <tr>
      <th>Fecha</th><th>Ticker</th>
      <th class="center">Tipo</th><th class="center">Cant.</th>
      <th class="right">Precio ARS</th><th class="right">Neto ARS</th>
    </tr>
    {filas_ops}
  </table>
</div>

<div class="page-break"></div>

<!-- PÁGINA 4: RECOMENDACIONES -->
<div class="section">
  <h2>🎯 Recomendaciones para el próximo mes</h2>
  <p style="color:#666;margin-bottom:10px;font-size:11px">
    Basadas en el modelo 60/20/20 (Fundamental · Técnico · Sector/Contexto).
    Optimizadas para perfil {perfil}: Sharpe primero, luego retorno USD.
  </p>
  <table>
    <tr>
      <th>Ticker</th><th>Acción</th>
      <th class="center">Score</th><th>Fundamento</th>
    </tr>
    {filas_rec}
  </table>
</div>

<div class="disclaimer">
  ⚠️ <strong>Disclaimer:</strong> Este reporte es generado automáticamente por el sistema MQ26-DSS
  y no constituye asesoramiento financiero registrado ante la CNV. Las recomendaciones se basan
  en modelos cuantitativos y deben ser validadas por un asesor calificado antes de operar.
  Invertir en instrumentos financieros conlleva riesgos. Performance pasada no garantiza
  resultados futuros. CCL de referencia: ${ccl:,.0f} ARS/USD.
</div>

<div class="footer">
  Master Quant 26 | DSS Unificado · comercial@tudominio.com ·
  Generado automáticamente el {date.today().strftime('%d/%m/%Y')} ·
  Modelo 60/20/20 v15
</div>

</body>
</html>"""

    return html


def guardar_reporte(html: str, ruta: Path) -> Path:
    """Guarda el HTML del reporte en disco."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(html, encoding="utf-8")
    return ruta
