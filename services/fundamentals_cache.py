"""
services/fundamentals_cache.py — Capa 1 del pipeline de análisis.

Ingesta y caché de fundamentales con TTL 24h. Persiste en db_mercado.fundamentals_cache.

Pipeline:
    Capa 1 (este módulo) → Capa 2 (scoring_engine) → Capa 3 (bdi_auto_generator)

Datos cacheados por ticker (todo opcional, devuelve None si no disponible):
    Precio:       precio_actual_usd, precio_52w_low, precio_52w_high
    Valuación:    pe_ttm, pe_forward, pb_ratio, ps_ratio, peg_ratio
    Rentabilidad: roe, roa, profit_margin, operating_margin, gross_margin
    Solvencia:    debt_to_equity, current_ratio, quick_ratio
    Crecimiento:  earnings_growth, revenue_growth
    Dividendos:   dividend_yield, dividend_rate, payout_ratio
    Eventos:      next_earnings_date, ex_dividend_date
    Mercado:      market_cap, enterprise_value, beta, shares_outstanding
    Negocio:      sector, industry, country, currency, business_summary
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# TTL: 24 horas — fundamentales no cambian intradía.
_TTL_HORAS = 24
_LOCK = threading.Lock()
_MEM_CACHE: dict[str, FundamentalsSnapshot] = {}


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class FundamentalsSnapshot:
    """Snapshot de fundamentales de un ticker en un momento dado."""
    ticker: str
    fetched_at: str                         # ISO timestamp UTC
    source: str = "yfinance"
    # Precio
    precio_actual_usd: float | None = None
    precio_52w_low: float | None = None
    precio_52w_high: float | None = None
    # Valuación
    pe_ttm: float | None = None
    pe_forward: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    peg_ratio: float | None = None
    # Rentabilidad
    roe: float | None = None
    roa: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    gross_margin: float | None = None
    # Solvencia
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    # Crecimiento
    earnings_growth: float | None = None
    revenue_growth: float | None = None
    # Dividendos
    dividend_yield: float | None = None
    dividend_rate: float | None = None
    payout_ratio: float | None = None
    # Eventos
    next_earnings_date: str | None = None
    ex_dividend_date: str | None = None
    # Mercado
    market_cap: float | None = None
    enterprise_value: float | None = None
    beta: float | None = None
    shares_outstanding: float | None = None
    # Negocio
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str | None = None
    business_summary: str | None = None
    # Calidad de los datos
    calidad: str = "live"   # "live" | "cache" | "stale" | "missing"
    errores: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def edad_horas(self) -> float:
        try:
            t = dt.datetime.fromisoformat(self.fetched_at.replace("Z", "+00:00"))
            ahora = dt.datetime.now(dt.UTC)
            return (ahora - t).total_seconds() / 3600.0
        except Exception:
            return 999.0

    @property
    def expirado(self) -> bool:
        return self.edad_horas >= _TTL_HORAS


# ─── Persistencia en BD (db_mercado) ──────────────────────────────────────────

def _ensure_table() -> None:
    """Crea la tabla fundamentals_cache si no existe (idempotente)."""
    try:
        from sqlalchemy import text

        from core.db_domains import MERCADO
        with MERCADO.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS fundamentals_cache (
                    ticker        VARCHAR(20) PRIMARY KEY,
                    fetched_at    VARCHAR(40) NOT NULL,
                    payload_json  TEXT NOT NULL,
                    source        VARCHAR(40) DEFAULT 'yfinance'
                )
            """))
    except Exception as e:
        logger.warning("fundamentals_cache: no se pudo crear tabla: %s", e)


def _persistir(snapshot: FundamentalsSnapshot) -> None:
    try:
        _ensure_table()
        from sqlalchemy import text

        from core.db_domains import MERCADO
        with MERCADO.engine.begin() as conn:
            conn.execute(text("""
                INSERT OR REPLACE INTO fundamentals_cache
                (ticker, fetched_at, payload_json, source)
                VALUES (:ticker, :fetched_at, :payload, :source)
            """), {
                "ticker": snapshot.ticker.upper(),
                "fetched_at": snapshot.fetched_at,
                "payload": json.dumps(snapshot.to_dict(), ensure_ascii=False),
                "source": snapshot.source,
            })
    except Exception as e:
        logger.debug("fundamentals_cache: no se pudo persistir %s: %s", snapshot.ticker, e)


