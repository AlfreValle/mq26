"""
services/reporte_inversor.py — Reportes HTML para inversor (tier IN / ES / SA)

Sin Streamlit. Salida HTML con estilos para impresión (Ctrl+P → PDF).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from core.diagnostico_types import (
    DiagnosticoResult,
    PrioridadAccion,
    RENDIMIENTO_MODELO_YTD_REF,
    RecomendacionResult,
    perfil_diagnostico_valido,
)
from core.renta_fija_ar import top_instrumentos_rf
from core.retirement_goal import simulate_retirement


def _esc(val: Any) -> str:
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _seccion_metricas_html(valor_usd: float, pnl_pct: float, semaforo: str) -> str:
    return f"""
    <div class="metrics">
      <div class="metric"><span>Valor USD</span><strong>USD {valor_usd:,.0f}</strong></div>
      <div class="metric"><span>Rend. acum. USD</span><strong>{pnl_pct:.1f}%</strong></div>
      <div class="metric"><span>Semáforo</span><strong>{_esc(semaforo)}</strong></div>
    </div>
    """


def _proyeccion_barras_html(
    perfil_key: str,
    aporte_mensual_usd: float,
    meses: int,
) -> str:
    REND = {"conservador": 0.06, "moderado": 0.09, "arriesgado": 0.12, "muy": 0.15}
    VOL = {"conservador": 0.025, "moderado": 0.04, "arriesgado": 0.06, "muy": 0.07}
    pk = perfil_key.lower().replace(" ", "")
    if "muy" in pk:
        rkey = "muy"
    elif "arries" in pk or "riesg" in pk:
        rkey = "arriesgado"
    elif "conserv" in pk:
        rkey = "conservador"
    else:
        rkey = "moderado"
    rng = np.random.default_rng(seed=42)
    rend = REND.get(rkey, 0.09)
    vol = VOL.get(rkey, 0.04)
    r_d = rng.normal(rend / 252, vol / 15, max(252, meses * 21))
    sim = simulate_retirement(
        aporte_mensual=aporte_mensual_usd,
        n_meses_acum=meses,
        retiro_mensual=0.0,
        n_meses_desacum=0,
        retornos_diarios=r_d,
        n_sim=800,
    )
    p10, p50, p90 = sim["p10"], sim["p50"], sim["p90"]
    m = max(abs(p10), abs(p50), abs(p90), 1.0)
    w10 = max(5, int(100 * abs(p10) / m))
    w50 = max(5, int(100 * abs(p50) / m))
    w90 = max(5, int(100 * abs(p90) / m))
    return f"""
    <h3>Tu proyección ({meses//12} años)</h3>
    <p class="muted">Simulación Montecarlo (semilla fija). Pesimista / Base / Optimista.</p>
    <div class="bars">
      <div class="barrow"><span>Pesimista (P10)</span><div class="bar" style="width:{w10}%">USD {p10:,.0f}</div></div>
      <div class="barrow"><span>Base (P50)</span><div class="bar" style="width:{w50}%">USD {p50:,.0f}</div></div>
      <div class="barrow"><span>Optimista (P90)</span><div class="bar" style="width:{w90}%">USD {p90:,.0f}</div></div>
    </div>
    """


def _tabla_top_rf_html(rows: list[dict[str, Any]]) -> str:
    h = "<table class='tbl'><tr><th>Ticker</th><th>Emisor</th><th>TIR ref. %</th><th>Calif.</th></tr>"
    for r in rows:
        h += (
            f"<tr><td>{_esc(r.get('ticker', ''))}</td><td>{_esc(r.get('emisor', ''))}</td>"
            f"<td>{float(r.get('tir_ref', 0.0)):.2f}</td><td>{_esc(r.get('calificacion', ''))}</td></tr>"
        )
    h += "</table>"
    return h


def _ladder_html(ladder: list[tuple[int, float]]) -> str:
    if not ladder:
        return "<p class='muted'>Sin vencimientos de renta fija local en cartera.</p>"
    mx = max(w for _, w in ladder) or 1.0
    html = "<div class='bars'>"
    for y, w in ladder:
        pct = max(4, int(100 * w / mx))
        html += f"<div class='barrow'><span>{y}</span><div class='bar' style='width:{pct}%'>{w * 100:.1f}%</div></div>"
    html += "</div>"
    return html


def _comparacion_rend_html(
    cmpd: dict[str, Any] | None,
    diag: DiagnosticoResult,
    modelo_frac_default: float,
) -> str:
    cliente = float(diag.rendimiento_ytd_usd_pct or 0.0)
    modelo_pct = modelo_frac_default * 100.0
    spy = None
    if cmpd:
        if "cliente" in cmpd:
            cliente = float(cmpd["cliente"])
        if "modelo" in cmpd:
            modelo_pct = float(cmpd["modelo"])
        spy = cmpd.get("spy")
    diff = cliente - modelo_pct
    p = f"""
    <p>Rendimiento <strong>acumulado en USD</strong> de tu cartera: <strong>{cliente:+.1f}%</strong>.
    Cartera modelo del perfil <em>{_esc(diag.perfil)}</em> (referencia estática): <strong>{modelo_pct:+.2f}%</strong> YTD.
    Diferencia vs modelo: <strong>{diff:+.2f} pp</strong>.</p>
    """
    p += "<table class='tbl'><tr><th>Serie</th><th>Rendimiento %</th></tr>"
    p += f"<tr><td>Tu cartera</td><td>{cliente:+.1f}%</td></tr>"
    p += f"<tr><td>Cartera modelo perfil</td><td>{modelo_pct:+.2f}%</td></tr>"
    if spy is not None:
        p += f"<tr><td>SPY (benchmark)</td><td>{float(spy):+.1f}%</td></tr>"
    else:
        p += "<tr><td>SPY (benchmark)</td><td>— (ver Riesgo / backtest)</td></tr>"
    p += "</table>"
    return p


def _tir_paragraph(tir_cli: float | None, top: list[dict[str, Any]]) -> str:
    best = top[0] if top else None
    if tir_cli is not None:
        t = f"<p>TIR promedio ponderada de tu renta fija AR (referencia): <strong>{tir_cli:.2f}%</strong>.</p>"
    else:
        t = "<p>No hay renta fija local con TIR de referencia ponderada en cartera.</p>"
    if best:
        t += (
            f"<p>Mayor TIR entre ON corporativas del universo MQ26: <strong>{_esc(best.get('ticker', ''))}</strong> "
            f"({float(best.get('tir_ref', 0)):.2f}%, {_esc(best.get('calificacion', ''))}).</p>"
        )
    return t


def _svg_three_lines(
    fechas: list[Any],
    y_cliente: list[float],
    y_modelo: list[float],
    y_spy: list[float],
) -> str:
    n = len(fechas)
    if n < 2 or n != len(y_cliente) or n != len(y_modelo) or n != len(y_spy):
        return ""

    def norm_y(seq: list[float]) -> list[float]:
        lo, hi = min(seq), max(seq)
        if hi - lo < 1e-9:
            return [50.0] * len(seq)
        return [10 + 80 * (v - lo) / (hi - lo) for v in seq]

    nc, nm, ns = norm_y(y_cliente), norm_y(y_modelo), norm_y(y_spy)
    xs = [40 + 320 * i / (n - 1) for i in range(n)]

    def path(coords: list[float]) -> str:
        pts = [f"{xs[i]:.1f},{100 - coords[i]:.1f}" for i in range(n)]
        return "M " + " L ".join(pts)

    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120" class="chart3">
      <text x="4" y="14" font-size="10">Cartera (azul) / modelo (naranja) / SPY (verde)</text>
      <path d="{path(nc)}" fill="none" stroke="#1565c0" stroke-width="2"/>
      <path d="{path(nm)}" fill="none" stroke="#e67e22" stroke-width="2"/>
      <path d="{path(ns)}" fill="none" stroke="#27ae60" stroke-width="2"/>
    </svg>
    """


def _seccion_ventaja_competitiva_html(
    diagnostico: DiagnosticoResult,
    bloque_competitivo: dict[str, Any] | None,
) -> str:
    bc = bloque_competitivo or {}
    perfil_v = perfil_diagnostico_valido(diagnostico.perfil)
    modelo_frac = float(
        bc.get("rendimiento_modelo_frac") or RENDIMIENTO_MODELO_YTD_REF.get(perfil_v, 0.09)
    )
    top: list[dict[str, Any]] = list(bc.get("top_rf") or [])
    if not top:
        top = top_instrumentos_rf(4)
    tir_cli = bc.get("tir_ponderada_cliente")
    if tir_cli is not None:
        tir_cli = float(tir_cli)
    ladder = list(bc.get("ladder") or [])
    cmpd = bc.get("comparacion_rendimientos_pct")
    series = bc.get("series_comparacion")

    body = "<h2>Tu cartera vs referencias</h2>"
    body += _comparacion_rend_html(cmpd if isinstance(cmpd, dict) else None, diagnostico, modelo_frac)
    body += "<h3>Renta fija local</h3>"
    body += _tir_paragraph(tir_cli, top)
    body += "<h3>Instrumentos de referencia (ON corporativas)</h3>"
    body += _tabla_top_rf_html(top)
    body += "<h3>Ladder de vencimientos (tu cartera)</h3>"
    body += _ladder_html([(y, w) for y, w in ladder])
    body += "<h3>Comparación de trayectorias</h3>"
    if series and isinstance(series, dict):
        fechas = list(series.get("fechas") or [])
        yc = list(series.get("cliente_norm") or [])
        ym = list(series.get("modelo_norm") or [])
        ys = list(series.get("spy_norm") or [])
        svg = _svg_three_lines(fechas, yc, ym, ys)
        if svg:
            body += svg
        else:
            body += "<p class='muted'>Series incompletas para gráfico inline.</p>"
    else:
        body += "<p class='muted'>Curvas históricas detalladas en la app (Riesgo / backtest).</p>"
    return body


def generar_reporte_inversor(
    diagnostico: DiagnosticoResult,
    recomendacion: RecomendacionResult | None,
    metricas: dict,
    aporte_mensual_usd: float = 100.0,
    horizon_meses: int = 36,
    bloque_competitivo: dict[str, Any] | None = None,
) -> str:
    obs_show = [
        o
        for o in diagnostico.observaciones
        if o.prioridad
        in (PrioridadAccion.CRITICA, PrioridadAccion.ALTA, PrioridadAccion.MEDIA)
    ][:3]
    ccl_ctx = float((recomendacion.ccl if recomendacion else 0) or metricas.get("ccl") or 1000.0)
    valor_usd = float(metricas.get("total_valor", 0) or 0) / max(ccl_ctx, 1e-9)
    if diagnostico.valor_cartera_usd > 0:
        valor_usd = diagnostico.valor_cartera_usd
    pnl_pct = float(diagnostico.rendimiento_ytd_usd_pct or 0.0)
    _anio = datetime.now().year

    obs_html = ""
    for o in obs_show:
        obs_html += f"""
        <div class="obs">
          <div class="obs-t">{_esc(o.icono)} {_esc(o.titulo)}</div>
          <p>{_esc(o.texto_corto)}</p>
          <p class="cifra">{_esc(o.cifra_clave)}</p>
        </div>
        """

    accion_html = "<p>Agregá capital disponible en la app para ver compras sugeridas.</p>"
    if recomendacion and recomendacion.compras_recomendadas and not recomendacion.alerta_mercado:
        accion_html = "<h3>Acción recomendada</h3><ul>"
        for it in recomendacion.compras_recomendadas:
            accion_html += (
                f"<li><strong>{_esc(it.ticker)}</strong> × {it.unidades} u. @ "
                f"${it.precio_ars_estimado:,.0f} ARS — {_esc(it.justificacion)}</li>"
            )
        accion_html += "</ul>"
        if recomendacion.pendientes_proxima_inyeccion:
            accion_html += "<p><em>Próxima inyección:</em></p><ul>"
            for p in recomendacion.pendientes_proxima_inyeccion[:5]:
                accion_html += f"<li>{_esc(p.get('ticker',''))}: {_esc(p.get('motivo',''))}</li>"
            accion_html += "</ul>"
    elif recomendacion and recomendacion.alerta_mercado:
        accion_html = f'<p class="alert">{_esc(recomendacion.mensaje_alerta)}</p>'

    ventaja_html = _seccion_ventaja_competitiva_html(diagnostico, bloque_competitivo)

    body = f"""
    <article class="rpt">
      <header>
        <div class="logo">MQ26</div>
        <h1>Informe para {_esc(diagnostico.cliente_nombre) or "inversor"}</h1>
        <p class="meta">{_esc(diagnostico.fecha_diagnostico)} · {_esc(diagnostico.perfil)} · Horizonte {_esc(diagnostico.horizonte_label)}</p>
      </header>
      <h2>Tu cartera en números</h2>
      {_seccion_metricas_html(valor_usd, pnl_pct, diagnostico.semaforo.value)}
      {ventaja_html}
      <h2>Diagnóstico</h2>
      <p>{_esc(diagnostico.titulo_semaforo)}</p>
      {obs_html}
      {accion_html}
      {_proyeccion_barras_html(diagnostico.perfil, aporte_mensual_usd, horizon_meses)}
      <footer class="disc">
        <p>Este informe es <strong>meramente informativo</strong> y no constituye asesoramiento
        financiero personalizado, diagnóstico fiscal ni recomendación de compra o venta
        de instrumentos negociables.</p>
        <p>Los rendimientos y escenarios mostrados son ilustrativos; resultados pasados
        o simulados no garantizan desempeños futuros.</p>
        <p class="foot-brand">Master Quant · {_anio}</p>
      </footer>
    </article>
    """
    return _html_doc("MQ26 — Informe inversor", body, compact=True)


def generar_reporte_estudio(
    filas_clientes: list[dict[str, Any]],
    diagnostico_cliente: DiagnosticoResult | None,
    recomendacion_cliente: RecomendacionResult | None,
    metricas: dict,
    bloque_competitivo: dict[str, Any] | None = None,
) -> str:
    tabla = "<table class='tbl'><tr><th>Cliente</th><th>Semáforo</th><th>Score</th></tr>"
    for row in filas_clientes:
        tabla += f"<tr><td>{_esc(row.get('nombre',''))}</td><td>{_esc(row.get('semaforo',''))}</td>"
        tabla += f"<td>{row.get('score',0):.0f}</td></tr>"
    tabla += "</table>"
    inner_full = generar_reporte_inversor(
        diagnostico_cliente or _dummy_diagnostico(),
        recomendacion_cliente,
        metricas,
        bloque_competitivo=bloque_competitivo,
    )
    a0 = inner_full.find("<article")
    a1 = inner_full.rfind("</article>")
    inner_fragment = inner_full[a0 : a1 + 12] if a0 >= 0 and a1 >= a0 else ""
    extra = f"""
    <section class="estudio">
      <h2>Panel de estudio</h2>
      {tabla}
      <h3>Metodología resumida</h3>
      <p>Score global = 35% cobertura defensiva + 25% concentración + 20% rendimiento relativo + 20% señales de salida.</p>
      <h3>Clientes en atención</h3>
      <p>Priorizá seguimiento en carteras con semáforo rojo o amarillo en el panel.</p>
    </section>
    """
    return _html_doc(
        "MQ26 — Informe estudio",
        extra + inner_fragment,
        compact=False,
    )


def generar_reporte_institucional(
    diagnostico: DiagnosticoResult,
    recomendacion: RecomendacionResult | None,
    metricas: dict,
    asesor: str = "",
    matricula: str = "",
    bloque_competitivo: dict[str, Any] | None = None,
) -> str:
    base = generar_reporte_estudio(
        [{"nombre": diagnostico.cliente_nombre, "semaforo": diagnostico.semaforo.value, "score": diagnostico.score_total}],
        diagnostico,
        recomendacion,
        metricas,
        bloque_competitivo=bloque_competitivo,
    )
    anexo = f"""
    <section class="sa">
      <h2>Metodología y parámetros</h2>
      <p>Targets de renta fija / renta variable y límites de concentración provienen de las reglas MQ26 (perfil × horizonte; versión publicada en el diagnóstico).</p>
      <p>Fuentes de datos: precios y series de mercado (proveedores configurados), BCRA/datos públicos AR según módulo.</p>
      <h3>Disclaimer regulatorio</h3>
      <p>Este documento no es una recomendación personalizada ni oferta pública. Las decisiones de inversión son exclusiva responsabilidad del destinatario.</p>
      <p>Firma: {_esc(asesor)} — Mat.: {_esc(matricula)}</p>
    </section>
    """
    insert_at = base.rfind("</body>")
    if insert_at > 0:
        return base[:insert_at] + anexo + base[insert_at:]
    return base + anexo


def _dummy_diagnostico() -> DiagnosticoResult:
    from core.diagnostico_types import Semaforo

    return DiagnosticoResult(
        cliente_nombre="",
        perfil="Moderado",
        horizonte_label="1 año",
        fecha_diagnostico="",
        score_total=50.0,
        semaforo=Semaforo.AMARILLO,
        score_cobertura_defensiva=50.0,
        score_concentracion=50.0,
        score_rendimiento=50.0,
        score_senales_salida=50.0,
    )


def _html_doc(title: str, body: str, compact: bool) -> str:
    css = """
    body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1a1a2e;background:#fafafa;}
    .rpt,.estudio,.sa{max-width:720px;margin:0 auto;background:#fff;padding:24px;border-radius:8px;}
    header .logo{font-weight:800;color:#1565c0;}
    .metrics{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0;}
    .metric{flex:1;min-width:140px;padding:12px;background:#f0f4f8;border-radius:6px;}
    .obs{border-left:4px solid #1565c0;padding-left:12px;margin:12px 0;}
    .cifra{font-weight:600;}
    .bars .barrow{margin:8px 0;}
    .bar{background:#1565c0;color:#fff;padding:4px 8px;border-radius:4px;font-size:0.9rem;}
    .tbl{width:100%;border-collapse:collapse;margin:12px 0;}
    .tbl th,.tbl td{border:1px solid #ccc;padding:6px;text-align:left;}
    .disc,.muted{font-size:0.85rem;color:#555;margin-top:24px;}
    .disc p{margin:0 0 0.65rem 0;line-height:1.45;}
    .disc p:last-child{margin-bottom:0;}
    .foot-brand{font-size:0.82rem;font-weight:600;color:#333;margin-top:10px;}
    .alert{background:#fff3e0;padding:12px;border-radius:6px;}
    .chart3{max-width:100%;height:auto;margin:12px 0;display:block;}
    """
    if compact:
        css += "h1{font-size:1.4rem;}h2{font-size:1.1rem;}"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{_esc(title)}</title>
    <style>{css}</style></head><body>{body}</body></html>"""
