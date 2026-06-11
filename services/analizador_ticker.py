"""
services/analizador_ticker.py — Analizador Elite por Ticker & Detector de Perlas (MQ26)

Para cada ticker produce:
  • Score MQ26 completo (60/20/20 + moat + volatilidad)
  • Detección de "perlas": activos de calidad con descuento temporal de mercado
  • Red flags: trampas de valor, deterioro fundamental, dilución, riesgo
  • Niveles técnicos: RSI, MACD, Bollinger, soporte/resistencia
  • Veredicto ejecutivo: 💎 Perla / 🥈 Interesante / ⚪ Neutral / ⚠️ Evitar / 🪤 Trampa

Uso standalone:
    result = analizar_ticker("MSFT")
    print(result.gem_rating, result.score_total, result.gem_reasons)

Scanner de universo:
    perlas = buscar_perlas(perfil="Moderado", min_gem_score=60)
"""
from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    SECTORES,
    TICKERS_NO_CEDEAR_BYMA,
    UNIVERSO_MERVAL_SCORING,
)
from core.logging_config import get_logger
from services.scoring_engine import (
    _MOAT_SCORE,
    _SECTOR_CICLO_2026,
    _ticker_yahoo,
    calcular_score_total,
)

_log = get_logger(__name__)


# ─── TIPOS ────────────────────────────────────────────────────────────────────

class GemRating(str, Enum):
    PERLA       = "💎 PERLA"
    INTERESANTE = "🥈 Interesante"
    NEUTRAL     = "⚪ Neutral"
    EVITAR      = "⚠️ Evitar"
    TRAMPA      = "🪤 Trampa de Valor"


