"""
Motor de Scoring Multifactorial Integrado — Value + Quality + Growth + Income.

Metodología
-----------
Transforma métricas absolutas (P/E=29, ROE=1.60…) a un espacio uniforme [0,1]
mediante ranking percentil (`.rank(pct=True)`).  Esto evita que empresas con
múltiplos extremos (NVDA: P/E=66, AAPL: ROE=1.60) distorsionen la escala de
las demás — cada activo compite solo dentro del universo cargado.

Factores y dirección
---------------------
  Value  (30 %):  P/E  ↓ mejor  → rank(ascending=False)
                  P/B  ↓ mejor  → rank(ascending=False)
  Quality(40 %):  ROE  ↑ mejor  → rank(ascending=True)
                  D/P  ↓ mejor  → rank(ascending=False)
  Growth (20 %):  Revenue YoY ↑ mejor → rank(ascending=True)
  Income (10 %):  Div Yield   ↑ mejor → rank(ascending=True)

Nulos (None / NaN)
-------------------
Imputados con la mediana de la columna **antes** del ranking.  Bancos y
holdings sin ratio Deuda/Patrimonio estándar reciben la mediana del universo,
que los ubica en posición "neutral" en ese factor sin distorsionar el resto.

Integración con señales técnicas
----------------------------------
``obtener_alpha_screen()`` combina el score fundamental (0-100) con señales
de RSI y tendencia SMA en un Alpha Score combinado.
Los pesos del mix se leen de ``config.ALPHA_SCREEN_MIX``.

Integración con metricas_riesgo
---------------------------------
``filtrar_por_perfil_y_score()`` cruza el score fundamental con
``RESTRICCIONES_POR_PERFIL`` (sectores excluidos) para devolver el ranking
ya filtrado por perfil del cliente.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ── Claves que deben existir en el dict de fundamentales ─────────────────────
_CAMPOS_REQUERIDOS = ("pe", "pb", "roe", "div_yield", "deuda_patrimonio", "rev_growth_yoy")


# ═════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL — Scoring factorial
# ═════════════════════════════════════════════════════════════════════════════

def calcular_scoring_fundamental(
    diccionario_fundamentales: dict[str, dict[str, Any]],
    pesos: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Transforma el diccionario de datos fundamentales en scores del 0 al 100.

    Parámetros
    ----------
    diccionario_fundamentales : dict
        Compatible con ``DATOS_FUNDAMENTALES_EXTENDIDOS``.
        Cada value es un dict con keys: pe, pb, roe, div_yield,
        deuda_patrimonio, rev_growth_yoy.  Nulos aceptados.
    pesos : dict, opcional
        Override de ``PESOS_SCORING_FUNDAMENTAL``.  Debe sumar 1.0.

    Retorna
    -------
    dict ticker → score_final (float, 0-100).
    Tickers con todos los campos None devuelven score 50.0 (neutral).
    """
    # ── Pesos ─────────────────────────────────────────────────────────────────
    if pesos is None:
        try:
            from config import PESOS_SCORING_FUNDAMENTAL
            pesos = PESOS_SCORING_FUNDAMENTAL
        except ImportError:
            pesos = {
                "score_pe":    0.15, "score_pb":    0.15,
                "score_roe":   0.25, "score_deuda": 0.15,
                "score_growth":0.20, "score_yield": 0.10,
            }

    total_peso = sum(pesos.values())
    if abs(total_peso - 1.0) > 0.01:
        log.warning("PESOS_SCORING_FUNDAMENTAL suman %.3f ≠ 1.0 — normalizando", total_peso)
        pesos = {k: v / total_peso for k, v in pesos.items()}

    # ── Filtrar sólo dicts válidos ─────────────────────────────────────────────
    datos_validos = {
        t: m for t, m in diccionario_fundamentales.items() if isinstance(m, dict)
    }
    if not datos_validos:
        log.warning("calcular_scoring_fundamental: diccionario vacío o sin dicts válidos.")
        return {}

    # ── Construir DataFrame ────────────────────────────────────────────────────
    df = pd.DataFrame.from_dict(datos_validos, orient="index")[list(_CAMPOS_REQUERIDOS)]
    df = df.astype(float, errors="ignore")   # convierte None → NaN

    # ── Imputación por mediana (neutral para bancos sin D/P) ───────────────────
    # numeric_only=True requerido en pandas ≥ 2.0
    medianas = df.median(numeric_only=True)
    df = df.fillna(medianas)

    # ── Rankings percentiles ───────────────────────────────────────────────────
    # VALUE — menor múltiplo = mejor → ascending=False
    df["score_pe"]    = df["pe"].rank(ascending=False, pct=True)
    df["score_pb"]    = df["pb"].rank(ascending=False, pct=True)
    # QUALITY
    df["score_roe"]   = df["roe"].rank(ascending=True, pct=True)
    df["score_deuda"] = df["deuda_patrimonio"].rank(ascending=False, pct=True)
    # GROWTH + INCOME
    df["score_growth"]= df["rev_growth_yoy"].rank(ascending=True, pct=True)
    df["score_yield"] = df["div_yield"].rank(ascending=True, pct=True)

    # ── Score final ponderado (0-100) ─────────────────────────────────────────
    score_cols = ["score_pe", "score_pb", "score_roe", "score_deuda", "score_growth", "score_yield"]
    df["scoring_final"] = sum(
        df[col] * pesos.get(col, 0.0) for col in score_cols
    ) * 100

    resultado = df["scoring_final"].round(2).to_dict()
    log.info("Scoring fundamental calculado para %d activos.", len(resultado))
    return resultado


