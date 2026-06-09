"""
services/bdi_generator.py — Capa 3 del motor MQ26.

Toma el output del Scoring Multifactor y genera un JSON BDI estructurado con:
  - Tesis en criollo (en español, fácil de leer)
  - Razones de compra (basadas en las dimensiones que dieron alto)
  - Riesgos asociados (basados en flags rojos detectados)
  - Cálculo automático de tramos escalonados (Target / Stop Loss)
    usando la VOLATILIDAD del activo (HV20d) — no porcentajes fijos

Pipeline:
    Capa 1 (fundamental_cache) → Capa 2 (scoring_multifactor) → Capa 3 (este módulo)

Compatible con `services/bdi_reports.py` — el JSON generado se puede leer con
`obtener_reporte_bdi()` igual que los manuales.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BDI_DIR = Path(__file__).resolve().parent.parent / "data" / "bdi_reports"
_BDI_DIR.mkdir(parents=True, exist_ok=True)


def _comparativa_industria_para_reporte(snap) -> dict[str, Any]:
    """Genera el bloque de comparativa empresa-vs-industria para el JSON del reporte."""
    try:
        from services.industry_benchmarks import comparar_vs_industria
        return comparar_vs_industria(snap, getattr(snap, "industry", None), snap.sector)
    except Exception as e:
        logger.debug("comparativa_industria: error: %s", e)
        return {"fuente": "—", "metricas": {}, "summary": {}}


def _evaluar_calidad_datos(snap) -> dict[str, Any]:
    """Capa de calidad de datos (Nivel A)."""
    try:
        from services.data_quality import evaluar_calidad
        dq = evaluar_calidad(snap)
        return dq.to_dict()
    except Exception as e:
        logger.debug("calidad_datos: error: %s", e)
        return {"confianza_pct": 0, "nivel": "—", "issues_criticos": [str(e)]}


def _calcular_dcf_safe(snap, ticker: str) -> dict[str, Any] | None:
    """Cálculo DCF safe — devuelve dict o None si faltan datos críticos."""
    try:
        from services.dcf_simple import calcular_dcf
        r = calcular_dcf(ticker, snap=snap)
        return r.to_dict() if r is not None else None
    except Exception as e:
        logger.debug("dcf: error: %s", e)
        return None


# ─── Cálculo de niveles por volatilidad (Target / Stop dinámicos) ─────────────

def _calcular_tramos_por_volatilidad(
    precio_actual: float,
    hv20d: float,
    pa_52w_low: float | None = None,
    pa_52w_high: float | None = None,
) -> dict[str, Any]:
    """
    Calcula stop loss, target y 3 tramos escalonados basados en volatilidad.

    Reglas:
      - Stop loss = precio_actual × (1 - factor_riesgo)
      - Target    = precio_actual × (1 + 2 × factor_riesgo)  → R/R 2:1
      - factor_riesgo se adapta a la volatilidad histórica:
          HV < 25%  → factor 0.18
          HV 25-40% → factor 0.22
          HV 40-60% → factor 0.28
          HV > 60%  → factor 0.35

    Tramos escalonados (estilo BDI):
      Tramo 1: 40% a precio actual (±2%)
      Tramo 2: 35% en soporte intermedio (factor_riesgo × 0.5 abajo)
      Tramo 3: 25% en soporte fuerte (factor_riesgo × 1 abajo)
    """
    # Factor de riesgo según volatilidad
    if hv20d <= 0:
        factor = 0.22
    elif hv20d < 0.25:
        factor = 0.18
    elif hv20d < 0.40:
        factor = 0.22
    elif hv20d < 0.60:
        factor = 0.28
    else:
        factor = 0.35

    px = float(precio_actual)
    stop = round(px * (1 - factor), 2)
    target = round(px * (1 + 2 * factor), 2)
    primer_obj = round(px * (1 + 1 * factor), 2)

    # Refinar stop con 52w_low si está más arriba
    if pa_52w_low and pa_52w_low > stop * 0.9:
        # No bajar stop por debajo del 52w_low × 0.95
        stop = max(stop, round(pa_52w_low * 0.95, 2))

    soporte_intermedio = round(px * (1 - factor * 0.5), 2)
    soporte_fuerte = round(px * (1 - factor * 0.85), 2)

    tramos = [
        {
            "tramo": 1, "proporcion": 0.40,
            "precio_min_usd": round(px * 0.98, 2),
            "precio_max_usd": round(px * 1.02, 2),
            "comentario": "A mercado / zona actual",
        },
        {
            "tramo": 2, "proporcion": 0.35,
            "precio_min_usd": round(soporte_intermedio * 0.99, 2),
            "precio_max_usd": round(soporte_intermedio * 1.01, 2),
            "comentario": f"Soporte intermedio (≈-{factor*50:.0f}%)",
        },
        {
            "tramo": 3, "proporcion": 0.25,
            "precio_min_usd": round(soporte_fuerte * 0.98, 2),
            "precio_max_usd": round(soporte_fuerte * 1.02, 2),
            "comentario": f"Soporte fuerte (sobrerreacción, ≈-{factor*85:.0f}%)",
        },
    ]

    return {
        "stop_loss_usd": stop,
        "primer_objetivo_usd": primer_obj,
        "target_usd": target,
        "soporte_intermedio_usd": soporte_intermedio,
        "soporte_fuerte_usd": soporte_fuerte,
        "factor_riesgo_aplicado": factor,
        "hv20d_usado": hv20d,
        "tramos_entrada": tramos,
    }


# ─── Tesis en criollo (español natural, fácil de leer) ────────────────────────

def _construir_tesis_criollo(score, snap) -> str:
    """Genera 2-3 frases en español natural, no técnico."""
    nombre_sec = snap.industry or snap.sector or "su sector"

    if score.score_total >= 75:
        intro = f"💎 {score.ticker} es una oportunidad de alta convicción."
    elif score.score_total >= 60:
        intro = f"📊 {score.ticker} muestra señales sólidas."
    elif score.score_total >= 45:
        intro = f"🤔 {score.ticker} está en zona neutral — hay tanto pros como contras."
    else:
        intro = f"⚠️ {score.ticker} no luce atractivo hoy."

    cuerpo = []
    if score.score_calidad >= 75:
        cuerpo.append("La empresa es de altísima calidad (ROE, márgenes y solvencia top)")
    if score.score_valor >= 70:
        cuerpo.append("cotiza barata respecto a sus ganancias futuras")
    elif score.score_valor <= 30:
        cuerpo.append("está cara según múltiplos de valuación")

    if score.score_momentum >= 70:
        cuerpo.append("el momentum técnico es favorable (señales de compra activas)")
    elif score.score_momentum <= 30:
        cuerpo.append("el técnico todavía no acompaña — esperar mejor punto de entrada")

    if score.score_sectorial >= 70:
        cuerpo.append(f"y supera ampliamente a la mediana de {nombre_sec}")
    elif score.score_sectorial <= 30:
        cuerpo.append(f"y está rezagada vs su sector ({nombre_sec})")

    cuerpo_txt = ", ".join(cuerpo) + "." if cuerpo else ""

    cierre = ""
    if score.recomendacion == "COMPRAR":
        cierre = f"Recomendación: COMPRAR escalonado (40/35/25%) con R/R 2:1."
    elif score.recomendacion == "MANTENER":
        cierre = "Recomendación: MANTENER si ya está en cartera, esperar mejor precio si no."
    else:
        cierre = "Recomendación: NO INICIAR posición ahora — flags de riesgo significativos."

    return f"{intro} {cuerpo_txt} {cierre}".strip()


# ─── Razones de compra (extraídas del score breakdown) ────────────────────────

def _razones_desde_score(score, snap) -> list[str]:
    """Top 7 razones derivadas del breakdown."""
    from services.fundamental_cache import pct_seguro, fraccion_segura

    razones = []

    if score.score_valor >= 70:
        if snap.pe_forward:
            razones.append(f"💰 P/E forward {snap.pe_forward:.1f}x — valuación atractiva")
        if snap.pb_ratio and snap.pb_ratio < 3:
            razones.append(f"📚 P/B {snap.pb_ratio:.2f}x — debajo del promedio")

    if score.score_calidad >= 70:
        roe_frac = fraccion_segura(snap.roe)
        if roe_frac and roe_frac > 0.15:
            razones.append(f"🏆 ROE {pct_seguro(snap.roe):.1f}% — uso muy eficiente del capital")
        mn_frac = fraccion_segura(snap.profit_margin)
        if mn_frac and mn_frac > 0.15:
            razones.append(f"💼 Margen neto {pct_seguro(snap.profit_margin):.1f}% — empresa muy rentable")
        mo_frac = fraccion_segura(snap.operating_margin)
        if mo_frac and mo_frac > 0.20:
            razones.append(f"⚙️ Margen operativo {pct_seguro(snap.operating_margin):.1f}% — operación eficiente")
        if snap.debt_to_equity and snap.debt_to_equity < 50:
            razones.append(f"🛡️ Deuda/Equity {snap.debt_to_equity:.0f}% — balance sólido")

    if score.score_momentum >= 70:
        rsi = score.detalle_momentum.get("rsi")
        if rsi and 30 <= rsi <= 55:
            razones.append(f"📈 RSI {rsi:.0f} — entrada técnica favorable")

    if score.score_sectorial >= 70:
        sec = score.sector or "sector"
        razones.append(f"🌟 Outperformer en {sec} — barato + más rentable que la mediana")

    rg_frac = fraccion_segura(snap.revenue_growth)
    if rg_frac and rg_frac > 0.10:
        razones.append(f"📊 Crecimiento de ingresos +{pct_seguro(snap.revenue_growth):.1f}% i.a.")
    dy_frac = fraccion_segura(snap.dividend_yield)
    if dy_frac and dy_frac > 0.025:
        razones.append(f"💵 Dividendo {pct_seguro(snap.dividend_yield):.2f}% — flujo en USD predecible")

    if not razones:
        razones.append("Sin razones cuantitativas destacadas — score general bajo")

    return razones[:7]


# ─── Riesgos (desde flags rojos/amarillos + flags adicionales) ────────────────

def _riesgos_desde_score(score, snap) -> list[str]:
    """Top 7 riesgos derivados del breakdown y flags."""
    riesgos = []

    # Convertir flags rojos/amarillos a riesgos
    for f in score.flags_alerta:
        if f.startswith("🔴") or f.startswith("🟡"):
            # Limpiar el emoji para el texto del riesgo
            riesgos.append(f.replace("🔴 ", "").replace("🟡 ", ""))

    # Riesgos adicionales por dimensión baja
    if score.score_valor <= 30:
        riesgos.append("Valuación exigente — el mercado ya pricea las buenas noticias")
    if score.score_calidad <= 30:
        riesgos.append("Calidad debajo del promedio — márgenes y ROE inferiores al sector")
    if score.score_momentum <= 30:
        riesgos.append("Técnico débil — no hay señales de momentum favorable")

    if not riesgos:
        riesgos.append("Sin riesgos cuantitativos destacados — revisar contexto cualitativo del sector")

    return riesgos[:7]


# ─── Función principal ────────────────────────────────────────────────────────

def generar_reporte_bdi(
    ticker: str,
    *,
    persist: bool = True,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Pipeline completo: calcula scoring multifactor + genera reporte BDI estructurado.

    Args:
        ticker: símbolo.
        persist: si True, guarda en data/bdi_reports/<TICKER>_<YYYY-MM>_auto.json
        force_refresh: ignora caché de fundamentales.

    Returns:
        dict compatible con services.bdi_reports._construir_reporte
        — se puede leer con obtener_reporte_bdi() después.
    """
    from services.scoring_multifactor import calcular_action_score
    from services.fundamental_cache import obtener_fundamentales, pct_seguro, fraccion_segura

    ticker = ticker.upper().strip()

    # Pipeline: Capa 1 (interno por calcular_action_score) + Capa 2 (score)
    score = calcular_action_score(ticker, force_refresh=force_refresh)
    snap = obtener_fundamentales(ticker)  # ya cacheado

    px = snap.precio_actual_usd or 0
    # Normalizar HV20d que viene del scoring_engine (puede estar en porcentaje 0-100)
    _hv_raw = float(score.detalle_momentum.get("hv20d", 0.30) or 0.30)
    hv = (_hv_raw / 100.0) if _hv_raw > 1.0 else _hv_raw

    # Calcular niveles dinámicos por volatilidad
    niveles = _calcular_tramos_por_volatilidad(
        precio_actual=px,
        hv20d=float(hv),
        pa_52w_low=snap.precio_52w_low,
        pa_52w_high=snap.precio_52w_high,
    )

    # Calificaciones BDI (0-5)
    cal_fund = round((score.score_valor * 0.5 + score.score_calidad * 0.5) / 20, 1)
    cal_tec  = round(score.score_momentum / 20, 1)
    cal_sec  = round(score.score_sectorial / 20, 1)
    cal_total = round(cal_fund * 0.60 + cal_tec * 0.20 + cal_sec * 0.20, 2)

    # Tesis y razones
    tesis_criollo = _construir_tesis_criollo(score, snap)
    razones = _razones_desde_score(score, snap)
    riesgos = _riesgos_desde_score(score, snap)

    # Potencial
    target = niveles["target_usd"]
    potencial = ((target / px) - 1) * 100 if px > 0 else 0

    # Perfil mínimo según volatilidad y score
    if hv < 0.25 and score.score_calidad >= 70:
        perfil_min = "Conservador"
    elif hv < 0.40 and score.score_total >= 60:
        perfil_min = "Moderado"
    elif hv < 0.60:
        perfil_min = "Arriesgado"
    else:
        perfil_min = "Muy arriesgado"

    fecha_hoy = dt.date.today()

    reporte = {
        "ticker":             ticker,
        "exchange":           "AUTO",
        "fecha_publicacion":  fecha_hoy.isoformat(),
        "autor":              "MQ26 Motor Multifactor v2 (Capas 1+2+3)",
        "auto_generated":     True,
        "fuentes":            ["yfinance fundamentales (Capa 1)",
                                "Scoring Multifactor 35/30/20/15 (Capa 2)",
                                "BDI Generator volatilidad-adaptativa (Capa 3)"],

        "recomendacion":           score.recomendacion,
        "precio_actual_usd":       round(px, 2),
        "precio_objetivo_usd":     target,
        "potencial_pct":           round(potencial, 1),
        "horizonte_meses":         12,

        # Calificaciones BDI 0-5
        "calificacion_total":      cal_total,
        "cal_fundamental":         cal_fund,
        "cal_tecnico":             cal_tec,
        "cal_sectorial":           cal_sec,

        # Pesos canónicos multifactor
        "scoring_multifactor": {
            "score_total":     score.score_total,
            "score_valor":     score.score_valor,
            "score_calidad":   score.score_calidad,
            "score_momentum":  score.score_momentum,
            "score_sectorial": score.score_sectorial,
            "pesos":           score.pesos,
        },

        "perfil_minimo":           perfil_min,
        "peso_cartera_pct_min":    0.02,
        "peso_cartera_pct_max":    0.08,
        "tipo_cartera_sugerida":   "Según perfil + constraints del motor de cartera",

        # Tramos calculados dinámicamente por volatilidad
        "tramos_entrada":          niveles["tramos_entrada"],

        "niveles_seguimiento": {
            "stop_loss_usd":          niveles["stop_loss_usd"],
            "stop_tipo":              (
                f"Cierre semanal por debajo de USD {niveles['stop_loss_usd']:.2f} "
                f"(-{niveles['factor_riesgo_aplicado']*100:.0f}% — ajustado a HV {hv*100:.0f}%)"
            ),
            "primer_objetivo_usd":    niveles["primer_objetivo_usd"],
            "primer_objetivo_accion": "Toma de ganancia parcial (50% posición)",
            "objetivo_final_usd":     niveles["target_usd"],
            "factor_riesgo":          niveles["factor_riesgo_aplicado"],
            "hv20d_usado":            niveles["hv20d_usado"],
        },

        "datos_clave": {
            "precio_usd":              snap.precio_actual_usd,
            "rango_52sem_min_usd":     snap.precio_52w_low,
            "rango_52sem_max_usd":     snap.precio_52w_high,
            "market_cap_usd":          snap.market_cap,
            "pe_ttm":                  snap.pe_ttm,
            "pe_forward":              snap.pe_forward,
            "pb_ratio":                snap.pb_ratio,
            "ps_ratio":                snap.ps_ratio,
            "peg_ratio":               snap.peg_ratio,
            # pct_seguro: detecta automáticamente si el valor viene en fracción o porcentaje
            "roe_pct":                 pct_seguro(snap.roe),
            "roa_pct":                 pct_seguro(snap.roa),
            "margen_neto_pct":         pct_seguro(snap.profit_margin),
            "margen_operativo_pct":    pct_seguro(snap.operating_margin),
            "margen_bruto_pct":        pct_seguro(snap.gross_margin),
            "deuda_equity":            snap.debt_to_equity,
            "current_ratio":           snap.current_ratio,
            "crecimiento_ingresos_pct": pct_seguro(snap.revenue_growth),
            "crecimiento_ganancias_pct": pct_seguro(snap.earnings_growth),
            "dividendo_yield_pct":     pct_seguro(snap.dividend_yield),
            "dividendo_anual_usd":     snap.dividend_rate,
            "payout_pct":              pct_seguro(snap.payout_ratio),
            "beta":                    snap.beta,
            "hv20d":                   hv,
            "proximo_earnings":        snap.next_earnings_date,
            "ex_dividend_date":        snap.ex_dividend_date,
        },

        "tesis_resumen":           tesis_criollo,
        "razones_compra":          razones,
        "riesgos":                 riesgos,

        "flags_alerta":            score.flags_alerta,

        "consenso_analistas": [
            {"fuente": "MQ26 Multifactor",
             "recomendacion": score.recomendacion,
             "target_usd":     target,
             "score_total":    score.score_total}
        ],

        "breakdown_dimensiones": {
            "valor":     {"score": score.score_valor,     "peso": "35%", "detalle": score.detalle_valor},
            "calidad":   {"score": score.score_calidad,   "peso": "30%", "detalle": score.detalle_calidad},
            "momentum":  {"score": score.score_momentum,  "peso": "20%", "detalle": score.detalle_momentum},
            "sectorial": {"score": score.score_sectorial, "peso": "15%", "detalle": score.detalle_sectorial},
        },

        "comparativa_industria":   _comparativa_industria_para_reporte(snap),

        # ── Nivel A — Confianza enriquecida ─────────────────────────────────
        "calidad_datos":           _evaluar_calidad_datos(snap),
        "dcf_valuacion":           _calcular_dcf_safe(snap, ticker),

        "sector":                  snap.sector,
        "industry":                snap.industry,
        "country":                 snap.country,
        "currency":                snap.currency,
        "business_summary":        snap.business_summary,

        "pdf_path":                None,
        "calidad_fundamentales":   snap.calidad,
        "errores_fundamentales":   snap.errores,
    }

    # Persistir
    if persist:
        try:
            mes = fecha_hoy.strftime("%Y-%m")
            path = _BDI_DIR / f"{ticker}_{mes}_auto.json"
            path.write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=str),
                            encoding="utf-8")
            logger.info("bdi_generator: %s persistido en %s", ticker, path)
        except Exception as e:
            logger.warning("bdi_generator: no se pudo persistir %s: %s", ticker, e)

    return reporte


def generar_reportes_bulk(tickers: list[str], persist: bool = True) -> dict[str, dict]:
    """Genera reportes para múltiples tickers."""
    out = {}
    for tk in tickers:
        try:
            out[tk.upper()] = generar_reporte_bdi(tk, persist=persist)
        except Exception as e:
            logger.warning("bdi_generator bulk: error con %s: %s", tk, e)
            out[tk.upper()] = {"error": str(e), "ticker": tk.upper()}
    return out