@dataclass
class AnalizadorResult:
    """Resultado completo del análisis elite de un ticker."""

    # ── Identificación ────────────────────────────────────────────────────────
    ticker:  str = ""
    tipo:    str = "CEDEAR"
    sector:  str = "Otros"
    nombre:  str = ""

    # ── Precio y rango ────────────────────────────────────────────────────────
    precio_actual:        float = 0.0
    precio_52w_high:      float = 0.0
    precio_52w_low:       float = 0.0
    descuento_vs_max_pct: float = 0.0   # % por debajo del máximo 52w (positivo = descuento)
    market_cap_m:         float = 0.0   # millones USD

    # ── Consenso analistas ────────────────────────────────────────────────────
    precio_target:    float = 0.0
    upside_pct:       float = 0.0
    consensus_rating: str   = ""
    n_analysts:       int   = 0

    # ── Score MQ26 ────────────────────────────────────────────────────────────
    score_total:       float = 0.0
    score_fundamental: float = 0.0
    score_tecnico:     float = 0.0
    score_sector:      float = 0.0
    moat:              int   = 0
    moat_bonus:        float = 0.0
    senal:             str   = ""

    # ── Técnico elite ────────────────────────────────────────────────────────
    rsi:          float = 50.0
    macd:         float = 0.0
    macd_signal:  float = 0.0
    bb_pos:       str   = ""
    hv20:         float = 0.0
    max_dd_1y:    float = 0.0
    pen_vol:      float = 0.0

    # ── Fundamentales clave ───────────────────────────────────────────────────
    revenue_ttm_m:      float = 0.0   # millones USD
    fcf_ttm_m:          float = 0.0   # millones USD
    fcf_yield_pct:      float = 0.0   # %
    roe_pct:            float = 0.0   # %
    pe_ratio:           float = 0.0
    revenue_growth_pct: float = 0.0   # %
    debt_to_equity:     float = 0.0
    cash_m:             float = 0.0   # millones USD

    # ── Ciclo y contexto ─────────────────────────────────────────────────────
    ciclo_sector: str = "neutral"

    # ── Gem detection ─────────────────────────────────────────────────────────
    gem_rating:  GemRating = GemRating.NEUTRAL
    gem_score:   float     = 0.0          # 0-100
    gem_reasons: list      = field(default_factory=list)
    red_flags:   list      = field(default_factory=list)

    # ── Detalles internos ────────────────────────────────────────────────────
    detalle_fundamental: dict = field(default_factory=dict)
    detalle_tecnico:     dict = field(default_factory=dict)
    detalle_sector:      dict = field(default_factory=dict)

    fecha_analisis: str = ""
    fuente: str = "yfinance + MQ26 Elite Engine"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gem_rating"] = self.gem_rating.value
        return d

    def resumen_texto(self) -> str:
        """Resumen ejecutivo en texto plano para CLI/logs."""
        lines = [
            f"{'─'*60}",
            f"  {self.gem_rating.value}  {self.ticker} ({self.tipo}) | {self.sector}",
            f"{'─'*60}",
            f"  Precio: ${self.precio_actual:.2f}  |  52w: ${self.precio_52w_low:.2f} – ${self.precio_52w_high:.2f}",
            f"  Descuento vs máx: {self.descuento_vs_max_pct:.1f}%",
            f"  Target consenso: ${self.precio_target:.2f} ({self.upside_pct:+.1f}%) [{self.consensus_rating}]",
            "",
            f"  Score MQ26:   {self.score_total:.1f}/100  →  {self.senal}",
            f"  Fundamental:  {self.score_fundamental:.1f}  |  Técnico: {self.score_tecnico:.1f}  |  Sector: {self.score_sector:.1f}",
            f"  Moat: {'⬛'*self.moat}{'⬜'*(3-self.moat)} (+{self.moat_bonus:.1f}pts)  |  HV20d: {self.hv20:.1f}%  |  MaxDD: {self.max_dd_1y:.1f}%",
            "",
            f"  RSI: {self.rsi:.1f}  |  MACD: {'▲' if self.macd > self.macd_signal else '▼'}  |  BB: {self.bb_pos}",
            f"  FCF Yield: {self.fcf_yield_pct:.1f}%  |  ROE: {self.roe_pct:.1f}%  |  P/E: {self.pe_ratio:.1f}",
            f"  Revenue growth: {self.revenue_growth_pct:+.1f}%  |  D/E: {self.debt_to_equity:.1f}",
            "",
            f"  Gem Score: {self.gem_score:.0f}/100",
        ]
        if self.gem_reasons:
            lines.append(f"  ✅ {chr(10).join('  ✅ ' + r for r in self.gem_reasons).removeprefix('  ✅ ')}")
        if self.red_flags:
            lines.append(f"  🚩 {chr(10).join('  🚩 ' + f for f in self.red_flags).removeprefix('  🚩 ')}")
        lines.append(f"{'─'*60}")
        return "\n".join(lines)


# ─── ENRIQUECIMIENTO VÍA YFINANCE ────────────────────────────────────────────

