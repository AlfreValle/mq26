"""
services/perlas_service.py — Detección DINÁMICA de "Perlas del Mercado" (20% táctico)

Una "perla" es un instrumento con buen score fundamental/técnico pero
temporalmente sobrevendido — oportunidad de entrada con R/R favorable.

DETECCIÓN (sin hardcoded):
    1. Score MOD-23 alto (Score_Total ≥ umbral según perfil)
    2. Sobrevendido: RSI ≤ 40  ó  MaxDD_1Y ≥ 25%
    3. Precio actual disponible (cotización válida)

NIVELES DINÁMICOS (calculados por ticker, sin hardcoded):
    Entrada  = precio actual
    Stop     = precio × (1 - factor_riesgo)
    Objetivo = precio × (1 + 2 × factor_riesgo)     ← R/R 2:1 garantizado

    factor_riesgo se adapta a la volatilidad del activo (HV20d):
        - HV < 30 %:  factor = 0.20  (Stop -20%, Target +40%)
        - HV 30-50%:  factor = 0.25  (Stop -25%, Target +50%)
        - HV > 50 %:  factor = 0.30  (Stop -30%, Target +60%)

    Si HV no está disponible, usa 0.25 (conservador medio).

HORIZONTE: ajustado al MaxDD del activo
    - MaxDD < 30%: 6 meses  (recuperación rápida histórica)
    - MaxDD ≥ 30%: 12 meses (drawdowns mayores tardan más en revertirse)
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


# ─── Definición de perla ──────────────────────────────────────────────────────

@dataclass
class Perla:
    """Oportunidad táctica con entrada y salida calculadas dinámicamente."""
    ticker:           str
    tipo:             str
    tesis:            str
    precio_entrada:   float
    precio_objetivo:  float
    stop_loss:        float
    horizonte_meses:  int      = 6
    pct_cartera_max:  float    = 0.08
    fecha_analisis:   str      = ""
    perfil_minimo:    str      = "Moderado"
    activa:           bool     = True
    razon_inactivar:  str      = ""
    # Métricas que dieron origen al pick (trazabilidad)
    score_total:      float    = 0.0
    rsi:              float    = 50.0
    max_dd_1y:        float    = 0.0
    hv20d:            float    = 0.0
    sector:           str      = ""
    # ── Nivel A: enriquecimiento con DCF + calidad ─────────────────
    dcf_valor_intrinseco_usd: float | None = None    # USD por acción (DCF)
    dcf_margen_seguridad_pct: float | None = None    # (intrinseco - precio) / precio × 100
    dcf_recomendacion:        str | None = None      # INFRAVALORADA | FAIR | SOBREVALUADA
    confianza_datos_pct:      float | None = None    # 0-100 score de calidad
    confianza_datos_nivel:    str | None = None      # ALTA | MEDIA | BAJA

    @property
    def riesgo_recompensa(self) -> float:
        ganancia = self.precio_objetivo - self.precio_entrada
        riesgo   = self.precio_entrada - self.stop_loss
        if riesgo <= 0:
            return 0.0
        return round(ganancia / riesgo, 2)

    @property
    def upside_pct(self) -> float:
        if self.precio_entrada <= 0:
            return 0.0
        return round((self.precio_objetivo / self.precio_entrada - 1) * 100, 1)

    @property
    def downside_pct(self) -> float:
        if self.precio_entrada <= 0:
            return 0.0
        return round((1 - self.stop_loss / self.precio_entrada) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker":          self.ticker,
            "tipo":            self.tipo,
            "sector":          self.sector,
            "tesis":           self.tesis,
            "precio_entrada":  self.precio_entrada,
            "precio_objetivo": self.precio_objetivo,
            "stop_loss":       self.stop_loss,
            "upside_pct":      self.upside_pct,
            "downside_pct":    self.downside_pct,
            "riesgo_recompensa": self.riesgo_recompensa,
            "horizonte_meses": self.horizonte_meses,
            "pct_cartera_max": self.pct_cartera_max,
            "perfil_minimo":   self.perfil_minimo,
            "fecha_analisis":  self.fecha_analisis,
            "activa":          self.activa,
            "score_total":     self.score_total,
            "rsi":             self.rsi,
            "max_dd_1y":       self.max_dd_1y,
            "hv20d":           self.hv20d,
            "dcf_valor_intrinseco_usd": self.dcf_valor_intrinseco_usd,
            "dcf_margen_seguridad_pct": self.dcf_margen_seguridad_pct,
            "dcf_recomendacion":        self.dcf_recomendacion,
            "confianza_datos_pct":      self.confianza_datos_pct,
            "confianza_datos_nivel":    self.confianza_datos_nivel,
        }


# ─── Configuración por perfil ─────────────────────────────────────────────────

_PERFIL_ORDEN = {"Conservador": 0, "Moderado": 1, "Arriesgado": 2, "Muy arriesgado": 3}

# Umbral mínimo de Score_Total según perfil para ser candidato a perla.
# Perfiles agresivos toleran tickers de menor score (más upside, más riesgo).
_SCORE_MIN_POR_PERFIL: dict[str, float] = {
    "Conservador":   75.0,
    "Moderado":      65.0,
    "Arriesgado":    55.0,
    "Muy arriesgado": 50.0,
}

# ── Filtros adicionales DIFERENCIADORES por perfil ───────────────────────────
# Volatilidad histórica anualizada (HV20d) — diferencia perfiles defensivos vs growth
_HV_MAX_POR_PERFIL: dict[str, float] = {
    "Conservador":   0.25,    # solo activos de BAJA volatilidad (defensivos)
    "Moderado":      0.40,    # volatilidad media
    "Arriesgado":    0.70,    # tolera alta volatilidad
    "Muy arriesgado": 9.99,   # cualquier volatilidad
}

# Drawdown máximo aceptado por perfil (perfiles conservadores no quieren tickers cayendo 50%+)
_DD_MAX_POR_PERFIL: dict[str, float] = {
    "Conservador":   0.35,    # max 35% caída (caídas mayores → cambio estructural)
    "Moderado":      0.50,
    "Arriesgado":    0.70,
    "Muy arriesgado": 0.99,
}

# Sectores apropiados por perfil — Conservador quiere defensivos, Muy arriesgado growth
_SECTORES_PREFERIDOS: dict[str, set[str]] = {
    "Conservador": {
        # Defensivos clásicos: consumo no cíclico, healthcare, utilities
        "Consumer Defensive", "Healthcare", "Utilities",
        "Consumer Staples", "Pharmaceuticals",
    },
    "Moderado": {
        # Defensivos + quality tech maduro + financiero grande
        "Consumer Defensive", "Healthcare", "Utilities",
        "Technology", "Financial Services", "Communication Services",
        "Industrials",
    },
    "Arriesgado": set(),   # vacío = acepta cualquier sector
    "Muy arriesgado": set(),
}

# RSI máximo para considerar "sobrevendido" (señal de entrada).
_RSI_MAX_SOBREVENDIDO = 45.0

# Drawdown mínimo desde máximo de 1 año para considerar "subvalorado".
_DRAWDOWN_MIN = 0.20   # 20% caída


def _normalizar_drawdown(raw: float | None) -> float:
    """
    Normaliza el valor de MaxDD_1Y a fracción (0.0 a 1.0).

    Algunas fuentes (scoring_engine) ya lo devuelven en porcentaje (ej: 35.0 = 35%),
    otras en fracción (0.35 = 35%). Esta función detecta y devuelve siempre fracción.

    Regla: si el valor absoluto es > 1.0 asumimos porcentaje y dividimos por 100.
    Topamos en 0.99 porque un drawdown ≥ 100% es imposible.
    """
    if raw is None:
        return 0.0
    try:
        v = abs(float(raw))
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:
        v = v / 100.0
    return min(v, 0.99)

# % máximo de cartera por perla individual (riesgo de concentración).
_PCT_CARTERA_MAX_POR_PERLA = 0.08

# Mínimo de 50% del pool a una sola perla (diversificación).
_MAX_PCT_POOL_POR_PERLA = 0.50


# ─── Cálculo de niveles dinámicos ─────────────────────────────────────────────

def _factor_riesgo_por_volatilidad(hv20d: float) -> float:
    """
    Devuelve el factor de stop/target en función de la volatilidad histórica.

    HV20d = desviación estándar anualizada de retornos de 20 días.
    Mantiene R/R 2:1 sin importar la volatilidad.
    """
    if hv20d <= 0:
        return 0.25  # default conservador
    if hv20d < 0.30:
        return 0.20
    if hv20d < 0.50:
        return 0.25
    return 0.30


def _horizonte_por_drawdown(max_dd_1y: float) -> int:
    """
    Drawdowns mayores tardan más en revertirse — extender el horizonte.
    """
    if max_dd_1y >= 0.30:
        return 12
    return 6


def _calcular_niveles(precio: float, hv20d: float, max_dd_1y: float) -> dict[str, float]:
    """
    Calcula entrada / stop / objetivo dinámicos para una perla.

    Returns dict con precio_entrada, stop_loss, precio_objetivo, horizonte_meses.
    """
    factor = _factor_riesgo_por_volatilidad(hv20d)
    return {
        "precio_entrada":  round(precio, 2),
        "stop_loss":       round(precio * (1.0 - factor), 2),
        "precio_objetivo": round(precio * (1.0 + 2.0 * factor), 2),
        "horizonte_meses": _horizonte_por_drawdown(max_dd_1y),
    }


# ─── Construcción de tesis dinámica ───────────────────────────────────────────

def _construir_tesis(row: dict[str, Any]) -> str:
    """
    Genera tesis breve en texto plano (compatible con dataclass).
    Para la versión HTML enriquecida, ver _construir_tesis_html().
    """
    ticker  = row.get("Ticker", "?")
    sector  = row.get("Sector", "—")
    score   = float(row.get("Score_Total", 0) or 0)
    rsi     = float(row.get("RSI", 50) or 50)
    # Normalizar: scoring puede devolver porcentaje (13.8) o fracción (0.138)
    max_dd  = _normalizar_drawdown(row.get("MaxDD_1Y", 0))
    senal   = str(row.get("Senal", "")).strip()

    razones = []
    if score >= 75:
        razones.append(f"score MOD-23 muy alto ({score:.0f}/100)")
    elif score >= 65:
        razones.append(f"score sólido ({score:.0f}/100)")
    else:
        razones.append(f"score aceptable ({score:.0f}/100)")

    if rsi <= 35:
        razones.append(f"RSI {rsi:.0f} (fuertemente sobrevendido)")
    elif rsi <= 45:
        razones.append(f"RSI {rsi:.0f} (sobrevendido)")

    if max_dd >= 0.35:
        razones.append(f"corrección {max_dd*100:.0f}% desde máximo (oportunidad de reversión)")
    elif max_dd >= 0.20:
        razones.append(f"caída {max_dd*100:.0f}% desde máximo")

    razon_txt = " · ".join(razones) if razones else "señales técnicas favorables"

    return (
        f"{ticker} ({sector}): {razon_txt}. "
        f"Señal motor: {senal}. "
        f"Niveles calculados dinámicamente desde volatilidad histórica."
    )


def construir_tesis_html(perla: Perla | dict) -> str:
    """
    Genera tesis ENRIQUECIDA en HTML con todas las razones de selección.
    Incluye: score breakdown, RSI interpretado, drawdown, volatilidad, sector,
    horizonte, riesgo/recompensa, advertencias y plan de acción.

    Usado en `ui/tab_perlas.py` para mostrar análisis detallado.
    """
    p = perla.to_dict() if hasattr(perla, "to_dict") else perla

    ticker  = p.get("ticker", "?")
    sector  = p.get("sector") or p.get("Sector", "—")
    score   = float(p.get("score_total") or p.get("Score_Total", 0) or 0)
    rsi     = float(p.get("rsi") or p.get("RSI", 50) or 50)
    # Normalizar drawdown y volatilidad: pueden venir en porcentaje desde scoring
    _dd_raw = float(p.get("max_dd_1y") or p.get("MaxDD_1Y", 0) or 0)
    max_dd  = _normalizar_drawdown(_dd_raw)
    _hv_raw = float(p.get("hv20d") or p.get("HV20d", 0) or 0)
    hv20d   = (_hv_raw / 100.0) if _hv_raw > 1.0 else _hv_raw
    horiz   = int(p.get("horizonte_meses", 6) or 6)
    rr      = float(p.get("riesgo_recompensa", 0) or 0)
    upside  = float(p.get("upside_pct", 0) or 0)
    downside = float(p.get("downside_pct", 0) or 0)

    # ── Bloque 1: Por qué entró ─────────────────────────────────────────────
    razones_score = []
    if score >= 80:
        razones_score.append(
            f"⭐⭐⭐ <b>Score MOD-23 muy alto: {score:.0f}/100</b> — "
            f"combina fundamentos sólidos (60% del score), señales técnicas "
            f"favorables (20%) y contexto sectorial positivo (20%)."
        )
    elif score >= 70:
        razones_score.append(
            f"⭐⭐ <b>Score MOD-23 sólido: {score:.0f}/100</b> — "
            f"el motor 60/20/20 valida la calidad fundamental + técnica."
        )
    else:
        razones_score.append(
            f"⭐ <b>Score MOD-23 aceptable: {score:.0f}/100</b> — "
            f"justo arriba del umbral para perfiles agresivos. Mayor riesgo."
        )

    # ── Bloque 2: Por qué es oportunidad (entrada) ───────────────────────────
    razones_entrada = []
    if rsi <= 30:
        razones_entrada.append(
            f"📉 <b>RSI {rsi:.0f} — fuertemente sobrevendido</b>. "
            f"Probabilidad estadística alta de rebote técnico en 1-3 meses."
        )
    elif rsi <= 40:
        razones_entrada.append(
            f"📉 <b>RSI {rsi:.0f} — sobrevendido</b>. "
            f"Zona de entrada favorable; el mercado pricea pesimismo."
        )
    elif rsi <= 45:
        razones_entrada.append(
            f"📊 <b>RSI {rsi:.0f} — entrada neutral-favorable</b>. "
            f"Margen de seguridad antes de sobrecompra."
        )

    if max_dd >= 0.40:
        razones_entrada.append(
            f"⚠️ <b>Corrección severa: {max_dd*100:.0f}% desde máximo 52sem</b>. "
            f"Catalizador potente para reversión a la media — pero verificá "
            f"que no haya cambio estructural en el negocio."
        )
    elif max_dd >= 0.25:
        razones_entrada.append(
            f"📉 <b>Caída relevante: {max_dd*100:.0f}% desde máximo 52sem</b>. "
            f"Oportunidad de reversión a la media."
        )
    elif max_dd >= 0.15:
        razones_entrada.append(
            f"📉 <b>Pull-back saludable: {max_dd*100:.0f}% desde máximo</b>. "
            f"Compra de calidad a descuento moderado."
        )

    # ── Bloque 3: Riesgo asociado ────────────────────────────────────────────
    razones_riesgo = []
    if hv20d >= 0.50:
        razones_riesgo.append(
            f"🌊 <b>Alta volatilidad: HV20d = {hv20d*100:.0f}%</b>. "
            f"Stop ampliado a -{downside:.0f}% para tolerar swings normales."
        )
    elif hv20d >= 0.30:
        razones_riesgo.append(
            f"🌊 <b>Volatilidad media: HV20d = {hv20d*100:.0f}%</b>. "
            f"Stop a -{downside:.0f}% — rango típico de la acción."
        )
    else:
        razones_riesgo.append(
            f"🛡️ <b>Baja volatilidad: HV20d = {hv20d*100:.0f}%</b>. "
            f"Activo defensivo — stop ajustado a -{downside:.0f}%."
        )

    # ── Bloque 4: Plan de acción ─────────────────────────────────────────────
    plan = (
        f"<b>🎯 Plan de acción</b>:<br>"
        f"&nbsp;&nbsp;• Entrar en el precio actual o ligeramente abajo (no perseguir si sube +5%)<br>"
        f"&nbsp;&nbsp;• Stop loss disciplinado a -{downside:.0f}% (corte automático si se rompe)<br>"
        f"&nbsp;&nbsp;• Target de salida +{upside:.0f}% en horizonte ~{horiz} meses<br>"
        f"&nbsp;&nbsp;• R/R {rr:.1f}:1 — ganancia esperada es {rr:.1f}× el riesgo asumido"
    )

    # ── Ensamble HTML con paleta WCAG AA ─────────────────────────────────────
    from ui.color_palette import PALETTE

    html = (
        f'<div style="background:{PALETTE.surface_card};border:1px solid {PALETTE.border_default};'
        f'border-left:4px solid {PALETTE.brand};'
        f'padding:14px 18px;border-radius:8px;margin:10px 0;line-height:1.65;'
        f'color:{PALETTE.text_primary};">'

        f'<div style="font-size:1.15em;font-weight:700;color:{PALETTE.text_primary};margin-bottom:8px;">'
        f'💎 {ticker} — Tesis de inversión'
        f'</div>'

        f'<div style="color:{PALETTE.text_secondary};font-style:italic;margin-bottom:12px;'
        f'background:{PALETTE.surface_section};padding:6px 10px;border-radius:4px;'
        f'display:inline-block;">'
        f'Sector: <b style="color:{PALETTE.text_primary};">{sector}</b> · '
        f'Horizonte: <b style="color:{PALETTE.text_primary};">{horiz} meses</b> · '
        f'R/R: <b style="color:{PALETTE.brand};">{rr:.1f}:1</b>'
        f'</div>'

        f'<div style="margin-bottom:12px;background:{PALETTE.success_bg};padding:10px 14px;'
        f'border-radius:6px;color:{PALETTE.success_fg};">'
        f'<b style="color:{PALETTE.success_fg};font-size:1.02em;">✓ Por qué la elegimos</b><br>'
        f'<span style="color:{PALETTE.success_fg};">'
        f'{" ".join(razones_score)} {" ".join(razones_entrada)}</span>'
        f'</div>'

        f'<div style="margin-bottom:12px;background:{PALETTE.warning_bg};padding:10px 14px;'
        f'border-radius:6px;color:{PALETTE.warning_fg};">'
        f'<b style="color:{PALETTE.warning_fg};font-size:1.02em;">⚠️ Consideraciones de riesgo</b><br>'
        f'<span style="color:{PALETTE.warning_fg};">{" ".join(razones_riesgo)}</span>'
        f'</div>'

        f'<div style="background:{PALETTE.info_bg};padding:10px 14px;border-radius:6px;'
        f'border:1px solid {PALETTE.info_accent};color:{PALETTE.info_fg};">'
        f'<span style="color:{PALETTE.info_fg};">{plan}</span>'
        f'</div>'

        f'</div>'
    )
    return html


# ─── API pública ──────────────────────────────────────────────────────────────

def detectar_perlas_desde_scoring(
    df_scores: pd.DataFrame,
    perfil: str = "Moderado",
    n_max: int = 5,
    ccl: float = 1490.0,
) -> list[Perla]:
    """
    Detecta perlas dinámicamente a partir del DataFrame de scoring MOD-23.

    Filtros aplicados:
      1. Score_Total ≥ umbral del perfil
      2. (RSI ≤ 45)  OR  (MaxDD_1Y ≥ 20%)   ← señal de sobrevendido
      3. Precio > 0  ← cotización disponible

    Ordena por upside esperado (mayor score → mayor convicción).

    Parameters:
        df_scores : DataFrame con columnas Ticker, Score_Total, RSI, Precio, MaxDD_1Y, HV20d, Sector
        perfil    : perfil de riesgo del inversor
        n_max     : máximo de perlas a retornar
        ccl       : usado solo para metadata, no afecta selección

    Returns:
        Lista de Perla objects con niveles calculados dinámicamente.
    """
    if df_scores is None or len(df_scores) == 0:
        return []


    score_min = _SCORE_MIN_POR_PERFIL.get(perfil, 65.0)
    fecha_hoy = dt.date.today().isoformat()

    # Filtros vectorizados
    df = df_scores.copy()

    # Normalizar columnas opcionales
    for col, default in [("RSI", 50.0), ("MaxDD_1Y", 0.0), ("HV20d", 0.0),
                          ("Precio", 0.0), ("Score_Total", 0.0), ("Sector", "—")]:
        if col not in df.columns:
            df[col] = default
        else:
            df[col] = df[col].fillna(default if col != "Sector" else "—")

    # Filtro 1: score mínimo según perfil (más estricto en Conservador)
    mask_score = df["Score_Total"].astype(float) >= score_min

    # Filtro 2: sobrevendido (RSI bajo O drawdown alto) — señal de entrada
    # Normalizar MaxDD_1Y vectorialmente — el scoring puede devolver porcentajes
    _dd_norm = df["MaxDD_1Y"].astype(float).abs().apply(
        lambda v: v / 100.0 if v > 1.0 else v
    ).clip(upper=0.99)
    mask_rsi = df["RSI"].astype(float) <= _RSI_MAX_SOBREVENDIDO
    mask_dd_min = _dd_norm >= _DRAWDOWN_MIN
    mask_oportunidad = mask_rsi | mask_dd_min

    # Filtro 3: precio disponible
    mask_precio = df["Precio"].astype(float) > 0

    # Filtro 4: VOLATILIDAD máxima según perfil (diferenciador clave)
    # Normalizar HV20d vectorialmente — puede venir en porcentaje
    _hv_norm = df["HV20d"].astype(float).abs().apply(
        lambda v: v / 100.0 if v > 1.0 else v
    ).clip(upper=2.0)
    hv_max = _HV_MAX_POR_PERFIL.get(perfil, 9.99)
    mask_vol = _hv_norm <= hv_max

    # Filtro 5: DRAWDOWN máximo (Conservador no quiere caídas extremas)
    dd_max = _DD_MAX_POR_PERFIL.get(perfil, 0.99)
    mask_dd_max = _dd_norm <= dd_max

    # Filtro 6: SECTOR apropiado (vacío = todos)
    sectores_pref = _SECTORES_PREFERIDOS.get(perfil, set())
    if sectores_pref:
        mask_sector = df["Sector"].astype(str).isin(sectores_pref)
    else:
        mask_sector = df["Sector"].astype(str).apply(lambda _: True)

    df_perlas = df[
        mask_score & mask_oportunidad & mask_precio
        & mask_vol & mask_dd_max & mask_sector
    ].copy()
    if df_perlas.empty:
        logger.info("perlas: 0 candidatas (perfil=%s, score_min=%.0f)", perfil, score_min)
        return []

    # Ordenar por score descendente (mayor convicción primero)
    df_perlas = df_perlas.sort_values("Score_Total", ascending=False).head(n_max)

    # ── Obtener precios CEDEAR en ARS reales desde el PriceEngine ──────────
    # NO usar el campo "Precio" del scoring: ese viene en USD del subyacente,
    # mientras que en la cartera (y BYMA) el CEDEAR cotiza en ARS por unidad.
    # PriceEngine ya maneja la conversión live × CCL / ratio con fallbacks.
    precios_cedear_ars: dict[str, float] = {}
    try:
        from core.price_engine import PriceEngine
        _pe = PriceEngine()
        tickers_perla = [str(r["Ticker"]).upper() for _, r in df_perlas.iterrows()]
        records = _pe.get_portfolio(tickers_perla, ccl=ccl, precios_live_override={})
        precios_cedear_ars = {t: rec.precio_cedear_ars for t, rec in records.items()}
    except Exception as _e:
        logger.warning("perlas: no se pudo cargar PriceEngine (%s) — usando precio scoring × CCL como fallback", _e)

    perlas: list[Perla] = []
    for _, row in df_perlas.iterrows():
        ticker = str(row["Ticker"]).upper()
        # Precio real CEDEAR ARS desde PriceEngine; fallback: precio_USD × CCL × ratio_implícito
        precio_ars = float(precios_cedear_ars.get(ticker, 0) or 0)
        if precio_ars <= 0:
            # Fallback: convertir precio USD del scoring usando el ratio de config
            precio_usd_sub = float(row.get("Precio", 0) or 0)
            try:
                from core.instrument_master import get_master
                ratio = get_master().ratio(ticker)
                if precio_usd_sub > 0 and ratio > 0 and ccl > 0:
                    precio_ars = round(precio_usd_sub * ccl / ratio, 2)
            except Exception:
                pass
        if precio_ars <= 0:
            logger.info("perlas: %s descartada (sin precio CEDEAR ARS)", ticker)
            continue

        # HV20d también puede venir en porcentaje (ej: 35.0) — normalizar a fracción
        _hv_raw = float(row.get("HV20d", 0) or 0)
        hv = (_hv_raw / 100.0) if _hv_raw > 1.0 else _hv_raw
        # Drawdown: aplicar mismo normalizador
        max_dd = _normalizar_drawdown(row.get("MaxDD_1Y", 0))
        tipo = str(row.get("Tipo", "CEDEAR"))

        # Los niveles se calculan sobre el precio CEDEAR ARS (no sobre USD)
        niveles = _calcular_niveles(precio_ars, hv, max_dd)
        tesis   = _construir_tesis(row.to_dict())

        # ── Nivel A: enriquecer con DCF + confianza de datos ─────────────
        dcf_intrinseco = None
        dcf_margen = None
        dcf_recom = None
        confianza_pct = None
        confianza_nivel = None
        try:
            from services.data_quality import evaluar_calidad
            from services.dcf_simple import calcular_dcf
            from services.fundamental_cache import obtener_fundamentales

            snap = obtener_fundamentales(ticker)
            # DCF (puede fallar para empresas pre-profit)
            dcf = calcular_dcf(ticker, snap=snap)
            if dcf is not None:
                dcf_intrinseco = dcf.valor_intrinseco_usd
                dcf_margen = dcf.margen_seguridad_pct
                dcf_recom = dcf.recomendacion_dcf
            # Confianza de datos
            dq = evaluar_calidad(snap)
            confianza_pct = dq.confianza_pct
            confianza_nivel = dq.nivel
        except Exception as _e_enriq:
            logger.debug("perlas: no se pudo enriquecer %s: %s", ticker, _e_enriq)

        perlas.append(Perla(
            ticker          = str(row["Ticker"]),
            tipo            = tipo,
            tesis           = tesis,
            precio_entrada  = niveles["precio_entrada"],
            precio_objetivo = niveles["precio_objetivo"],
            stop_loss       = niveles["stop_loss"],
            horizonte_meses = niveles["horizonte_meses"],
            pct_cartera_max = _PCT_CARTERA_MAX_POR_PERLA,
            fecha_analisis  = fecha_hoy,
            perfil_minimo   = perfil,
            score_total     = float(row.get("Score_Total", 0) or 0),
            rsi             = float(row.get("RSI", 50) or 50),
            max_dd_1y       = max_dd,
            hv20d           = hv,
            sector          = str(row.get("Sector", "—")),
            dcf_valor_intrinseco_usd = dcf_intrinseco,
            dcf_margen_seguridad_pct = dcf_margen,
            dcf_recomendacion        = dcf_recom,
            confianza_datos_pct      = confianza_pct,
            confianza_datos_nivel    = confianza_nivel,
        ))

    logger.info(
        "perlas: %d candidata(s) detectada(s) dinámicamente (perfil=%s, score_min=%.0f)",
        len(perlas), perfil, score_min,
    )
    return perlas


def seleccionar_perlas(
    capital_ars: float,
    ccl: float,
    perfil: str = "Moderado",
    n_max: int = 3,
    precio_actual: dict[str, float] | None = None,
    df_scores: pd.DataFrame | None = None,
) -> list[Perla]:
    """
    Interfaz compatible con la versión anterior.

    Si `df_scores` se pasa, lo usa directamente.
    Si no, intenta cargar el último DataFrame de scores desde sesión/cache.
    Si no hay scores disponibles, retorna lista vacía (no inventa perlas hardcoded).
    """
    if df_scores is None:
        df_scores = _intentar_cargar_scores_actuales()

    if df_scores is None or len(df_scores) == 0:
        logger.info(
            "perlas: sin DataFrame de scores disponible — esperar próximo escaneo del universo. "
            "Para generar perlas, ejecutar primero escanear_universo_completo() o "
            "abrir el tab de Universo & Señales."
        )
        return []

    return detectar_perlas_desde_scoring(
        df_scores=df_scores,
        perfil=perfil,
        n_max=n_max,
        ccl=ccl,
    )


def _intentar_cargar_scores_actuales() -> pd.DataFrame | None:
    """
    Intenta cargar el último DataFrame de scores desde la BD o sesión Streamlit.
    Retorna None si no hay scores disponibles.
    """
    # 1) Streamlit session_state (cuando la app está corriendo)
    try:
        import streamlit as st
        df = st.session_state.get("df_scores", None)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass

    # 2) Tabla scores_historicos de la BD (último día)
    try:
        from core.db_mercado import obtener_scores_df
        df = obtener_scores_df(dias=2)
        if df is not None and len(df) > 0:
            # Convertir formato de BD a formato esperado por detectar_perlas_desde_scoring
            df_out = df.rename(columns={
                "ticker": "Ticker",
                "score_total": "Score_Total",
                "score_tecnico": "Score_Tec",
                "score_fundamental": "Score_Fund",
            })
            return df_out
    except Exception:
        pass

    return None


def capital_por_perla(
    perla: Perla,
    capital_perlas_ars: float,
    precio_unit_ars: float,
) -> tuple[int, float]:
    """
    Calcula cuántas unidades comprar de una perla.

    Respeta:
      - perla.pct_cartera_max (riesgo individual)
      - _MAX_PCT_POOL_POR_PERLA (diversificación del pool)
      - precio_actual ≤ precio_entrada × 1.05 (entrar cerca del precio analizado)
    """
    if precio_unit_ars <= 0 or precio_unit_ars > perla.precio_entrada * 1.05:
        return 0, 0.0
    monto_max = capital_perlas_ars * perla.pct_cartera_max
    monto_max = min(monto_max, capital_perlas_ars * _MAX_PCT_POOL_POR_PERLA)
    unidades = int(monto_max // precio_unit_ars)
    if unidades < 1:
        return 0, 0.0
    return unidades, round(unidades * precio_unit_ars, 2)


def resumen_perlas_df(perlas: list[Perla]) -> pd.DataFrame:
    """DataFrame con el resumen de perlas para tabla en UI."""
    import pandas as pd
    if not perlas:
        return pd.DataFrame(columns=[
            "Ticker", "Sector", "Score", "RSI", "Tesis",
            "Entrada ARS", "Stop ARS", "Objetivo ARS",
            "Upside %", "Downside %", "R/R", "Horizonte", "Perfil min.",
        ])
    return pd.DataFrame([{
        "Ticker":       p.ticker,
        "Sector":       p.sector,
        "Score":        f"{p.score_total:.0f}",
        "RSI":          f"{p.rsi:.0f}",
        "Tesis":        p.tesis[:120] + "..." if len(p.tesis) > 120 else p.tesis,
        "Entrada ARS":  p.precio_entrada,
        "Stop ARS":     p.stop_loss,
        "Objetivo ARS": p.precio_objetivo,
        "Upside %":     f"+{p.upside_pct:.0f}%",
        "Downside %":   f"-{p.downside_pct:.0f}%",
        "R/R":          f"{p.riesgo_recompensa:.1f}:1",
        "Horizonte":    f"{p.horizonte_meses} meses",
        "Perfil min.":  p.perfil_minimo,
    } for p in perlas])
