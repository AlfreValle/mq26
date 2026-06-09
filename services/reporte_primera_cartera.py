"""
services/reporte_primera_cartera.py — HTML imprimible para "Mi Primera Cartera" (sin Streamlit).

Incluye por cada activo:
  - Fundamentals: P/E, ROE, Deuda/Capital, Dividend Yield, EPS Growth, Margen Neto
  - Objetivo de salida en ARS (consenso analistas o proyección EPS)
  - Upside estimado y horizonte de inversión
  - Tesis de inversión: párrafo profesional generado desde datos reales
"""
from __future__ import annotations

import html as _html
from datetime import datetime
from typing import Any


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return _html.escape(str(s), quote=True)


def _fmt_pct(v: Any, decimals: int = 1) -> str:
    if v is None:
        return "N/D"
    try:
        return f"{float(v):.{decimals}f}%"
    except Exception:
        return "N/D"


def _fmt_num(v: Any, decimals: int = 1, suffix: str = "") -> str:
    if v is None:
        return "N/D"
    try:
        return f"{float(v):.{decimals}f}{suffix}"
    except Exception:
        return "N/D"


def _fmt_ars(v: Any) -> str:
    if v is None:
        return "N/D"
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return "N/D"


def _upside_badge(upside: Any) -> str:
    if upside is None:
        return ""
    try:
        u = float(upside)
        if u >= 20:
            color, label = "#1a7f4b", f"+{u:.1f}%"
        elif u >= 5:
            color, label = "#2563eb", f"+{u:.1f}%"
        elif u >= 0:
            color, label = "#555", f"+{u:.1f}%"
        else:
            color, label = "#b91c1c", f"{u:.1f}%"
        return (
            f'<span style="display:inline-block;padding:2px 8px;border-radius:12px;'
            f'background:{color}18;color:{color};font-weight:600;font-size:0.82rem">'
            f'{_esc(label)}</span>'
        )
    except Exception:
        return ""


def _fund_row(label: str, value: str, hint: str = "") -> str:
    hint_span = f'<span class="fund-hint">{_esc(hint)}</span>' if hint else ""
    return (
        f'<tr><td class="fund-label">{_esc(label)}</td>'
        f'<td class="fund-val">{_esc(value)} {hint_span}</td></tr>'
    )


def _render_fundamentals_table(fund: dict[str, Any]) -> str:
    if not fund:
        return ""

    def hint_pe(v):
        if v is None:
            return ""
        if v < 12:
            return "bajo — posible descuento"
        if v < 22:
            return "razonable"
        if v < 35:
            return "moderadamente elevado"
        return "elevado — crecimiento descontado"

    def hint_roe(v):
        if v is None:
            return ""
        if v > 25:
            return "excepcional"
        if v > 15:
            return "sólido"
        if v > 8:
            return "aceptable"
        return "débil"

    def hint_dce(v):
        if v is None:
            return ""
        if v < 30:
            return "bajo"
        if v < 80:
            return "moderado"
        return "alto — vigilar"

    rows = []
    pe = fund.get("pe_ratio")
    rows.append(_fund_row("P/E (trailing)", _fmt_num(pe, 1, "x"), hint_pe(pe)))
    rows.append(_fund_row("ROE", _fmt_pct(fund.get("roe_pct")), hint_roe(fund.get("roe_pct"))))
    rows.append(_fund_row("Deuda / Capital", _fmt_pct(fund.get("deuda_capital_pct")), hint_dce(fund.get("deuda_capital_pct"))))
    rows.append(_fund_row("Dividend Yield", _fmt_pct(fund.get("div_yield_pct"))))
    rows.append(_fund_row("Crec. EPS", _fmt_pct(fund.get("eps_growth_pct"))))
    rows.append(_fund_row("Margen Neto", _fmt_pct(fund.get("profit_margin_pct"))))
    if fund.get("beta") is not None:
        rows.append(_fund_row("Beta", _fmt_num(fund.get("beta"), 2)))

    obj_ars = fund.get("objetivo_salida_ars")
    upside  = fund.get("upside_pct")
    horiz   = fund.get("horizonte_meses", 12)
    fuente  = fund.get("fuente_objetivo", "")

    obj_html = ""
    if obj_ars:
        badge = _upside_badge(upside)
        fuente_lbl = f"<br/><span class='fund-hint'>{_esc(fuente)}</span>" if fuente else ""
        obj_html = (
            f'<tr><td class="fund-label">Objetivo de salida ({horiz}m)</td>'
            f'<td class="fund-val">{_esc(_fmt_ars(obj_ars))} {badge}{fuente_lbl}</td></tr>'
        )

    n_anal = fund.get("n_analistas", 0)
    anal_row = ""
    if n_anal and int(n_anal) > 0:
        anal_row = _fund_row("Analistas cobertura", str(n_anal))

    return (
        '<table class="fund-table">'
        + "".join(rows)
        + obj_html
        + anal_row
        + "</table>"
    )


