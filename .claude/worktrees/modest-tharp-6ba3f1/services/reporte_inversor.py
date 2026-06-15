"""
services/reporte_inversor.py — Reportes HTML para inversor (tier IN / ES / SA)

Sin Streamlit. Salida HTML con estilos para impresión (Ctrl+P → PDF).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from core.diagnostico_types import (
    DiagnosticoResult,
    PrioridadAccion,
    RENDIMIENTO_MODELO_YTD_REF,
    RecomendacionResult,
    perfil_diagnostico_valido,
)
from core.renta_fija_ar import es_renta_fija, top_instrumentos_rf
from core.retirement_goal import simulate_retirement

_PALETA_POS = ("#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777", "#0d9488", "#ea580c", "#4f46e5")


def _tipo_es_rf_local(tipo: str) -> bool:
    t = (tipo or "").upper().strip()
    return t in (
        "ON", "ON_USD", "BONO", "BONO_USD", "LETRA", "LECAP", "LEDE",
        "BONCER", "BOPREAL", "DUAL", "USD_LINKED",
    )


def _fila_es_rf(ticker: str, tipo: str) -> bool:
    return _tipo_es_rf_local(tipo) or es_renta_fija(str(ticker or "").upper().strip())


def _explica_activo(
    ticker: str,
    peso_pct: float,
    es_rf: bool,
    resultado_pct: float | None,
    es_top_concentr: bool,
) -> str:
    """Texto corto en palabras llanas (sin jerga de trading)."""
    t = _esc(ticker)
    rol = (
        "Actúa como <strong>apoyo más estable</strong> en tu cartera (ingresos / menor vaivén que muchas acciones). "
        if es_rf
        else "Aporta <strong>crecimiento y exposición al mercado</strong>; conviene combinarlo con renta fija según tu perfil. "
    )
    tam = ""
    if peso_pct >= 22:
        tam = f"Es una de tus <strong>posiciones centrales</strong> (~{peso_pct:.1f}% del patrimonio). "
    elif peso_pct >= 8:
        tam = f"Pesa <strong>~{peso_pct:.1f}%</strong> del total: suma, pero no es lo único que mueve tu resultado. "
    else:
        tam = f"Es una <strong>línea más chica</strong> (~{peso_pct:.1f}%): aporta diversificación sin dominar el todo. "
    res = ""
    if resultado_pct is not None:
        if resultado_pct > 0.5:
            res = f"Respecto de tu costo, viene <strong>{resultado_pct:+.1f}% arriba</strong> (referencia, no garantía futura). "
        elif resultado_pct < -0.5:
            res = (
                f"Está <strong>{abs(resultado_pct):.1f}% debajo</strong> de tu costo: no significa que “esté mal”, "
                "pero conviene mirarlo junto con el resto del plan. "
            )
        else:
            res = "Va <strong>cerca de tu precio de entrada</strong>: momento de observar con calma. "
    conc = ""
    if es_top_concentr:
        conc = (
            "<strong>Concentración:</strong> acá tenés un buen pedazo del patrimonio; si el peso te incomoda, "
            "es razonable diluir con el tiempo y con asesoramiento. "
        )
    return f"{rol}{tam}{res}{conc}"


def _grafico_barras_pesos_html(pares: list[tuple[str, float]]) -> str:
    """Barras horizontales de participación por activo."""
    if not pares:
        return "<p class='muted'>No hay datos de pesos para graficar.</p>"
    mx = max(w for _, w in pares) or 1.0
    h = "<div class='chart-bars'>"
    for i, (tk, w) in enumerate(pares[:12]):
        pct = max(3, int(100 * w / mx))
        col = _PALETA_POS[i % len(_PALETA_POS)]
        h += (
            f"<div class='crow'><span class='ctk'>{_esc(tk)}</span>"
            f"<div class='cbar-wrap'><div class='cbar' style='width:{pct}%;background:{col};'>"
            f"<span class='cval'>{w:.1f}%</span></div></div></div>"
        )
    h += "</div>"
    return h


def _grafico_rf_rv_dona_html(pct_rf: float, pct_rv: float) -> str:
    """Donut simple RF vs RV con CSS."""
    pr = max(0.0, min(100.0, float(pct_rf)))
    pv = max(0.0, min(100.0, float(pct_rv)))
    s = pr + pv
    if s < 1e-6:
        pr, pv = 50.0, 50.0
        s = 100.0
    pr_n, pv_n = 100.0 * pr / s, 100.0 * pv / s
    return f"""
    <div class="donut-wrap">
      <div class="donut" style="background:conic-gradient(#2563eb 0% {pr_n:.1f}%, #059669 {pr_n:.1f}% 100%);"></div>
      <ul class="donut-legend">
        <li><span class="lg rf"></span> Renta fija ~{pr:.0f}%</li>
        <li><span class="lg rv"></span> Renta variable ~{pv:.0f}%</li>
      </ul>
    </div>
    """


def _tabla_posiciones_con_razon(
    df_ag: pd.DataFrame,
    diag: DiagnosticoResult,
) -> str:
    if df_ag is None or df_ag.empty:
        return "<p class='muted'>No hay posiciones cargadas en el informe; importá tu broker en la app para personalizar esta hoja.</p>"
    max_t = str(getattr(diag, "activo_mas_concentrado", "") or "").strip().upper()
    rows: list[tuple[str, float, str, str, bool, float | None]] = []
    for _, r in df_ag.iterrows():
        tk = str(r.get("TICKER", "") or "").strip().upper()
        if not tk:
            continue
        try:
            w = float(r.get("PESO_PCT", 0) or 0) * 100.0
        except (TypeError, ValueError):
            w = 0.0
        tipo = str(r.get("TIPO", "") or "")
        es_rf = _fila_es_rf(tk, tipo)
        res = None
        for col in ("PNL_PCT_USD", "PNL_PCT"):
            if col in r.index:
                try:
                    res = float(r.get(col, 0) or 0) * 100.0
                    break
                except (TypeError, ValueError):
                    res = None
        es_top = tk == max_t and w > 15
        razon = _explica_activo(tk, w, es_rf, res, es_top)
        clase = "Renta fija" if es_rf else "Renta variable"
        rows.append((tk, w, clase, razon, es_rf, res))
    rows.sort(key=lambda x: -x[1])
    h = "<table class='tbl tbl-pos'><tr><th>Activo</th><th class='num'>Peso</th><th>Tipo</th><th>Por qué está en tu cartera</th></tr>"
    for tk, w, clase, razon, _, _ in rows:
        h += (
            f"<tr><td class='sym'>{_esc(tk)}</td><td class='num'>{w:.1f}%</td>"
            f"<td>{_esc(clase)}</td><td class='razon'>{razon}</td></tr>"
        )
    h += "</table>"
    return h


def _esc(val: Any) -> str:
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _seccion_metricas_html(valor_usd: float, resultado_pct: float, semaforo: str) -> str:
    _sem = _esc(str(getattr(semaforo, "value", semaforo)))
    _sem_cls = str(getattr(semaforo, "value", semaforo)).lower().replace(" ", "-")
    _sub = (
        "variación no realizada: sube o baja con el mercado hasta que vendas."
        if resultado_pct >= 0
        else "menos valor que tu costo de compra, aún no realizada hasta que vendas."
    )
    return f"""
    <div class="metrics">
      <div class="metric metric--pri"><span>Patrimonio (referencia USD)</span><strong>USD {valor_usd:,.0f}</strong></div>
      <div class="metric metric--{'ok' if resultado_pct >= 0 else 'warn'}"><span>Tu resultado respecto del costo</span>
        <strong>{resultado_pct:+.1f}%</strong>
        <span class="metric-sub">{_sub}</span></div>
      <div class="metric"><span>Estado general</span><strong class="sem-{_esc(_sem_cls)}">{_sem}</strong></div>
    </div>
    """


def _seccion_plan_simulacion_html(bloque: dict[str, Any] | None) -> str:
    """Parámetros y salidas de «Plan y simulaciones» desde la app (si el usuario generó el bloque)."""
    if not bloque:
        return ""
    hz = _esc(str(bloque.get("horizonte_label") or ""))
    meses = int(bloque.get("meses") or 0)
    ap_usd = float(bloque.get("aporte_mensual_usd") or 0.0)
    ap_ars = float(bloque.get("aporte_mensual_ars") or 0.0)
    obj = float(bloque.get("objetivo_usd") or 0.0)
    cap0 = float(bloque.get("capital_inicial_usd") or 0.0)
    ed = bloque.get("escenarios_det") or {}
    rows_esc = ""
    for k in ("Pesimista", "Base", "Optimista"):
        if k in ed:
            rows_esc += f"<tr><td>{_esc(k)}</td><td>USD {float(ed[k]):,.0f}</td></tr>"
    mc = bloque.get("montecarlo")
    mc_html = ""
    if isinstance(mc, dict) and mc.get("p50") is not None:
        mc_html = (
            "<h4>Montecarlo SPY (bootstrap)</h4>"
            "<table class='tbl'><tr><th>Percentil</th><th>Patrimonio final ref. USD</th></tr>"
            f"<tr><td>P10</td><td>{float(mc.get('p10', 0)):,.0f}</td></tr>"
            f"<tr><td>P50</td><td>{float(mc.get('p50', 0)):,.0f}</td></tr>"
            f"<tr><td>P90</td><td>{float(mc.get('p90', 0)):,.0f}</td></tr></table>"
        )
        if "prob_supera_objetivo" in mc:
            mc_html += (
                f"<p class='muted'>Prob. de superar el objetivo declarado: "
                f"<strong>{float(mc['prob_supera_objetivo']) * 100:.1f}%</strong>.</p>"
            )
    obj_row = ""
    if obj > 0:
        obj_row = f"<tr><td>Objetivo patrimonio (USD)</td><td>{obj:,.0f}</td></tr>"
    return f"""
    <div class="plan-sim-block">
      <h3 class="h-sec">Plan y simulaciones (capturado desde la app)</h3>
      <p class="muted">Parámetros y resultados ilustrativos al descargar; no incluye comisiones ni impuestos.</p>
      <table class="tbl">
        <tr><th>Concepto</th><th>Valor</th></tr>
        <tr><td>Horizonte</td><td>{hz} ({meses} meses)</td></tr>
        <tr><td>Patrimonio inicial ref. USD</td><td>{cap0:,.0f}</td></tr>
        <tr><td>Aporte mensual</td><td>USD {ap_usd:,.0f} (~ ARS {ap_ars:,.0f})</td></tr>
        {obj_row}
      </table>
      <h4>Escenarios determinísticos (fin de período)</h4>
      <table class="tbl">
        <tr><th>Escenario</th><th>Final ref. USD</th></tr>
        {rows_esc}
      </table>
      {mc_html}
    </div>
    """


def _proyeccion_barras_html(
    perfil_key: str,
    aporte_mensual_usd: float,
    meses: int,
    capital_inicial_usd: float = 0.0,
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
        capital_inicial_usd=float(capital_inicial_usd or 0.0),
    )
    p10, p50, p90 = sim["p10"], sim["p50"], sim["p90"]
    m = max(abs(p10), abs(p50), abs(p90), 1.0)
    w10 = max(5, int(100 * abs(p10) / m))
    w50 = max(5, int(100 * abs(p50) / m))
    w90 = max(5, int(100 * abs(p90) / m))
    return f"""
    <h3>Tu proyección ilustrativa ({meses//12} años)</h3>
    <p class="muted">Simulación Montecarlo con semilla fija: escenarios pesimista, base y optimista (no es promesa de resultado).</p>
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
    <p><strong>Resultado de tu cartera</strong> (referencia USD, acumulado): <strong>{cliente:+.1f}%</strong>.
    La <strong>cartera modelo MQ26</strong> para tu perfil <em>{_esc(diag.perfil)}</em> usa una referencia estática YTD de
    <strong>{modelo_pct:+.2f}%</strong> (no es una inversión que podás comprar tal cual; sirve para comparar el “estilo” del armado).
    La brecha aproximada es <strong>{diff:+.2f} puntos</strong>.</p>
    """
    p += "<table class='tbl'><tr><th>Serie</th><th>Resultado / ref. %</th></tr>"
    p += f"<tr><td>Tu cartera</td><td>{cliente:+.1f}%</td></tr>"
    p += f"<tr><td>Cartera modelo (perfil)</td><td>{modelo_pct:+.2f}%</td></tr>"
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
      <text x="4" y="14" font-size="10" fill="#475569">Evolución normalizada: tu cartera · modelo · SPY</text>
      <path d="{path(nc)}" fill="none" stroke="#2563eb" stroke-width="2.2"/>
      <path d="{path(nm)}" fill="none" stroke="#d97706" stroke-width="2.2"/>
      <path d="{path(ns)}" fill="none" stroke="#059669" stroke-width="2.2"/>
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

    body = "<h3 class='h-sec'>Tu resultado vs. referencias de mercado</h3>"
    body += _comparacion_rend_html(cmpd if isinstance(cmpd, dict) else None, diagnostico, modelo_frac)
    body += "<h4 class='h-sub'>Renta fija local</h4>"
    body += _tir_paragraph(tir_cli, top)
    body += "<h4 class='h-sub'>Instrumentos de referencia (ON corporativas)</h4>"
    body += _tabla_top_rf_html(top)
    body += "<h4 class='h-sub'>Vencimientos de tus bonos / ON (ponderado)</h4>"
    body += _ladder_html([(y, w) for y, w in ladder])
    body += "<h4 class='h-sub'>Trayectoria normalizada (tu cartera · modelo · SPY)</h4>"
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
    df_ag: pd.DataFrame | None = None,
    bloque_plan_simulacion: dict[str, Any] | None = None,
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
        accion_html = "<h4>Sugerencias de compra recientes (desde «¿Qué compro ahora?»)</h4><ul>"
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

    pct_rf = float(getattr(diagnostico, "pct_defensivo_actual", 0) or 0) * 100.0
    pct_rv = float(getattr(diagnostico, "pct_rv_actual", 0) or 0) * 100.0
    if pct_rv <= 0 and pct_rf <= 99:
        pct_rv = max(0.0, 100.0 - pct_rf)

    pares: list[tuple[str, float]] = []
    _df = df_ag if df_ag is not None else pd.DataFrame()
    if not _df.empty and "PESO_PCT" in _df.columns:
        for _, r in _df.iterrows():
            tk = str(r.get("TICKER", "") or "").strip().upper()
            if not tk:
                continue
            try:
                w = float(r.get("PESO_PCT", 0) or 0) * 100.0
            except (TypeError, ValueError):
                w = 0.0
            if w > 0.05:
                pares.append((tk, w))
        pares.sort(key=lambda x: -x[1])

    _lead = _esc(
        (diagnostico.resumen_ejecutivo or "").strip() or (diagnostico.titulo_semaforo or "") or "—",
    )
    _titulo_sem = _esc(diagnostico.titulo_semaforo or "—")
    plan_snap_html = _seccion_plan_simulacion_html(bloque_plan_simulacion)

    body = f"""
    <article class="rpt">
      <header class="rpt-hero">
        <div class="hero-top">
          <span class="logo-mark">MQ26</span>
          <span class="hero-badge">Informe personal</span>
        </div>
        <h1>Hola, {_esc(diagnostico.cliente_nombre) or "inversor"}</h1>
        <p class="meta">{_esc(diagnostico.fecha_diagnostico)} · Perfil <strong>{_esc(diagnostico.perfil)}</strong> · Horizonte {_esc(diagnostico.horizonte_label)}</p>
        <p class="intro-p">Este documento tiene <strong>tres partes</strong> para leer con calma: situación actual, qué hace cada activo, y contexto de mercado con una proyección ilustrativa. Lenguaje claro; los números concentran lo técnico.</p>
      </header>

      <section class="sheet sheet-1">
        <p class="sheet-kicker">Parte 1 de 3 · Situación actual</p>
        <h2>Cómo está tu cartera hoy</h2>
        <p class="one-liner"><strong>En breve:</strong> {_titulo_sem}</p>
        <div class="resumen-box"><p>{_lead}</p></div>
        {_seccion_metricas_html(valor_usd, pnl_pct, diagnostico.semaforo)}
        <p class="fine-print">Los importes en USD son referencia (CCL y precios en MQ26). No reemplazan el estado de cuenta del broker.</p>
        <h3>Puntos que conviene tener presentes</h3>
        {obs_html if obs_html.strip() else "<p class='muted'>Sin alertas destacadas en esta corrida del motor.</p>"}
      </section>

      <section class="sheet sheet-2">
        <p class="sheet-kicker">Parte 2 de 3 · Tu cartera en detalle</p>
        <h2>Qué tenés y qué rol cumple cada activo</h2>
        <p>Cada fila muestra el <strong>peso en tu patrimonio</strong> y una explicación sencilla del rol que suele cumplir ese instrumento dentro de un plan diversificado.</p>
        <div class="viz-row">
          <div class="viz-col">{_grafico_rf_rv_dona_html(pct_rf, pct_rv)}</div>
          <div class="viz-col viz-grow">{_grafico_barras_pesos_html(pares)}</div>
        </div>
        {_tabla_posiciones_con_razon(_df, diagnostico)}
      </section>

      <section class="sheet sheet-3">
        <p class="sheet-kicker">Parte 3 de 3 · Contexto y siguiente paso</p>
        <h2>Hacia dónde apunta tu estrategia</h2>
        {ventaja_html}
        <h3 class="h-sec">Ideas concretas desde la app</h3>
        {accion_html}
        {_proyeccion_barras_html(diagnostico.perfil, aporte_mensual_usd, horizon_meses, valor_usd)}
        {plan_snap_html}
      </section>

      <footer class="disc">
        <p><strong>Aviso importante.</strong> Este informe es <strong>meramente informativo</strong> y no constituye asesoramiento financiero personalizado, diagnóstico fiscal ni recomendación de compra o venta de instrumentos.</p>
        <p>Resultados y simulaciones ilustrativos; el pasado y los modelos no garantizan el futuro.</p>
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
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;800&display=swap');
    body{font-family:'Barlow',Segoe UI,sans-serif;margin:0;color:#0f172a;background:linear-gradient(180deg,#e2e8f0 0%,#f8fafc 40%,#eef2ff 100%);min-height:100vh;}
    .rpt{max-width:840px;margin:0 auto;padding:0 16px 56px;}
    .estudio,.sa{max-width:840px;margin:24px auto;background:#fff;padding:24px;border-radius:12px;border:1px solid #e2e8f0;}
    .rpt-hero{background:linear-gradient(125deg,#1e3a8a 0%,#3730a3 45%,#0f766e 100%);color:#f8fafc;padding:32px 28px;border-radius:0 0 22px 22px;box-shadow:0 16px 48px rgba(15,23,42,.2);}
    .hero-top{display:flex;align-items:center;gap:12px;margin-bottom:6px;}
    .logo-mark{font-weight:800;letter-spacing:.08em;font-size:1.15rem;}
    .hero-badge{font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;opacity:.92;border:1px solid rgba(248,250,252,.4);padding:5px 12px;border-radius:999px;}
    .rpt-hero h1{margin:10px 0 6px;font-weight:800;font-size:1.8rem;}
    .rpt-hero .meta{opacity:.93;margin:0;font-size:.92rem;}
    .intro-p{opacity:.95;margin:14px 0 0;line-height:1.6;max-width:42rem;font-size:1rem;}
    header .logo{font-weight:800;color:#1e40af;}
    .sheet{background:#fff;margin:28px 0;padding:26px 24px;border-radius:16px;box-shadow:0 6px 30px rgba(15,23,42,.07);border:1px solid #e2e8f0;page-break-after:always;}
    .sheet-3{page-break-after:auto;}
    .sheet-kicker{font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;color:#64748b;margin:0 0 8px;}
    .sheet>h2:first-of-type{margin-top:0;}
    .sheet h2{margin:0 0 14px;font-size:1.32rem;font-weight:800;color:#0f172a;}
    .sheet h3{margin:22px 0 8px;font-size:1.05rem;font-weight:600;color:#1e293b;}
    .one-liner{margin:0 0 12px;line-height:1.5;}
    .resumen-box{background:linear-gradient(100deg,#eff6ff 0%,#f0fdf4 100%);border-left:4px solid #2563eb;padding:14px 18px;border-radius:0 12px 12px 0;margin:14px 0;}
    .resumen-box p{margin:0;line-height:1.55;}
    .fine-print{font-size:.82rem;color:#64748b;margin:12px 0 0;line-height:1.45;}
    .metrics{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0;}
    .metric{flex:1;min-width:152px;padding:14px 16px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;}
    .metric--pri{background:linear-gradient(160deg,#eff6ff,#ffffff);border-color:#93c5fd;}
    .metric--ok{background:linear-gradient(160deg,#ecfdf5,#ffffff);border-color:#6ee7b7;}
    .metric--warn{background:linear-gradient(160deg,#fffbeb,#ffffff);border-color:#fcd34d;}
    .metric span:first-child{display:block;font-size:.7rem;text-transform:uppercase;letter-spacing:.09em;color:#64748b;margin-bottom:5px;}
    .metric strong{font-size:1.22rem;display:block;font-weight:800;}
    .metric-sub{display:block;font-size:.78rem;color:#64748b;margin-top:7px;line-height:1.4;}
    .sem-verde{color:#059669;}
    .sem-amarillo{color:#d97706;}
    .sem-rojo{color:#dc2626;}
    .viz-row{display:flex;gap:22px;flex-wrap:wrap;margin:20px 0;align-items:flex-start;}
    .viz-col{flex:1;min-width:260px;}
    .viz-grow{flex:1.8;}
    .donut-wrap{display:flex;align-items:center;gap:20px;flex-wrap:wrap;}
    .donut{width:150px;height:150px;border-radius:50%;margin:10px 0;}
    .donut-legend{list-style:none;padding:0;margin:0;font-size:.9rem;}
    .donut-legend li{margin:8px 0;display:flex;align-items:center;gap:10px;}
    .lg{display:inline-block;width:14px;height:14px;border-radius:3px;}
    .lg.rf{background:#2563eb;}
    .lg.rv{background:#059669;}
    .chart-bars{margin:6px 0;}
    .crow{display:flex;align-items:center;gap:12px;margin:7px 0;}
    .ctk{min-width:76px;font-size:.8rem;font-weight:600;color:#334155;}
    .cbar-wrap{flex:1;background:#e2e8f0;height:24px;border-radius:7px;overflow:hidden;}
    .cbar{height:100%;min-width:3px;display:flex;align-items:center;padding:0 9px;box-sizing:border-box;}
    .cval{font-size:.72rem;font-weight:700;color:#fff;text-shadow:0 0 3px rgba(0,0,0,.4);}
    .tbl-pos .razon{font-size:.86rem;line-height:1.45;}
    .tbl-pos .sym{font-family:ui-monospace,Consolas,monospace;font-weight:700;}
    .obs{border-left:4px solid #6366f1;padding:12px 16px;margin:12px 0;background:#f8fafc;border-radius:0 12px 12px 0;}
    .obs-t{font-weight:600;color:#3730a3;}
    .cifra{font-weight:600;color:#0f172a;}
    .h-sec{color:#0f172a;}
    .h-sub{color:#475569;font-size:.92rem;margin-top:1rem;}
    .bars .barrow{margin:8px 0;}
    .bar{background:#2563eb;color:#fff;padding:6px 10px;border-radius:8px;font-size:0.88rem;}
    .tbl{width:100%;border-collapse:collapse;margin:14px 0;font-size:.87rem;}
    .tbl th,.tbl td{border:1px solid #e2e8f0;padding:9px 11px;text-align:left;}
    .tbl th{background:#1e293b;color:#f8fafc;font-weight:600;}
    .tbl .num{text-align:right;font-variant-numeric:tabular-nums;}
    .disc,.muted{font-size:0.86rem;color:#475569;}
    .disc{max-width:840px;margin:28px auto 0;padding:22px 24px;background:#fff;border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 4px 20px rgba(15,23,42,.06);}
    .disc p{margin:0 0 0.7rem 0;line-height:1.5;}
    .disc p:last-child{margin-bottom:0;}
    .foot-brand{font-size:0.88rem;font-weight:700;color:#334155;margin-top:14px;}
    .alert{background:#fff7ed;border:1px solid #fdba74;padding:14px;border-radius:10px;}
    .chart3{max-width:100%;height:auto;margin:14px 0;display:block;}
    @media print{
      body{background:#fff;}
      .sheet{page-break-after:always;box-shadow:none;}
      .sheet-3{page-break-after:auto;}
      .rpt-hero{print-color-adjust:exact;-webkit-print-color-adjust:exact;}
    }
    """
    if compact:
        css += ".rpt-hero h1{font-size:1.55rem;}"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(title)}</title>
    <style>{css}</style></head><body>{body}</body></html>"""
