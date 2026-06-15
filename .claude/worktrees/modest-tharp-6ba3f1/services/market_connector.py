"""
market_connector.py — Conector de Mercado Unificado
MQ26 + DSS | MEP real via GGAL, reintentos con backoff, fallback integrado.
"""
import sys
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CCL_FALLBACK as _CCL_FALLBACK_CFG
from core.logging_config import get_logger

_CCL_FALLBACK = _CCL_FALLBACK_CFG  # alias interno usado en obtener_ccl_mep

logger = get_logger(__name__)

try:
    import requests_cache
    _session = requests_cache.CachedSession(
        "yfinance_cache", expire_after=timedelta(hours=24)
    )
except ImportError:
    _session = None

# ─── CONFIGURACIÓN DE RESILIENCIA ─────────────────────────────────────────────
_MAX_REINTENTOS  = 3
_PAUSA_BASE_SEG  = 1.5   # backoff exponencial: 1.5s, 3s, 6s
_TIMEOUT_TICKER  = 10    # timeout yfinance por ticker (segundos)

# ── Circuit breaker (D7): tickers que fallaron en esta sesión no se reintenta ──
_circuit_breaker: set = set()

# ── Cache de fundamentales en memoria por sesión (F2) ──
import datetime as _dt

_fundamentales_cache: dict = {}
_FUNDAMENTALES_CACHE_TTL_DIAS = 1


def _fetch_con_reintento(fn, *args, etiqueta: str = "", **kwargs):
    """
    Llama a fn(*args, **kwargs) con reintentos exponenciales.
    Circuit breaker (D7): si el ticker ya falló en esta sesión, retorna None inmediatamente.
    """
    # Extraer nombre del ticker del etiqueta para circuit breaker
    ticker_key = etiqueta.split("/")[-1] if "/" in etiqueta else etiqueta
    if ticker_key and ticker_key in _circuit_breaker:
        return None

    for intento in range(1, _MAX_REINTENTOS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            espera = _PAUSA_BASE_SEG * (2 ** (intento - 1))
            logger.warning(
                "market_connector [%s]: intento %d/%d fallido (%s). Reintentando en %.1fs...",
                etiqueta, intento, _MAX_REINTENTOS, exc, espera,
            )
            if intento < _MAX_REINTENTOS:
                time.sleep(espera)

    logger.error("market_connector [%s]: todos los reintentos agotados.", etiqueta)
    if ticker_key:
        _circuit_breaker.add(ticker_key)
    return None


# ─── CCL/MEP ──────────────────────────────────────────────────────────────────
def obtener_ccl_mep() -> float:
    """
    CCL/MEP via GGAL.BA / GGAL × 10 con reintentos.
    Fallback: _CCL_FALLBACK si yfinance no responde.
    """
    def _fetch():
        ba  = yf.Ticker("GGAL.BA").history(period="2d")["Close"].dropna()
        adr = yf.Ticker("GGAL").history(period="2d")["Close"].dropna()
        if ba.empty or adr.empty:
            raise ValueError("Sin datos GGAL")
        return round((float(ba.iloc[-1]) / float(adr.iloc[-1])) * 10, 2)

    resultado = _fetch_con_reintento(_fetch, etiqueta="CCL/MEP")
    if resultado is None:
        logger.info("CCL: usando fallback %.2f", _CCL_FALLBACK)
        return _CCL_FALLBACK
    return resultado


def obtener_tipo_cambio_mep() -> float:
    """Alias para compatibilidad con código DSS existente."""
    return obtener_ccl_mep()


# ─── DESCARGA DE PRECIOS ──────────────────────────────────────────────────────
def descargar_precios(tickers, periodo: str = "1y") -> pd.DataFrame:
    """Descarga precios de cierre para múltiples tickers con reintentos."""
    if not tickers:
        return pd.DataFrame()
    if isinstance(tickers, str):
        tickers = [tickers]
    tickers = list(tickers)

    def _fetch():
        kwargs = {"period": periodo, "progress": False, "auto_adjust": True}
        if _session:
            kwargs["session"] = _session
        datos = yf.download(tickers, **kwargs)
        close = datos["Close"] if "Close" in datos else datos
        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])
        return close.ffill().bfill().dropna(how="all")

    resultado = _fetch_con_reintento(_fetch, etiqueta=f"precios/{','.join(tickers[:3])}")
    if resultado is None:
        return pd.DataFrame()
    return resultado