def _enriquecer_yfinance(ticker: str, tipo: str) -> dict[str, Any]:
    """
    Obtiene datos adicionales de yfinance.info que el scorer no expone:
      52w high/low, market cap, consensus, nombre, FCF, cash, D/E, etc.
    Nunca lanza excepción — retorna dict con defaults.
    """
    out: dict[str, Any] = {
        "nombre":           "",
        "precio_actual":    0.0,
        "52w_high":         0.0,
        "52w_low":          0.0,
        "market_cap_m":     0.0,
        "consensus_rating": "",
        "precio_target":    0.0,
        "n_analysts":       0,
        "revenue_ttm_m":    0.0,
        "fcf_ttm_m":        0.0,
        "fcf_yield_pct":    0.0,
        "roe_pct":          0.0,
        "pe_ratio":         0.0,
        "revenue_growth_pct": 0.0,
        "debt_to_equity":   0.0,
        "cash_m":           0.0,
    }
    try:
        t_yf = _ticker_yahoo(ticker, tipo)
        info = yf.Ticker(t_yf).info
        if not info:
            return out

        out["nombre"] = str(info.get("longName") or info.get("shortName") or "")
        out["precio_actual"] = float(
            info.get("currentPrice") or info.get("regularMarketPrice") or 0
        )
        out["52w_high"] = float(info.get("fiftyTwoWeekHigh") or 0)
        out["52w_low"]  = float(info.get("fiftyTwoWeekLow") or 0)

        mkt = info.get("marketCap") or 0
        out["market_cap_m"] = round(float(mkt) / 1_000_000, 1)

        # Consenso analistas
        out["consensus_rating"] = str(info.get("recommendationKey") or "")
        out["precio_target"]    = float(info.get("targetMeanPrice") or 0)
        out["n_analysts"]       = int(info.get("numberOfAnalystOpinions") or 0)

        # Fundamentales
        rev = info.get("totalRevenue") or 0
        out["revenue_ttm_m"] = round(float(rev) / 1_000_000, 1)

        fcf = info.get("freeCashflow") or 0
        out["fcf_ttm_m"] = round(float(fcf) / 1_000_000, 1)
        if mkt > 0 and fcf != 0:
            out["fcf_yield_pct"] = round(float(fcf) / float(mkt) * 100, 2)

        out["roe_pct"]            = round((info.get("returnOnEquity") or 0) * 100, 1)
        out["pe_ratio"]           = round(float(info.get("trailingPE") or info.get("forwardPE") or 0), 1)
        out["revenue_growth_pct"] = round((info.get("revenueGrowth") or info.get("earningsGrowth") or 0) * 100, 1)
        out["debt_to_equity"]     = round(float(info.get("debtToEquity") or 0), 1)

        cash = (info.get("totalCash") or 0)
        out["cash_m"] = round(float(cash) / 1_000_000, 1)

    except Exception as exc:
        _log.debug("_enriquecer_yfinance %s: %s", ticker, exc)

    return out


# ─── GEM DETECTION ────────────────────────────────────────────────────────────

_GEM_CRITERIA_MAX = 100.0