def _cargar_de_bd(ticker: str) -> FundamentalsSnapshot | None:
    try:
        _ensure_table()
        from sqlalchemy import text

        from core.db_domains import MERCADO
        with MERCADO.engine.connect() as conn:
            row = conn.execute(
                text("SELECT payload_json FROM fundamentals_cache WHERE ticker = :t"),
                {"t": ticker.upper()},
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        return FundamentalsSnapshot(**{k: v for k, v in payload.items()
                                       if k in FundamentalsSnapshot.__dataclass_fields__})
    except Exception as e:
        logger.debug("fundamentals_cache: error cargando %s desde BD: %s", ticker, e)
        return None


# ─── Fetch desde yfinance ─────────────────────────────────────────────────────

def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _safe_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("none", "nan", "n/a") else None


def _fetch_yfinance(ticker: str) -> FundamentalsSnapshot:
    """Descarga fundamentales reales de yfinance."""
    snap = FundamentalsSnapshot(
        ticker=ticker.upper(),
        fetched_at=dt.datetime.now(dt.UTC).isoformat(),
        source="yfinance",
    )
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = {}
        try:
            info = t.info or {}
        except Exception as e_info:
            snap.errores.append(f"info: {e_info}")

        # Precio actual via fast_info (más confiable)
        try:
            fi = t.fast_info
            snap.precio_actual_usd = _safe_float(getattr(fi, "last_price", None) or info.get("currentPrice"))
            snap.precio_52w_low = _safe_float(getattr(fi, "year_low", None) or info.get("fiftyTwoWeekLow"))
            snap.precio_52w_high = _safe_float(getattr(fi, "year_high", None) or info.get("fiftyTwoWeekHigh"))
            snap.market_cap = _safe_float(getattr(fi, "market_cap", None) or info.get("marketCap"))
            snap.shares_outstanding = _safe_float(getattr(fi, "shares", None) or info.get("sharesOutstanding"))
        except Exception as e_fi:
            snap.errores.append(f"fast_info: {e_fi}")

        # Valuación
        snap.pe_ttm        = _safe_float(info.get("trailingPE"))
        snap.pe_forward    = _safe_float(info.get("forwardPE"))
        snap.pb_ratio      = _safe_float(info.get("priceToBook"))
        snap.ps_ratio      = _safe_float(info.get("priceToSalesTrailing12Months"))
        snap.peg_ratio     = _safe_float(info.get("pegRatio") or info.get("trailingPegRatio"))

        # Rentabilidad (yfinance devuelve fracciones, ej. 0.114 = 11.4%)
        snap.roe              = _safe_float(info.get("returnOnEquity"))
        snap.roa              = _safe_float(info.get("returnOnAssets"))
        snap.profit_margin    = _safe_float(info.get("profitMargins"))
        snap.operating_margin = _safe_float(info.get("operatingMargins"))
        snap.gross_margin     = _safe_float(info.get("grossMargins"))

        # Solvencia
        snap.debt_to_equity = _safe_float(info.get("debtToEquity"))
        snap.current_ratio  = _safe_float(info.get("currentRatio"))

        # Crecimiento
        snap.earnings_growth = _safe_float(info.get("earningsQuarterlyGrowth") or info.get("earningsGrowth"))
        snap.revenue_growth  = _safe_float(info.get("revenueGrowth"))

        # Dividendos
        snap.dividend_yield = _safe_float(info.get("dividendYield"))
        snap.dividend_rate  = _safe_float(info.get("dividendRate"))
        snap.payout_ratio   = _safe_float(info.get("payoutRatio"))

        # Eventos
        try:
            cal = info.get("earningsDate") or info.get("nextEarningsDate")
            if cal:
                if isinstance(cal, (list, tuple)) and cal:
                    cal = cal[0]
                snap.next_earnings_date = str(cal)[:10]
        except Exception:
            pass
        ed = info.get("exDividendDate")
        if ed:
            try:
                snap.ex_dividend_date = dt.datetime.fromtimestamp(int(ed)).date().isoformat()
            except Exception:
                pass

        # Mercado
        snap.enterprise_value = _safe_float(info.get("enterpriseValue"))
        snap.beta             = _safe_float(info.get("beta"))

        # Negocio
        snap.sector             = _safe_str(info.get("sector"))
        snap.industry           = _safe_str(info.get("industry"))
        snap.country            = _safe_str(info.get("country"))
        snap.currency           = _safe_str(info.get("currency") or info.get("financialCurrency"))
        snap.business_summary   = _safe_str(info.get("longBusinessSummary"))

        snap.calidad = "live" if snap.precio_actual_usd else "missing"
    except ImportError:
        snap.errores.append("yfinance no instalado")
        snap.calidad = "missing"
    except Exception as e:
        snap.errores.append(f"general: {e}")
        snap.calidad = "missing"
        logger.warning("fundamentals_cache fetch %s: %s", ticker, e)

    return snap


# ─── API pública ──────────────────────────────────────────────────────────────

def obtener_fundamentales(
    ticker: str,
    *,
    force_refresh: bool = False,
    persist: bool = True,
) -> FundamentalsSnapshot:
    """
    Devuelve los fundamentales de un ticker con caché TTL 24h.

    Estrategia:
      1. Memoria (más rápido) si está fresca
      2. BD si está fresca
      3. yfinance live (descarga + persiste)
      4. BD stale si yfinance falla
    """
    t = ticker.upper().strip()
    if not t:
        return FundamentalsSnapshot(ticker="", fetched_at=dt.datetime.now(dt.UTC).isoformat(),
                                     calidad="missing")

    # 1) Memoria
    if not force_refresh:
        with _LOCK:
            mem = _MEM_CACHE.get(t)
            if mem and not mem.expirado:
                mem.calidad = "cache"
                return mem

    # 2) BD
    if not force_refresh:
        bd_snap = _cargar_de_bd(t)
        if bd_snap and not bd_snap.expirado:
            bd_snap.calidad = "cache"
            with _LOCK:
                _MEM_CACHE[t] = bd_snap
            return bd_snap

    # 3) yfinance live
    live_snap = _fetch_yfinance(t)
    if live_snap.calidad == "live":
        if persist:
            _persistir(live_snap)
        with _LOCK:
            _MEM_CACHE[t] = live_snap
        return live_snap

    # 4) Fallback: BD stale si live falló
    bd_stale = _cargar_de_bd(t)
    if bd_stale is not None:
        bd_stale.calidad = "stale"
        return bd_stale

    return live_snap   # calidad = missing


def precargar_fundamentales(tickers: list[str], force_refresh: bool = False) -> dict[str, FundamentalsSnapshot]:
    """
    Descarga fundamentales para múltiples tickers en background (un thread por ticker).
    Returns {ticker: snapshot} sincrónicamente (los hilos se joinean).
    """
    out: dict[str, FundamentalsSnapshot] = {}
    threads: list[threading.Thread] = []

    def _worker(t):
        out[t] = obtener_fundamentales(t, force_refresh=force_refresh)

    for tk in tickers:
        th = threading.Thread(target=_worker, args=(tk.upper(),), daemon=True)
        th.start()
        threads.append(th)
        # Throttle suave para evitar rate-limit de yfinance
        time.sleep(0.05)

    for th in threads:
        th.join(timeout=15)   # max 15s por ticker

    return out


def listar_tickers_cacheados() -> list[str]:
    """Tickers que tienen al menos una entrada en el caché BD."""
    try:
        _ensure_table()
        from sqlalchemy import text

        from core.db_domains import MERCADO
        with MERCADO.engine.connect() as conn:
            rows = conn.execute(text("SELECT ticker FROM fundamentals_cache ORDER BY ticker")).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def estadisticas_cache() -> dict[str, Any]:
    """Resumen del estado del caché (cuántos frescos, cuántos expirados)."""
    try:
        _ensure_table()
        from sqlalchemy import text

        from core.db_domains import MERCADO
        with MERCADO.engine.connect() as conn:
            rows = conn.execute(text("SELECT ticker, fetched_at FROM fundamentals_cache")).fetchall()
        n_total = len(rows)
        ahora = dt.datetime.now(dt.UTC)
        n_fresco = 0
        n_stale = 0
        for r in rows:
            try:
                t = dt.datetime.fromisoformat(str(r[1]).replace("Z", "+00:00"))
                edad = (ahora - t).total_seconds() / 3600.0
                if edad < _TTL_HORAS:
                    n_fresco += 1
                else:
                    n_stale += 1
            except Exception:
                n_stale += 1
        return {"total": n_total, "frescos": n_fresco, "stale": n_stale, "ttl_horas": _TTL_HORAS}
    except Exception as e:
        return {"total": 0, "frescos": 0, "stale": 0, "ttl_horas": _TTL_HORAS, "error": str(e)}
