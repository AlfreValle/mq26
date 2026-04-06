"""
services/scoring_engine.py — Motor de Scoring 60/20/20
Master Quant 26 | DSS Unificado

Arquitectura:
  60% Fundamental  → P/E, ROE, Deuda/Capital, Dividendo, Crecimiento EPS
  20% Técnico      → MOD-23: SMA150 (4) + RSI14 (3) + Momentum3M (3)
  20% Sector/Ctx   → Ciclo macro EEUU + Contexto Argentina + Fuerza relativa sectorial

Universo completo del inversor argentino:
  - CEDEARs BYMA
  - Acciones Merval
  - Bonos soberanos ARS/USD
  - ONs corporativas
  - Apartado internacional (ADRs/ETFs directos)

Score final: 0-100 → ordena el universo completo para la recomendación semanal.
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
from config import RATIOS_CEDEAR, RSI_COMPRA, RSI_VENTA, RSI_VENTANA, SECTORES, SMA_VENTANA
from core.logging_config import get_logger

_log = get_logger(__name__)

# ─── PESOS DEL MODELO ─────────────────────────────────────────────────────────
PESO_FUNDAMENTAL = 0.60
PESO_TECNICO     = 0.20
PESO_SECTOR_CTX  = 0.20

# ─── UNIVERSO COMPLETO INVERSOR ARGENTINO ────────────────────────────────────
# Categorías de activos disponibles en brokers locales

UNIVERSO_CEDEARS = [
    # Tecnología
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","AMD","ADBE","CRM","NFLX",
    "UBER","SHOP","INTC","ORCL","AVGO","QCOM","CSCO",
    # Consumo Defensivo
    "KO","PEP","COST","WMT","PG","MO","PM","CL","KMB",
    # Consumo Discrecional
    "TSLA","MCD","NKE","SBUX","HD","LOW","TGT",
    # Salud
    "UNH","ABBV","JNJ","LLY","PFE","MRK","ABT","TMO","GILD","AMGN",
    # Energía
    "CVX","XOM","PBR","SHEL","VIST","CEG","OKLO",
    # Industria / Defensa
    "CAT","GE","BA","LMT","RTX","HON","MMM","DE",
    # Financiero
    "BRKB","JPM","GS","V","MA","AXP","BAC","C","WFC","BLK",
    # Materiales
    "VALE","RIO","FCX","NEM","BHP",
    # ETFs / Cobertura
    "SPY","QQQ","DIA","GLD","SLV","XLE","XLF","XLK","EEM","VWO",
    # Latam
    "MELI","NU",
]

UNIVERSO_MERVAL = [
    "YPFD","CEPU","TGNO4","TGSU2","PAMP","GGAL","BMA","SUPV",
    "ALUA","BYMA","CRES","IRSA","MIRG","LOMA","TXAR","AGRO",
    "MOLI","BBAR","VALO",
]

UNIVERSO_BONOS_USD = [
    "GD30","GD35","GD38","GD41","AL29","AL30","AL35","AE38",
]

UNIVERSO_ONS = [
    "YMCXO","MGCEO","RUCDO","YCA6O","TLC1O","MRCAO",
]

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
# Fuente: Fred, Bloomberg, BCRA
CONTEXTO_MACRO = {
    # EEUU
    "sp500_tendencia":    "ALCISTA",   # Sobre SMA200
    "fed_ciclo":          "PAUSA",     # SUBA / BAJA / PAUSA
    "recesion_riesgo":    "BAJO",      # BAJO / MEDIO / ALTO
    "dxy_tendencia":      "LATERAL",   # Índice dólar
    # Argentina
    "riesgo_pais":        "MEDIO",     # BAJO <700 / MEDIO 700-1500 / ALTO >1500
    "ccl_tendencia":      "ESTABLE",   # SUBE / BAJA / ESTABLE
    "cepo_status":        "PARCIAL",   # PLENO / PARCIAL / SIN
    "bcra_reservas":      "RECUPERANDO",
    # Commodities
    "petroleo":           "LATERAL",
    "oro":                "ALCISTA",
    "soja":               "LATERAL",
}

# Puntaje por sector según contexto macro actual (0-10)
SCORE_SECTORIAL_BASE = {
    "Tecnología":      7.5,
    "Salud":           8.0,
    "Consumo Def.":    7.0,
    "Defensa":         8.5,
    "Energía":         6.5,
    "Energía Local":   6.0,
    "Financiero":      7.0,
    "Materiales":      6.0,
    "Industria":       6.5,
    "E-Commerce":      7.0,
    "ETF":             7.5,
    "Cobertura":       7.0,
    "Bono USD":        6.5,
    "ON Corporativa":  6.0,
    "Acción Local":    5.5,
    "Internacional":   7.0,
    "Otros":           5.0,
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
    Calcula score fundamental 0-100 usando yfinance.
    Métricas: P/E, ROE, Debt/Equity, Dividend Yield, EPS Growth, Profit Margin.
    Para bonos y acciones locales usa heurísticas simplificadas.
    """
    detalle = {
        "pe_score": 0, "roe_score": 0, "deuda_score": 0,
        "dividendo_score": 0, "crecimiento_score": 0, "margen_score": 0,
    }

    if tipo in ("Bono USD", "ON Corporativa"):
        # Bonos: score basado en rendimiento vs riesgo
        return _score_bono(ticker)

    if tipo in ("Acción Local", "Merval"):
        # Acciones locales: score simplificado por sector y contexto
        return _score_accion_local(ticker)

    try:
        t_yf = _ticker_yahoo(ticker)
        info = yf.Ticker(t_yf).info
        if not info or info.get("regularMarketPrice") is None:
            return 40.0, detalle  # Score neutro si no hay datos

        # P/E Ratio (menor es mejor, máx 25pts)
        pe = info.get("trailingPE") or info.get("forwardPE") or 0
        if 0 < pe <= 12:    detalle["pe_score"] = 25
        elif 12 < pe <= 20: detalle["pe_score"] = 20
        elif 20 < pe <= 30: detalle["pe_score"] = 12
        elif 30 < pe <= 50: detalle["pe_score"] = 5
        else:               detalle["pe_score"] = 0

        # ROE (mayor es mejor, máx 20pts)
        roe = (info.get("returnOnEquity") or 0) * 100
        if roe >= 25:        detalle["roe_score"] = 20
        elif roe >= 15:      detalle["roe_score"] = 15
        elif roe >= 8:       detalle["roe_score"] = 8
        elif roe >= 0:       detalle["roe_score"] = 3
        else:                detalle["roe_score"] = 0

        # Deuda/Capital (menor es mejor, máx 15pts)
        de = info.get("debtToEquity") or 0
        if de == 0:           detalle["deuda_score"] = 15
        elif de <= 30:        detalle["deuda_score"] = 12
        elif de <= 80:        detalle["deuda_score"] = 8
        elif de <= 150:       detalle["deuda_score"] = 4
        else:                 detalle["deuda_score"] = 0

        # Dividend Yield (flujo recurrente, máx 15pts)
        dy = (info.get("dividendYield") or 0) * 100
        if dy >= 4:           detalle["dividendo_score"] = 15
        elif dy >= 2:         detalle["dividendo_score"] = 10
        elif dy >= 0.5:       detalle["dividendo_score"] = 5
        else:                 detalle["dividendo_score"] = 2

        # Crecimiento EPS (mayor es mejor, máx 15pts)
        eg = (info.get("earningsGrowth") or info.get("revenueGrowth") or 0) * 100
        if eg >= 20:          detalle["crecimiento_score"] = 15
        elif eg >= 10:        detalle["crecimiento_score"] = 12
        elif eg >= 0:         detalle["crecimiento_score"] = 6
        else:                 detalle["crecimiento_score"] = 0

        # Margen de Beneficio (mayor es mejor, máx 10pts)
        pm = (info.get("profitMargins") or 0) * 100
        if pm >= 25:          detalle["margen_score"] = 10
        elif pm >= 15:        detalle["margen_score"] = 7
        elif pm >= 5:         detalle["margen_score"] = 4
        elif pm >= 0:         detalle["margen_score"] = 1
        else:                 detalle["margen_score"] = 0

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
    base_score = float(bonos_soberanos_base.get(ticker, bonos_ons_base.get(ticker, 55.0)))
    try:
        import yfinance as yf
        _t = ticker
        # Intento de cotización en formato BYMA para bonos
        _mapeo = {"GD30":"GD30=RX","GD35":"GD35=RX","AL30":"AL30=RX","GD38":"GD38=RX"}
        _sym = _mapeo.get(_t, _t)
        _hist = yf.Ticker(_sym).history(period="5d")["Close"].dropna()
        if len(_hist) >= 2:
            retorno_5d = (_hist.iloc[-1] / _hist.iloc[0] - 1) * 100
            # Modifica score dinámicamente: +/- 10 pts según retorno vs tendencia
            score = max(20.0, min(95.0, base_score + retorno_5d * 2))
            return score, {"rendimiento_estimado": base_score, "retorno_5d": round(retorno_5d, 2), "dinamico": True}
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