def _calcular_gem_score(
    score_mq26:         float,
    precio_actual:      float,
    precio_52w_high:    float,
    fcf_yield_pct:      float,
    moat:               int,
    ciclo_sector:       str,
    upside_pct:         float,
    consensus_rating:   str,
    rsi:                float,
    macd:               float,
    macd_signal:        float,
    revenue_growth_pct: float,
    roe_pct:            float,
    pe_ratio:           float,
    hv20:               float,
    max_dd_1y:          float,
    revenue_ttm_m:      float,
    fcf_ttm_m:          float,
    debt_to_equity:     float,
    market_cap_m:       float,
) -> tuple[float, list[str], list[str]]:
    """
    Calcula Gem Score (0-100) y genera listas de razones positivas y red flags.

    Criterios (total = 100 pts):
      1. Calidad con descuento   20 pts  — score MQ26 alto + precio lejos del máximo
      2. FCF Yield real          20 pts  — generación de caja libre / precio
      3. Moat + Ciclo sectorial  15 pts  — ventaja competitiva + viento de cola sectorial
      4. Potencial analistas     15 pts  — upside vs consenso
      5. Momento técnico         15 pts  — RSI zona compra + MACD bullish
      6. Crecimiento real        15 pts  — revenue / earnings growth sostenido
    """
    reasons:    list[str] = []
    red_flags:  list[str] = []
    gem         = 0.0

    # ── 1. Calidad con descuento (20 pts) ─────────────────────────────────────
    desc = 0.0
    if precio_52w_high > 0 and precio_actual > 0:
        desc = (precio_52w_high - precio_actual) / precio_52w_high * 100

    if score_mq26 >= 68 and desc >= 25:
        gem += 20
        reasons.append(f"Calidad alta (score {score_mq26:.0f}) con {desc:.0f}% de descuento vs máx 52w")
    elif score_mq26 >= 60 and desc >= 15:
        gem += 14
        reasons.append(f"Buen score ({score_mq26:.0f}) con {desc:.0f}% de descuento vs máx 52w")
    elif score_mq26 >= 55 and desc >= 8:
        gem += 8
        reasons.append(f"Score moderado ({score_mq26:.0f}) con {desc:.0f}% de descuento")
    elif score_mq26 >= 70:
        gem += 10
        reasons.append(f"Score MQ26 muy alto: {score_mq26:.0f}/100")
    elif score_mq26 < 35:
        red_flags.append(f"Score MQ26 bajo: {score_mq26:.0f}/100 — calidad cuestionable")

    # ── 2. FCF Yield real (20 pts) ────────────────────────────────────────────
    if fcf_yield_pct >= 7:
        gem += 20
        reasons.append(f"FCF Yield excepcional: {fcf_yield_pct:.1f}% — genera caja real")
    elif fcf_yield_pct >= 4:
        gem += 15
        reasons.append(f"FCF Yield sólido: {fcf_yield_pct:.1f}%")
    elif fcf_yield_pct >= 2:
        gem += 9
        reasons.append(f"FCF Yield positivo: {fcf_yield_pct:.1f}%")
    elif fcf_yield_pct >= 0.5:
        gem += 4
    elif fcf_ttm_m < 0:
        red_flags.append(f"FCF negativo: ${fcf_ttm_m:.0f}M — quema caja")
    else:
        pass  # sin dato — neutro

    # ── 3. Moat + Ciclo sectorial (15 pts) ────────────────────────────────────
    ciclo_bueno = ciclo_sector in ("expansion", "recovery")
    if moat >= 3 and ciclo_bueno:
        gem += 15
        reasons.append(f"Moat muy amplio + sector en {ciclo_sector} — combinación ideal")
    elif moat >= 3:
        gem += 10
        reasons.append("Moat muy amplio (máximo nivel) — ventaja competitiva durable")
    elif moat >= 2 and ciclo_bueno:
        gem += 12
        reasons.append(f"Moat amplio + ciclo {ciclo_sector} — viento de cola")
    elif moat >= 2:
        gem += 8
        reasons.append("Moat amplio — ventaja competitiva sostenible")
    elif moat >= 1 and ciclo_bueno:
        gem += 6
    elif moat == 0 and ciclo_sector == "contraction":
        red_flags.append("Sin moat en sector en contracción — doble vulnerabilidad")

    # ── 4. Potencial según analistas (15 pts) ────────────────────────────────
    rating_buy = consensus_rating.lower() in ("buy", "strong_buy", "outperform")
    if upside_pct >= 30 and rating_buy:
        gem += 15
        reasons.append(f"Analistas: +{upside_pct:.0f}% upside con consenso BUY ({consensus_rating})")
    elif upside_pct >= 20 and rating_buy:
        gem += 11
        reasons.append(f"Upside {upside_pct:.0f}% con consenso BUY")
    elif upside_pct >= 12:
        gem += 7
        reasons.append(f"Upside de analistas: +{upside_pct:.0f}%")
    elif upside_pct <= -10:
        red_flags.append(f"Analistas con precio target inferior al actual ({upside_pct:.0f}%)")
    elif consensus_rating.lower() in ("sell", "underperform"):
        red_flags.append("Consenso analistas SELL/UNDERPERFORM")

    # ── 5. Momento técnico (15 pts) ───────────────────────────────────────────
    rsi_bueno    = 32 <= rsi <= 52
    macd_bullish = macd > macd_signal
    if rsi_bueno and macd_bullish:
        gem += 15
        reasons.append(f"Técnico ideal: RSI {rsi:.0f} (zona compra) + MACD alcista")
    elif rsi_bueno:
        gem += 10
        reasons.append(f"RSI en zona de acumulación ({rsi:.0f})")
    elif rsi < 32:
        gem += 7
        reasons.append(f"RSI oversold ({rsi:.0f}) — posible rebote técnico")
        red_flags.append(f"RSI muy bajo ({rsi:.0f}) — puede seguir cayendo")
    elif macd_bullish and rsi < 62:
        gem += 8
        reasons.append(f"MACD alcista con RSI moderado ({rsi:.0f})")
    elif rsi > 72:
        red_flags.append(f"RSI sobrecomprado ({rsi:.0f}) — riesgo de corrección")

    if hv20 > 55:
        red_flags.append(f"Volatilidad histórica muy alta: {hv20:.0f}% anualizada")
    if max_dd_1y > 50:
        red_flags.append(f"Drawdown máximo 1Y: -{max_dd_1y:.0f}% — alta destrucción de valor")

    # ── 6. Crecimiento real (15 pts) ─────────────────────────────────────────
    rentable = fcf_ttm_m > 0 or roe_pct > 8
    if revenue_growth_pct >= 20 and rentable:
        gem += 15
        reasons.append(f"Crecimiento revenue {revenue_growth_pct:+.0f}% + rentabilidad confirmada")
    elif revenue_growth_pct >= 12:
        gem += 11
        reasons.append(f"Crecimiento sólido: revenue +{revenue_growth_pct:.0f}%")
    elif revenue_growth_pct >= 5:
        gem += 7
    elif revenue_growth_pct < -5:
        red_flags.append(f"Revenue cayendo {revenue_growth_pct:.0f}% — deterioro fundamental")

    if roe_pct >= 20:
        reasons.append(f"ROE excepcional: {roe_pct:.0f}% — alta eficiencia de capital")
    elif roe_pct < 0:
        red_flags.append(f"ROE negativo ({roe_pct:.0f}%) — patrimonio destruyéndose")

    if 0 < pe_ratio <= 12:
        reasons.append(f"P/E muy bajo: {pe_ratio:.1f}x — valoración atractiva")
    elif pe_ratio > 80 and fcf_ttm_m <= 0:
        red_flags.append(f"P/E de {pe_ratio:.0f}x sin FCF positivo — valuación especulativa")

    if debt_to_equity > 250:
        red_flags.append(f"Deuda/Equity muy alto: {debt_to_equity:.0f}% — riesgo solvencia")

    gem = round(min(100.0, max(0.0, gem)), 1)
    return gem, reasons, red_flags


