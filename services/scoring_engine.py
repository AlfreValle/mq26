"""
services/scoring_engine.py — Motor de Scoring Elite (60/20/20 + modificadores)
Master Quant 26 | DSS Unificado

Arquitectura base:
  60% Fundamental  → P/E, ROE, D/E, Dividendo, EPS Growth, Margen, FCF Yield, ROIC
  20% Técnico      → SMA150(25) + RSI14(20) + Mom(25) + MACD(20) + Bollinger(7) + Volumen(3)
  20% Sector/Ctx   → Ciclo macro EEUU + Contexto Argentina + Ciclo sectorial 2026

Modificadores sobre el score base:
  +0 a +5  Moat (ventaja competitiva durable)
  -0 a -8  Volatilidad (HV20d + MaxDD 1Y)
  -0 a -10 Liquidez (volumen promedio 30d, existente)

Score final: 0-100 → ordena el universo completo para la recomendación semanal.

Universo:
  - CEDEARs BYMA | Acciones Merval | Bonos soberanos ARS/USD | ONs corporativas
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    RATIOS_CEDEAR,
    RSI_COMPRA, RSI_VENTA, RSI_VENTANA,
    SECTORES, SMA_VENTANA,
    TICKERS_NO_CEDEAR_BYMA,
    UNIVERSO_CEDEARS_SCORING,
    UNIVERSO_MERVAL_SCORING,
)
from core.logging_config import get_logger

_log = get_logger(__name__)

# ─── PESOS DEL MODELO ─────────────────────────────────────────────────────────
PESO_FUNDAMENTAL = 0.60
PESO_TECNICO     = 0.20
PESO_SECTOR_CTX  = 0.20

# ─── UNIVERSO COMPLETO INVERSOR ARGENTINO ────────────────────────────────────
# Categorías de activos disponibles en brokers locales

# Listas canónicas importadas desde config.py (fuente única de verdad).
# Para agregar un CEDEAR al scoring: RATIOS_CEDEAR + SECTORES en config.py.
UNIVERSO_CEDEARS: list[str] = UNIVERSO_CEDEARS_SCORING
UNIVERSO_MERVAL:  list[str] = UNIVERSO_MERVAL_SCORING

UNIVERSO_BONOS_USD = [
    "GD30","GD35","GD38","GD41","AL29","AL30","AL35","AE38",
]

UNIVERSO_ONS_LEGACY: list[str] = [
    "YMCXO", "MGCEO", "RUCDO", "YCA6O", "TLC1O", "MRCAO",
]


def universo_ons_tickers() -> list[str]:
    """ON USD BYMA: lista legacy del motor + catálogo activo en renta_fija_ar."""
    try:
        from core.renta_fija_ar import INSTRUMENTOS_RF

        out: set[str] = {str(x).upper().strip() for x in UNIVERSO_ONS_LEGACY}
        for tk, meta in INSTRUMENTOS_RF.items():
            if str(meta.get("tipo", "")).upper() != "ON_USD":
                continue
            if not meta.get("activo", True):
                continue
            out.add(str(tk).upper().strip())
        return sorted(out)
    except Exception:
        return list(UNIVERSO_ONS_LEGACY)


UNIVERSO_ONS: list[str] = universo_ons_tickers()

# Yahoo Finance: soberanos suelen cotizar como *=RX; ON y otros en *.BA
BONOS_SOBERANOS_YAHOO_RX: dict[str, str] = {
    "GD30": "GD30=RX",
    "GD35": "GD35=RX",
    "GD38": "GD38=RX",
    "GD41": "GD41=RX",
    "AL29": "AL29=RX",
    "AL30": "AL30=RX",
    "AL35": "AL35=RX",
    "AE38": "AE38=RX",
}


def _simbolos_yfinance_rf(ticker: str) -> list[str]:
    """Orden de prueba: RX (soberanos) → .BA (BYMA) → ticker plano."""
    t = str(ticker).upper().strip()
    ordered: list[str] = []
    if t in BONOS_SOBERANOS_YAHOO_RX:
        ordered.append(BONOS_SOBERANOS_YAHOO_RX[t])
    ordered.append(f"{t}.BA")
    ordered.append(t)
    seen: set[str] = set()
    out: list[str] = []
    for s in ordered:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _history_close_rf(ticker: str, period: str = "5d") -> pd.Series:
    for sym in _simbolos_yfinance_rf(ticker):
        try:
            h = yf.Ticker(sym).history(period=period)
            if h is None or h.empty or "Close" not in h.columns:
                continue
            s = h["Close"].dropna()
            if len(s) >= 2:
                return s
        except Exception:
            continue
    return pd.Series(dtype=float)


def _base_score_on_catalog(ticker: str) -> float | None:
    """Heurística de base para ON USD desde metadatos (TIR, calificación)."""
    try:
        from core.renta_fija_ar import get_meta

        m = get_meta(ticker)
        if not m or str(m.get("tipo", "")).upper() != "ON_USD":
            return None
        tir = float(m.get("tir_ref") or 0.0)
        base = 48.0 + min(22.0, max(0.0, (tir - 4.5) * 2.2))
        cal = str(m.get("calificacion") or "").strip().upper()
        if cal.startswith("AA"):
            base += 5.0
        elif "BBB" in cal:
            base += 1.0
        elif cal and cal not in ("—", "-", "N/A", ""):
            base -= 4.0
        return max(38.0, min(82.0, base))
    except Exception:
        return None


UNIVERSO_FCI_LISTA = [
    "MAF AHORRO ARS", "MEGAINVER RENTA FIJA", "PIONEER PESOS", "BALANZ AHORRO",
    "FONDOS FIMA USD", "BALANZ CAPITAL USD", "MEGAINVER DOLAR",
    "BALANZ ACCIONES", "FIMA ACCIONES", "COMPASS GROWTH",
    "PIONEER MIXTO", "MAF MIXTO",
]

UNIVERSO_INTERNACIONAL = [
    # Para quien opera afuera (Interactive Brokers, etc.)
    "VTI","VOO","ARKK","IWM","HYG","TLT","GDX","BITO",
]

# ─── CONTEXTO MACRO (actualizar semanalmente) ─────────────────────────────────
# Fuente: Fred, Bloomberg, BCRA — Actualizado Mayo 2026
CONTEXTO_MACRO = {
    # EEUU — Fed en pausa con incertidumbre arancelaria Trump; S&P sobre SMA200
    "sp500_tendencia":    "ALCISTA",   # Sobre SMA200 (recuperación desde corrección Q1-26)
    "fed_ciclo":          "PAUSA",     # Fed funds 4.25-4.50%; sin recortes confirmados
    "recesion_riesgo":    "MEDIO",     # Riesgo recesión elevado por aranceles; GDP Q1 negativo
    "dxy_tendencia":      "BAJISTA",   # Dólar debilitado por déficit y guerra comercial
    "inflacion_eeuu":     "MEDIA",     # PCE ~2.5%; aranceles generan presión al alza
    "aranceles_trump":    "ALTO",      # Aranceles 10-145%; incertidumbre geopolítica alta
    # Argentina — Post-levantamiento cepo; riesgo país bajando
    "riesgo_pais":        "MEDIO",     # EMBI ~700-900; normalización gradual
    "ccl_tendencia":      "ESTABLE",   # CCL ~$1.429; banda de flotación post-cepo activa
    "cepo_status":        "PARCIAL",   # Cepo levantado parcialmente (personas físicas)
    "bcra_reservas":      "RECUPERANDO",  # Reservas netas aún negativas pero mejorando
    "inflacion_ar":       "BAJANDO",   # Mensual ~3%; tendencia desinflacionaria
    # Commodities
    "petroleo":           "LATERAL",   # WTI ~$65-75; presión OPEC+ y demanda China
    "oro":                "ALCISTA",   # ATH superados; refugio ante incertidumbre USD
    "soja":               "LATERAL",   # $350-380/ton; clima neutro
}

# Puntaje por sector según contexto macro actual (0-10)
# Actualizado Mayo 2026: aranceles pesan sobre industria/materiales; oro/defensa/tech beneficiados
SCORE_SECTORIAL_BASE = {
    "Tecnología":      7.5,   # AI/cloud impulso; aranceles chips moderan
    "Salud":           8.0,   # Defensivo + demografía; M&A activo
    "Consumo Def.":    7.2,   # Resistente a recesión; marcas globales fuertes
    "Consumo Ciclico": 6.5,   # MCD/SBUX/COST: calidad + pricing power
    "Comunicaciones":  7.4,   # META/GOOGL/MELI: plataformas digitales, publicidad resiliente
    "Defensa":         8.5,   # Gasto OTAN en alza; demanda geopolítica alta
    "Energía":         6.3,   # Petróleo lateral; transición energética
    "Energía Local":   6.5,   # VIST/PAMP: Vaca Muerta + normalización AR
    "Financiero":      7.0,   # Tasas altas benefician; riesgo crédito latente
    "Materiales":      5.8,   # Aranceles pesados en acero/aluminio
    "Industria":       6.2,   # Reshoring EEUU positivo; aranceles negativos
    "Real Estate":     5.5,   # Tasas altas limitan; REITs presionados
    "E-Commerce":      7.2,   # MELI dominante AR/LAT; Amazon resiliente
    "ETF":             7.5,   # SPY/QQQ/GLD: diversificación
    "Cobertura":       7.5,   # GLD en ATH; cobertura inflación/incertidumbre
    "Bono USD":        6.5,
    "ON Corporativa":  6.0,
    "Acción Local":    6.0,   # Acciones AR beneficiadas por normalización
    "Internacional":   7.0,
    "Otros":           5.0,
}

# ─── MOAT (VENTAJA COMPETITIVA DURABLE) ──────────────────────────────────────
# 0=Sin moat | 1=Estrecho | 2=Amplio | 3=Muy amplio
# Bonus en score_total: moat × 1.67 pts (0 a +5 pts)
_MOAT_SCORE: dict[str, int] = {
    # Muy amplio (3): network effects + switching costs + pricing power + escala
    "MSFT": 3, "AAPL": 3, "GOOGL": 3, "META": 3, "AMZN": 3,
    "V": 3, "MA": 3, "BRKB": 3, "WMT": 3, "COST": 3,
    # Amplio (2): marca fuerte + eficiencia + ecosistema
    "NVDA": 2, "JPM": 2, "MCD": 2, "KO": 2, "PG": 2, "JNJ": 2,
    "ABBV": 2, "CVX": 2, "LMT": 2, "MELI": 2, "SPY": 2, "GLD": 2,
    "UNH": 2, "HD": 2, "BAC": 2, "T": 2, "VZ": 2,
    # Estrecho (1): ventaja competitiva limitada o en desarrollo
    "AMD": 1, "TSLA": 1, "PLTR": 1, "NU": 1, "VIST": 1,
    "GGAL": 1, "UBER": 1, "BABA": 1, "CEPU": 1, "PAMP": 1,
    "YPFD": 1, "NKE": 1, "SBUX": 1, "PEP": 1, "MO": 1,
}

# ─── CICLO SECTORIAL 2026 ─────────────────────────────────────────────────────
# Fase: expansion / peak / contraction / recovery / neutral
# Ajuste en score_sector_contexto: expansion+3, recovery+2, neutral 0, peak-1, contraction-3
_SECTOR_CICLO_2026: dict[str, str] = {
    "Tecnología":      "expansion",    # AI/cloud en pleno ciclo expansivo
    "Defensa":         "expansion",    # Geopolítica impulsa gasto global
    "Cobertura":       "expansion",    # Oro en ATH; refugio activo
    "Comunicaciones":  "expansion",    # Publicidad digital + AI integrations
    "Salud":           "recovery",     # Post-corrección; biotech rebote
    "Energía Local":   "recovery",     # Vaca Muerta + cepo parcial levantado
    "Acción Local":    "recovery",     # Normalización Argentina en curso
    "E-Commerce":      "recovery",     # MELI y LAT rebotando desde mínimos
    "Consumo Def.":    "neutral",      # Estable; sin catalizador claro
    "Financiero":      "neutral",      # Tasas altas = doble filo
    "ETF":             "neutral",      # Diversificado; sigue el índice
    "Consumo Ciclico": "neutral",      # Resistente pero sensible a recesión
    "Industria":       "contraction",  # Aranceles y débil PMI manufacturero
    "Materiales":      "contraction",  # Aranceles Trump + China débil
    "Real Estate":     "contraction",  # Tasas altas prolongadas
    "Energía":         "contraction",  # WTI bajo presión; OPEC+ inestable
    "Bono USD":        "neutral",
    "ON Corporativa":  "neutral",
    "Internacional":   "neutral",
    "Otros":           "neutral",
}

_CICLO_AJUSTE: dict[str, float] = {
    "expansion":  3.0,
    "recovery":   2.0,
    "neutral":    0.0,
    "peak":      -1.0,
    "contraction":-3.0,
}

# ─── CACHE DE SCORE TÉCNICO (TTL 1h, módulo-level) ────────────────────────────
_SCORE_TEC_CACHE: dict[str, tuple[tuple, float]] = {}
_SCORE_TEC_TTL = 3_600  # 1 hora


def _get_score_tecnico_cached(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Score técnico con cache de 1h por clave ticker:tipo.
    Nunca lanza excepción — retorna (40.0, {detalle_vacio}) si falla.
    Invariante: llamadas sucesivas dentro del TTL NO llaman a yfinance.
    """
    now = time.time()
    key = f"{ticker.upper()}:{tipo.upper()}"
    if key in _SCORE_TEC_CACHE:
        val, ts = _SCORE_TEC_CACHE[key]
        if now - ts < _SCORE_TEC_TTL:
            return val
    try:
        val = score_tecnico(ticker, tipo)
    except Exception:
        val = (40.0, {"sma_score": 0, "rsi": 50, "rsi_score": 0, "mom_score": 0, "precio": 0})
    _SCORE_TEC_CACHE[key] = (val, now)
    return val