def descargar_ohlcv(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """OHLCV completo para gráficos de velas con reintentos."""
    def _fetch():
        return yf.download(ticker, period=period, interval=interval,
                           auto_adjust=False, progress=False)

    resultado = _fetch_con_reintento(_fetch, etiqueta=f"OHLCV/{ticker}")
    if resultado is None:
        return pd.DataFrame()
    return resultado


# ─── PRECIOS EN ARS ───────────────────────────────────────────────────────────
def precios_en_ars(precios_usd: pd.DataFrame, ccl: float | None = None) -> pd.DataFrame:
    if ccl is None:
        ccl = obtener_ccl_mep()
    return precios_usd * ccl


# ─── RATIOS FUNDAMENTALES con cache (F2) ──────────────────────────────────────
def obtener_ratios_fundamentales(tickers: list[str]) -> pd.DataFrame:
    """
    P/E, P/E Forward, Price/Book, ROE, Margen Operativo, Dividend Yield.
    Cache en memoria por día hábil — reduce de ~30s a <1s en renders sucesivos.
    Circuit breaker: tickers que fallaron previamente se omiten.
    """
    hoy = str(_dt.date.today())
    rows = []
    for ticker in tickers:
        # Circuit breaker: omitir tickers que fallaron en esta sesión
        if ticker in _circuit_breaker:
            rows.append({"Ticker": ticker, "Sector": "Circuit breaker"})
            continue
        # Cache hit
        cached = _fundamentales_cache.get(ticker)
        if cached and cached.get("fecha") == hoy:
            rows.append(cached["data"])
            continue
        # Cache miss: descargar
        def _fetch(t=ticker):
            return yf.Ticker(t).info

        info = _fetch_con_reintento(_fetch, etiqueta=f"fundamentales/{ticker}")
        if info:
            row = {
                "Ticker":           ticker,
                "Sector":           info.get("sector", "N/D"),
                "P/E Trailing":     info.get("trailingPE"),
                "P/E Forward":      info.get("forwardPE"),
                "Price/Book":       info.get("priceToBook"),
                "ROE":              info.get("returnOnEquity"),
                "Margen Operativo": info.get("operatingMargins"),
                "Dividend Yield %": (info.get("dividendYield") or 0) * 100,
                "Market Cap B":     (info.get("marketCap") or 0) / 1e9,
            }
            _fundamentales_cache[ticker] = {"fecha": hoy, "data": row}
            rows.append(row)
        else:
            _circuit_breaker.add(ticker)
            rows.append({"Ticker": ticker, "Sector": "ERROR"})
    return pd.DataFrame(rows)


# ─── PRECIOS CARTERA EN TIEMPO REAL ──────────────────────────────────────────
def precios_actuales_cartera(
    tickers: list[str],
    ratios: dict[str, float],
    ccl: float | None = None,
) -> dict[str, dict]:
    """
    Para cada ticker devuelve: precio_usd, precio_ars, precio_teorico, ratio, ccl.
    Prioriza precio BYMA real; si no, usa precio teórico via CCL.
    """
    if ccl is None:
        ccl = obtener_ccl_mep()

    resultado = {}
    traducciones = {"BRKB": "BRK-B", "YPFD": "YPF", "PAMP": "PAM"}

    for ticker in tickers:
        ratio     = ratios.get(ticker, 1.0)
        ticker_yf = traducciones.get(ticker, ticker)

        precio_usd = 0.0
        def _fetch_usd(t=ticker_yf):
            data = yf.Ticker(t).history(period="2d")["Close"].dropna()
            return float(data.iloc[-1]) if not data.empty else 0.0

        val_usd = _fetch_con_reintento(_fetch_usd, etiqueta=f"USD/{ticker}")
        if val_usd is not None and val_usd > 0:
            precio_usd = val_usd

        precio_ars_teorico = (precio_usd * ccl) / ratio if ratio > 0 else 0.0
        precio_ars = precio_ars_teorico

        def _fetch_ba(t=ticker):
            data = yf.Ticker(f"{t}.BA").history(period="2d")["Close"].dropna()
            return float(data.iloc[-1]) if not data.empty else 0.0

        val_ba = _fetch_con_reintento(_fetch_ba, etiqueta=f"BA/{ticker}")
        if val_ba and val_ba > 0 and precio_ars_teorico > 0:
            if 0.7 * precio_ars_teorico <= val_ba <= 1.3 * precio_ars_teorico:
                precio_ars = val_ba

        resultado[ticker] = {
            "precio_usd":     round(precio_usd, 4),
            "precio_ars":     round(precio_ars, 2),
            "precio_teorico": round(precio_ars_teorico, 2),
            "ratio":          ratio,
            "ccl":            ccl,
        }

    return resultado