def _determinar_gem_rating(
    gem_score:   float,
    red_flags:   list[str],
    score_mq26:  float,
    fcf_ttm_m:   float,
    debt_to_equity: float,
    hv20:        float,
) -> GemRating:
    """
    Determina el GemRating final combinando gem_score y red_flags críticas.
    Detecta 'Trampa de Valor': score aparentemente bueno pero con deterioro oculto.
    """
    criticos = sum(1 for f in red_flags if any(
        kw in f.lower() for kw in ("fcf negativo", "roe negativo", "revenue cayendo",
                                    "deuda/equity muy alto", "destrucción")
    ))

    # Trampa de valor: score MQ26 > 50 pero fundamentales deteriorados reales
    es_trampa = (score_mq26 >= 50 and criticos >= 2 and fcf_ttm_m < 0 and debt_to_equity > 150)

    if es_trampa:
        return GemRating.TRAMPA

    if gem_score >= 70:
        return GemRating.PERLA
    elif gem_score >= 50:
        return GemRating.INTERESANTE
    elif gem_score >= 32:
        if len(red_flags) >= 3:
            return GemRating.EVITAR
        return GemRating.NEUTRAL
    else:
        return GemRating.EVITAR


# ─── ANALIZADOR PRINCIPAL ────────────────────────────────────────────────────