def _render_item_card(it: dict[str, Any], idx: int) -> str:
    ticker   = _esc(it.get("ticker") or "")
    tipo     = _esc(it.get("tipo") or "")
    sector   = _esc(it.get("sector") or "")
    score_t  = it.get("score_total") or 0
    senal    = _esc(it.get("senal") or "")
    px       = it.get("precio_ars")
    unidades = it.get("unidades") or 0
    subtotal = it.get("subtotal_ars")
    var_txt  = _esc(it.get("var_txt") or "")
    rsi_txt  = _esc(it.get("rsi_txt") or "")
    fund     = it.get("fundamentals") or {}
    tesis    = _esc(it.get("tesis") or "")

    obj_ars  = fund.get("objetivo_salida_ars")
    upside   = fund.get("upside_pct")
    horiz    = fund.get("horizonte_meses", 12)

    # Score bar
    score_color = "#1a7f4b" if score_t >= 65 else ("#2563eb" if score_t >= 50 else "#d97706")
    score_bar = (
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:6px">'
        f'<div style="width:{min(score_t,100):.0f}%;background:{score_color};'
        f'border-radius:4px;height:6px"></div></div>'
        f'<span style="font-size:0.82rem;font-weight:600;color:{score_color}">'
        f'{score_t:.0f}/100</span></div>'
    )

    obj_badge = ""
    if obj_ars:
        badge = _upside_badge(upside)
        obj_badge = (
            f'<div style="margin-top:4px;font-size:0.82rem;color:#444">'
            f'Objetivo: <strong>{_esc(_fmt_ars(obj_ars))}</strong> '
            f'en {horiz} meses {badge}</div>'
        )

    fund_html = _render_fundamentals_table(fund)

    tesis_html = ""
    if tesis:
        tesis_html = (
            f'<div class="tesis">'
            f'<div class="tesis-title">Tesis de inversión</div>'
            f'<p>{tesis}</p>'
            f'</div>'
        )

    return f"""
<div class="item-card">
  <div class="item-header">
    <div>
      <span class="item-ticker">{ticker}</span>
      <span class="item-badge">{tipo}</span>
      {f'<span class="item-badge sector-badge">{sector}</span>' if sector else ""}
    </div>
    <div class="item-senal">{senal}</div>
  </div>

  {score_bar}

  <div class="item-meta">
    <span>Precio: <strong>{_esc(_fmt_ars(px))}</strong></span>
    <span>Unidades: <strong>{unidades}</strong></span>
    <span>Subtotal: <strong>{_esc(_fmt_ars(subtotal))}</strong></span>
  </div>

  {obj_badge}

  <div class="item-context"><p>{var_txt}</p><p>{rsi_txt}</p></div>

  <details class="fund-details">
    <summary>Ver análisis fundamental</summary>
    {fund_html}
  </details>

  {tesis_html}
</div>
"""


def generar_html_semana(payload: dict[str, Any]) -> str:
    """Genera documento HTML completo desde el dict de `generar_narrativa_semana` / persistido."""
    anio = _esc(payload.get("anio"))
    sem  = _esc(payload.get("semana"))
    fecha = _esc(payload.get("fecha_generacion"))
    pres = payload.get("presupuesto_ars")
    ccl  = payload.get("ccl")
    resumen = _esc(payload.get("resumen_ejecutivo") or "")
    nota    = (payload.get("nota") or "").strip()
    items   = payload.get("items") or []

    _raw_disc = (payload.get("disclaimer") or "").strip()
    if not _raw_disc:
        _raw_disc = (
            "Documento educativo. No es asesoramiento financiero ni recomendación de inversión. "
            "Consultá a un profesional matriculado antes de operar. "
            "Los precios, señales y objetivos son referenciales."
        )
    disc = _esc(_raw_disc)

    cards_html = "".join(_render_item_card(it, i) for i, it in enumerate(items))

    nota_block = ""
    if nota:
        nota_block = f'<section class="nota-admin"><h3>Nota del equipo</h3><p>{_esc(nota)}</p></section>'

    gen_at   = _esc(datetime.now().strftime("%Y-%m-%d %H:%M"))
    anio_foot = datetime.now().year
    pres_s   = _esc(f"{float(pres):,.0f}" if pres is not None else "—")
    ccl_s    = _esc(f"{float(ccl):,.0f}" if ccl is not None else "—")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Mi Primera Cartera — Semana {sem}/{anio}</title>
