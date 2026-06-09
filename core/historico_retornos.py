"""
Motor automatizado de descarga y preprocesamiento de retornos históricos.

Responsabilidades
-----------------
1. Extraer los ``yf_ticker`` de los diccionarios de activos (CEDEAR_INFO,
   ACCIONES_ARGENTINAS, OBLIGACIONES_NEGOCIABLES, …) — cualquier dict con clave
   ``yf_ticker`` en el value es compatible.
2. Descarga en bloque via ``yfinance`` con gestión de errores y reintentos.
3. Unificación de calendarios operativos mundiales mediante Forward Fill.
4. Cálculo de retornos logarítmicos y filtro estricto de observaciones mínimas.
5. Integración con ``core/historical_cache.py`` (SHA-256 key) para evitar
   descargas redundantes dentro de la misma sesión.
6. Renombramiento de columnas: yf_ticker → ticker local BYMA.

Parámetros externos
--------------------
Todos los valores por defecto se toman de ``config.PARAMETROS_HISTORICO``.
Pasar ``parametros`` custom sólo para tests o experimentos.

Dependencias opcionales
------------------------
``core.returns_sanitize.winsorize_returns_panel`` — aplicado si
``winsorize=True`` (recomendado para períodos con alta inflación o crashes).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Lazy imports para no romper el import si no están instalados ──────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:  # pragma: no cover
    _YF_OK = False
    log.warning("yfinance no instalado — obtener_matriz_retornos_limpios retornará DataFrame vacío")

# ── Integraciones internas ────────────────────────────────────────────────────
try:
    from core.historical_cache import (
        historico_cache_get,
        historico_cache_key,
        historico_cache_set,
    )
    _CACHE_OK = True
except ImportError:
    _CACHE_OK = False
    log.debug("historical_cache no disponible — caché desactivado")

try:
    from core.returns_sanitize import winsorize_returns_panel
    _WINSORIZE_OK = True
except ImportError:
    _WINSORIZE_OK = False

# ── Defaults de seguridad si config no está disponible ───────────────────────
_DEFAULT_PARAMS: dict[str, Any] = {
    "ventana_dias":     252,
    "ventana_corta":     63,
    "min_obs_validos":  120,
    "frecuencia":       "1d",
    "benchmark_global": "^GSPC",
    "benchmark_local":  "^MERV",
    "fill_method":      "ffill",
}


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def obtener_matriz_retornos_limpios(
    diccionario_activos: dict[str, Any],
    parametros: dict[str, Any] | None = None,
    *,
    winsorize: bool = False,
    usar_cache: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Descarga el historial de los ``yf_ticker``, unifica los calendarios
    operativos mundiales y devuelve el DataFrame de retornos logarítmicos diarios.

    Parámetros
    ----------
    diccionario_activos : dict
        Cualquier dict con estructura ``ticker_local → {yf_ticker: str, ...}``.
        Compatible con CEDEAR_INFO, ACCIONES_ARGENTINAS, OBLIGACIONES_NEGOCIABLES.
    parametros : dict, opcional
        Overrides de ``PARAMETROS_HISTORICO``.  Claves parciales están permitidas.
    winsorize : bool
        Si True aplica winsorizado (p=0.5 % / 99.5 %) via returns_sanitize.
    usar_cache : bool
        Si True consulta / guarda en ``historical_cache`` (caché in-process).
    verbose : bool
        Imprime mensajes de progreso (útil en notebooks; desactivar en prod).

    Retorna
    -------
    pd.DataFrame
        Índice: fechas.  Columnas: tickers BYMA locales (renombrados desde yf_ticker).
        Retornos logarítmicos diarios ya filtrados y renombrados.
        DataFrame vacío si la descarga falla o no hay activos válidos.
    """
    if not _YF_OK:
        return pd.DataFrame()

    # ── 0. Consolidar parámetros ──────────────────────────────────────────────
    params = {**_DEFAULT_PARAMS}
    if parametros:
        params.update(parametros)

    ventana    = int(params["ventana_dias"])
    min_obs    = int(params["min_obs_validos"])
    frecuencia = str(params["frecuencia"])
    fill_meth  = str(params["fill_method"])

    # ── 1. Calcular fechas límites ────────────────────────────────────────────
    fecha_fin    = datetime.now()
    dias_corridos = int(ventana * 1.5)   # margen para garantizar ruedas hábiles
    fecha_inicio  = fecha_fin - timedelta(days=dias_corridos)

    # ── 2. Extraer tickers válidos de Yahoo Finance ───────────────────────────
    tickers_list: list[str] = []
    map_yf_a_local: dict[str, str] = {}

    for ticker_local, meta in diccionario_activos.items():
        if not isinstance(meta, dict):
            continue                   # RATIOS_CEDEAR es plano (float) — ignorar
        yf_tk = meta.get("yf_ticker")
        if yf_tk and isinstance(yf_tk, str):
            tickers_list.append(yf_tk)
            map_yf_a_local[yf_tk] = ticker_local

    if not tickers_list:
        log.warning("obtener_matriz_retornos_limpios: ningún yf_ticker encontrado en el diccionario.")
        return pd.DataFrame()

    if verbose:
        print(f"  Descargando {len(tickers_list)} activos desde Yahoo Finance...")

    # ── 3. Consultar caché in-process ─────────────────────────────────────────
    cache_key: str | None = None
    if usar_cache and _CACHE_OK:
        cache_key = historico_cache_key(
            tickers_list,
            period=f"{ventana}d",
            align_calendar_strict=False,
            relax_alignment_if_short=True,
            min_filas=min_obs,
        )
        cached = historico_cache_get(cache_key)
        if cached is not None and not cached.empty:
            if verbose:
                print(f"  ✓ Caché hit ({len(cached.columns)} activos, {len(cached)} filas)")
            return cached

    # ── 4. Descarga en bloque (batch) ─────────────────────────────────────────
    try:
        raw = yf.download(
            tickers=tickers_list,
            start=fecha_inicio.strftime("%Y-%m-%d"),
            end=fecha_fin.strftime("%Y-%m-%d"),
            interval=frecuencia,
            group_by="column",
            auto_adjust=True,
            progress=False,
        )
        # yfinance ≥ 0.2.x: multi-ticker → MultiIndex columns; single-ticker → plano
        if isinstance(raw.columns, pd.MultiIndex):
            precios_cierre = raw["Close"].copy()
        else:
            # Un solo ticker descargado
            precios_cierre = raw[["Close"]].rename(columns={"Close": tickers_list[0]})

    except Exception as exc:
        log.error("Error crítico en la descarga de yfinance: %s", exc, exc_info=True)
        if verbose:
            print(f"  ❌ Error crítico en la descarga de yfinance: {exc}")
        return pd.DataFrame()

    # ── 5. Unificar calendarios (Forward Fill) ────────────────────────────────
    # ffill() reemplaza fillna(method='ffill') deprecated en pandas ≥ 2.0
    if fill_meth == "ffill":
        precios_unificados = precios_cierre.ffill()
    elif fill_meth == "bfill":
        precios_unificados = precios_cierre.bfill()
    else:
        precios_unificados = precios_cierre

    # Recortar estrictamente a las últimas N ruedas hábiles configuradas
    precios_finales = precios_unificados.tail(ventana)

    # ── 6. Retornos logarítmicos (más estables que % para Markowitz) ──────────
    retornos_log = np.log(
        precios_finales / precios_finales.shift(1)
    ).dropna(how="all")

    # ── 7. Filtro estricto de observaciones mínimas ───────────────────────────
    # Evita matrices de Σ singulares por IPOs recientes o suspensiones largas
    columnas_validas: list[str] = []
    for col in retornos_log.columns:
        obs_reales = int(retornos_log[col].notna().sum())
        if obs_reales >= min_obs:
            columnas_validas.append(col)
        else:
            ticker_local = map_yf_a_local.get(str(col), str(col))
            msg = (
                f"⚠️  {ticker_local} ({col}) descartado — "
                f"solo {obs_reales} obs. válidas (mínimo: {min_obs})"
            )
            log.warning(msg)
            if verbose:
                print(f"  {msg}")

    retornos_filtrados = retornos_log[columnas_validas].copy()

    # ── 8. Winsorizado opcional (outliers por flash-crash o inflación) ─────────
    if winsorize and _WINSORIZE_OK:
        retornos_filtrados, reporte_w = winsorize_returns_panel(retornos_filtrados)
        if verbose and reporte_w["n_recortes_total"] > 0:
            print(f"  ✂  Winsorizado: {reporte_w['n_recortes_total']} observaciones recortadas")

    # ── 9. Renombrar yf_ticker → ticker BYMA local ────────────────────────────
    retornos_finales = retornos_filtrados.rename(columns=map_yf_a_local)

    if verbose:
        print(
            f"  ✓ Matriz lista: {len(retornos_finales.columns)} activos × "
            f"{len(retornos_finales)} ruedas"
        )

    # ── 10. Guardar en caché ───────────────────────────────────────────────────
    if usar_cache and _CACHE_OK and cache_key:
        historico_cache_set(cache_key, retornos_finales)

    return retornos_finales