def analizar_ticker(
    ticker: str,
    tipo:   str  = "CEDEAR",
    ccl:    float = 1429.0,   # CCL referencia 2026-05-27 (implícito precio DNC7O)
) -> AnalizadorResult:
    """
    Análisis elite completo de un ticker.

    Pasos:
      1. calcular_score_total() → score MQ26 + fundamentales + técnicos
      2. _enriquecer_yfinance()  → 52w range, market cap, consensus, etc.
      3. _calcular_gem_score()   → detección de perlas y red flags
      4. _determinar_gem_rating()→ rating final
      5. Construir AnalizadorResult

    Parámetros:
        ticker  — código del activo (ej: "MSFT", "GGAL")
        tipo    — "CEDEAR" | "Acción Local" | "Bono USD" | "ON Corporativa" | "ETF"
        ccl     — tipo de cambio CCL vigente (para conversiones ARS)
    """
    ticker = ticker.upper().strip()
    _log.info("Analizando %s (%s)...", ticker, tipo)

    # ── Paso 1: Score MQ26 completo ───────────────────────────────────────────
    try:
        score_dict = calcular_score_total(ticker, tipo)
    except Exception as exc:
        _log.warning("calcular_score_total %s: %s", ticker, exc)
        score_dict = {
            "Score_Total": 40.0, "Score_Fund": 40.0, "Score_Tec": 40.0, "Score_Sector": 40.0,
            "RSI": 50.0, "Senal": "⚪ MANTENER", "Sector": SECTORES.get(ticker, "Otros"),
            "Moat": 0, "Moat_Bonus": 0.0, "HV20d": 0.0, "MaxDD_1Y": 0.0,
            "Penalizacion_Volatilidad": 0.0,
            "MACD": 0.0, "MACD_Signal": 0.0, "BB_Pos": "",
            "Ciclo_Sector": "neutral",
            "Detalle_Fund": {}, "Detalle_Tec": {}, "Detalle_Sector": {},
        }

    sector       = score_dict.get("Sector", SECTORES.get(ticker, "Otros"))
    ciclo_sector = score_dict.get("Ciclo_Sector", _SECTOR_CICLO_2026.get(sector, "neutral"))

    # ── Paso 2: Enriquecimiento yfinance ──────────────────────────────────────
    extra = _enriquecer_yfinance(ticker, tipo)

    precio_actual   = extra["precio_actual"] or float(score_dict.get("Precio") or 0)
    precio_52w_high = extra["52w_high"]
    precio_52w_low  = extra["52w_low"]
    desc_vs_max     = 0.0
    if precio_52w_high > 0 and precio_actual > 0:
        desc_vs_max = round((precio_52w_high - precio_actual) / precio_52w_high * 100, 1)

    upside = 0.0
    if extra["precio_target"] > 0 and precio_actual > 0:
        upside = round((extra["precio_target"] - precio_actual) / precio_actual * 100, 1)

    # ── Paso 3: Gem Score ─────────────────────────────────────────────────────
    gem_score, gem_reasons, red_flags = _calcular_gem_score(
        score_mq26         = score_dict["Score_Total"],
        precio_actual      = precio_actual,
        precio_52w_high    = precio_52w_high,
        fcf_yield_pct      = extra["fcf_yield_pct"],
        moat               = score_dict.get("Moat", _MOAT_SCORE.get(ticker, 0)),
        ciclo_sector       = ciclo_sector,
        upside_pct         = upside,
        consensus_rating   = extra["consensus_rating"],
        rsi                = float(score_dict.get("RSI") or 50),
        macd               = float(score_dict.get("MACD") or 0),
        macd_signal        = float(score_dict.get("MACD_Signal") or 0),
        revenue_growth_pct = extra["revenue_growth_pct"],
        roe_pct            = extra["roe_pct"],
        pe_ratio           = extra["pe_ratio"],
        hv20               = float(score_dict.get("HV20d") or 0),
        max_dd_1y          = float(score_dict.get("MaxDD_1Y") or 0),
        revenue_ttm_m      = extra["revenue_ttm_m"],
        fcf_ttm_m          = extra["fcf_ttm_m"],
        debt_to_equity     = extra["debt_to_equity"],
        market_cap_m       = extra["market_cap_m"],
    )

    # ── Paso 4: Rating final ──────────────────────────────────────────────────
    gem_rating = _determinar_gem_rating(
        gem_score      = gem_score,
        red_flags      = red_flags,
        score_mq26     = score_dict["Score_Total"],
        fcf_ttm_m      = extra["fcf_ttm_m"],
        debt_to_equity = extra["debt_to_equity"],
        hv20           = float(score_dict.get("HV20d") or 0),
    )

    # ── Paso 5: Construir resultado ───────────────────────────────────────────
    return AnalizadorResult(
        ticker  = ticker,
        tipo    = tipo,
        sector  = sector,
        nombre  = extra["nombre"],

        precio_actual        = round(precio_actual, 2),
        precio_52w_high      = round(precio_52w_high, 2),
        precio_52w_low       = round(precio_52w_low, 2),
        descuento_vs_max_pct = desc_vs_max,
        market_cap_m         = extra["market_cap_m"],

        precio_target    = round(extra["precio_target"], 2),
        upside_pct       = upside,
        consensus_rating = extra["consensus_rating"],
        n_analysts       = extra["n_analysts"],

        score_total       = score_dict["Score_Total"],
        score_fundamental = score_dict["Score_Fund"],
        score_tecnico     = score_dict["Score_Tec"],
        score_sector      = score_dict["Score_Sector"],
        moat              = score_dict.get("Moat", _MOAT_SCORE.get(ticker, 0)),
        moat_bonus        = round(float(score_dict.get("Moat_Bonus") or 0), 2),
        senal             = score_dict.get("Senal", ""),

        rsi         = float(score_dict.get("RSI") or 50),
        macd        = float(score_dict.get("MACD") or 0),
        macd_signal = float(score_dict.get("MACD_Signal") or 0),
        bb_pos      = str(score_dict.get("BB_Pos") or ""),
        hv20        = float(score_dict.get("HV20d") or 0),
        max_dd_1y   = float(score_dict.get("MaxDD_1Y") or 0),
        pen_vol     = float(score_dict.get("Penalizacion_Volatilidad") or 0),

        revenue_ttm_m      = extra["revenue_ttm_m"],
        fcf_ttm_m          = extra["fcf_ttm_m"],
        fcf_yield_pct      = extra["fcf_yield_pct"],
        roe_pct            = extra["roe_pct"],
        pe_ratio           = extra["pe_ratio"],
        revenue_growth_pct = extra["revenue_growth_pct"],
        debt_to_equity     = extra["debt_to_equity"],
        cash_m             = extra["cash_m"],

        ciclo_sector = ciclo_sector,

        gem_rating  = gem_rating,
        gem_score   = gem_score,
        gem_reasons = gem_reasons,
        red_flags   = red_flags,

        detalle_fundamental = score_dict.get("Detalle_Fund", {}),
        detalle_tecnico     = score_dict.get("Detalle_Tec", {}),
        detalle_sector      = score_dict.get("Detalle_Sector", {}),

        fecha_analisis = str(date.today()),
    )


