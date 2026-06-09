"""
Filtros y restricciones de cartera por perfil del inversor.

Funciones
---------
aplicar_filtros_perfil_y_etf(ticker, datos_perfil)
    Determina elegibilidad de un activo según restricciones éticas y de tipo.
    Usa EXCLUSIONES_ETICAS (dict ticker→tickers) y ETF_INFO para cripto.

ajustar_restriccion_liquidez_por_cliente(weights, tickers, datos_perfil)
    Valida que la porción líquida del portafolio cubra la necesidad del cliente.
    Umbral configurable via ADV_LIQUIDEZ_MINIMA de config.

filtrar_universo_por_perfil(universo, datos_perfil)
    Filtra en bloque un universo de tickers devolviendo sólo los elegibles.

ajustar_mu_por_ter(mu_series, etf_info)
    Deduce el TER anual del retorno esperado (μ) de cada ETF.
    Implementa: μ_neto = μ_bruto - TER

restriccion_duration_horizonte(tickers_rf, metricas_riesgo, datos_perfil)
    Verifica que la duration promedio de las ONs no supere el horizonte
    de inversión del cliente (en años).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


# ── Imports lazy ─────────────────────────────────────────────────────────────
def _cfg() -> Any:
    import config
    return config


# ═════════════════════════════════════════════════════════════════════════════
#  ELEGIBILIDAD POR ACTIVO
# ═════════════════════════════════════════════════════════════════════════════

def aplicar_filtros_perfil_y_etf(
    ticker: str,
    datos_perfil: dict[str, Any],
) -> tuple[bool, str]:
    """
    Determina si un activo es elegible para la cartera del cliente.

    Parámetros
    ----------
    ticker       : ticker BYMA local (ej. "IBIT", "MO", "AAPL")
    datos_perfil : dict de PERFIL_INVERSOR_CODIFICADO (un cliente)

    Retorna
    -------
    (elegible, razon)
        elegible : True si el activo pasa todos los filtros
        razon    : descripción del rechazo (vacío si elegible)
    """
    cfg = _cfg()
    etf_info      = getattr(cfg, "ETF_INFO",         {})
    excl_eticas   = getattr(cfg, "EXCLUSIONES_ETICAS", {})
    sectores       = getattr(cfg, "SECTORES",          {})

    excluir_cripto  = bool(datos_perfil.get("excluir_criptoassets", False))
    restr_eticas    = list(datos_perfil.get("restricciones_eticas", []))

    # ── 1. ETF: tipo alternativo / apalancado ──────────────────────────────────
    if ticker in etf_info:
        tipo_etf = etf_info[ticker].get("tipo", "")

        if tipo_etf == "alternativo" and excluir_cripto:
            razon = f"{ticker} excluido: cliente no admite criptoactivos (tipo=alternativo)"
            log.info(razon)
            return False, razon

        if tipo_etf == "apalancado":
            # ETFs apalancados sólo para perfiles Agresivo / Muy Agresivo
            perfil_rv_max = datos_perfil.get("max_renta_variable",
                            datos_perfil.get("objetivo_retorno_usd_anual", 0))
            # Si el objetivo de retorno < 10 % lo consideramos perfil conservador/moderado
            if float(datos_perfil.get("objetivo_retorno_usd_anual", 0)) < 0.10:
                razon = f"{ticker} excluido: ETF apalancado no apto para perfil conservador/moderado"
                log.info(razon)
                return False, razon

    # ── 2. Restricciones éticas — resolución a tickers concretos ──────────────
    # Construir set de tickers prohibidos para este cliente
    tickers_prohibidos: set[str] = set()
    for categoria in restr_eticas:
        prohibidos_cat = excl_eticas.get(categoria, [])
        tickers_prohibidos.update(prohibidos_cat)
        # También excluir via SECTORES (nombres de sector como "Defensa")
        # EXCLUSIONES_ETICAS["Armamento"] puede incluir tickers; SECTORES da el sector
        # Complemento: si la categoria coincide con un valor de SECTORES, excluir todos
        for t, sector in sectores.items():
            if sector.lower() == categoria.lower():
                tickers_prohibidos.add(t)

    if ticker in tickers_prohibidos:
        razon = (
            f"{ticker} excluido: restriccion etica del cliente "
            f"({', '.join(restr_eticas)})"
        )
        log.info(razon)
        return False, razon

    # ── 3. Criptoassets via EXCLUSIONES_ETICAS directa ────────────────────────
    if excluir_cripto:
        cripto_tickers = set(excl_eticas.get("Criptoassets", []))
        if ticker in cripto_tickers:
            razon = f"{ticker} excluido: cliente no admite criptoassets (excluir_criptoassets=True)"
            log.info(razon)
            return False, razon

    return True, ""


# ═════════════════════════════════════════════════════════════════════════════
#  FILTRO BATCH — universo completo
# ═════════════════════════════════════════════════════════════════════════════

def filtrar_universo_por_perfil(
    universo: list[str] | set[str],
    datos_perfil: dict[str, Any],
    *,
    verbose: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """
    Filtra en bloque un universo de tickers por las restricciones del perfil.

    Parámetros
    ----------
    universo      : iterable de tickers BYMA
    datos_perfil  : dict de PERFIL_INVERSOR_CODIFICADO (un cliente)
    verbose       : si True, loguea cada exclusión

    Retorna
    -------
    (elegibles, excluidos_con_razon)
        elegibles            : lista de tickers que pasan todos los filtros
        excluidos_con_razon  : dict {ticker: razon_textual}
    """
    elegibles: list[str]        = []
    excluidos: dict[str, str]   = {}

    for ticker in universo:
        ok, razon = aplicar_filtros_perfil_y_etf(ticker, datos_perfil)
        if ok:
            elegibles.append(ticker)
        else:
            excluidos[ticker] = razon
            if verbose:
                log.info("  EXCLUIDO %s: %s", ticker, razon)

    log.info(
        "filtrar_universo_por_perfil: %d elegibles, %d excluidos (universo=%d)",
        len(elegibles), len(excluidos), len(list(universo)),
    )
    return elegibles, excluidos


# ═════════════════════════════════════════════════════════════════════════════
#  RESTRICCIÓN DE LIQUIDEZ POR CLIENTE
# ═════════════════════════════════════════════════════════════════════════════

def ajustar_restriccion_liquidez_por_cliente(
    weights: list[float] | np.ndarray,
    tickers_cartera: list[str],
    datos_perfil: dict[str, Any],
    *,
    adv_umbral: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Verifica que el portafolio mantenga la porción líquida exigida por el cliente.

    Parámetros
    ----------
    weights         : array de pesos (misma longitud que tickers_cartera)
    tickers_cartera : lista de tickers en el mismo orden que weights
    datos_perfil    : dict de PERFIL_INVERSOR_CODIFICADO
    adv_umbral      : ADV mínimo (M ARS) para clasificar activo como líquido.
                      Si None, usa ADV_LIQUIDEZ_MINIMA de config (default 1500 M).

    Retorna
    -------
    (cumple, detalle)
        cumple  : True si peso_liquido >= necesidad_liquidez_pct
        detalle : dict con métricas de liquidez y lista de activos líquidos
    """
    cfg = _cfg()
    volumen = getattr(cfg, "VOLUMEN_PROMEDIO_BYMA",       {})
    default  = float(getattr(cfg, "VOLUMEN_PROMEDIO_BYMA_DEFAULT", 50.0))
    umbral   = float(adv_umbral or getattr(cfg, "ADV_LIQUIDEZ_MINIMA", 1500.0))

    liquidez_requerida = float(datos_perfil.get("necesidad_liquidez_pct", 0.0))

    if liquidez_requerida == 0.0:
        return True, {"necesidad_pct": 0.0, "liquido_pct": 1.0, "cumple": True,
                      "activos_liquidos": tickers_cartera}

    w = np.asarray(weights, dtype=float)
    peso_liquido   = 0.0
    activos_liquidos: list[str] = []

    for i, ticker in enumerate(tickers_cartera):
        adv = float(volumen.get(ticker, default))
        if adv >= umbral:
            peso_liquido += float(w[i])
            activos_liquidos.append(ticker)

    cumple = peso_liquido >= liquidez_requerida
    detalle: dict[str, Any] = {
        "necesidad_pct":    round(liquidez_requerida, 4),
        "liquido_pct":      round(peso_liquido, 4),
        "deficit_pct":      round(max(0.0, liquidez_requerida - peso_liquido), 4),
        "adv_umbral_m_ars": umbral,
        "activos_liquidos": activos_liquidos,
        "cumple":           cumple,
    }

    if not cumple:
        log.warning(
            "Restriccion liquidez INCUMPLIDA: necesita %.1f%% liquido, tiene %.1f%%",
            liquidez_requerida * 100, peso_liquido * 100,
        )

    return cumple, detalle


