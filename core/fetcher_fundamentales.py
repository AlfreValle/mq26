"""
Fetcher dinámico de datos fundamentales via yfinance.

Responsabilidades
-----------------
1. Recorrer CEDEAR_INFO + ACCIONES_ARGENTINAS (dicts con yf_ticker).
2. Extraer de yf.Ticker(yf_ticker).info: P/E, P/B, ROE, D/P, DivYield, RevGrowth.
3. Normalizar formatos inconsistentes (YF reporta D/P en escala 0-200, no 0-2).
4. Fusionar con la semilla estática (DATOS_FUNDAMENTALES_EXTENDIDOS) para tickers
   sin cobertura en Yahoo Finance (acciones locales BYMA-only).
5. Guardar JSON en 0_Data_Maestra/fundamentales_cache.json con timestamp.
6. Proveer cargar_fundamentales_cache() para lectura rápida en runtime.

Flujo nocturno
--------------
    scripts/cron_update_fundamentales.py
        → descargar_fundamentales_universo()
        → guardar_cache_json()

Flujo en runtime del optimizador
---------------------------------
    obtener_fundamentales()          # punto de entrada unificado
        → cargar_fundamentales_cache()  si cache fresco
        → descargar_fundamentales_universo() si vencido o ausente
        → fusionar con seed estático para tickers sin datos YF

Nota sobre rate-limiting
------------------------
Yahoo Finance bloquea IPs con muchas requests simultáneas.
El fetcher usa pausa_seg=0.5 entre tickers + reintentos con backoff exponencial.
En producción Railway usar pausa_seg=1.0 para mayor seguridad.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Lazy import yfinance ──────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False
    log.warning("yfinance no instalado — fetcher_fundamentales no operativo")

# ── Campos requeridos en la salida ───────────────────────────────────────────
_CAMPOS_SALIDA = ("pe", "pb", "roe", "div_yield", "deuda_patrimonio", "rev_growth_yoy")


# ═════════════════════════════════════════════════════════════════════════════
#  EXTRACCIÓN SEGURA DE CAMPOS
# ═════════════════════════════════════════════════════════════════════════════

def extraer_dato_seguro(
    info_dict: dict[str, Any],
    primary_key: str,
    secondary_key: str | None = None,
    default: Any = None,
) -> Any:
    """
    Lectura tolerante a fallos del dict .info de yfinance.

    YF cambia los nombres de campos entre versiones — esta función prueba
    primary_key, luego secondary_key, y devuelve default si ambos fallan.
    Nunca lanza KeyError ni TypeError.
    """
    try:
        val = info_dict.get(primary_key)
        if val is None and secondary_key:
            val = info_dict.get(secondary_key)
        return val if val is not None else default
    except Exception:
        return default


def _parsear_info_ticker(
    ticker_local: str,
    yf_ticker: str,
    info: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Transforma el dict .info crudo de YF en la estructura del scoring.

    Normalización de D/P:
        YF reporta debtToEquity en escala 0-N × 100 (ej: deuda=2× patrimonio → 200.0).
        Dividimos por 100 para obtener el multiplicador bruto (2.0x).
        Bancos y holdings pueden tener None — queda como None (imputación por mediana en scoring).

    Retorna None si la respuesta de YF está vacía o incompleta.
    """
    if not info or len(info) < 5:
        log.warning("[%s / %s] Respuesta YF vacia o incompleta (%d campos)",
                    ticker_local, yf_ticker, len(info) if info else 0)
        return None

    # ── Value ────────────────────────────────────────────────────────────────
    pe = extraer_dato_seguro(info, "trailingPE", "forwardPE")
    pb = extraer_dato_seguro(info, "priceToBook")

    # ── Quality ──────────────────────────────────────────────────────────────
    roe = extraer_dato_seguro(info, "returnOnEquity")
    dp_raw = extraer_dato_seguro(info, "debtToEquity")      # YF: 0-200 escala
    if dp_raw is not None:
        try:
            dp = round(float(dp_raw) / 100.0, 4)           # → 0-2 multiplicador
        except (ValueError, TypeError):
            dp = None
    else:
        dp = None   # bancos / holdings — None = neutral en scoring

    # ── Growth + Income ───────────────────────────────────────────────────────
    div_yield  = extraer_dato_seguro(info, "dividendYield",   default=0.0)
    rev_growth = extraer_dato_seguro(info, "revenueGrowth",
                                    "quarterlyRevenueGrowth", default=0.0)

    def _safe_round(val: Any, decimales: int) -> float | None:
        """Convierte a float redondeado; retorna None si es inválido."""
        if val is None:
            return None
        try:
            return round(float(val), decimales)
        except (ValueError, TypeError):
            return None

    return {
        "pe":               _safe_round(pe, 2),
        "pb":               _safe_round(pb, 2),
        "roe":              _safe_round(roe, 4),
        "div_yield":        _safe_round(div_yield, 4) or 0.0,
        "deuda_patrimonio": dp,
        "rev_growth_yoy":   _safe_round(rev_growth, 4) or 0.0,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  DESCARGA CON REINTENTOS Y BACKOFF
# ═════════════════════════════════════════════════════════════════════════════

def _descargar_con_backoff(
    yf_ticker: str,
    max_reintentos: int = 3,
    pausa_base: float = 0.5,
) -> dict[str, Any] | None:
    """
    Descarga .info con reintentos exponenciales ante errores de red o 429.
    Retorna None si todos los intentos fallan.
    """
    for intento in range(1, max_reintentos + 1):
        try:
            info = yf.Ticker(yf_ticker).info
            return info
        except Exception as exc:
            espera = pausa_base * (2 ** (intento - 1))
            log.warning(
                "[%s] Intento %d/%d fallido (%s) — reintentando en %.1fs",
                yf_ticker, intento, max_reintentos, exc, espera,
            )
            if intento < max_reintentos:
                time.sleep(espera)

    log.error("[%s] Todos los reintentos fallaron.", yf_ticker)
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  DESCARGA DEL UNIVERSO COMPLETO
# ═════════════════════════════════════════════════════════════════════════════

def descargar_fundamentales_universo(
    universo_activos: dict[str, dict[str, Any]],
    *,
    pausa_seg: float = 0.5,
    max_reintentos: int = 3,
    verbose: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Recorre universo_activos (CEDEAR_INFO o ACCIONES_ARGENTINAS),
    descarga métricas fundamentales de YF y devuelve el dict normalizado.

    Parámetros
    ----------
    universo_activos : dict  ticker_local → {yf_ticker: str, ...}
                       Compatible con CEDEAR_INFO y ACCIONES_ARGENTINAS.
                       Ignora silenciosamente tickers sin yf_ticker (RATIOS_CEDEAR plano).
    pausa_seg        : segundos entre requests (default 0.5; usar 1.0 en Railway)
    max_reintentos   : intentos por ticker ante errores de red
    verbose          : imprime progreso en stdout

    Retorna
    -------
    dict  ticker_local → {pe, pb, roe, div_yield, deuda_patrimonio, rev_growth_yoy}
    Solo incluye tickers con respuesta válida de YF.
    """
    if not _YF_OK:
        log.error("yfinance no disponible — retornando dict vacío")
        return {}

    resultado: dict[str, dict[str, Any]] = {}
    total = len(universo_activos)
    sin_yf_ticker = 0
    errores       = 0

    if verbose:
        print(f"Iniciando captura de fundamentales para {total} activos...")

    for idx, (ticker_local, meta) in enumerate(universo_activos.items(), 1):
        # Sólo dicts con yf_ticker (ignora RATIOS_CEDEAR plano, etc.)
        if not isinstance(meta, dict):
            sin_yf_ticker += 1
            continue
        yf_ticker = meta.get("yf_ticker")
        if not yf_ticker:
            sin_yf_ticker += 1
            continue

        if verbose:
            print(f"  [{idx:3}/{total}] {ticker_local:8} ({yf_ticker})...", end=" ", flush=True)

        # Descarga con backoff
        info = _descargar_con_backoff(yf_ticker, max_reintentos, pausa_seg)
        if info is None:
            errores += 1
            if verbose:
                print("ERROR (sin datos)")
            continue

        # Parseo y normalización
        datos = _parsear_info_ticker(ticker_local, yf_ticker, info)
        if datos is None:
            errores += 1
            if verbose:
                print("SKIP (respuesta vacia)")
            continue

        resultado[ticker_local] = datos
        if verbose:
            pe_str = f"PE={datos['pe']}" if datos['pe'] else "PE=N/A"
            roe_str = f"ROE={datos['roe']:.2%}" if datos['roe'] else "ROE=N/A"
            print(f"OK  {pe_str}  {roe_str}")

        # Rate limiting preventivo
        time.sleep(pausa_seg)

    if verbose:
        print(f"\nCompleto: {len(resultado)} OK, {errores} errores, {sin_yf_ticker} sin yf_ticker")

    return resultado


# ═════════════════════════════════════════════════════════════════════════════
#  PERSISTENCIA JSON
# ═════════════════════════════════════════════════════════════════════════════

def guardar_cache_json(
    datos: dict[str, dict[str, Any]],
    path: str | None = None,
) -> str:
    """
    Guarda el dict de fundamentales en JSON con timestamp de auditoría.

    Parámetros
    ----------
    datos : salida de descargar_fundamentales_universo
    path  : ruta destino. Si None, usa FUNDAMENTALES_CACHE_PATH de config.

    Retorna
    -------
    str — ruta donde se guardó el archivo
    """
    if path is None:
        try:
            from config import FUNDAMENTALES_CACHE_PATH
            path = FUNDAMENTALES_CACHE_PATH
        except ImportError:
            path = str(Path(__file__).parent.parent / "0_Data_Maestra" / "fundamentales_cache.json")

    payload = {
        "metadata": {
            "generado_en": datetime.now(timezone.utc).isoformat(),
            "n_tickers":   len(datos),
            "fuente":      "yfinance",
        },
        "datos": datos,
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    log.info("Cache fundamental guardado: %s (%d tickers)", path, len(datos))
    return path


def cargar_fundamentales_cache(
    path: str | None = None,
    *,
    max_edad_horas: float | None = None,
) -> dict[str, dict[str, Any]] | None:
    """
    Lee el JSON de cache de fundamentales.

    Parámetros
    ----------
    path           : ruta al JSON. Si None, usa FUNDAMENTALES_CACHE_PATH.
    max_edad_horas : si el archivo tiene más antigüedad, retorna None (forzar re-descarga).
                     Si None, usa FUNDAMENTALES_CACHE_MAX_EDAD_H de config.

    Retorna
    -------
    dict de fundamentales, o None si el archivo no existe / está vencido.
    """
    if path is None:
        try:
            from config import FUNDAMENTALES_CACHE_PATH
            path = FUNDAMENTALES_CACHE_PATH
        except ImportError:
            path = str(Path(__file__).parent.parent / "0_Data_Maestra" / "fundamentales_cache.json")

    if max_edad_horas is None:
        try:
            from config import FUNDAMENTALES_CACHE_MAX_EDAD_H
            max_edad_horas = float(FUNDAMENTALES_CACHE_MAX_EDAD_H)
        except ImportError:
            max_edad_horas = 26.0

    p = Path(path)
    if not p.exists():
        log.info("Cache fundamental no encontrado en %s", path)
        return None

    # Verificar antigüedad del archivo
    edad_horas = (time.time() - p.stat().st_mtime) / 3600.0
    if edad_horas > max_edad_horas:
        log.info(
            "Cache fundamental vencido (%.1f h > max %.1f h) — se descargará de YF",
            edad_horas, max_edad_horas,
        )
        return None

    try:
        with open(p, encoding="utf-8") as f:
            payload = json.load(f)
        datos = payload.get("datos", payload)   # compatibilidad con formato sin metadata
        log.info(
            "Cache fundamental cargado: %d tickers (%.1f h de antiguedad)",
            len(datos), edad_horas,
        )
        return datos
    except (json.JSONDecodeError, KeyError) as exc:
        log.warning("Cache fundamental corrupto (%s) — re-descarga necesaria", exc)
        return None


# ═════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA UNIFICADO
# ═════════════════════════════════════════════════════════════════════════════

def obtener_fundamentales(
    universo_activos: dict[str, dict[str, Any]] | None = None,
    *,
    forzar_descarga: bool = False,
    pausa_seg: float = 0.5,
    verbose: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Punto de entrada único para el optimizador y el scoring.

    Prioridad:
    1. Cache JSON fresco (< FUNDAMENTALES_CACHE_MAX_EDAD_H horas) → rápido, sin red
    2. Descarga de yfinance → guarda en cache automáticamente
    3. Fusión con semilla estática → cubre tickers sin respuesta YF (locales BYMA-only)

    Parámetros
    ----------
    universo_activos : dict compatible con CEDEAR_INFO / ACCIONES_ARGENTINAS.
                       Si None, los importa directamente de config.
    forzar_descarga  : si True, ignora el cache y descarga aunque sea fresco.
    pausa_seg        : rate limiting entre requests YF.
    verbose          : imprime progreso.

    Retorna
    -------
    dict  ticker_local → {pe, pb, roe, div_yield, deuda_patrimonio, rev_growth_yoy}
    """
    # ── 1. Intentar cache ─────────────────────────────────────────────────────
    if not forzar_descarga:
        cached = cargar_fundamentales_cache()
        if cached:
            if verbose:
                print(f"  Fundamentales: usando cache ({len(cached)} tickers)")
            return _fusionar_con_seed(cached)

    # ── 2. Construir universo si no se pasa ───────────────────────────────────
    if universo_activos is None:
        try:
            from config import CEDEAR_INFO, ACCIONES_ARGENTINAS
            universo_activos = {**CEDEAR_INFO, **ACCIONES_ARGENTINAS}
        except ImportError:
            log.error("No se pudo importar CEDEAR_INFO / ACCIONES_ARGENTINAS de config")
            return _fusionar_con_seed({})

    # ── 3. Descargar de YF ────────────────────────────────────────────────────
    datos_yf = descargar_fundamentales_universo(
        universo_activos, pausa_seg=pausa_seg, verbose=verbose
    )

    # ── 4. Guardar cache actualizado ──────────────────────────────────────────
    if datos_yf:
        guardar_cache_json(datos_yf)

    return _fusionar_con_seed(datos_yf)


def _fusionar_con_seed(
    datos_yf: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Completa datos_yf con la semilla estática para tickers ausentes.
    La descarga en vivo tiene prioridad sobre la semilla.
    """
    try:
        from config import DATOS_FUNDAMENTALES_EXTENDIDOS as seed
    except ImportError:
        return datos_yf

    fusionado = dict(seed)          # base: semilla estática (25 tickers)
    fusionado.update(datos_yf)      # sobreescribe con datos frescos de YF (prioridad)
    log.debug(
        "Fundamentales fusionados: %d de YF + %d de seed -> %d totales",
        len(datos_yf), len(seed), len(fusionado),
    )
    return fusionado
