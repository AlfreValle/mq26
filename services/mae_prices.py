"""
services/mae_prices.py — Precios de referencia de ONs desde MAE (Mercado Abierto Electrónico).

Estrategia de obtención en orden de prioridad:
  1. MAE REST API  (requiere MAE_API_KEY en env; devuelve 403 sin credenciales)
  2. Precio teórico NPV desde flujos de OBLIGACIONES_NEGOCIABLES + yield supuesto

API MAE:
  Endpoint: https://api.mae.com.ar/v1/on/precios-referencia
  Auth:     Bearer <MAE_API_KEY>
  Respuesta esperada:
    [{"ticker": "YMCQO", "precio": 94.5, "tir": 8.2, "fecha": "2026-05-21"}, ...]
  Nota: en ausencia de credenciales, el endpoint devuelve 403 Forbidden.
        Configurar MAE_API_KEY como variable de entorno para habilitar esta fuente.

Precio teórico fallback:
  PV = Σ (flujo_i / (1 + r_periodo)^i)   donde r_periodo = ytm_anual / frecuencia
  ytm_supuesto = risk_free_us + embi_arg + spread_credito
  spread_credito default: 2 % para ley NY, 3 % para ley local (diferencial jurídico).

Interfaz pública:
  fetch_on_prices(ccl, macro) → dict[str, OnPrice]

  OnPrice:
    ticker        : str
    paridad_pct   : float     — % sobre VN (100 = al par)
    precio_ars    : float     — ARS por 100 nominales USD
    fuente        : str       — "MAE" | "TEORICO"
    tir_estimada  : float     — yield % anual (solo fuente TEORICO)
    fecha         : str       — YYYY-MM-DD
"""
from __future__ import annotations

import logging
import os
import warnings
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

logger = logging.getLogger(__name__)

MAE_API_URL  = "https://api.mae.com.ar/v1/on/precios-referencia"
HTTP_TIMEOUT = 10

# Spread de crédito por defecto sobre soberano (embi + risk_free)
# para ONs sin precio de mercado conocido.
_SPREAD_LEY_NY    = 0.020   # 200 bps — ley extranjera (menor riesgo jurídico)
_SPREAD_LEY_LOCAL = 0.030   # 300 bps — ley local (más riesgo de subordinación)


@dataclass
class OnPrice:
    ticker:       str
    paridad_pct:  float   # % de par (100 = at par)
    precio_ars:   float   # ARS por 100 nominales USD
    fuente:       str     # "MAE" | "TEORICO"
    tir_estimada: float   # % anual (0 si viene de MAE sin TIR)
    fecha:        str     # YYYY-MM-DD


# ─── FUENTE 1: MAE API ────────────────────────────────────────────────────────

def _fetch_mae_api() -> dict[str, dict[str, Any]]:
    """
    Llama al endpoint REST de MAE con Bearer token desde MAE_API_KEY.
    Retorna {ticker: {paridad_pct, tir, fecha}} o {} si no hay credenciales / falla.
    """
    api_key = os.environ.get("MAE_API_KEY", "").strip()
    if not api_key:
        logger.debug("MAE_API_KEY no configurada — omitiendo fuente MAE API")
        return {}

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(
                MAE_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=HTTP_TIMEOUT,
                verify=False,
            )
        if resp.status_code == 403:
            logger.warning("MAE API: 403 Forbidden — credenciales inválidas o acceso no habilitado")
            return {}
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            rows = rows.get("data", [])

        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            ticker = str(r.get("ticker") or r.get("symbol") or "").upper().strip()
            precio = r.get("precio") or r.get("price")
            if not ticker or precio is None:
                continue
            try:
                out[ticker] = {
                    "paridad_pct": float(precio),
                    "tir":         float(r.get("tir") or r.get("yield") or 0),
                    "fecha":       str(r.get("fecha") or r.get("date") or date.today().isoformat()),
                }
            except (TypeError, ValueError):
                pass

        logger.info("MAE API: %d precios de ON obtenidos", len(out))
        return out

    except Exception as exc:
        logger.warning("MAE API: %s", exc)
        return {}


# ─── FUENTE 2: PRECIO TEÓRICO ─────────────────────────────────────────────────

def _ytm_supuesto(on_data: dict[str, Any], macro: dict[str, Any]) -> float:
    """
    Yield to maturity supuesto para el fallback teórico.
    ytm = risk_free_us + embi_arg + spread_credito_juridico
    """
    rf  = float(macro.get("risk_free_rate_us", 0.0435))
    embi_bps = float(macro.get("embi_arg_bps", 580))
    embi = embi_bps / 10_000

    ley = str(on_data.get("ley", "")).lower()
    spread = _SPREAD_LEY_NY if "york" in ley or "ny" in ley else _SPREAD_LEY_LOCAL

    return round(rf + embi + spread, 4)