# ═════════════════════════════════════════════════════════════════════════════
#  AJUSTE μ POR TER (ETFs)
# ═════════════════════════════════════════════════════════════════════════════

def ajustar_mu_por_ter(
    mu_series: pd.Series,
    etf_info: dict[str, dict[str, Any]] | None = None,
) -> pd.Series:
    """
    Deduce el TER anual del vector de retornos esperados (μ) de cada ETF.

    Fórmula:  μ_neto_i = μ_bruto_i - TER_i   (para tickers en ETF_INFO)
    Activos que no son ETF quedan sin modificar.

    Parámetros
    ----------
    mu_series : pd.Series con índice = tickers, valores = μ anualizado
    etf_info  : dict ETF_INFO; si None lo lee de config

    Retorna
    -------
    pd.Series ajustada (misma forma que la entrada)
    """
    if etf_info is None:
        etf_info = getattr(_cfg(), "ETF_INFO", {})

    mu_neto = mu_series.copy().astype(float)
    ajustados: list[str] = []

    for ticker in mu_neto.index:
        if ticker in etf_info:
            ter = float(etf_info[ticker].get("ter", 0.0))
            mu_neto[ticker] -= ter
            ajustados.append(f"{ticker}(-{ter:.4f})")

    if ajustados:
        log.debug("TER descontado de mu: %s", ", ".join(ajustados))

    return mu_neto