# ─── SCANNER DE UNIVERSO — BUSCAR PERLAS ─────────────────────────────────────

_UNIVERSO_DEFAULT = (
    ["AAPL","MSFT","NVDA","GOOGL","META","AMZN","BRKB","V","MA","JPM",
     "MCD","KO","PG","JNJ","ABBV","CVX","WMT","COST",
     "MELI","NU","AMD","PLTR","TSLA","UBER",
     "GGAL","YPFD","CEPU","PAMP","VIST",
     "SPY","QQQ",
     "BABA","INTC","NKE","PEP","T","VZ","HD","BAC",
    ]
)


def buscar_perlas(
    tickers:        list[str] | None = None,
    tipo_default:   str              = "CEDEAR",
    min_gem_score:  float            = 55.0,
    max_resultados: int              = 20,
    delay_segundos: float            = 1.2,
    callback        = None,
) -> list[AnalizadorResult]:
    """
    Escanea un universo de tickers buscando "perlas" — activos de alta calidad
    con descuento temporal, FCF real, moat y viento de cola sectorial.

    Parámetros:
        tickers        — lista de tickers a evaluar (None = universo default)
        tipo_default   — tipo para tickers no clasificados
        min_gem_score  — umbral mínimo de gem_score para incluir en resultados
        max_resultados — máximo de perlas a retornar (las mejores)
        delay_segundos — pausa entre calls a yfinance para no saturar rate limit
        callback       — fn(i, total, ticker) para progreso (ej: barra Streamlit)

    Retorna lista ordenada por gem_score DESC, filtrada >= min_gem_score.
    """
    if tickers is None:
        tickers = _UNIVERSO_DEFAULT

    # Deduplicar y filtrar bloqueados
    tickers = list(dict.fromkeys(
        t.upper().strip() for t in tickers
        if t.upper().strip() not in TICKERS_NO_CEDEAR_BYMA
    ))

    resultados: list[AnalizadorResult] = []
    total = len(tickers)

    _log.info("buscar_perlas: escaneando %d tickers (min_gem=%.0f)", total, min_gem_score)

    for i, ticker in enumerate(tickers):
        if callback:
            callback(i + 1, total, ticker)

        # Detectar tipo automáticamente
        tipo = tipo_default
        if ticker in UNIVERSO_MERVAL_SCORING:
            tipo = "Acción Local"
        elif ticker in ("GLD", "SPY", "QQQ", "IWM", "EEM"):
            tipo = "ETF"

        try:
            r = analizar_ticker(ticker, tipo)
            if r.gem_score >= min_gem_score:
                resultados.append(r)
                _log.debug("  %s gem=%.0f %s", ticker, r.gem_score, r.gem_rating.value)
        except Exception as exc:
            _log.warning("buscar_perlas skip %s: %s", ticker, exc)

        if i < total - 1:
            time.sleep(delay_segundos)

    # Ordenar por gem_score DESC, luego score_total DESC
    resultados.sort(key=lambda r: (-r.gem_score, -r.score_total))

    return resultados[:max_resultados]