<style>
:root {{
  --blue:   #1e3a5f;
  --blue2:  #2563eb;
  --green:  #1a7f4b;
  --amber:  #d97706;
  --red:    #b91c1c;
  --bg:     #f8fafc;
  --card:   #ffffff;
  --border: #e2e8f0;
  --text:   #1e293b;
  --muted:  #64748b;
}}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', system-ui, sans-serif; margin: 0; padding: 24px 32px;
       background: var(--bg); color: var(--text); line-height: 1.5; }}

/* Header */
.report-header {{ background: var(--blue); color: #fff; border-radius: 12px;
  padding: 20px 28px; margin-bottom: 24px; }}
.report-header h1 {{ margin: 0 0 4px; font-size: 1.4rem; font-weight: 700; }}
.report-header .meta {{ font-size: 0.88rem; opacity: .8; }}

/* Resumen */
.summary-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px;
  padding: 14px 18px; white-space: pre-wrap; font-size: 0.9rem; margin-bottom: 24px; }}

/* Cards */
.items-grid {{ display: grid; gap: 20px; }}
.item-card {{ background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 20px 24px; }}

.item-header {{ display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 10px; }}
.item-ticker {{ font-size: 1.25rem; font-weight: 700; color: var(--blue); margin-right: 8px; }}
.item-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
  background: #e0e7ff; color: #3730a3; font-size: 0.76rem; font-weight: 600;
  margin-right: 4px; }}
.sector-badge {{ background: #dcfce7; color: #166534; }}
.item-senal {{ font-size: 0.92rem; font-weight: 600; color: var(--muted); }}

.item-meta {{ display: flex; gap: 20px; font-size: 0.88rem; color: var(--muted);
  margin: 8px 0; flex-wrap: wrap; }}
.item-meta strong {{ color: var(--text); }}

.item-context {{ font-size: 0.84rem; color: var(--muted); margin: 8px 0 0; }}
.item-context p {{ margin: 2px 0; }}

/* Fundamentals */
.fund-details {{ margin-top: 14px; }}
.fund-details summary {{ cursor: pointer; font-size: 0.88rem; font-weight: 600;
  color: var(--blue2); user-select: none; }}
.fund-details summary:hover {{ text-decoration: underline; }}
.fund-table {{ width: 100%; border-collapse: collapse; margin-top: 10px;
  font-size: 0.86rem; }}
.fund-table td {{ padding: 5px 10px; border-bottom: 1px solid var(--border); }}
.fund-label {{ color: var(--muted); width: 45%; }}
.fund-val   {{ font-weight: 600; }}
.fund-hint  {{ font-weight: 400; color: var(--muted); font-size: 0.80rem;
  margin-left: 6px; }}

/* Tesis */
.tesis {{ margin-top: 16px; background: #f0fdf4; border-left: 3px solid var(--green);
  border-radius: 0 8px 8px 0; padding: 12px 16px; }}
.tesis-title {{ font-size: 0.82rem; font-weight: 700; color: var(--green);
  text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }}
.tesis p {{ margin: 0; font-size: 0.88rem; line-height: 1.55; color: var(--text); }}

/* Nota admin */
.nota-admin {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
  padding: 14px 18px; margin: 20px 0; }}
.nota-admin h3 {{ margin: 0 0 6px; font-size: 0.92rem; color: #92400e; }}

/* Footer */
.disclaimer {{ font-size: 0.76rem; color: var(--muted); margin-top: 32px;
  padding-top: 16px; border-top: 1px solid var(--border); }}
.footer {{ margin-top: 12px; font-size: 0.72rem; color: #94a3b8; text-align: center; }}

@media print {{
  body {{ padding: 12px 16px; background: #fff; }}
  .item-card {{ page-break-inside: avoid; }}
  .fund-details {{ display: block; }}
  .fund-details summary {{ display: none; }}
}}
</style>
</head>
<body>

<div class="report-header">
  <h1>Mi Primera Cartera de Inversiones</h1>
  <div class="meta">
    Año {anio} · Semana ISO {sem} · {fecha or gen_at} &nbsp;|&nbsp;
    Presupuesto: ${pres_s} ARS &nbsp;|&nbsp; CCL ref.: ${ccl_s}
  </div>
</div>

<h2 style="font-size:1rem;color:var(--blue);margin:0 0 8px">Resumen ejecutivo</h2>
<div class="summary-box">{resumen}</div>

{nota_block}

<h2 style="font-size:1rem;color:var(--blue);margin:0 0 12px">Activos recomendados</h2>
<div class="items-grid">
{cards_html}
</div>

<p class="disclaimer">{disc}</p>
<p class="footer">Master Quant · generado {gen_at} · {anio_foot} · solo informativo</p>

</body>
</html>
"""
