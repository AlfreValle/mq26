"""
services/reporte_primera_cartera.py — HTML imprimible para "Mi Primera Cartera" (sin Streamlit).
"""
from __future__ import annotations

import html as _html
from datetime import datetime
from typing import Any


def _esc(s: Any) -> str:
    if s is None:
        return ""
    return _html.escape(str(s), quote=True)


def generar_html_semana(payload: dict[str, Any]) -> str:
    """Genera documento HTML completo desde el dict de `generar_narrativa_semana` / persistido."""
    anio = _esc(payload.get("anio"))
    sem = _esc(payload.get("semana"))
    fecha = _esc(payload.get("fecha_generacion"))
    pres = payload.get("presupuesto_ars")
    ccl = payload.get("ccl")
    resumen = _esc(payload.get("resumen_ejecutivo"))
    _raw_disc = (payload.get("disclaimer") or "").strip()
    if not _raw_disc:
        _raw_disc = (
            "Documento educativo. No es asesoramiento financiero ni recomendación de inversión. "
            "Consultá a un profesional matriculado antes de operar. "
            "Los precios y señales son referenciales y pueden no reflejar el mercado en tiempo real."
        )
    disc = _esc(_raw_disc)
    nota = (payload.get("nota") or "").strip()
    items = payload.get("items") or []

    filas = []
    for it in items:
        t = _esc(it.get("ticker"))
        tipo = _esc(it.get("tipo"))
        st = _esc(it.get("score_total"))
        px = it.get("precio_ars")
        un = _esc(it.get("unidades"))
        var_txt = _esc(it.get("var_txt"))
        rsi_txt = _esc(it.get("rsi_txt"))
        senal = _esc(it.get("senal"))
        sub = it.get("subtotal_ars")
        px_s = _esc(f"{float(px):,.2f}" if px is not None else "—")
        sub_s = _esc(f"{float(sub):,.2f}" if sub is not None else "—")
        filas.append(
            f"""<tr>
<td><strong>{t}</strong><br/><span class="muted">{tipo}</span></td>
<td>{st}</td>
<td>{senal}</td>
<td class="num">{px_s}</td>
<td class="num">{un}</td>
<td class="num">{sub_s}</td>
</tr>
<tr class="detail"><td colspan="6"><p>{var_txt}</p><p>{rsi_txt}</p></td></tr>"""
        )

    nota_block = ""
    if nota:
        nota_block = f'<section class="nota"><h3>Nota</h3><p>{_esc(nota)}</p></section>'

    gen_at = _esc(datetime.now().strftime("%Y-%m-%d %H:%M"))
    anio_foot = datetime.now().year

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Mi Primera Cartera — Semana {sem}/{anio}</title>
<style>
body {{ font-family: 'Segoe UI', system-ui, sans-serif; margin: 24px; color: #1a1a1a; line-height: 1.45; }}
h1 {{ font-size: 1.35rem; margin-bottom: 0.25rem; }}
h2 {{ font-size: 1.05rem; margin-top: 1.5rem; }}
.muted {{ color: #555; font-size: 0.85rem; }}
.meta {{ color: #444; font-size: 0.9rem; margin-bottom: 1rem; }}
.summary {{ background: #f4f6fa; padding: 12px 16px; border-radius: 8px; white-space: pre-wrap; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.92rem; }}
th, td {{ border: 1px solid #d8dee9; padding: 8px 10px; vertical-align: top; }}
th {{ background: #e8ecff; text-align: left; }}
tr.detail td {{ background: #fafbfd; font-size: 0.88rem; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.disclaimer {{ font-size: 0.78rem; color: #444; margin-top: 2rem; padding-top: 12px; border-top: 1px solid #ccc; }}
.nota {{ margin-top: 1rem; }}
.footer {{ margin-top: 2rem; font-size: 0.75rem; color: #666; }}
</style>
</head>
<body>
<h1>Mi Primera Cartera de Inversiones</h1>
<p class="meta">Año {anio} — Semana ISO {sem} — Generado {fecha or gen_at}</p>
<p class="muted">Presupuesto orientativo: ${_esc(f"{float(pres):,.0f}" if pres is not None else "—")} ARS · CCL ref.: ${_esc(f"{float(ccl):,.0f}" if ccl is not None else "—")}</p>

<h2>Resumen</h2>
<div class="summary">{resumen}</div>

{nota_block}

<h2>Detalle</h2>
<table>
<thead><tr>
<th>Activo</th><th>Score</th><th>Señal</th><th class="num">Precio ARS</th><th class="num">Unidades</th><th class="num">Subtotal ARS</th>
</tr></thead>
<tbody>{"".join(filas)}</tbody>
</table>

<p class="disclaimer">{disc}</p>
<p class="footer">Master Quant · documento informativo generado automáticamente · {gen_at} · {anio_foot}</p>
</body>
</html>
"""
