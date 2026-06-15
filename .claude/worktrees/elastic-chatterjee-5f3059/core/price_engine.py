"""
core/price_engine.py — PriceEngine: fuente única de verdad para precios (Sprint 1)
MQ26-DSS | Sin dependencias de Streamlit ni de UI.

Jerarquía de resolución (idéntica a Bloomberg PORT):
    1. LIVE_YFINANCE  — precio en vivo desde yfinance (< 5 min de antigüedad)
    2. FALLBACK_BD    — último precio persistido en BD (precio_cache_service)
    3. FALLBACK_HARD  — precio manual hardcodeado en cartera_service.PRECIOS_FALLBACK_ARS
    4. MISSING        — sin precio disponible (nunca devuelve 0 implícito)

Invariante de conversión CEDEAR (inmutable):
    precio_cedear_ars  = subyacente_usd * ccl / ratio
    subyacente_usd     = precio_cedear_ars * ratio / ccl

Uso:
    engine = PriceEngine()
    records = engine.get_portfolio(["AAPL", "KO", "PAMP"], ccl=1465.0)
    cobertura = engine.cobertura_pct(records)  # % con precio válido
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field, replace as dc_replace
from datetime import datetime
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


# ─── Fuente de precio ──────────────────────────────────────────────────────────

class PriceSource(Enum):
    LIVE_YFINANCE = "live_yfinance"
    LIVE_BYMA = "live_byma"
    FALLBACK_BD   = "fallback_bd"
    FALLBACK_HARD = "fallback_hard"
    FALLBACK_PPC  = "fallback_ppc"  # último PPC de Maestra_Transaccional
    MISSING       = "missing"

    @property
    def label(self) -> str:
        return {
            "live_yfinance": "LIVE",
            "live_byma":     "LIVE-BYMA",
            "fallback_bd":   "FALLBACK-BD",
            "fallback_hard": "FALLBACK",
            "fallback_ppc":  "FALLBACK-PPC",
            "missing":       "SIN PRECIO",
        }[self.value]

    @property
    def is_live(self) -> bool:
        return self in (PriceSource.LIVE_YFINANCE, PriceSource.LIVE_BYMA)

    @property
    def is_valid(self) -> bool:
        return self != PriceSource.MISSING


# ─── Registro de precio ────────────────────────────────────────────────────────

@dataclass
class PriceRecord:
    """
    Registro atómico de precio con trazabilidad de fuente y timestamp.
    Todas las conversiones usan la invariante canónica CEDEAR.
    """
    ticker:               str
    precio_cedear_ars:    float        # precio de 1 CEDEAR en ARS
    precio_subyacente_usd: float       # precio del activo subyacente en USD
    ccl:                  float
    ratio:                float
    source:               PriceSource
    timestamp:            datetime
    stale:                bool = False  # True si > STALE_MINUTES antigüedad

    STALE_MINUTES: int = field(default=30, repr=False, compare=False)

    @property
    def calidad(self) -> str:
        if self.stale:
            return "STALE"
        return self.source.label

    @property
    def es_valido(self) -> bool:
        return self.source.is_valid and self.precio_cedear_ars > 0

    def to_dict(self) -> dict:
        return {
            "ticker":               self.ticker,
            "precio_cedear_ars":    self.precio_cedear_ars,
            "precio_subyacente_usd": self.precio_subyacente_usd,
            "ccl":                  self.ccl,
            "ratio":                self.ratio,
            "source":               self.source.label,
            "calidad":              self.calidad,
            "timestamp":            self.timestamp.isoformat(),
        }


def records_tras_rellenar_ppc(
    records: dict[str, PriceRecord],
    precios_antes_ppc: dict[str, float],
    precios_despues_ppc: dict[str, float],
    ccl: float,
) -> dict[str, PriceRecord]:
    """
    Marca como FALLBACK_PPC las posiciones que quedaron valoradas solo tras último PPC.
    """
    out = dict(records)
    for t_raw, px_after in (precios_despues_ppc or {}).items():
        tu = str(t_raw).upper().strip()
        if not tu:
            continue
        before = float(precios_antes_ppc.get(tu, 0) or 0)
        try:
            after = float(px_after or 0)
        except (TypeError, ValueError):
            continue
        if before > 0 or after <= 0:
            continue
        prev = out.get(tu)
        ratio = prev.ratio if prev is not None else 1.0
        px_usd = (after * ratio / ccl) if ccl > 0 and ratio > 0 else 0.0
        if prev is not None:
            out[tu] = dc_replace(
                prev,
                precio_cedear_ars=after,
                precio_subyacente_usd=px_usd,
                source=PriceSource.FALLBACK_PPC,
            )
        else:
            out[tu] = PriceRecord(
                ticker=tu,
                precio_cedear_ars=after,
                precio_subyacente_usd=px_usd,
                ccl=ccl,
                ratio=ratio,
                source=PriceSource.FALLBACK_PPC,
                timestamp=datetime.now(),
            )
    return out


# ─── PriceEngine ──────────────────────────────────────────────────────────────

class PriceEngine:
    """
    Motor de precios con jerarquía: live > fallback_bd > fallback_hard > missing.

    Reemplaza la lógica dispersa en:
        - cartera_service.resolver_precios()
        - cartera_service.PRECIOS_FALLBACK_ARS
        - pricing_utils (conversiones CEDEAR)

    Compatibilidad: devuelve dict[str, float] via .to_precios_ars()
    para integración con calcular_posicion_neta() existente sin romper nada.
    """

    # Fórmulas canónicas — documentadas como constantes para referencia
    _FORMULA_CEDEAR_ARS  = "subyacente_usd * ccl / ratio"
    _FORMULA_SUBYACENTE  = "precio_cedear_ars * ratio / ccl"

    # Mapa de tickers locales a sufijos yfinance
    _YF_MAP: dict[str, str] = {
        "BRKB":  "BRK-B",
        "YPFD":  "YPFD.BA",
        "CEPU":  "CEPU.BA",
        "TGNO4": "TGNO4.BA",
        "PAMP":  "PAMP.BA",
        "GGAL":  "GGAL.BA",
        "BMA":   "BMA.BA",
        "MIRG":  "MIRG.BA",
        "ALUA":  "ALUA.BA",
        "BYMA":  "BYMA.BA",
    }

    def __init__(self, universo_df=None) -> None:
        from config import RATIOS_CEDEAR
        from services.cartera_service import PRECIOS_FALLBACK_ARS

        from core.pricing_utils import obtener_ratio

        self._ratios: dict[str, float] = {k: float(v) for k, v in RATIOS_CEDEAR.items()}
        if universo_df is not None and not universo_df.empty and "Ticker" in universo_df.columns:
            for t_raw in universo_df["Ticker"].dropna().unique():
                t = str(t_raw).upper().strip()
                if not t:
                    continue
                r = obtener_ratio(t, universo_df)
                if r > 0:
                    self._ratios[t] = r
        self._fallback_hard: dict[str, float] = dict(PRECIOS_FALLBACK_ARS)
        self._fallback_bd: dict[str, float] = {}
        try:
            from core.db_manager import obtener_precios_fallback
            self._fallback_bd = {k.upper(): float(v) for k, v in (obtener_precios_fallback() or {}).items()}
        except Exception:
            self._fallback_bd = {}
        self._cache: dict[str, PriceRecord] = {}

    def _reload_fallback_bd(self) -> None:
        """Recarga precios persistidos en BD (útil cuando yfinance está degradado o tras edición admin)."""
        try:
            from core.db_manager import obtener_precios_fallback

            cargados = obtener_precios_fallback() or {}
            for k, v in cargados.items():
                self._fallback_bd[str(k).upper()] = float(v)
        except Exception:
            pass

    @staticmethod
    def _yfinance_habilitado() -> bool:
        try:
            from services.precio_cache_service import yfinance_disponible

            return bool(yfinance_disponible())
        except Exception:
            return True

    def _yf_symbol_candidates(self, ticker: str) -> list[str]:
        """Símbolos a probar en yfinance (BYMA suele usar sufijo .BA en renta fija)."""
        from core.pricing_utils import es_instrumento_local_ars

        t = ticker.upper().strip()
        base = self._YF_MAP.get(t, t)
        out: list[str] = []
        for x in (base, t):
            if x and x not in out:
                out.append(x)
        if es_instrumento_local_ars(t):
            ba = f"{t}.BA"
            if ba not in out:
                out.append(ba)
        return out

    # ── API pública ───────────────────────────────────────────────────────────

    def get(self, ticker: str, ccl: float) -> PriceRecord:
        """Resuelve un ticker con la jerarquía completa."""
        t = ticker.upper().strip()
        ratio = self._ratios.get(t, 1.0)

        # Fase C motores: si el circuit breaker bloqueó yfinance, recargar BD antes de resolver
        if not self._yfinance_habilitado():
            self._reload_fallback_bd()

        from core.data_providers import BYMA_FIRST

        chain: list = []
        if BYMA_FIRST:
            chain.append(self._try_byma)
        chain.extend([self._try_live, self._try_fallback_bd, self._try_fallback_hard])
        for source_fn in chain:
            rec = source_fn(t, ccl, ratio)
            if rec is not None:
                self._cache[t] = rec
                return rec

        # MISSING — nunca None, nunca lanza excepción
        return PriceRecord(
            ticker=t, precio_cedear_ars=0.0, precio_subyacente_usd=0.0,
            ccl=ccl, ratio=ratio, source=PriceSource.MISSING,
            timestamp=datetime.now(),
        )

    def get_portfolio(
        self,
        tickers: list[str],
        ccl: float,
        precios_live_override: dict[str, float] | None = None,
    ) -> dict[str, PriceRecord]:
        """
        Resuelve todos los tickers del portfolio.

        precios_live_override: dict {ticker: precio_ars} ya obtenido por el
        caller (ej. desde market_connector). Si se pasa, tiene prioridad
        sobre yfinance para esos tickers.
        """
        import time as _t
        _t0 = _t.monotonic()

        override = {k.upper(): v for k, v in (precios_live_override or {}).items()}
        result: dict[str, PriceRecord] = {}

        from core.data_providers import BYMA_FIRST
        from services.byma_provider import fetch_precios_ars_batch

        byma_batch: dict[str, float] = {}
        if BYMA_FIRST:
            try:
                byma_batch = fetch_precios_ars_batch([x.upper().strip() for x in tickers if x])
            except Exception:
                byma_batch = {}

        for ticker in tickers:
            t = ticker.upper().strip()
            ratio = self._ratios.get(t, 1.0)

            if t in override and override[t] > 0:
                px_ars = float(override[t])
                px_usd = (px_ars * ratio / ccl) if ccl > 0 else 0.0
                rec = PriceRecord(
                    ticker=t, precio_cedear_ars=px_ars,
                    precio_subyacente_usd=px_usd,
                    ccl=ccl, ratio=ratio,
                    source=PriceSource.LIVE_YFINANCE,
                    timestamp=datetime.now(),
                )
            elif t in byma_batch and float(byma_batch[t]) > 0:
                px_ars = float(byma_batch[t])
                px_usd = (px_ars * ratio / ccl) if ccl > 0 and ratio > 0 else 0.0
                rec = PriceRecord(
                    ticker=t, precio_cedear_ars=px_ars,
                    precio_subyacente_usd=px_usd,
                    ccl=ccl, ratio=ratio,
                    source=PriceSource.LIVE_BYMA,
                    timestamp=datetime.now(),
                )
            else:
                rec = self.get(t, ccl)

            result[t] = rec

        try:
            from services.metrics_service import incrementar, registrar_tiempo
            elapsed = _t.monotonic() - _t0
            registrar_tiempo("price_engine.get_portfolio", elapsed)
            n_missing = sum(1 for r in result.values() if not r.es_valido)
            if n_missing:
                incrementar("price_engine.missing_tickers", n_missing)
        except Exception:
            pass

        return result

    def cobertura_pct(self, records: dict[str, PriceRecord]) -> float:
        """% de tickers con precio válido (no MISSING y precio > 0)."""
        if not records:
            return 0.0
        validos = sum(1 for r in records.values() if r.es_valido)
        return round(validos / len(records) * 100, 1)

    def tickers_sin_precio(self, records: dict[str, PriceRecord]) -> list[str]:
        """Lista de tickers en estado MISSING."""
        return [t for t, r in records.items() if not r.es_valido]

    def to_precios_ars(self, records: dict[str, PriceRecord]) -> dict[str, float]:
        """
        Compatibilidad con calcular_posicion_neta() existente.
        Devuelve {ticker: precio_cedear_ars} — mismo contrato que resolver_precios().
        """
        return {t: r.precio_cedear_ars for t, r in records.items()}

    def refresh_fallback(self, nuevos_precios: dict[str, float] | None = None) -> int:
        """
        Recarga/actualiza _fallback_hard.

        - Sin argumento: recarga desde BD y retorna cantidad de precios cargados.
        - Con argumento: actualiza desde el dict en memoria y retorna su longitud.
        Invariante: nunca lanza excepción — retorna 0 si la BD no está disponible.
        """
        if nuevos_precios is not None:
            self._fallback_hard.update({k.upper(): float(v) for k, v in nuevos_precios.items()})
            return len(nuevos_precios)
        try:
            from core.db_manager import obtener_precios_fallback
            cargados = obtener_precios_fallback()
            self._fallback_bd.update({k.upper(): float(v) for k, v in (cargados or {}).items()})
            self._fallback_hard.update(cargados)
            return len(cargados)
        except Exception:
            return 0

    # ── Fuentes de precio (privadas) ──────────────────────────────────────────

    def _try_byma(self, ticker: str, ccl: float, ratio: float) -> PriceRecord | None:
        """Precio vía API BYMA / tercero (MQ26_BYMA_API_URL)."""
        from core.data_providers import BYMA_FIRST

        if not BYMA_FIRST:
            return None
        try:
            from services.byma_provider import fetch_precios_ars_batch

            px = fetch_precios_ars_batch([ticker]).get(ticker.upper().strip(), 0.0)
        except Exception:
            return None
        if px <= 0 or ccl <= 0:
            return None
        px_ars = float(px)
        px_usd = (px_ars * ratio / ccl) if ratio > 0 else 0.0
        return PriceRecord(
            ticker=ticker.upper().strip(),
            precio_cedear_ars=px_ars,
            precio_subyacente_usd=px_usd,
            ccl=ccl,
            ratio=ratio,
            source=PriceSource.LIVE_BYMA,
            timestamp=datetime.now(),
        )

    def _try_live(self, ticker: str, ccl: float, ratio: float) -> PriceRecord | None:
        """
        Intenta obtener precio desde yfinance.
        Retry: hasta 2 intentos con 0.3s de backoff entre ellos.
        Invariante: nunca lanza excepción — retorna None si ambos intentos fallan.
        """
        if not self._yfinance_habilitado():
            return None

        import time as _time
        from core.pricing_utils import es_instrumento_local_ars

        is_local = es_instrumento_local_ars(ticker)
        for attempt in range(2):
            try:
                import yfinance as yf

                px_usd = 0.0
                for yf_ticker in self._yf_symbol_candidates(ticker):
                    try:
                        info = yf.Ticker(yf_ticker).fast_info
                        px_usd = float(getattr(info, "last_price", 0) or 0)
                        if px_usd > 0:
                            break
                    except Exception:
                        continue

                if px_usd <= 0:
                    if attempt == 0:
                        _time.sleep(0.3)
                    continue

                # Bonos GD* (ley NY): Yahoo suele devolver USD por nominal; pasar a ARS con CCL.
                if is_local and ticker.startswith("GD") and px_usd < 500 and ccl > 0:
                    px_ars = px_usd * ccl
                elif is_local:
                    px_ars = px_usd  # panel local en ARS por unidad
                else:
                    px_ars = (px_usd * ccl / ratio) if ratio > 0 and ccl > 0 else 0.0

                if px_ars <= 0:
                    if attempt == 0:
                        _time.sleep(0.3)
                    continue

                return PriceRecord(
                    ticker=ticker, precio_cedear_ars=px_ars,
                    precio_subyacente_usd=px_usd,
                    ccl=ccl, ratio=ratio,
                    source=PriceSource.LIVE_YFINANCE,
                    timestamp=datetime.now(),
                )
            except Exception as e:
                if attempt == 0:
                    _time.sleep(0.3)
                else:
                    logger.debug("PriceEngine._try_live %s falló en intento %d: %s",
                                 ticker, attempt + 1, e)
        return None

    def _try_fallback_hard(self, ticker: str, ccl: float, ratio: float) -> PriceRecord | None:
        """Usa el fallback manual hardcodeado."""
        px_ars = self._fallback_hard.get(ticker, 0.0)
        if px_ars <= 0:
            return None
        px_usd = (px_ars * ratio / ccl) if ccl > 0 and ratio > 0 else 0.0
        return PriceRecord(
            ticker=ticker, precio_cedear_ars=px_ars,
            precio_subyacente_usd=px_usd,
            ccl=ccl, ratio=ratio,
            source=PriceSource.FALLBACK_HARD,
            timestamp=datetime.now(),
        )

    def _try_fallback_bd(self, ticker: str, ccl: float, ratio: float) -> PriceRecord | None:
        """Usa último precio persistido en BD (si existe)."""
        px_ars = float(self._fallback_bd.get(ticker, 0.0) or 0.0)
        if px_ars <= 0:
            return None
        px_usd = (px_ars * ratio / ccl) if ccl > 0 and ratio > 0 else 0.0
        return PriceRecord(
            ticker=ticker, precio_cedear_ars=px_ars,
            precio_subyacente_usd=px_usd,
            ccl=ccl, ratio=ratio,
            source=PriceSource.FALLBACK_BD,
            timestamp=datetime.now(),
        )

    # ── Conversiones estáticas (accesibles sin instanciar) ────────────────────

    @staticmethod
    def cedear_ars(subyacente_usd: float, ratio: float, ccl: float) -> float:
        """precio_cedear_ars = subyacente_usd * ccl / ratio"""
        if ratio <= 0 or ccl <= 0 or subyacente_usd <= 0:
            return 0.0
        return round(subyacente_usd * ccl / ratio, 2)

    @staticmethod
    def subyacente_usd(precio_cedear_ars: float, ratio: float, ccl: float) -> float:
        """subyacente_usd = precio_cedear_ars * ratio / ccl"""
        if ccl <= 0 or ratio <= 0 or precio_cedear_ars <= 0:
            return 0.0
        return round(precio_cedear_ars * ratio / ccl, 4)