# ─── 2. SCORE TÉCNICO MOD-23 (0-100) ─────────────────────────────────────────

def score_tecnico(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Calcula score técnico 0-100.
    Basado en MOD-23 pero normalizado a 100:
      SMA150   → 0/40 pts
      RSI14    → 0/30 pts (zona compra = 30, neutral = 15, sobrecomprado = 5)
      Mom 3M   → 0/30 pts

    Para bonos usa solo momentum de precio.
    """
    detalle = {"sma_score": 0, "rsi": 50, "rsi_score": 0, "mom_score": 0, "precio": 0}

    if tipo in ("Bono USD", "ON Corporativa"):
        return _score_tecnico_bono(ticker)

    try:
        t_yf = _ticker_yahoo(ticker, tipo)
        data = yf.Ticker(t_yf).history(period="1y")
        if data.empty or len(data) < 30:
            return 40.0, detalle

        cierre = data["Close"].dropna()
        precio = float(cierre.iloc[-1])
        detalle["precio"] = round(precio, 2)

        # SMA 150 (40 pts)
        if len(cierre) >= SMA_VENTANA:
            sma150 = float(cierre.rolling(SMA_VENTANA).mean().dropna().iloc[-1])
            dist_pct = (precio - sma150) / sma150 * 100
            if dist_pct > 5:    detalle["sma_score"] = 40   # Bien por encima
            elif dist_pct > 0:  detalle["sma_score"] = 30   # Levemente encima
            elif dist_pct > -5: detalle["sma_score"] = 10   # Apenas debajo
            else:               detalle["sma_score"] = 0    # Bajo la SMA

        # RSI 14 (30 pts)
        delta = cierre.diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        rsi_s = 100 - (100 / (1 + rs))
        rsi   = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0
        detalle["rsi"] = round(rsi, 1)

        if RSI_COMPRA <= rsi <= 55:      detalle["rsi_score"] = 30  # Zona compra ideal
        elif 30 <= rsi < RSI_COMPRA:     detalle["rsi_score"] = 25  # Sobrevendido (rebote)
        elif 55 < rsi <= RSI_VENTA:      detalle["rsi_score"] = 15  # Zona neutral
        elif rsi > RSI_VENTA:            detalle["rsi_score"] = 5   # Sobrecomprado
        else:                            detalle["rsi_score"] = 10

        # Momentum 3M y 1M (30 pts: 20+10)
        if len(cierre) >= 60:
            mom3m = float((precio / cierre.iloc[-60]) - 1) * 100
            if mom3m > 15:    detalle["mom_score"] += 20
            elif mom3m > 5:   detalle["mom_score"] += 15
            elif mom3m > 0:   detalle["mom_score"] += 8
            elif mom3m > -5:  detalle["mom_score"] += 3
            else:             detalle["mom_score"] += 0

        if len(cierre) >= 20:
            mom1m = float((precio / cierre.iloc[-20]) - 1) * 100
            if mom1m > 5:     detalle["mom_score"] += 10
            elif mom1m > 0:   detalle["mom_score"] += 6
            elif mom1m > -3:  detalle["mom_score"] += 2
            else:             detalle["mom_score"] += 0

        total = detalle["sma_score"] + detalle["rsi_score"] + detalle["mom_score"]
        return round(min(100.0, float(total)), 1), detalle

    except Exception as e:
        _log.debug("score_tecnico %s: %s", ticker, e)
        return 40.0, detalle


def _score_tecnico_bono(ticker: str) -> tuple[float, dict]:
    """Score técnico para bonos: solo momentum de precio."""
    detalle = {"sma_score": 0, "rsi": 50, "rsi_score": 0, "mom_score": 0}
    try:
        # Bonos cotizan como ticker.BA en BYMA
        data = yf.Ticker(f"{ticker}.BA").history(period="6mo")
        if data.empty:
            return 45.0, detalle
        cierre = data["Close"].dropna()
        if len(cierre) >= 20:
            mom = (float(cierre.iloc[-1]) / float(cierre.iloc[-20]) - 1) * 100
            detalle["mom_score"] = min(40, max(0, int(mom * 2 + 20)))
        return float(detalle["mom_score"] + 40), detalle
    except Exception:
        return 45.0, detalle


# ─── 3. SCORE SECTOR/CONTEXTO (0-100) ────────────────────────────────────────

def score_sector_contexto(ticker: str, tipo: str = "CEDEAR") -> tuple[float, dict]:
    """
    Calcula score de sector y contexto 0-100.
    Combina:
      - Fuerza relativa del sector vs SPY (40 pts)
      - Ajuste por contexto macro EEUU (30 pts)
      - Ajuste por contexto Argentina (30 pts)
    """
    sector = SECTORES.get(ticker.upper(), "Otros")
    score_base = SCORE_SECTORIAL_BASE.get(sector, 5.0) * 10  # 0-100

    detalle = {
        "sector": sector,
        "score_base": score_base,
        "ajuste_macro_eeuu": 0,
        "ajuste_arg": 0,
    }

    # Ajuste EEUU (±15 pts)
    if CONTEXTO_MACRO["recesion_riesgo"] == "BAJO":
        detalle["ajuste_macro_eeuu"] = 10
    elif CONTEXTO_MACRO["recesion_riesgo"] == "ALTO":
        detalle["ajuste_macro_eeuu"] = -10

    if CONTEXTO_MACRO["fed_ciclo"] == "BAJA":
        # Beneficia: growth, bonos, inmuebles
        if sector in ("Tecnología", "E-Commerce", "Bono USD"):
            detalle["ajuste_macro_eeuu"] += 5
    elif CONTEXTO_MACRO["fed_ciclo"] == "SUBA":
        # Beneficia: financiero, defensivos
        if sector in ("Financiero", "Consumo Def."):
            detalle["ajuste_macro_eeuu"] += 5

    # Ajuste Argentina (±15 pts)
    if tipo in ("CEDEAR", "ETF"):
        # CEDEARs: ccl sube → cubre inflación
        if CONTEXTO_MACRO["ccl_tendencia"] == "SUBE":
            detalle["ajuste_arg"] = 10
        elif CONTEXTO_MACRO["ccl_tendencia"] == "ESTABLE":
            detalle["ajuste_arg"] = 5
    elif tipo in ("Acción Local", "Merval"):
        if CONTEXTO_MACRO["riesgo_pais"] == "BAJO":
            detalle["ajuste_arg"] = 15
        elif CONTEXTO_MACRO["riesgo_pais"] == "MEDIO":
            detalle["ajuste_arg"] = 5
        else:
            detalle["ajuste_arg"] = -5
    elif tipo in ("Bono USD",):
        if CONTEXTO_MACRO["riesgo_pais"] == "BAJO":
            detalle["ajuste_arg"] = 12
        elif CONTEXTO_MACRO["riesgo_pais"] == "MEDIO":
            detalle["ajuste_arg"] = 6

    total = score_base + detalle["ajuste_macro_eeuu"] + detalle["ajuste_arg"]
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


# ─── SCORE TOTAL 60/20/20 ─────────────────────────────────────────────────────

def calcular_score_total(ticker: str, tipo: str = "CEDEAR") -> dict:
    """
    Calcula el score final 60/20/20 para un activo.
    Retorna dict completo con todos los componentes.
    """
    _log.debug("Scoring %s (%s)", ticker, tipo)

    if tipo == "FCI":
        sf, df_fund = score_fci(ticker)
        st, df_tec  = 50.0, {"rsi": 50, "precio": 0, "sma_score": 0, "rsi_score": 0, "mom_score": 0}
        ss, df_sec  = score_sector_contexto(ticker, tipo)
        score_total = round(sf * PESO_FUNDAMENTAL + st * PESO_TECNICO + ss * PESO_SECTOR_CTX, 1)
        senal = "🟡 ACUMULAR" if score_total >= 60 else "⚪ MANTENER" if score_total >= 45 else "🟠 REDUCIR"
        return {
            "Ticker": ticker, "Tipo": tipo, "Sector": "FCI",
            "Score_Total": score_total, "Score_Fund": sf, "Score_Tec": st, "Score_Sector": ss,
            "RSI": 50, "Precio": 0, "Senal": senal,
            "Detalle_Fund": df_fund, "Detalle_Tec": df_tec, "Detalle_Sector": df_sec,
            "Fecha_Score": str(date.today()),
        }

    sf, df_fund = score_fundamental(ticker, tipo)
    st, df_tec  = _get_score_tecnico_cached(ticker, tipo)
    ss, df_sec  = score_sector_contexto(ticker, tipo)

    # MQ2-U7: penalización por baja liquidez (volumen promedio 30d)
    _vol_promedio = 0.0
    _penalizacion_liquidez = 0.0
    try:
        import yfinance as _yf_vol
        _hist_vol = _yf_vol.Ticker(ticker).history(period="35d")
        if not _hist_vol.empty and "Volume" in _hist_vol.columns:
            _vol_promedio = float(_hist_vol["Volume"].tail(30).mean())
            _umbral_vol = 50_000  # volumen mínimo configurable
            if _vol_promedio < _umbral_vol and _vol_promedio > 0:
                _penalizacion_liquidez = min(10.0, 10 * (1 - _vol_promedio / _umbral_vol))
    except Exception:
        pass

    score_total = round(
        sf * PESO_FUNDAMENTAL +
        st * PESO_TECNICO     +
        ss * PESO_SECTOR_CTX  -
        _penalizacion_liquidez,
        1
    )

    # Señal de acción
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
        "Volumen_Promedio_30d": _vol_promedio,       # MQ2-U7
        "Penalizacion_Liquidez": _penalizacion_liquidez,
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

    tickers_a_escanear = tickers_a_escanear[:max_activos]

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
    """F2: Calcula score técnico reutilizando la serie de precios del batch download."""
    detalle_tec = {"sma_score": 0, "rsi": 50, "rsi_score": 0, "mom_score": 0, "precio": 0}

    cierre = serie_precios.dropna()
    if len(cierre) < 30:
        st_score, dt = 40.0, detalle_tec
    else:
        precio = float(cierre.iloc[-1])
        detalle_tec["precio"] = round(precio, 2)

        # SMA 150
        if len(cierre) >= SMA_VENTANA:
            sma150 = float(cierre.rolling(SMA_VENTANA).mean().dropna().iloc[-1])
            dist_pct = (precio - sma150) / sma150 * 100
            if dist_pct > 5:    detalle_tec["sma_score"] = 40
            elif dist_pct > 0:  detalle_tec["sma_score"] = 30
            elif dist_pct > -5: detalle_tec["sma_score"] = 10
            else:               detalle_tec["sma_score"] = 0

        # RSI 14 EMA-Wilder
        delta = cierre.diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        rsi_s = 100 - (100 / (1 + rs))
        rsi   = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0
        detalle_tec["rsi"] = round(rsi, 1)

        if RSI_COMPRA <= rsi <= 55:    detalle_tec["rsi_score"] = 30
        elif 30 <= rsi < RSI_COMPRA:   detalle_tec["rsi_score"] = 25
        elif 55 < rsi <= RSI_VENTA:    detalle_tec["rsi_score"] = 15
        elif rsi > RSI_VENTA:          detalle_tec["rsi_score"] = 5
        else:                          detalle_tec["rsi_score"] = 10

        if len(cierre) >= 60:
            mom3m = float((precio / cierre.iloc[-60]) - 1) * 100
            detalle_tec["mom_score"] += 20 if mom3m > 15 else 15 if mom3m > 5 else 8 if mom3m > 0 else 3 if mom3m > -5 else 0
        if len(cierre) >= 20:
            mom1m = float((precio / cierre.iloc[-20]) - 1) * 100
            detalle_tec["mom_score"] += 10 if mom1m > 5 else 6 if mom1m > 0 else 2 if mom1m > -3 else 0

        st_score = round(min(100.0, float(
            detalle_tec["sma_score"] + detalle_tec["rsi_score"] + detalle_tec["mom_score"]
        )), 1)
        dt = detalle_tec

    sf, df_fund = score_fundamental(ticker, tipo)
    ss, df_sec  = score_sector_contexto(ticker, tipo)
    score_total = round(sf * PESO_FUNDAMENTAL + st_score * PESO_TECNICO + ss * PESO_SECTOR_CTX, 1)

    if score_total >= 75:    senal = "🟢 COMPRAR"
    elif score_total >= 60:  senal = "🟡 ACUMULAR"
    elif score_total >= 45:  senal = "⚪ MANTENER"
    elif score_total >= 30:  senal = "🟠 REDUCIR"
    else:                    senal = "🔴 SALIR"

    return {
        "Ticker": ticker, "Tipo": tipo, "Sector": df_sec.get("sector", SECTORES.get(ticker, "Otros")),
        "Score_Total": score_total, "Score_Fund": sf, "Score_Tec": st_score, "Score_Sector": ss,
        "RSI": dt.get("rsi", 50), "Precio": dt.get("precio", 0), "Senal": senal,
        "Detalle_Fund": df_fund, "Detalle_Tec": dt, "Detalle_Sector": df_sec,
        "Fecha_Score": str(date.today()),
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