# ─── 1. SCORE FUNDAMENTAL (0-100) ────────────────────────────────────────────

def score_fundamental(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Score fundamental 0-100 — arquitectura elite 8 métricas.

    Distribución de puntos (total = 100):
      P/E Trailing   18  — valoración relativa
      ROE            15  — rentabilidad sobre equity
      Deuda/Capital  12  — solvencia
      Dividendo       8  — flujo recurrente
      Crecimiento EPS13  — momentum de ganancias
      Margen Neto    10  — eficiencia operativa
      FCF Yield      14  — generación real de caja / precio
      ROIC proxy     10  — retorno sobre capital invertido

    Para bonos y acciones locales usa heurísticas simplificadas.
    """
    detalle: dict = {
        "pe_score": 0, "roe_score": 0, "deuda_score": 0,
        "dividendo_score": 0, "crecimiento_score": 0, "margen_score": 0,
        "fcf_yield_score": 0, "roic_score": 0,
    }

    if tipo in ("Bono USD", "ON Corporativa"):
        return _score_bono(ticker)

    if tipo in ("Acción Local", "Merval"):
        return _score_accion_local(ticker)

    try:
        t_yf = _ticker_yahoo(ticker)
        info = yf.Ticker(t_yf).info
        if not info or info.get("regularMarketPrice") is None:
            return 40.0, detalle

        # ── P/E Trailing (18 pts) ─────────────────────────────────────────────
        # Forward P/E como fallback; penalizar ausencia de ganancias
        pe = info.get("trailingPE") or info.get("forwardPE") or 0
        if 0 < pe <= 12:    detalle["pe_score"] = 18
        elif 12 < pe <= 20: detalle["pe_score"] = 14
        elif 20 < pe <= 30: detalle["pe_score"] = 9
        elif 30 < pe <= 50: detalle["pe_score"] = 4
        elif pe > 50:       detalle["pe_score"] = 1
        else:               detalle["pe_score"] = 5  # Sin P/E pero puede tener growth

        # ── ROE (15 pts) ──────────────────────────────────────────────────────
        roe = (info.get("returnOnEquity") or 0) * 100
        if roe >= 30:        detalle["roe_score"] = 15
        elif roe >= 20:      detalle["roe_score"] = 12
        elif roe >= 12:      detalle["roe_score"] = 8
        elif roe >= 5:       detalle["roe_score"] = 4
        elif roe >= 0:       detalle["roe_score"] = 2
        else:                detalle["roe_score"] = 0

        # ── Deuda/Capital (12 pts) ────────────────────────────────────────────
        de = info.get("debtToEquity") or 0
        if de == 0:           detalle["deuda_score"] = 12
        elif de <= 25:        detalle["deuda_score"] = 10
        elif de <= 60:        detalle["deuda_score"] = 7
        elif de <= 120:       detalle["deuda_score"] = 4
        elif de <= 200:       detalle["deuda_score"] = 1
        else:                 detalle["deuda_score"] = 0

        # ── Dividend Yield (8 pts) ────────────────────────────────────────────
        dy = (info.get("dividendYield") or 0) * 100
        if dy >= 5:           detalle["dividendo_score"] = 8
        elif dy >= 3:         detalle["dividendo_score"] = 7
        elif dy >= 1.5:       detalle["dividendo_score"] = 5
        elif dy >= 0.5:       detalle["dividendo_score"] = 3
        else:                 detalle["dividendo_score"] = 1   # growth sin dividendo = mínimo

        # ── Crecimiento EPS / Revenue (13 pts) ───────────────────────────────
        eg = (info.get("earningsGrowth") or info.get("revenueGrowth") or 0) * 100
        if eg >= 25:          detalle["crecimiento_score"] = 13
        elif eg >= 15:        detalle["crecimiento_score"] = 11
        elif eg >= 8:         detalle["crecimiento_score"] = 8
        elif eg >= 0:         detalle["crecimiento_score"] = 4
        else:                 detalle["crecimiento_score"] = 0

        # ── Margen Neto (10 pts) ──────────────────────────────────────────────
        pm = (info.get("profitMargins") or 0) * 100
        if pm >= 30:          detalle["margen_score"] = 10
        elif pm >= 20:        detalle["margen_score"] = 8
        elif pm >= 10:        detalle["margen_score"] = 6
        elif pm >= 3:         detalle["margen_score"] = 3
        elif pm >= 0:         detalle["margen_score"] = 1
        else:                 detalle["margen_score"] = 0

        # ── FCF Yield (14 pts) — free cash flow / market cap ─────────────────
        # FCF real = freeCashflow; mkt cap = marketCap
        fcf = info.get("freeCashflow") or 0
        mkt = info.get("marketCap") or 0
        if fcf > 0 and mkt > 0:
            fcf_y = (fcf / mkt) * 100   # porcentaje
            if fcf_y >= 8:          detalle["fcf_yield_score"] = 14
            elif fcf_y >= 5:        detalle["fcf_yield_score"] = 11
            elif fcf_y >= 3:        detalle["fcf_yield_score"] = 8
            elif fcf_y >= 1.5:      detalle["fcf_yield_score"] = 5
            elif fcf_y >= 0:        detalle["fcf_yield_score"] = 3
        elif fcf < 0:               detalle["fcf_yield_score"] = 0   # FCF negativo
        else:                       detalle["fcf_yield_score"] = 4   # Sin dato = neutro

        # ── ROIC proxy (10 pts) — return on assets ajustado por apalancamiento ─
        # Proxy: ROA * (1 + D/E / 100) aproxima ROIC cuando D/E disponible
        roa = (info.get("returnOnAssets") or 0) * 100
        de_ratio = info.get("debtToEquity") or 0
        roic_proxy = roa * (1 + min(de_ratio, 300) / 100) if roa > 0 else roa
        if roic_proxy >= 20:        detalle["roic_score"] = 10
        elif roic_proxy >= 14:      detalle["roic_score"] = 8
        elif roic_proxy >= 9:       detalle["roic_score"] = 6
        elif roic_proxy >= 5:       detalle["roic_score"] = 4
        elif roic_proxy >= 0:       detalle["roic_score"] = 2
        else:                       detalle["roic_score"] = 0

        total = sum(detalle.values())
        return round(min(100.0, float(total)), 1), detalle

    except Exception as e:
        _log.debug("score_fundamental %s: %s", ticker, e)
        return 40.0, detalle


def _score_bono(ticker: str) -> tuple[float, dict]:
    """
    MQ2-D7: Score dinámico para bonos — usa yfinance para obtener precio actual
    y calcula score relativo al par USD. Fallback a scores estáticos si yfinance falla.
    """
    bonos_soberanos_base = {"GD30":60,"GD35":62,"GD38":63,"GD41":64,
                            "AL29":58,"AL30":60,"AL35":61,"AE38":63}
    bonos_ons_base       = {"YMCXO":68,"MGCEO":65,"RUCDO":67,"MRCAO":64}
    _cat = _base_score_on_catalog(ticker)
    base_score = float(
        _cat
        if _cat is not None
        else bonos_soberanos_base.get(ticker, bonos_ons_base.get(ticker, 55.0))
    )
    try:
        _hist = _history_close_rf(ticker, "5d")
        if len(_hist) >= 2:
            retorno_5d = (float(_hist.iloc[-1]) / float(_hist.iloc[0]) - 1) * 100
            score = max(20.0, min(95.0, base_score + retorno_5d * 2))
            return score, {
                "rendimiento_estimado": base_score,
                "retorno_5d": round(retorno_5d, 2),
                "dinamico": True,
            }
    except Exception:
        pass
    return base_score, {"rendimiento_estimado": base_score, "dinamico": False}


def _score_accion_local(ticker: str) -> tuple[float, dict]:
    """
    MQ2-D7: Score dinámico para acciones del Merval — calcula momentum 20d via yfinance.
    Fallback a scores estáticos si yfinance no responde.
    """
    scores_merval_base = {
        "YPFD":58, "CEPU":62, "TGNO4":60, "TGSU2":60, "PAMP":65,
        "GGAL":63, "BMA":61, "ALUA":58, "LOMA":56, "MOLI":57,
        "CRES":55, "IRSA":60, "TXAR":54, "AGRO":57, "BYMA":52,
    }
    base = float(scores_merval_base.get(ticker, 50.0))
    try:
        import yfinance as yf
        _sym_ba = f"{ticker}.BA"
        _hist = yf.Ticker(_sym_ba).history(period="25d")["Close"].dropna()
        if len(_hist) >= 5:
            retorno_20d = (_hist.iloc[-1] / _hist.iloc[0] - 1) * 100
            score = max(20.0, min(95.0, base + retorno_20d * 1.5))
            return score, {"score_merval": base, "retorno_20d": round(retorno_20d, 2), "dinamico": True}
    except Exception:
        pass
    return base, {"score_merval": base, "dinamico": False}


# ─── HELPERS TÉCNICOS ELITE ───────────────────────────────────────────────────

def _calcular_tecnico_elite(cierre: "pd.Series") -> tuple[float, dict]:
    """
    Calcula score técnico 0-100 sobre una Serie de precios de cierre.
    Distribución de puntos:
      SMA150    25 pts  — tendencia de largo plazo
      RSI14     20 pts  — momento / zona de compra
      Mom 3M+1M 25 pts  — impulso reciente (15+10)
      MACD      20 pts  — señal de cruce + posición relativa a cero
      Bollinger  7 pts  — posición del precio dentro de las bandas
      Volumen    3 pts  — confirmación de tendencia con volumen
    Total:      100 pts

    Retorna (score, detalle_dict). Nunca lanza excepción.
    """
    det: dict = {
        "sma_score": 0, "rsi": 50.0, "rsi_score": 0, "mom_score": 0,
        "macd_score": 0, "bb_score": 0, "vol_score": 0, "precio": 0.0,
        "macd": 0.0, "macd_signal": 0.0, "bb_pos": "",
        "hv20": 0.0,
    }
    try:
        cierre = cierre.dropna()
        if len(cierre) < 30:
            return 40.0, det

        precio = float(cierre.iloc[-1])
        det["precio"] = round(precio, 2)

        # ── SMA 150 (25 pts) ─────────────────────────────────────────────────
        if len(cierre) >= SMA_VENTANA:
            sma150 = float(cierre.rolling(SMA_VENTANA).mean().dropna().iloc[-1])
            dist = (precio - sma150) / sma150 * 100
            if dist > 8:    det["sma_score"] = 25
            elif dist > 3:  det["sma_score"] = 20
            elif dist > 0:  det["sma_score"] = 14
            elif dist > -5: det["sma_score"] = 6
            else:           det["sma_score"] = 0

        # ── RSI 14 EMA-Wilder (20 pts) ───────────────────────────────────────
        delta = cierre.diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        rsi_s = 100 - (100 / (1 + rs))
        rsi   = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0
        det["rsi"] = round(rsi, 1)
        if RSI_COMPRA <= rsi <= 55:    det["rsi_score"] = 20
        elif 30 <= rsi < RSI_COMPRA:   det["rsi_score"] = 17   # sobrevendido → rebote
        elif 55 < rsi <= RSI_VENTA:    det["rsi_score"] = 10
        elif rsi > RSI_VENTA:          det["rsi_score"] = 3    # sobrecomprado
        else:                          det["rsi_score"] = 7    # < 30 deep oversold

        # ── Momentum 3M (15 pts) + 1M (10 pts) = 25 pts ─────────────────────
        if len(cierre) >= 63:
            mom3m = float((precio / float(cierre.iloc[-63])) - 1) * 100
            if mom3m > 20:    det["mom_score"] += 15
            elif mom3m > 10:  det["mom_score"] += 12
            elif mom3m > 3:   det["mom_score"] += 8
            elif mom3m > 0:   det["mom_score"] += 4
            elif mom3m > -8:  det["mom_score"] += 2
        if len(cierre) >= 21:
            mom1m = float((precio / float(cierre.iloc[-21])) - 1) * 100
            if mom1m > 7:     det["mom_score"] += 10
            elif mom1m > 3:   det["mom_score"] += 8
            elif mom1m > 0:   det["mom_score"] += 5
            elif mom1m > -4:  det["mom_score"] += 2

        # ── MACD 12/26/9 (20 pts) ────────────────────────────────────────────
        if len(cierre) >= 35:
            ema12 = cierre.ewm(span=12, adjust=False).mean()
            ema26 = cierre.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            macd_sig  = macd_line.ewm(span=9, adjust=False).mean()
            macd_val  = float(macd_line.iloc[-1])
            sig_val   = float(macd_sig.iloc[-1])
            det["macd"]        = round(macd_val, 4)
            det["macd_signal"] = round(sig_val, 4)

            bullish_cross = macd_val > sig_val
            positive_zone = macd_val > 0
            # Cruce reciente (último cambio de señal en los 5 días previos)
            if len(macd_line) >= 6:
                cross_reciente = (
                    (macd_line.iloc[-1] > macd_sig.iloc[-1]) !=
                    (macd_line.iloc[-6] > macd_sig.iloc[-6])
                )
            else:
                cross_reciente = False

            if bullish_cross and positive_zone and cross_reciente:
                det["macd_score"] = 20  # cruce alcista reciente sobre cero → señal fuerte
            elif bullish_cross and positive_zone:
                det["macd_score"] = 16  # sobre cero, sin cruce reciente
            elif bullish_cross and not positive_zone:
                det["macd_score"] = 10  # cruce alcista pero aún negativo
            elif not bullish_cross and positive_zone:
                det["macd_score"] = 6   # bajando pero en zona positiva
            else:
                det["macd_score"] = 0   # bearish bajo cero

        # ── Bollinger Bands 20/2 (7 pts) ─────────────────────────────────────
        if len(cierre) >= 20:
            sma20 = float(cierre.rolling(20).mean().iloc[-1])
            std20 = float(cierre.rolling(20).std().iloc[-1])
            if std20 > 0:
                bb_upper = sma20 + 2 * std20
                bb_lower = sma20 - 2 * std20
                bb_mid   = sma20
                if precio < bb_lower:
                    det["bb_score"] = 5    # debajo de banda inferior → posible rebote
                    det["bb_pos"]   = "below_lower"
                elif precio <= bb_mid:
                    det["bb_score"] = 7    # entre lower y mid → zona de compra
                    det["bb_pos"]   = "lower_half"
                elif precio <= bb_upper * 0.97:
                    det["bb_score"] = 4    # entre mid y upper (sin tocar techo)
                    det["bb_pos"]   = "upper_half"
                else:
                    det["bb_score"] = 1    # tocando/superando banda superior
                    det["bb_pos"]   = "above_upper"

        # ── Volatilidad histórica 20d (usada también por penalizador) ─────────
        if len(cierre) >= 22:
            log_ret = np.log(cierre / cierre.shift(1)).dropna()
            hv20 = float(log_ret.tail(20).std()) * np.sqrt(252) * 100
            det["hv20"] = round(hv20, 1)

        # ── Tendencia de Volumen (3 pts) — requiere datos externos ────────────
        # Se calculará en calcular_score_total/escanear_universo si hay volumen
        # Aquí dejamos vol_score = 0; se puede setear externamente.

        total = (det["sma_score"] + det["rsi_score"] + det["mom_score"]
                 + det["macd_score"] + det["bb_score"] + det["vol_score"])
        return round(min(100.0, max(0.0, float(total))), 1), det

    except Exception as exc:
        _log.debug("_calcular_tecnico_elite: %s", exc)
        return 40.0, det


def _calcular_volatilidad_penalizacion(cierre: "pd.Series") -> tuple[float, dict]:
    """
    Calcula penalización por riesgo/volatilidad (0 a -8 puntos).

    Métricas:
      HV20d (volatilidad histórica 20 días anualizada)  — peso principal
      Max Drawdown 1Y                                   — riesgo de caída

    Retorna (penalizacion_positiva, dict_detalle).
    La penalización se RESTA del score total.
    """
    pen_det: dict = {"hv20": 0.0, "max_dd_1y": 0.0, "penalizacion": 0.0}
    try:
        c = cierre.dropna()
        if len(c) < 22:
            return 0.0, pen_det

        # HV20d
        log_ret = np.log(c / c.shift(1)).dropna()
        hv20 = float(log_ret.tail(20).std()) * np.sqrt(252) * 100
        pen_det["hv20"] = round(hv20, 1)

        # Max Drawdown 1Y (últimos 252 días)
        ventana = c.tail(252)
        rolling_max = ventana.cummax()
        dd = (ventana - rolling_max) / rolling_max * 100
        max_dd = abs(float(dd.min()))
        pen_det["max_dd_1y"] = round(max_dd, 1)

        # Penalización por HV (0-6)
        if hv20 > 80:    pen_hv = 6.0
        elif hv20 > 60:  pen_hv = 5.0
        elif hv20 > 45:  pen_hv = 3.5
        elif hv20 > 35:  pen_hv = 2.0
        elif hv20 > 25:  pen_hv = 1.0
        else:            pen_hv = 0.0

        # Penalización por drawdown (0-2)
        if max_dd > 50:    pen_dd = 2.0
        elif max_dd > 35:  pen_dd = 1.5
        elif max_dd > 25:  pen_dd = 1.0
        elif max_dd > 15:  pen_dd = 0.5
        else:              pen_dd = 0.0

        total_pen = round(min(8.0, pen_hv + pen_dd), 2)
        pen_det["penalizacion"] = total_pen
        return total_pen, pen_det

    except Exception as exc:
        _log.debug("_calcular_volatilidad_penalizacion: %s", exc)
        return 0.0, pen_det


# ─── 2. SCORE TÉCNICO ELITE (0-100) ──────────────────────────────────────────

def score_tecnico(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Score técnico elite 0-100.
    Delega el cálculo en _calcular_tecnico_elite() para coherencia con el batch path.
    Para bonos usa solo momentum de precio (_score_tecnico_bono).
    """
    if tipo in ("Bono USD", "ON Corporativa"):
        return _score_tecnico_bono(ticker)

    default_det = {
        "sma_score": 0, "rsi": 50.0, "rsi_score": 0, "mom_score": 0,
        "macd_score": 0, "bb_score": 0, "vol_score": 0, "precio": 0.0,
        "macd": 0.0, "macd_signal": 0.0, "bb_pos": "", "hv20": 0.0,
    }
    try:
        t_yf = _ticker_yahoo(ticker, tipo)
        data = yf.Ticker(t_yf).history(period="1y")
        if data.empty or len(data) < 30:
            return 40.0, default_det
        cierre = data["Close"].dropna()

        score, det = _calcular_tecnico_elite(cierre)

        # Tendencia de volumen (3 pts extras disponibles en score_tecnico individual)
        if "Volume" in data.columns and len(data) >= 20:
            vol_s = data["Volume"].dropna()
            if len(vol_s) >= 20:
                vol_5d  = float(vol_s.tail(5).mean())
                vol_20d = float(vol_s.tail(20).mean())
                if vol_20d > 0:
                    if vol_5d >= vol_20d * 1.2:
                        det["vol_score"] = 3    # volumen confirmando
                    elif vol_5d >= vol_20d * 0.8:
                        det["vol_score"] = 2    # volumen neutro
                    else:
                        det["vol_score"] = 0    # volumen débil / distribución
                    score = min(100.0, score + det["vol_score"])

        return score, det

    except Exception as e:
        _log.debug("score_tecnico %s: %s", ticker, e)
        return 40.0, default_det


def _score_tecnico_bono(ticker: str) -> tuple[float, dict]:
    """Score técnico para bonos: solo momentum de precio."""
    detalle = {"sma_score": 0, "rsi": 50, "rsi_score": 0, "mom_score": 0, "precio": 0}
    cierre = pd.Series(dtype=float)
    for sym in _simbolos_yfinance_rf(ticker):
        try:
            data = yf.Ticker(sym).history(period="6mo")
            if data is None or data.empty or "Close" not in data.columns:
                continue
            cierre = data["Close"].dropna()
            if not cierre.empty:
                break
        except Exception:
            continue
    if cierre.empty:
        return 45.0, detalle
    try:
        detalle["precio"] = round(float(cierre.iloc[-1]), 4)
        if len(cierre) >= 20:
            mom = (float(cierre.iloc[-1]) / float(cierre.iloc[-20]) - 1) * 100
            detalle["mom_score"] = min(40, max(0, int(mom * 2 + 20)))
        return float(detalle["mom_score"] + 40), detalle
    except Exception:
        return 45.0, detalle


# ─── 3. SCORE SECTOR/CONTEXTO (0-100) ────────────────────────────────────────

def score_sector_contexto(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Score de sector y contexto 0-100.
    Componentes:
      score_base        → SCORE_SECTORIAL_BASE[sector] × 10   (0-100)
      ajuste_macro_eeuu → recesión + ciclo Fed                 (±15 pts)
      ajuste_arg        → riesgo país + CCL                    (±15 pts)
      ajuste_ciclo_2026 → _SECTOR_CICLO_2026 fase              (±3 pts)
    """
    if tipo == "Bono USD":
        sector = "Bono USD"
    elif tipo == "ON Corporativa":
        sector = "ON Corporativa"
    else:
        sector = SECTORES.get(ticker.upper(), "Otros")

    score_base = SCORE_SECTORIAL_BASE.get(sector, 5.0) * 10  # 0-100

    detalle: dict = {
        "sector":            sector,
        "score_base":        score_base,
        "ajuste_macro_eeuu": 0,
        "ajuste_arg":        0,
        "ajuste_ciclo":      0,
        "ciclo_sector":      _SECTOR_CICLO_2026.get(sector, "neutral"),
    }

    # ── Ajuste EEUU (±15 pts) ─────────────────────────────────────────────────
    recesion = CONTEXTO_MACRO.get("recesion_riesgo", "BAJO")
    if recesion == "BAJO":
        detalle["ajuste_macro_eeuu"] = 10
    elif recesion == "MEDIO":
        detalle["ajuste_macro_eeuu"] = 3
    elif recesion == "ALTO":
        detalle["ajuste_macro_eeuu"] = -10

    fed_ciclo = CONTEXTO_MACRO.get("fed_ciclo", "PAUSA")
    if fed_ciclo == "BAJA":
        if sector in ("Tecnología", "E-Commerce", "Comunicaciones", "Bono USD", "ON Corporativa"):
            detalle["ajuste_macro_eeuu"] += 5
        if sector == "Real Estate":
            detalle["ajuste_macro_eeuu"] += 4
    elif fed_ciclo == "SUBA":
        if sector in ("Financiero", "Consumo Def."):
            detalle["ajuste_macro_eeuu"] += 5
        if sector in ("Tecnología", "E-Commerce"):
            detalle["ajuste_macro_eeuu"] -= 3

    # DXY bajista → beneficia commodities y emergentes
    if CONTEXTO_MACRO.get("dxy_tendencia") == "BAJISTA":
        if sector in ("Energía", "Materiales", "Cobertura", "Acción Local", "Energía Local"):
            detalle["ajuste_macro_eeuu"] += 3

    # ── Ajuste Argentina (±15 pts) ────────────────────────────────────────────
    if tipo in ("CEDEAR", "ETF"):
        ccl = CONTEXTO_MACRO.get("ccl_tendencia", "ESTABLE")
        if ccl == "SUBE":
            detalle["ajuste_arg"] = 10
        elif ccl == "ESTABLE":
            detalle["ajuste_arg"] = 5
        else:
            detalle["ajuste_arg"] = 2
    elif tipo in ("Acción Local", "Merval"):
        rp = CONTEXTO_MACRO.get("riesgo_pais", "MEDIO")
        if rp == "BAJO":
            detalle["ajuste_arg"] = 15
        elif rp == "MEDIO":
            detalle["ajuste_arg"] = 7
        else:
            detalle["ajuste_arg"] = -5
        if CONTEXTO_MACRO.get("cepo_status") == "SIN":
            detalle["ajuste_arg"] += 3
        elif CONTEXTO_MACRO.get("cepo_status") == "PARCIAL":
            detalle["ajuste_arg"] += 1
    elif tipo in ("Bono USD", "ON Corporativa"):
        rp = CONTEXTO_MACRO.get("riesgo_pais", "MEDIO")
        if rp == "BAJO":
            detalle["ajuste_arg"] = 12
        elif rp == "MEDIO":
            detalle["ajuste_arg"] = 6
        else:
            detalle["ajuste_arg"] = 0

    # ── Ajuste ciclo sectorial 2026 (±3 pts) ─────────────────────────────────
    ciclo = detalle["ciclo_sector"]
    detalle["ajuste_ciclo"] = _CICLO_AJUSTE.get(ciclo, 0.0)

    total = (score_base
             + detalle["ajuste_macro_eeuu"]
             + detalle["ajuste_arg"]
             + detalle["ajuste_ciclo"])
    return round(min(100.0, max(0.0, float(total))), 1), detalle


def score_fci(ticker: str) -> tuple[float, dict]:
    """
    Score fundamental para fondos comunes (FCI).
    Delega en CAFCI cuando está disponible; heurística / neutro si falla.
    Invariante: retorna siempre (score en [0, 100], dict detalle) sin propagar excepción.
    """
    try:
        from services.cafci_connector import score_fci_real
        return score_fci_real(ticker)
    except Exception as exc:
        _log.debug("score_fci %s: %s", ticker, exc)
        return 50.0, {"fuente": "fallback", "error": str(exc)}


# ─── SCORE TOTAL ELITE (60/20/20 + moat bonus - volatilidad - liquidez) ───────

def _moat_bonus(ticker: str) -> float:
    """Bonus por moat: 0 a +5 pts. moat_nivel × 1.67."""
    return round(_MOAT_SCORE.get(ticker.upper(), 0) * (5.0 / 3.0), 2)


def calcular_score_total(ticker: str, tipo: str = "CEDEAR") -> dict:
    """
    Score final elite para un activo.

    Fórmula:
      base = sf×0.60 + st×0.20 + ss×0.20
      final = base + moat_bonus - volatilidad_pen - liquidez_pen
      clamp [0, 100]

    Campos nuevos en el dict de salida:
      Moat, Moat_Bonus, HV20d, MaxDD_1Y, Penalizacion_Volatilidad,
      MACD, MACD_Signal, BB_Pos, Ciclo_Sector
    """
    _log.debug("Scoring elite %s (%s)", ticker, tipo)

    if tipo == "FCI":
        sf, df_fund = score_fci(ticker)
        st, df_tec  = 50.0, {
            "rsi": 50, "precio": 0, "sma_score": 0, "rsi_score": 0, "mom_score": 0,
            "macd_score": 0, "bb_score": 0, "vol_score": 0,
            "macd": 0.0, "macd_signal": 0.0, "bb_pos": "", "hv20": 0.0,
        }
        ss, df_sec  = score_sector_contexto(ticker, tipo)
        score_total = round(min(100.0, sf * PESO_FUNDAMENTAL + st * PESO_TECNICO + ss * PESO_SECTOR_CTX), 1)
        senal = "🟡 ACUMULAR" if score_total >= 60 else "⚪ MANTENER" if score_total >= 45 else "🟠 REDUCIR"
        return {
            "Ticker": ticker, "Tipo": tipo, "Sector": "FCI",
            "Score_Total": score_total, "Score_Fund": sf, "Score_Tec": st, "Score_Sector": ss,
            "RSI": 50, "Precio": 0, "Senal": senal,
            "Detalle_Fund": df_fund, "Detalle_Tec": df_tec, "Detalle_Sector": df_sec,
            "Fecha_Score": str(date.today()),
            "Moat": _MOAT_SCORE.get(ticker.upper(), 0),
            "Moat_Bonus": 0.0, "HV20d": 0.0, "MaxDD_1Y": 0.0,
            "Penalizacion_Volatilidad": 0.0, "Volumen_Promedio_30d": 0.0,
            "Penalizacion_Liquidez": 0.0, "Ciclo_Sector": "neutral",
        }

    sf, df_fund = score_fundamental(ticker, tipo)
    st, df_tec  = _get_score_tecnico_cached(ticker, tipo)
    ss, df_sec  = score_sector_contexto(ticker, tipo)

    # ── Volatilidad / riesgo — requiere descargar serie de precios ────────────
    _pen_volatilidad = 0.0
    _vol_det: dict = {"hv20": 0.0, "max_dd_1y": 0.0, "penalizacion": 0.0}
    try:
        _t_yf_v = _ticker_yahoo(ticker, tipo)
        _hist_v = yf.Ticker(_t_yf_v).history(period="1y")
        if not _hist_v.empty and "Close" in _hist_v.columns:
            _cierre_v = _hist_v["Close"].dropna()
            _pen_volatilidad, _vol_det = _calcular_volatilidad_penalizacion(_cierre_v)
    except Exception:
        pass

    # ── Liquidez — penalización por volumen bajo (MQ2-U7) ────────────────────
    _vol_promedio       = 0.0
    _penalizacion_liq   = 0.0
    try:
        if tipo in ("Bono USD", "ON Corporativa"):
            _sym_vol = _simbolos_yfinance_rf(ticker)[0]
        else:
            _sym_vol = _ticker_yahoo(ticker, tipo)
        _hist_liq = yf.Ticker(_sym_vol).history(period="35d")
        if not _hist_liq.empty and "Volume" in _hist_liq.columns:
            _vol_promedio = float(_hist_liq["Volume"].tail(30).mean())
            _umbral_vol   = 50_000
            if 0 < _vol_promedio < _umbral_vol:
                _penalizacion_liq = min(10.0, 10.0 * (1 - _vol_promedio / _umbral_vol))
    except Exception:
        pass

    # ── Moat bonus ────────────────────────────────────────────────────────────
    _mb = _moat_bonus(ticker)

    # ── Score final ───────────────────────────────────────────────────────────
    base = sf * PESO_FUNDAMENTAL + st * PESO_TECNICO + ss * PESO_SECTOR_CTX
    score_total = round(
        min(100.0, max(0.0, base + _mb - _pen_volatilidad - _penalizacion_liq)),
        1
    )

    if score_total >= 75:    senal = "🟢 COMPRAR"
    elif score_total >= 60:  senal = "🟡 ACUMULAR"
    elif score_total >= 45:  senal = "⚪ MANTENER"
    elif score_total >= 30:  senal = "🟠 REDUCIR"
    else:                    senal = "🔴 SALIR"

    return {
        "Ticker":          ticker,
        "Tipo":            tipo,
        "Sector":          df_sec.get("sector", SECTORES.get(ticker, "Otros")),
        "Score_Total":     score_total,
        "Score_Fund":      sf,
        "Score_Tec":       st,
        "Score_Sector":    ss,
        "RSI":             df_tec.get("rsi", 50),
        "Precio":          df_tec.get("precio", 0),
        "Senal":           senal,
        "Detalle_Fund":    df_fund,
        "Detalle_Tec":     df_tec,
        "Detalle_Sector":  df_sec,
        "Fecha_Score":     str(date.today()),
        # ── Nuevos campos elite ───────────────────────────────────────────────
        "Moat":                    _MOAT_SCORE.get(ticker.upper(), 0),
        "Moat_Bonus":              _mb,
        "HV20d":                   _vol_det.get("hv20", 0.0),
        "MaxDD_1Y":                _vol_det.get("max_dd_1y", 0.0),
        "Penalizacion_Volatilidad":_pen_volatilidad,
        "MACD":                    df_tec.get("macd", 0.0),
        "MACD_Signal":             df_tec.get("macd_signal", 0.0),
        "BB_Pos":                  df_tec.get("bb_pos", ""),
        "Ciclo_Sector":            df_sec.get("ciclo_sector", "neutral"),
        "Volumen_Promedio_30d":    _vol_promedio,
        "Penalizacion_Liquidez":   _penalizacion_liq,
    }


# ─── SCANNER COMPLETO DEL UNIVERSO ────────────────────────────────────────────

def escanear_universo_completo(
    incluir_cedears:       bool = True,
    incluir_merval:        bool = True,
    incluir_bonos:         bool = False,
    incluir_internacional: bool = False,
    incluir_fci:           bool = False,
    max_activos:           int  = 50,
    callback_progreso      = None,
) -> pd.DataFrame:
    """
    F2: Escanea el universo con batch download para precios históricos.
    Descarga todos los precios en una sola llamada HTTP → speedup 5-10x.
    callback_progreso(i, total, ticker): para barra de progreso en Streamlit.
    """
    tickers_a_escanear = []

    if incluir_cedears:
        tickers_a_escanear += [(t, "CEDEAR") for t in UNIVERSO_CEDEARS]
    if incluir_merval:
        tickers_a_escanear += [(t, "Acción Local") for t in UNIVERSO_MERVAL]
    if incluir_bonos:
        tickers_a_escanear += [(t, "Bono USD") for t in UNIVERSO_BONOS_USD]
        tickers_a_escanear += [(t, "ON Corporativa") for t in UNIVERSO_ONS]
    if incluir_internacional:
        tickers_a_escanear += [(t, "Internacional") for t in UNIVERSO_INTERNACIONAL]
    if incluir_fci:
        tickers_a_escanear += [(t, "FCI") for t in UNIVERSO_FCI_LISTA]

    tickers_a_escanear = [
        (t, tp) for t, tp in tickers_a_escanear
        if t not in TICKERS_NO_CEDEAR_BYMA
    ][:max_activos]

    # F2: Batch download de precios históricos para todos los tickers no-FCI
    tickers_no_fci = [t for t, tipo in tickers_a_escanear if tipo not in ("FCI",)]
    tickers_yf_batch = [_ticker_yahoo(t, tipo) for t, tipo in tickers_a_escanear if tipo not in ("FCI",)]
    tickers_yf_batch = list(dict.fromkeys(tickers_yf_batch))  # deduplicar

    # Mapa Yahoo → ticker local para lookup rápido
    _yf_to_local = {_ticker_yahoo(t, tipo): t
                    for t, tipo in tickers_a_escanear if tipo not in ("FCI",)}

    precios_batch: dict = {}
    try:
        raw = yf.download(tickers_yf_batch, period="1y", auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            close_batch = raw["Close"]
        else:
            close_batch = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame()
        for col in close_batch.columns:
            s = close_batch[col].dropna()
            if not s.empty:
                precios_batch[str(col)] = s  # Serie completa para SMA/RSI
    except Exception as _e:
        _log.warning("batch download falló, se usará descarga individual: %s", _e)

    resultados = []
    total = len(tickers_a_escanear)

    for i, (ticker, tipo) in enumerate(tickers_a_escanear):
        if callback_progreso:
            callback_progreso(i + 1, total, ticker)
        try:
            # Inyectar datos batch en el score técnico si están disponibles
            t_yf = _ticker_yahoo(ticker, tipo)
            if t_yf in precios_batch and tipo not in ("FCI", "Bono USD", "ON Corporativa"):
                r = _calcular_score_con_serie(ticker, tipo, precios_batch[t_yf])
            else:
                r = calcular_score_total(ticker, tipo)
            resultados.append(r)
            # F2: sin sleep cuando usamos batch (el sleep era para evitar rate limit individual)
        except Exception as e:
            _log.warning("Error escaneando %s: %s", ticker, e)

    if not resultados:
        return pd.DataFrame()

    df = pd.DataFrame(resultados)
    df = df.sort_values("Score_Total", ascending=False).reset_index(drop=True)
    df.index += 1
    return df


def _calcular_score_con_serie(ticker: str, tipo: str, serie_precios: pd.Series) -> dict:
    """
    F2: Calcula score elite reutilizando la serie de precios del batch download.
    Usa _calcular_tecnico_elite() y _calcular_volatilidad_penalizacion() sobre
    la misma serie para evitar llamadas extra a yfinance.
    """
    cierre = serie_precios.dropna()
    if len(cierre) < 30:
        st_score, dt = 40.0, {
            "sma_score": 0, "rsi": 50.0, "rsi_score": 0, "mom_score": 0,
            "macd_score": 0, "bb_score": 0, "vol_score": 0, "precio": 0.0,
            "macd": 0.0, "macd_signal": 0.0, "bb_pos": "", "hv20": 0.0,
        }
        _pen_vol = 0.0
        _vol_det: dict = {"hv20": 0.0, "max_dd_1y": 0.0}
    else:
        st_score, dt = _calcular_tecnico_elite(cierre)
        _pen_vol, _vol_det = _calcular_volatilidad_penalizacion(cierre)

    sf, df_fund = score_fundamental(ticker, tipo)
    ss, df_sec  = score_sector_contexto(ticker, tipo)
    _mb = _moat_bonus(ticker)

    base = sf * PESO_FUNDAMENTAL + st_score * PESO_TECNICO + ss * PESO_SECTOR_CTX
    score_total = round(min(100.0, max(0.0, base + _mb - _pen_vol)), 1)

    if score_total >= 75:    senal = "🟢 COMPRAR"
    elif score_total >= 60:  senal = "🟡 ACUMULAR"
    elif score_total >= 45:  senal = "⚪ MANTENER"
    elif score_total >= 30:  senal = "🟠 REDUCIR"
    else:                    senal = "🔴 SALIR"

    return {
        "Ticker":          ticker,
        "Tipo":            tipo,
        "Sector":          df_sec.get("sector", SECTORES.get(ticker, "Otros")),
        "Score_Total":     score_total,
        "Score_Fund":      sf,
        "Score_Tec":       st_score,
        "Score_Sector":    ss,
        "RSI":             dt.get("rsi", 50),
        "Precio":          dt.get("precio", 0),
        "Senal":           senal,
        "Detalle_Fund":    df_fund,
        "Detalle_Tec":     dt,
        "Detalle_Sector":  df_sec,
        "Fecha_Score":     str(date.today()),
        # ── Campos elite ──────────────────────────────────────────────────────
        "Moat":                    _MOAT_SCORE.get(ticker.upper(), 0),
        "Moat_Bonus":              _mb,
        "HV20d":                   _vol_det.get("hv20", 0.0),
        "MaxDD_1Y":                _vol_det.get("max_dd_1y", 0.0),
        "Penalizacion_Volatilidad":_pen_vol,
        "MACD":                    dt.get("macd", 0.0),
        "MACD_Signal":             dt.get("macd_signal", 0.0),
        "BB_Pos":                  dt.get("bb_pos", ""),
        "Ciclo_Sector":            df_sec.get("ciclo_sector", "neutral"),
        "Volumen_Promedio_30d":    0.0,   # no disponible en batch sin columna Volume
        "Penalizacion_Liquidez":   0.0,
    }


# ─── CARTERA ÓPTIMA ───────────────────────────────────────────────────────────

def calcular_cartera_optima(
    df_scores:      pd.DataFrame,
    cartera_actual: dict[str, int],  # {ticker: cantidad}
    presupuesto_semanal_ars: float,
    perfil:         str = "Moderado",  # Conservador / Moderado / Agresivo
    n_posiciones:   int = 12,
    ccl:            float = 1465.0,
) -> pd.DataFrame:
    """
    A partir del ranking de scores, construye la cartera óptima a largo plazo
    y genera las recomendaciones semanales para acercarse a ella.

    Restricciones:
      - Mínimo 5 sectores distintos (diversificación)
      - Máx 20% en un solo activo
      - Incluir siempre al menos 1 activo defensivo (KO, PEP, ABBV, GLD)
      - Para perfil Conservador: priorizar dividendos y baja volatilidad
      - Para perfil Agresivo: priorizar score_total sin restricción de dividendo
    """
    if df_scores.empty:
        return pd.DataFrame()

    defensivos = {"KO","PEP","ABBV","GLD","JNJ","PG","MO","VZ"}
    PESO_MAX = {"Conservador": 0.15, "Moderado": 0.20, "Agresivo": 0.25}.get(perfil, 0.20)

    # Excluir tickers que no son CEDEAR comprables con ARS
    df_scores = df_scores[~df_scores["Ticker"].isin(TICKERS_NO_CEDEAR_BYMA)].copy()
    if df_scores.empty:
        return pd.DataFrame()

    # Filtrar los mejores candidatos
    candidatos = df_scores[df_scores["Score_Total"] >= 50].copy()

    if candidatos.empty:
        candidatos = df_scores.head(20).copy()

    # Asegurar al menos 1 defensivo
    tiene_defensivo = candidatos["Ticker"].isin(defensivos).any()
    if not tiene_defensivo:
        defensivos_disponibles = df_scores[df_scores["Ticker"].isin(defensivos)]
        if not defensivos_disponibles.empty:
            candidatos = pd.concat([candidatos, defensivos_disponibles.head(2)])

    # Seleccionar top N con diversificación sectorial
    seleccionados = []
    sectores_incluidos = set()
    for _, row in candidatos.iterrows():
        if len(seleccionados) >= n_posiciones:
            break
        sector = row.get("Sector", "Otros")
        ticker = row["Ticker"]

        # Máx 3 por sector
        sector_count = sum(1 for r in seleccionados if r.get("Sector") == sector)
        if sector_count >= 3:
            continue

        sectores_incluidos.add(sector)
        seleccionados.append(row.to_dict())

    df_opt = pd.DataFrame(seleccionados)
    if df_opt.empty:
        return pd.DataFrame()

    # ── Optimizador multi-objetivo (Sharpe primero) ──────────────────────────
    # Prioridades: 1.Sharpe 2.Retorno_USD 3.Preservación_ARS 4.Dividendos
    from config import PESOS_OPTIMIZADOR

    s_total   = df_opt["Score_Total"].values.astype(float)
    s_fund    = df_opt["Score_Fund"].values.astype(float)
    s_tec     = df_opt["Score_Tec"].values.astype(float)

    # Proxy Sharpe: Score_Total / (100 - Score_Tec + 1) — mayor score tec = mayor volatilidad
    sharpe_proxy  = s_total / (101 - s_tec)
    # Proxy retorno USD: Score_Total (ya incorpora fundamentales en USD)
    retorno_proxy = s_total / 100
    # Proxy preservación ARS: penalizar activos de alta volatilidad local
    tipo_col  = df_opt.get("Tipo", pd.Series(["CEDEAR"]*len(df_opt))).values
    preserv_proxy = np.where(
        pd.Series(tipo_col).isin(["FCI","Bono USD","ON Corporativa"]), 1.2, 1.0
    )
    # Proxy dividendo: Score_Fund (incluye dividend yield)
    div_proxy = s_fund / 100

    # Score compuesto multi-objetivo
    score_compuesto = (
        sharpe_proxy  * PESOS_OPTIMIZADOR["sharpe"]           +
        retorno_proxy * PESOS_OPTIMIZADOR["retorno_usd"]      +
        preserv_proxy * PESOS_OPTIMIZADOR["preservacion_ars"] +
        div_proxy     * PESOS_OPTIMIZADOR["dividendos"]
    )

    pesos_raw = score_compuesto / score_compuesto.sum()
    pesos = np.clip(pesos_raw, 0.03, PESO_MAX)
    pesos = pesos / pesos.sum()  # Renormalizar

    df_opt["Peso_Optimo_Pct"] = np.round(pesos * 100, 1)
    df_opt["Tiene_Posicion"]  = df_opt["Ticker"].isin(cartera_actual)
    df_opt["Cant_Actual"]     = df_opt["Ticker"].map(cartera_actual).fillna(0).astype(int)

    # Generar recomendación semanal
    recomendaciones = []
    presupuesto_restante = presupuesto_semanal_ars

    for _, row in df_opt.iterrows():
        ticker = row["Ticker"]
        senal  = row.get("Senal", "")
        precio = float(row.get("Precio", 0)) or 1.0
        ratio  = float(RATIOS_CEDEAR.get(ticker, 1.0))
        precio_ars = precio * ccl / ratio  # precio del CEDEAR en ARS

        if precio_ars <= 0:
            accion = "—"
        elif "COMPRAR" in senal or "ACUMULAR" in senal:
            cant_posible = max(1, int(presupuesto_restante / precio_ars))
            cant_semanal = min(cant_posible, max(1, int(presupuesto_restante * 0.2 / precio_ars)))
            costo_ars = cant_semanal * precio_ars
            presupuesto_restante -= costo_ars

            if cant_semanal > 0 and costo_ars <= presupuesto_semanal_ars:
                if row["Tiene_Posicion"]:
                    accion = f"Agregar {cant_semanal}u (${costo_ars:,.0f})"
                else:
                    accion = f"Iniciar {cant_semanal}u (${costo_ars:,.0f})"
            else:
                accion = "Mantener"
        else:
            accion = "Esperar"

        recomendaciones.append(accion)

    df_opt["Accion_Semanal"] = recomendaciones

    return df_opt[[
        "Ticker","Sector","Score_Total","Score_Fund","Score_Tec","Score_Sector",
        "RSI","Senal","Peso_Optimo_Pct","Cant_Actual","Tiene_Posicion","Accion_Semanal"
    ]].reset_index(drop=True)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _ticker_yahoo(ticker: str, tipo: str = "CEDEAR") -> str:
    """Convierte ticker local a formato Yahoo Finance."""
    if tipo in ("Bono USD", "ON Corporativa"):
        syms = _simbolos_yfinance_rf(ticker)
        return syms[0] if syms else f"{str(ticker).upper().strip()}.BA"
    mapa = {
        "BRKB": "BRK-B", "YPFD": "YPFD.BA", "CEPU": "CEPU.BA",
        "TGNO4": "TGNO4.BA", "TGSU2": "TGSU2.BA", "PAMP": "PAMP.BA",
        "GGAL": "GGAL.BA", "BMA": "BMA.BA", "ALUA": "ALUA.BA",
        "LOMA": "LOMA.BA", "CRES": "CRES.BA", "TXAR": "TXAR.BA",
        "AGRO": "AGRO.BA", "BYMA": "BYMA.BA", "MOLI": "MOLI.BA",
        "IRSA": "IRSA.BA", "MIRG": "MIRG.BA",
    }
    return mapa.get(ticker.upper(), ticker.upper())


def actualizar_contexto_macro(nuevos_valores: dict) -> None:
    """B12: Actualiza el contexto macro en memoria Y lo persiste en SQLite.
    Sobrevive reinicios de la app."""
    CONTEXTO_MACRO.update(nuevos_valores)
    _log.info("Contexto macro actualizado: %s", list(nuevos_valores.keys()))
    try:
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        import core.db_manager as _dbm
        _dbm.guardar_config("contexto_macro", CONTEXTO_MACRO)
    except Exception as _e:
        _log.debug("No se pudo persistir contexto macro: %s", _e)


def cargar_contexto_macro_desde_bd() -> None:
    """B12: Carga el contexto macro persistido desde SQLite al iniciar el módulo."""
    try:
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        import core.db_manager as _dbm
        guardado = _dbm.obtener_config("contexto_macro")
        if guardado and isinstance(guardado, dict):
            CONTEXTO_MACRO.update(guardado)
            _log.info("Contexto macro cargado desde BD: %s claves", len(guardado))
    except Exception as _e:
        _log.debug("cargar_contexto_macro_desde_bd: %s", _e)


def obtener_contexto_macro() -> dict:
    """Retorna el contexto macro actual."""
    return CONTEXTO_MACRO.copy()


# Cargar contexto macro al importar el módulo (B12)
cargar_contexto_macro_desde_bd()


# ── T-2.2: indicadores fundamentales ponderados de cartera ────────────────────

def calcular_indicadores_cartera(pesos: dict[str, float]) -> dict[str, float]:
    """
    Calcula indicadores fundamentales promedio ponderado de una cartera.
    Retorna exactamente 5 keys: per_w, ps_w, roe_w, roa_w, dividend_yield_w.

    pesos: {ticker: peso_decimal}, tolerante a que no sumen exactamente 1.
    Usa yfinance.Ticker(ticker).info con try/except por ticker.
    """
    import yfinance as yf

    total = sum(pesos.values())
    if total <= 0:
        return {"per_w": 0.0, "ps_w": 0.0, "roe_w": 0.0, "roa_w": 0.0, "dividend_yield_w": 0.0}
    pesos_norm = {t: v / total for t, v in pesos.items()}

    acum = {"per_w": 0.0, "ps_w": 0.0, "roe_w": 0.0, "roa_w": 0.0, "dividend_yield_w": 0.0}
    YFINANCE_KEYS = {
        "per_w":            "trailingPE",
        "ps_w":             "priceToSalesTrailing12Months",
        "roe_w":            "returnOnEquity",
        "roa_w":            "returnOnAssets",
        "dividend_yield_w": "dividendYield",
    }

    for ticker, peso in pesos_norm.items():
        try:
            info = yf.Ticker(ticker).info
        except Exception:
            info = {}
        for key, yf_key in YFINANCE_KEYS.items():
            val = info.get(yf_key)
            if val is None or not isinstance(val, (int, float)):
                val = 0.0
            acum[key] += float(val) * peso

    return acum