# ═════════════════════════════════════════════════════════════════════════════
#  ALPHA SCREEN — Combina fundamental + técnico
# ═════════════════════════════════════════════════════════════════════════════

def obtener_alpha_screen(
    ticker: str,
    rsi_actual: float | None,
    tendencia_sma_ok: bool | None,
    scores_fundamentales: dict[str, float],
    *,
    rsi_umbral_sobreventa: float = 35.0,
    mix: dict[str, float] | None = None,
) -> float:
    """
    Alpha Score combinado para un ticker.

    Parámetros
    ----------
    ticker                  : ticker BYMA local
    rsi_actual              : RSI actual (None → señal técnica neutra)
    tendencia_sma_ok        : True si la media larga está por debajo del precio
    scores_fundamentales    : salida de ``calcular_scoring_fundamental``
    rsi_umbral_sobreventa   : umbral de sobrecompra/venta (default: 35)
    mix                     : override de ``ALPHA_SCREEN_MIX``

    Retorna
    -------
    float 0-100 — mayor = más atractivo para el optimizador
    """
    # ── Peso del mix ──────────────────────────────────────────────────────────
    if mix is None:
        try:
            from config import ALPHA_SCREEN_MIX
            mix = ALPHA_SCREEN_MIX
        except ImportError:
            mix = {"fundamental": 0.60, "tecnico": 0.40}

    w_f = float(mix.get("fundamental", 0.60))
    w_t = float(mix.get("tecnico", 0.40))

    # ── Componente fundamental (0-100, 50 si no hay datos) ────────────────────
    score_f = float(scores_fundamentales.get(ticker, 50.0))

    # ── Componente técnico (0-100) ────────────────────────────────────────────
    score_t = 0.0
    if rsi_actual is not None and rsi_actual < rsi_umbral_sobreventa:
        score_t += 50.0   # sobrevendido → oportunidad de entrada
    if tendencia_sma_ok:
        score_t += 50.0   # tendencia de fondo alcista

    # ── Mix institucional ─────────────────────────────────────────────────────
    alpha = (score_f * w_f) + (score_t * w_t)
    return round(alpha, 2)


def calcular_alpha_screen_batch(
    tickers: list[str],
    rsi_map: dict[str, float | None],
    sma_map: dict[str, bool | None],
    scores_fundamentales: dict[str, float],
    **kwargs: Any,
) -> pd.DataFrame:
    """
    Calcula el Alpha Screen para una lista de tickers y devuelve un DataFrame
    ordenado de mayor a menor score.

    Parámetros
    ----------
    tickers               : lista de tickers BYMA
    rsi_map               : {ticker: rsi_value}  (None si no disponible)
    sma_map               : {ticker: True/False}  (None si no disponible)
    scores_fundamentales  : salida de ``calcular_scoring_fundamental``
    **kwargs              : se pasan a ``obtener_alpha_screen``

    Retorna
    -------
    pd.DataFrame con columnas: ticker, score_fundamental, score_tecnico, alpha_screen
    """
    rows = []
    for t in tickers:
        sf = float(scores_fundamentales.get(t, 50.0))
        rsi = rsi_map.get(t)
        sma = sma_map.get(t)
        alpha = obtener_alpha_screen(t, rsi, sma, scores_fundamentales, **kwargs)

        # Score técnico en bruto para reporting
        st = 0.0
        umbral = kwargs.get("rsi_umbral_sobreventa", 35.0)
        if rsi is not None and rsi < umbral:
            st += 50.0
        if sma:
            st += 50.0

        rows.append({
            "ticker":             t,
            "score_fundamental":  round(sf, 2),
            "score_tecnico":      round(st, 2),
            "alpha_screen":       alpha,
        })

    df = (
        pd.DataFrame(rows)
          .sort_values("alpha_screen", ascending=False)
          .reset_index(drop=True)
    )
    df.index += 1   # ranking desde 1
    return df