def buscar_perlas_rapido(
    tickers:       list[str],
    tipo_default:  str   = "CEDEAR",
    min_gem_score: float = 50.0,
) -> pd.DataFrame:
    """
    Versión rápida de buscar_perlas sin delay, para uso en tests o análisis offline.
    Retorna un DataFrame con las columnas clave para visualización.
    """
    resultados = buscar_perlas(
        tickers        = tickers,
        tipo_default   = tipo_default,
        min_gem_score  = min_gem_score,
        delay_segundos = 0.3,
    )
    if not resultados:
        return pd.DataFrame()

    rows = []
    for r in resultados:
        rows.append({
            "Ticker":       r.ticker,
            "Rating":       r.gem_rating.value,
            "Gem Score":    r.gem_score,
            "Score MQ26":   r.score_total,
            "Señal":        r.senal,
            "Precio":       r.precio_actual,
            "Descuento %":  r.descuento_vs_max_pct,
            "Upside %":     r.upside_pct,
            "FCF Yield %":  r.fcf_yield_pct,
            "Moat":         r.moat,
            "RSI":          r.rsi,
            "Ciclo":        r.ciclo_sector,
            "Sector":       r.sector,
            "Reasons":      " | ".join(r.gem_reasons[:2]),
        })
    return pd.DataFrame(rows)


# ─── CLI / DEMO ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analizador Elite MQ26")
    parser.add_argument("tickers", nargs="*", default=["MSFT"],
                        help="Tickers a analizar (ej: MSFT AAPL BRKB)")
    parser.add_argument("--scan", action="store_true",
                        help="Escanear universo completo buscando perlas")
    parser.add_argument("--min-gem", type=float, default=55.0,
                        help="Score mínimo para considerar perla (default: 55)")
    args = parser.parse_args()

    if args.scan:
        print(f"\n🔍 Escaneando universo MQ26 (min_gem={args.min_gem:.0f})...\n")
        perlas = buscar_perlas(min_gem_score=args.min_gem, delay_segundos=0.8)
        print(f"Se encontraron {len(perlas)} candidatos:\n")
        for r in perlas:
            print(r.resumen_texto())
    else:
        for tk in args.tickers:
            print(f"\n⚙️  Analizando {tk}...")
            r = analizar_ticker(tk)
            print(r.resumen_texto())
