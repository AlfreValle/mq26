"""
services/bdi_auto_generator.py — Capa 3 del pipeline de análisis.

Genera reportes BDI automáticos combinando:
    Capa 1: fundamentales (fundamentals_cache)
    Capa 2: scoring MOD-23 (scoring_engine)
    Datos derivados: técnico, sectorial, niveles de soporte/resistencia

Output: dict con estructura idéntica a data/bdi_reports/<TICKER>.json
       Persiste con sufijo "_auto" para distinguir de los manuales BDI:
       data/bdi_reports/<TICKER>_<YYYY-MM>_auto.json
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


# ─── Helpers de scoring ───────────────────────────────────────────────────────

def _puntaje_dimension(score: float) -> float:
    """Convierte un score 0-100 a estrellas 0-5."""
    if score >= 85: return 5.0
    if score >= 70: return 4.0
    if score >= 55: return 3.0
    if score >= 40: return 2.0
    if score >= 25: return 1.0
    return 0.5


def _recomendacion_desde_score(score_total: float) -> str:
    if score_total >= 65: return "COMPRAR"
    if score_total >= 50: return "MANTENER"
    return "VENDER"


def _perfil_minimo_segun_riesgo(beta: float | None, vol: float | None, score: float) -> str:
    """Determina el perfil mínimo que puede comprar este ticker."""
    b = beta or 1.0
    v = vol or 0.30
    # Activo defensivo: beta bajo + score alto → apto para Conservador
    if b < 0.7 and v < 0.25 and score >= 70:
        return "Conservador"
    if b < 1.2 and v < 0.40 and score >= 60:
        return "Moderado"
    if b < 1.8 and v < 0.60:
        return "Arriesgado"
    return "Muy arriesgado"


# ─── Niveles técnicos (sin librerías externas) ────────────────────────────────

def _calcular_niveles_tecnicos(
    precio_actual: float,
    precio_52w_low: float | None,
    precio_52w_high: float | None,
    hv20d: float = 0.30,
) -> dict[str, float]:
    """
    Calcula soportes/resistencias y tramos de entrada usando el rango 52sem
    y la volatilidad histórica como proxy de stop/objetivo.
    """
    low = float(precio_52w_low or 0)
    high = float(precio_52w_high or 0)
    px = float(precio_actual or 0)
    factor_vol = max(0.20, min(0.35, hv20d * 0.7))  # 20-35% según volatilidad

    if px <= 0:
        return {}

    # Soportes: el inmediato es el min(precio_actual × 0.95, 52w_low × 1.1)
    if low > 0 and low < px:
        # Soporte fuerte = punto medio entre actual y 52w low
        soporte_fuerte = round(px - (px - low) * 0.6, 2)
        soporte_inmediato = round(px - (px - low) * 0.3, 2)
    else:
        soporte_inmediato = round(px * (1 - factor_vol * 0.5), 2)
        soporte_fuerte = round(px * (1 - factor_vol * 1.2), 2)

    # Stop loss: bajo el soporte fuerte
    stop_loss = round(soporte_fuerte * 0.92, 2)

    # Target: 2x el riesgo (R/R = 2:1)
    riesgo_usd = px - stop_loss
    target = round(px + 2 * riesgo_usd, 2)
    primer_objetivo = round(px + 1 * riesgo_usd, 2)

    # Resistencias
    if high > px:
        resistencia_mayor = high
        resistencia_intermedia = round(px + (high - px) * 0.5, 2)
    else:
        resistencia_mayor = round(px * (1 + factor_vol * 2), 2)
        resistencia_intermedia = round(px * (1 + factor_vol * 1), 2)

    return {
        "precio_actual_usd": px,
        "soporte_inmediato_usd": soporte_inmediato,
        "soporte_fuerte_usd": soporte_fuerte,
        "soporte_largo_plazo_usd": round(soporte_fuerte * 0.85, 2),
        "resistencia_intermedia_usd": resistencia_intermedia,
        "resistencia_mayor_usd": resistencia_mayor,
        "stop_loss_usd": stop_loss,
        "primer_objetivo_usd": primer_objetivo,
        "target_usd": target,
    }


def _tramos_entrada_dinamicos(
    px_actual: float,
    soporte_inmediato: float,
    soporte_fuerte: float,
) -> list[dict[str, Any]]:
    """3 tramos escalonados similar a la estrategia BDI: 40% / 35% / 25%."""
    return [
        {
            "tramo": 1, "proporcion": 0.40,
            "precio_min_usd": round(px_actual * 0.98, 2),
            "precio_max_usd": round(px_actual * 1.02, 2),
            "comentario": "A mercado / zona actual",
        },
        {
            "tramo": 2, "proporcion": 0.35,
            "precio_min_usd": round(soporte_inmediato * 0.99, 2),
            "precio_max_usd": round(soporte_inmediato * 1.01, 2),
            "comentario": "En soporte inmediato",
        },
        {
            "tramo": 3, "proporcion": 0.25,
            "precio_min_usd": round(soporte_fuerte * 0.98, 2),
            "precio_max_usd": round(soporte_fuerte * 1.02, 2),
            "comentario": "En soporte fuerte (sobrerreacción)",
        },
    ]


# ─── Construcción de razones y riesgos ────────────────────────────────────────

def _construir_razones(snap, score_dict: dict | None) -> list[str]:
    """Extrae razones de compra desde los fundamentales y scoring."""
    razones = []
    if score_dict:
        st = float(score_dict.get("Score_Total", 0) or 0)
        if st >= 70:
            razones.append(f"Score MOD-23 alto: {st:.0f}/100 — fundamentales y técnico sólidos")
        elif st >= 60:
            razones.append(f"Score MOD-23 sólido: {st:.0f}/100")

    if snap.roe and snap.roe > 0.15:
        razones.append(f"ROE elevado: {snap.roe*100:.1f}% — uso eficiente del capital de los accionistas")
    if snap.profit_margin and snap.profit_margin > 0.15:
        razones.append(f"Margen neto fuerte: {snap.profit_margin*100:.1f}% — empresa muy rentable")
    if snap.revenue_growth and snap.revenue_growth > 0.10:
        razones.append(f"Crecimiento de ingresos: +{snap.revenue_growth*100:.1f}% i.a.")
    if snap.earnings_growth and snap.earnings_growth > 0.15:
        razones.append(f"Crecimiento de ganancias: +{snap.earnings_growth*100:.1f}% i.a.")
    if snap.pe_forward and 0 < snap.pe_forward < 18:
        razones.append(f"Valuación atractiva: P/E forward {snap.pe_forward:.1f}x (debajo del promedio histórico)")
    if snap.dividend_yield and snap.dividend_yield > 0.025:
        razones.append(f"Dividendo {snap.dividend_yield*100:.2f}% — flujo de caja predecible")
    if snap.beta and snap.beta < 1.0:
        razones.append(f"Beta {snap.beta:.2f} — menos volátil que el mercado (defensivo)")
    if snap.precio_52w_high and snap.precio_actual_usd:
        descuento = (snap.precio_52w_high - snap.precio_actual_usd) / snap.precio_52w_high
        if 0.20 < descuento < 0.50:
            razones.append(f"Cotiza {descuento*100:.0f}% bajo el máximo 52 semanas (oportunidad de reversión)")

    if not razones:
        razones.append("Datos limitados — análisis basado únicamente en señales técnicas")
    return razones[:7]


def _construir_riesgos(snap, score_dict: dict | None) -> list[str]:
    """Extrae los principales riesgos detectables desde los fundamentales."""
    riesgos = []
    if snap.debt_to_equity and snap.debt_to_equity > 150:
        riesgos.append(f"Apalancamiento alto: deuda/patrimonio {snap.debt_to_equity:.0f}% — riesgo financiero")
    if snap.pe_ttm and snap.pe_ttm > 35:
        riesgos.append(f"Valuación exigente: P/E TTM {snap.pe_ttm:.1f}x — poco margen para decepciones")
    if snap.profit_margin is not None and snap.profit_margin < 0.05:
        riesgos.append(f"Margen neto bajo: {snap.profit_margin*100:.1f}% — sensible a costos")
    if snap.beta and snap.beta > 1.5:
        riesgos.append(f"Alta volatilidad: beta {snap.beta:.2f} — drawdowns potencialmente severos")
    if snap.payout_ratio and snap.payout_ratio > 0.80:
        riesgos.append(f"Payout {snap.payout_ratio*100:.0f}% — dividendo poco sostenible si caen ganancias")
    if snap.earnings_growth is not None and snap.earnings_growth < -0.10:
        riesgos.append(f"Caída de ganancias: {snap.earnings_growth*100:.1f}% i.a. — señal de presión")
    if snap.current_ratio and snap.current_ratio < 1.0:
        riesgos.append(f"Liquidez ajustada: current ratio {snap.current_ratio:.2f} — puede tener stress de corto plazo")

    if not riesgos:
        riesgos.append("Sin riesgos cuantitativos relevantes detectados — revisar contexto cualitativo del sector")
    return riesgos[:7]


# ─── Tesis resumen ────────────────────────────────────────────────────────────

def _construir_tesis_resumen(snap, score_dict: dict | None) -> str:
    """Construye 2-3 frases de síntesis ejecutiva."""
    nombre = snap.industry or snap.sector or "el sector"
    partes = []
    if score_dict:
        st = float(score_dict.get("Score_Total", 0) or 0)
        partes.append(f"{snap.ticker} tiene un score MOD-23 de {st:.0f}/100.")
    if snap.roe and snap.profit_margin:
        partes.append(
            f"Opera en {nombre} con ROE {snap.roe*100:.1f}% y margen neto {snap.profit_margin*100:.1f}%."
        )
    if snap.revenue_growth:
        partes.append(f"Crecimiento de ingresos {snap.revenue_growth*100:+.1f}% i.a.")
    if snap.pe_forward:
        partes.append(f"Cotiza a P/E forward de {snap.pe_forward:.1f}x.")
    if snap.precio_actual_usd and snap.precio_52w_high:
        descuento = (snap.precio_52w_high - snap.precio_actual_usd) / snap.precio_52w_high * 100
        if descuento > 5:
            partes.append(f"Está {descuento:.0f}% bajo el máximo de 52 semanas.")
    if not partes:
        partes.append(f"{snap.ticker}: análisis automático generado a partir del scoring MOD-23.")
    return " ".join(partes)


# ─── Generador principal ──────────────────────────────────────────────────────

def generar_reporte_bdi_auto(
    ticker: str,
    *,
    persist: bool = True,
    forzar_refresh_fundamentales: bool = False,
) -> dict[str, Any]:
    """
    Pipeline completo de generación de reporte BDI automático.

    Args:
        ticker: símbolo BYMA (CEDEAR) o NYSE/NASDAQ (subyacente).
        persist: si True, guarda el JSON en data/bdi_reports/.
        forzar_refresh_fundamentales: ignora caché y re-descarga.

    Returns:
        dict con la misma estructura que data/bdi_reports/RTX_2026-06.json
        (compatible con services.bdi_reports._construir_reporte).
    """
    from services.fundamentals_cache import obtener_fundamentales

    ticker = ticker.upper().strip()

    # ── Capa 1: fundamentales ──
    snap = obtener_fundamentales(ticker, force_refresh=forzar_refresh_fundamentales)

    # ── Capa 2: scoring (si está disponible) ──
    score_dict: dict | None = None
    try:
        from services.scoring_engine import calcular_score_total
        score_dict = calcular_score_total(ticker, tipo="CEDEAR")
    except Exception as e:
        logger.debug("bdi_auto: scoring no disponible para %s: %s", ticker, e)

    # Score y calificaciones
    score_total = float(score_dict.get("Score_Total", 0) or 0) if score_dict else 0
    cal_fund = _puntaje_dimension(float(score_dict.get("Score_Fund", score_total) or score_total)) if score_dict else 3.0
    cal_tec  = _puntaje_dimension(float(score_dict.get("Score_Tec", score_total) or score_total)) if score_dict else 3.0
    cal_sec  = _puntaje_dimension(float(score_dict.get("Score_Sector", 50) or 50)) if score_dict else 3.0
    cal_total = round(cal_fund * 0.60 + cal_tec * 0.20 + cal_sec * 0.20, 2)

    # Niveles técnicos
    px_actual = snap.precio_actual_usd or 0
    hv = 0.30  # default si no hay HV20d en scoring
    if score_dict and "Detalle_Tec" in score_dict:
        hv = float(score_dict.get("Detalle_Tec", {}).get("hv20d", 0.30) or 0.30)
    niveles = _calcular_niveles_tecnicos(px_actual, snap.precio_52w_low, snap.precio_52w_high, hv)

    tramos = _tramos_entrada_dinamicos(
        px_actual,
        niveles.get("soporte_inmediato_usd", px_actual * 0.95),
        niveles.get("soporte_fuerte_usd", px_actual * 0.90),
    ) if px_actual > 0 else []

    # Recomendación y potencial
    recomendacion = _recomendacion_desde_score(score_total)
    target = niveles.get("target_usd", px_actual * 1.30)
    potencial_pct = ((target / px_actual) - 1) * 100 if px_actual > 0 else 0

    # Perfil mínimo
    perfil_min = _perfil_minimo_segun_riesgo(snap.beta, hv, score_total)

    # Razones y riesgos
    razones = _construir_razones(snap, score_dict)
    riesgos = _construir_riesgos(snap, score_dict)

    # Tesis
    tesis = _construir_tesis_resumen(snap, score_dict)

    # ── Ensamble final ──
    fecha_hoy = dt.date.today()
    reporte = {
        "ticker":             ticker,
        "exchange":           "AUTO",
        "fecha_publicacion":  fecha_hoy.isoformat(),
        "autor":              "MQ26 Auto-Generator (pipeline 3 capas)",
        "auto_generated":     True,
        "fuentes":            ["yfinance fundamentales", "scoring_engine MOD-23 60/20/20"],

        "recomendacion":           recomendacion,
        "precio_actual_usd":       round(px_actual, 2),
        "precio_objetivo_usd":     round(target, 2),
        "potencial_pct":           round(potencial_pct, 1),
        "horizonte_meses":         12,

        "calificacion_total":      cal_total,
        "cal_fundamental":         cal_fund,
        "cal_tecnico":             cal_tec,
        "cal_sectorial":           cal_sec,
        "pesos_calificacion":      {"fundamental": 0.60, "tecnico": 0.20, "sectorial": 0.20},

        "perfil_minimo":           perfil_min,
        "peso_cartera_pct_min":    0.02,
        "peso_cartera_pct_max":    0.08,
        "tipo_cartera_sugerida":   "Según perfil y constraints del motor de cartera",

        "tramos_entrada":          tramos,

        "niveles_seguimiento": {
            "stop_loss_usd":          niveles.get("stop_loss_usd", 0),
            "stop_tipo":              "Cierre semanal por debajo del soporte fuerte (-25% del precio actual aprox)",
            "primer_objetivo_usd":    niveles.get("primer_objetivo_usd", 0),
            "primer_objetivo_accion": "Toma de ganancia parcial",
            "objetivo_final_usd":     niveles.get("target_usd", 0),
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
            "roe_pct":                 (snap.roe * 100) if snap.roe else None,
            "roa_pct":                 (snap.roa * 100) if snap.roa else None,
            "margen_neto_pct":         (snap.profit_margin * 100) if snap.profit_margin else None,
            "margen_operativo_pct":    (snap.operating_margin * 100) if snap.operating_margin else None,
            "margen_bruto_pct":        (snap.gross_margin * 100) if snap.gross_margin else None,
            "deuda_equity":            snap.debt_to_equity,
            "current_ratio":           snap.current_ratio,
            "crecimiento_ingresos_pct": (snap.revenue_growth * 100) if snap.revenue_growth else None,
            "crecimiento_ganancias_pct": (snap.earnings_growth * 100) if snap.earnings_growth else None,
            "dividendo_yield_pct":     (snap.dividend_yield * 100) if snap.dividend_yield else None,
            "dividendo_anual_usd":     snap.dividend_rate,
            "payout_pct":              (snap.payout_ratio * 100) if snap.payout_ratio else None,
            "beta":                    snap.beta,
            "proximo_earnings":        snap.next_earnings_date,
            "ex_dividend_date":        snap.ex_dividend_date,
        },

        "tesis_resumen":           tesis,
        "razones_compra":          razones,
        "riesgos":                 riesgos,

        "consenso_analistas": [
            {"fuente": "MQ26 Scoring MOD-23",
             "recomendacion": recomendacion,
             "target_usd":     round(target, 2)}
        ],

        "niveles_tecnicos":        niveles,

        "segmentos_negocio":       [],   # No disponible automáticamente
        "split_negocio":           {},

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
            path.write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info("bdi_auto: reporte persistido en %s", path)
        except Exception as e:
            logger.warning("bdi_auto: no se pudo persistir reporte %s: %s", ticker, e)

    return reporte


def generar_reportes_bulk(tickers: list[str], persist: bool = True) -> dict[str, dict]:
    """Genera reportes para múltiples tickers (uno por ticker, secuencial por simplicidad)."""
    out = {}
    for tk in tickers:
        try:
            out[tk.upper()] = generar_reporte_bdi_auto(tk, persist=persist)
        except Exception as e:
            logger.warning("bdi_auto bulk: error con %s: %s", tk, e)
            out[tk.upper()] = {"error": str(e), "ticker": tk.upper()}
    return out
