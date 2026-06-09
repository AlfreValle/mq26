#!/usr/bin/env python3
"""
cron_update_adv_byma.py — Actualiza VOLUMEN_PROMEDIO_BYMA en config.py.

Fuentes:
  - CEDEARs (AAPL, MSFT, …)  : yfinance volumen 20 días del subyacente NYSE/NASDAQ
                                 convertido a millones ARS via CCL y ratio CEDEAR
  - Acciones locales y bonos  : BYMA Open Data API (requiere sesión autenticada)
                                 Si el POST falla con 401, esos tickers se omiten.

Actualización incremental (EMA):
  ADV_nuevo = (1 - ALPHA) * ADV_previo + ALPHA * vol_hoy
  ALPHA = 0.1  →  media ponderada ~20 dias (suavizado exponencial)

Uso:
  python scripts/cron_update_adv_byma.py
  python scripts/cron_update_adv_byma.py --dry-run
  python scripts/cron_update_adv_byma.py --alpha 0.2 --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH   = ROOT / "config.py"
BYMA_BASE_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"
BYMA_TIMEOUT  = 12

# CEDEAR ratios (ticker_local → ratio)
_CEDEAR_RATIO: dict[str, int] = {
    "AAPL": 20, "MSFT": 30, "GOOGL": 58, "AMZN": 144, "META": 24,
    "NVDA": 240, "VIST": 3, "KO": 5, "PEP": 18, "COST": 48,
    "V": 18, "CAT": 20, "LMT": 10, "GLD": 10, "SPY": 20,
    "QQQ": 20, "UNH": 33, "ABBV": 10, "CVX": 16, "VALE": 2,
    "MELI": 120, "BRKB": 30,
}
# Mapa ticker_local → ticker_yfinance (cuando difieren)
_YFINANCE_ALIAS: dict[str, str] = {
    "BRKB": "BRK-B",
}


def _byma_fetch(endpoint: str) -> list[dict[str, Any]]:
    """POST a BYMA Open Data. Retorna [] si falla (incluido 401)."""
    url  = f"{BYMA_BASE_URL}/{endpoint}"
    body = json.dumps({"excludeZeroPxAndQty": True, "T2": True, "T1": False, "T0": False})
    req  = Request(
        url, data=body.encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "MQ26Terminal/1.0"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=BYMA_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            data = raw if isinstance(raw, list) else raw.get("data", [])
            return data if isinstance(data, list) else []
    except HTTPError as exc:
        if exc.code == 401:
            logger.warning("BYMA %s: 401 Unauthorized — se omite (requiere sesion autenticada)", endpoint)
        else:
            logger.warning("BYMA %s: HTTPError %s", endpoint, exc.code)
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("BYMA %s: %s", endpoint, exc)
    return []


def _adv_cedears_yfinance(ccl: float) -> dict[str, float]:
    """
    Calcula ADV en millones ARS para CEDEARs usando el subyacente NYSE/NASDAQ.
    ADV_ARS = (media_vol_20d_usd / 1e6) * ccl / ratio

    vol_20d_usd = avg_daily_volume_shares * price_usd
    """
    out: dict[str, float] = {}
    try:
        import yfinance as yf  # noqa: PLC0415
    except ImportError:
        logger.warning("yfinance no instalado — CEDEARs omitidos")
        return out

    # Mapear ticker_local → ticker_yfinance
    local_to_yf = {t: _YFINANCE_ALIAS.get(t, t) for t in _CEDEAR_RATIO}
    tickers_us  = list(set(local_to_yf.values()))
    logger.info("Descargando volumen 20d yfinance para %d tickers US...", len(tickers_us))

    # Batch download
    try:
        hist = yf.download(
            tickers_us, period="1mo", progress=False, auto_adjust=True,
        )
        if hist.empty:
            return out

        for t_local, ratio in _CEDEAR_RATIO.items():
            t_yf = local_to_yf[t_local]
            try:
                closes = hist["Close"][t_yf].dropna()
                vols   = hist["Volume"][t_yf].dropna()
                common = closes.index.intersection(vols.index)[-20:]
                if len(common) < 5:
                    continue
                precio_usd = float(closes.loc[common].mean())
                vol_medio  = float(vols.loc[common].mean())
                # Cada CEDEAR representa 1/ratio de la acción US
                # ADV_ARS = vol_medio_shares × precio_USD × CCL / ratio / 1e6
                adv_ars = vol_medio * precio_usd * ccl / ratio / 1e6
                out[t_local] = round(adv_ars, 1)
                logger.debug("%s: vol=%d px=%.2f ratio=%d ADV=%.1fM ARS", t_local, int(vol_medio), precio_usd, ratio, adv_ars)
            except (KeyError, TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("yfinance batch download: %s", exc)

    return out


def _adv_byma_endpoint(endpoint: str, tipo_log: str) -> dict[str, float]:
    """ADV en millones ARS desde un endpoint BYMA. Usa effectiveVolume si disponible."""
    rows = _byma_fetch(endpoint)
    out: dict[str, float] = {}
    for r in rows:
        sym = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
        if not sym:
            continue
        # effectiveVolume = volumen en ARS, nominalVolume = en nominales
        vol = r.get("effectiveVolume") or r.get("volumeAmount") or r.get("volume")
        if vol:
            try:
                out[sym] = round(float(vol) / 1e6, 1)
            except (TypeError, ValueError):
                pass
    if out:
        logger.info("%s: %d tickers con volumen desde BYMA", tipo_log, len(out))
    return out


def fetch_adv_live(ccl: float) -> dict[str, float]:
    """Combina todas las fuentes de ADV. Retorna dict ticker → ADV en millones ARS."""
    volumes: dict[str, float] = {}

    # 1. CEDEARs desde yfinance (más confiable sin auth)
    volumes.update(_adv_cedears_yfinance(ccl))

    # 2. Acciones locales desde BYMA (puede fallar con 401)
    volumes.update(_adv_byma_endpoint("equities", "Acciones"))

    # 3. Bonos soberanos
    volumes.update(_adv_byma_endpoint("government-bonds", "Bonos Soberanos"))

    # 4. ONs corporativas
    volumes.update(_adv_byma_endpoint("corporate-bonds", "ONs"))

    logger.info("Total tickers con ADV fresco: %d", len(volumes))
    return volumes


# ─── PATCH DE config.py ───────────────────────────────────────────────────────

def _leer_adv_config() -> dict[str, float]:
    """Lee los valores actuales de VOLUMEN_PROMEDIO_BYMA desde config.py."""
    texto = CONFIG_PATH.read_text(encoding="utf-8")
    # Extrae el bloque dict
    m = re.search(r'VOLUMEN_PROMEDIO_BYMA\s*=\s*\{(.+?)\}', texto, re.DOTALL)
    if not m:
        return {}
    bloque = m.group(1)
    out: dict[str, float] = {}
    for linea in bloque.splitlines():
        linea = linea.strip()
        if linea.startswith('"') or linea.startswith("'"):
            parts = re.match(r'["\'](\w+)["\']\s*:\s*([0-9.]+)', linea)
            if parts:
                out[parts.group(1)] = float(parts.group(2))
    return out


def _patch_adv_config(nuevos: dict[str, float], alpha: float, dry_run: bool) -> bool:
    """
    Actualiza VOLUMEN_PROMEDIO_BYMA usando EMA:
      ADV_nuevo = (1-alpha) * ADV_previo + alpha * ADV_live
    Solo actualiza tickers dentro del bloque VOLUMEN_PROMEDIO_BYMA.
    Aísla el bloque antes de hacer reemplazos para evitar colisiones con otros dicts.
    """
    previos = _leer_adv_config()
    if not previos:
        logger.error("No se encontró VOLUMEN_PROMEDIO_BYMA en config.py")
        return False

    texto_full = CONFIG_PATH.read_text(encoding="utf-8")

    # Localizar el bloque VOLUMEN_PROMEDIO_BYMA para reemplazar SOLO ahí
    m_bloque = re.search(
        r'(VOLUMEN_PROMEDIO_BYMA\s*=\s*\{)(.+?)(\})',
        texto_full,
        re.DOTALL,
    )
    if not m_bloque:
        logger.error("Bloque VOLUMEN_PROMEDIO_BYMA no encontrado en config.py")
        return False

    bloque_inicio = m_bloque.start(2)
    bloque_fin    = m_bloque.end(2)
    bloque_orig   = texto_full[bloque_inicio:bloque_fin]
    bloque_nuevo  = bloque_orig
    cambios       = 0

    for ticker, vol_live in nuevos.items():
        if ticker not in previos:
            continue
        if vol_live <= 0:
            continue

        vol_prev = previos[ticker]
        # Guard: clampar vol_live a max 3× ADV previo para aislar señales de fuentes no BYMA.
        # El volumen US (yfinance) es órdenes de magnitud mayor al de BYMA → sin clamp
        # el EMA deriva hasta valores absurdos (billones de ARS).
        vol_live_clamped = min(vol_live, vol_prev * 3.0) if vol_prev > 0 else vol_live
        vol_new = round((1 - alpha) * vol_prev + alpha * vol_live_clamped, 1)

        if abs(vol_new - vol_prev) < 0.5:
            continue

        # Reemplaza solo dentro del bloque extraído
        patron = re.compile(
            r'("' + re.escape(ticker) + r'"\s*:)\s*[0-9.]+([,\s])',
            re.MULTILINE,
        )
        bloque_nuevo, n = patron.subn(
            lambda m, v=vol_new: f'{m.group(1)} {v}{m.group(2)}',
            bloque_nuevo,
        )
        if n:
            logger.debug("%s: %.1f -> %.1f (live=%.1f)", ticker, vol_prev, vol_new, vol_live)
            cambios += 1

    if cambios == 0:
        logger.info("Sin cambios significativos en ADV.")
        return False

    # Reensamblar el texto completo reemplazando solo el bloque interno
    texto_final = texto_full[:bloque_inicio] + bloque_nuevo + texto_full[bloque_fin:]

    logger.info("Actualizando %d tickers con alpha=%.2f", cambios, alpha)
    if dry_run:
        logger.info("[DRY-RUN] config.py NO fue modificado.")
        return True

    CONFIG_PATH.write_text(texto_final, encoding="utf-8")
    logger.info("config.py actualizado con nuevos ADV.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Actualiza VOLUMEN_PROMEDIO_BYMA en config.py")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--alpha",   type=float, default=0.1, help="Factor EMA (default 0.10 ~20d)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=== cron_update_adv_byma.py %s ===", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Leer CCL actual de config.py
    try:
        sys.path.insert(0, str(ROOT))
        from config import MACRO_AR  # noqa: PLC0415
        ccl = float(MACRO_AR.get("ccl_promedio", 1400.0))
    except Exception:
        ccl = 1400.0
    logger.info("CCL usado para conversion: %.1f", ccl)

    adv_live = fetch_adv_live(ccl)
    exito    = _patch_adv_config(adv_live, alpha=args.alpha, dry_run=args.dry_run)
    return 0 if exito else 1


if __name__ == "__main__":
    sys.exit(main())