# ═════════════════════════════════════════════════════════════════════════════
#  FILTRO POR PERFIL — Excluye sectores y devuelve ranking filtrado
# ═════════════════════════════════════════════════════════════════════════════

def filtrar_por_perfil_y_score(
    df_alpha: pd.DataFrame,
    perfil: str,
    sectores_activos: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Aplica los ``sectores_excluidos`` del perfil sobre el DataFrame de alpha screen.

    Parámetros
    ----------
    df_alpha          : salida de ``calcular_alpha_screen_batch``
    perfil            : "CONSERVADOR" | "MODERADO" | "AGRESIVO" | "MUY AGRESIVO"
    sectores_activos  : dict ticker → sector (usa ``SECTORES`` de config si es None)

    Retorna
    -------
    pd.DataFrame filtrado y re-numerado.
    """
    from config import RESTRICCIONES_POR_PERFIL  # import late

    restricciones = RESTRICCIONES_POR_PERFIL.get(perfil, {})
    excluidos_sector = set(restricciones.get("sectores_excluidos", []))

    if not excluidos_sector:
        return df_alpha.copy()

    # Cargar SECTORES si no se pasan
    if sectores_activos is None:
        try:
            from config import SECTORES
            sectores_activos = SECTORES
        except ImportError:
            sectores_activos = {}

    def _sector_excluido(ticker: str) -> bool:
        return sectores_activos.get(ticker, "") in excluidos_sector

    mask = ~df_alpha["ticker"].apply(_sector_excluido)
    resultado = df_alpha[mask].copy().reset_index(drop=True)
    resultado.index += 1
    return resultado


# ═════════════════════════════════════════════════════════════════════════════
#  DESGLOSE DE FACTORES — Para reporting / explicabilidad
# ═════════════════════════════════════════════════════════════════════════════

def desglosar_factores(
    ticker: str,
    diccionario_fundamentales: dict[str, dict[str, Any]],
    scores_fundamentales: dict[str, float],
) -> dict[str, Any]:
    """
    Devuelve los valores brutos + percentil de cada factor para un ticker.
    Útil para mostrar al cliente "por qué" un activo tiene ese score.

    Retorna
    -------
    dict con "datos_brutos", "percentiles", "score_final", "interpretacion"
    """
    meta = diccionario_fundamentales.get(ticker, {})
    score = scores_fundamentales.get(ticker, 50.0)

    # Calcular percentiles de todo el universo
    df = pd.DataFrame.from_dict(
        {t: m for t, m in diccionario_fundamentales.items() if isinstance(m, dict)},
        orient="index",
    )[list(_CAMPOS_REQUERIDOS)].astype(float, errors="ignore")
    medianas = df.median(numeric_only=True)
    df = df.fillna(medianas)

    if ticker not in df.index:
        return {"error": f"Ticker '{ticker}' no encontrado en el diccionario."}

    percentiles = {
        "pe":              round(df["pe"].rank(ascending=False, pct=True)[ticker], 3),
        "pb":              round(df["pb"].rank(ascending=False, pct=True)[ticker], 3),
        "roe":             round(df["roe"].rank(ascending=True,  pct=True)[ticker], 3),
        "deuda_patrimonio":round(df["deuda_patrimonio"].rank(ascending=False, pct=True)[ticker], 3),
        "rev_growth_yoy":  round(df["rev_growth_yoy"].rank(ascending=True, pct=True)[ticker], 3),
        "div_yield":       round(df["div_yield"].rank(ascending=True, pct=True)[ticker], 3),
    }

    if score >= 70:
        interp = "Muy atractivo"
    elif score >= 55:
        interp = "Atractivo"
    elif score >= 45:
        interp = "Neutral"
    elif score >= 30:
        interp = "Poco atractivo"
    else:
        interp = "Evitar"

    return {
        "ticker":       ticker,
        "datos_brutos": {k: meta.get(k) for k in _CAMPOS_REQUERIDOS},
        "percentiles":  percentiles,
        "score_final":  round(score, 2),
        "interpretacion": interp,
    }