# ─────────────────────────────────────────────────────────────────────────────
# Helpers para Markowitz
# ─────────────────────────────────────────────────────────────────────────────

def calcular_mu_sigma(
    df_retornos: pd.DataFrame,
    *,
    ruedas_anio: int = 252,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    Calcula el vector de retornos esperados (μ) y la matriz de covarianza (Σ),
    ambos anualizados.

    Parámetros
    ----------
    df_retornos : pd.DataFrame
        Salida de ``obtener_matriz_retornos_limpios``.
    ruedas_anio : int
        Factor de anualización (252 para acciones diarias).

    Retorna
    -------
    (mu, sigma) : tuple[pd.Series, pd.DataFrame]
        mu    — retorno esperado diario × ruedas_anio
        sigma — cov. diaria × ruedas_anio
    """
    if df_retornos.empty:
        return pd.Series(dtype=float), pd.DataFrame()

    mu    = df_retornos.mean() * ruedas_anio
    sigma = df_retornos.cov()  * ruedas_anio
    return mu, sigma


def calcular_betas_dinamicos(
    df_retornos: pd.DataFrame,
    benchmark_col: str,
    ventana_corta: int = 63,
) -> pd.Series:
    """
    Beta rodante de cada activo vs. ``benchmark_col`` usando los últimos
    ``ventana_corta`` días.  Devuelve el beta del último período disponible.

    Parámetros
    ----------
    df_retornos   : pd.DataFrame — retornos de todos los activos (incluido benchmark)
    benchmark_col : str          — columna del benchmark (ej. "^GSPC" o "^MERV")
    ventana_corta : int          — ruedas para OLS rodante

    Retorna
    -------
    pd.Series : beta por ticker (excluye el propio benchmark)
    """
    if benchmark_col not in df_retornos.columns:
        log.warning("calcular_betas_dinamicos: benchmark '%s' no encontrado.", benchmark_col)
        return pd.Series(dtype=float)

    ventana_tail = df_retornos.tail(ventana_corta)
    bm = ventana_tail[benchmark_col]
    var_bm = float(bm.var())

    if var_bm == 0.0:
        log.warning("calcular_betas_dinamicos: varianza del benchmark es 0.")
        return pd.Series(dtype=float)

    betas: dict[str, float] = {}
    for col in ventana_tail.columns:
        if col == benchmark_col:
            continue
        cov = float(ventana_tail[col].cov(bm))
        betas[col] = cov / var_bm

    return pd.Series(betas, name="beta_dinamico")