def _precio_teorico_pct(on_data: dict[str, Any], ytm: float, fecha_liq: date) -> float | None:
    """
    Precio como % del VN por DCF sobre los flujos futuros de la ON.

    P = Σ_{i=1}^{n} flujo_i / (1 + ytm/freq)^i   × 100
    donde flujo_i es sobre base VN=1.

    Retorna None si no hay flujos futuros.
    """
    try:
        from core.renta_fija_ar import generar_vector_flujos  # noqa: PLC0415
    except ImportError:
        logger.warning("core.renta_fija_ar no disponible — fallback teórico omitido")
        return None

    flujos = generar_vector_flujos(on_data, fecha_liq)
    if not flujos:
        return None

    freq    = int(on_data.get("frecuencia_pago", 2))
    r_prd   = ytm / freq   # tasa por período

    pv = 0.0
    for i, f in enumerate(flujos, start=1):
        pv += f["monto"] / ((1.0 + r_prd) ** i)

    return round(pv * 100.0, 2)  # % del VN


def _fetch_teorico(ccl: float, macro: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Calcula precios teóricos para todas las ONs en OBLIGACIONES_NEGOCIABLES.
    Retorna {ticker: {paridad_pct, tir, fecha}}.
    """
    try:
        from config import OBLIGACIONES_NEGOCIABLES  # noqa: PLC0415
    except ImportError:
        logger.error("No se pudo importar OBLIGACIONES_NEGOCIABLES desde config")
        return {}

    hoy   = date.today()
    out: dict[str, dict[str, Any]] = {}

    for ticker, on_data in OBLIGACIONES_NEGOCIABLES.items():
        # Aviso si los cupones listados no cubren hasta el vencimiento real
        cupones = on_data.get("proximos_cupones_estimados", [])
        vto     = on_data.get("fecha_vencimiento", "")
        if cupones and vto and cupones[-1] < vto:
            logger.debug(
                "%s: cupones hasta %s pero vto=%s — precio teórico subestimado",
                ticker, cupones[-1], vto,
            )

        ytm   = _ytm_supuesto(on_data, macro)
        par   = _precio_teorico_pct(on_data, ytm, hoy)
        if par is None:
            continue
        # Guard: paridad < 10% con cupones incompletos → omitir (resultado sin sentido)
        if par < 10.0 and cupones and vto and cupones[-1] < vto:
            logger.warning(
                "%s: paridad teórica %.1f%% — cupones incompletos en config, ticker omitido",
                ticker, par,
            )
            continue
        out[ticker] = {
            "paridad_pct": par,
            "tir":         round(ytm * 100.0, 2),
            "fecha":       hoy.isoformat(),
        }

    logger.info("Precios teóricos calculados para %d ONs", len(out))
    return out


# ─── INTERFAZ PÚBLICA ─────────────────────────────────────────────────────────

def fetch_on_prices(
    ccl: float,
    macro: dict[str, Any] | None = None,
) -> dict[str, OnPrice]:
    """
    Obtiene precios de ONs desde MAE API (si hay key) o calcula el precio teórico.

    Parámetros
    ----------
    ccl   : tipo de cambio CCL (ARS/USD) para convertir paridad → precio ARS
    macro : dict MACRO_AR de config.py; si es None lo importa automáticamente

    Retorna
    -------
    dict[ticker, OnPrice] — vacío si ninguna fuente disponible.
    """
    if macro is None:
        try:
            from config import MACRO_AR  # noqa: PLC0415
            macro = MACRO_AR
        except ImportError:
            macro = {}

    # Intentar MAE API primero
    mae_raw = _fetch_mae_api()

    # Fallback teórico para tickers sin precio de MAE
    teorico_raw = _fetch_teorico(ccl, macro)

    # Combinar: MAE tiene prioridad sobre teórico
    result: dict[str, OnPrice] = {}
    hoy = date.today().isoformat()

    # Tickers base = todos en el catálogo teórico (OBLIGACIONES_NEGOCIABLES)
    all_tickers = set(teorico_raw.keys()) | set(mae_raw.keys())

    for ticker in all_tickers:
        if ticker in mae_raw:
            r      = mae_raw[ticker]
            fuente = "MAE"
        elif ticker in teorico_raw:
            r      = teorico_raw[ticker]
            fuente = "TEORICO"
        else:
            continue

        par = float(r["paridad_pct"])
        result[ticker] = OnPrice(
            ticker       = ticker,
            paridad_pct  = par,
            precio_ars   = round(par * ccl / 100.0, 1),  # ARS por 100 VN USD
            fuente       = fuente,
            tir_estimada = float(r.get("tir", 0)),
            fecha        = str(r.get("fecha", hoy)),
        )

    mae_count    = sum(1 for p in result.values() if p.fuente == "MAE")
    teorico_count = sum(1 for p in result.values() if p.fuente == "TEORICO")
    logger.info(
        "fetch_on_prices: %d total (%d MAE, %d teórico)",
        len(result), mae_count, teorico_count,
    )
    return result


def get_paridad_on(
    ticker: str,
    ccl: float,
    macro: dict[str, Any] | None = None,
) -> float | None:
    """
    Atajo: devuelve solo la paridad_pct de un ticker. None si no disponible.
    """
    prices = fetch_on_prices(ccl, macro)
    p = prices.get(ticker.upper())
    return p.paridad_pct if p else None