# ═════════════════════════════════════════════════════════════════════════════
#  RESTRICCIÓN DURATION vs. HORIZONTE DEL CLIENTE
# ═════════════════════════════════════════════════════════════════════════════

def restriccion_duration_horizonte(
    tickers_rf: list[str],
    metricas_riesgo: dict[str, dict[str, Any]],
    datos_perfil: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """
    Verifica que ninguna ON individual supere el horizonte de inversión del cliente.

    Lógica: si el cliente tiene horizonte de 3 años, no tiene sentido comprar
    una ON con Duration Modificada de 7 años — el riesgo de reinversión y
    mark-to-market es inconsistente con su objetivo temporal.

    Parámetros
    ----------
    tickers_rf      : lista de tickers de renta fija en la cartera
    metricas_riesgo : salida de calcular_metricas_riesgo_universo
    datos_perfil    : dict de PERFIL_INVERSOR_CODIFICADO

    Retorna
    -------
    (cumple, detalle) — True si todas las ONs respetan el horizonte
    """
    horizonte = float(datos_perfil.get("horizonte_inversion_anios", 999.0))
    violaciones: list[dict[str, Any]] = []

    for ticker in tickers_rf:
        riesgo = metricas_riesgo.get(ticker, {})
        if riesgo.get("metrica_riesgo_tipo") != "DURATION_MODIFICADA":
            continue
        dm = float(riesgo.get("valor_riesgo", 0.0))
        if dm > horizonte:
            violaciones.append({"ticker": ticker, "duration_mod": dm, "horizonte": horizonte})
            log.warning(
                "ON %s: Duration=%.2f anos supera horizonte cliente=%.1f anos",
                ticker, dm, horizonte,
            )

    cumple = len(violaciones) == 0
    return cumple, {
        "horizonte_anios":  horizonte,
        "violaciones":      violaciones,
        "cumple":           cumple,
    }
