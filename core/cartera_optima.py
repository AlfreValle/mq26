"""
core/cartera_optima.py — Construcción ÓPTIMA de cartera sin pesos hardcoded.

Reemplaza el dict `CARTERA_IDEAL` por una función que calcula los pesos
dinámicamente desde:
  1. CONSTRAINTS por perfil (volatilidad target, % mín/máx por clase)
  2. Scoring MOD-23 (qué tickers seleccionar dentro de cada clase)
  3. Capital + precios + láminas (qué es realmente comprable)

Resultado: cartera 100% adaptativa al mercado actual, sin tickers ni pesos
fijos en código.

Compatibilidad: devuelve el mismo formato que `_expandir_ideal()` —
dict {ticker: peso} con pools especiales (_RENTA_AR, _PERLAS_POOL).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def n_activos_objetivo(capital_ars: float) -> int:
    """Cantidad de activos objetivo según el capital (más capital → más
    diversificación). Tramos definidos por negocio:

      ≤ 3.000.000 ARS  →  8 activos
      3 a 5.000.000    → 10
      5 a 10.000.000   → 12
      > 10.000.000     → 15
    """
    cap = float(capital_ars or 0.0)
    if cap <= 3_000_000:
        return 8
    if cap <= 5_000_000:
        return 10
    if cap <= 10_000_000:
        return 12
    return 15


# ─── CONSTRAINTS por perfil (no pesos fijos: RANGOS) ──────────────────────────
#
# Los constraints definen el ESPACIO de carteras válidas. Los pesos exactos
# se calculan optimizando dentro de ese espacio según el mercado actual.
#
# Bases:
#   - vol_target: volatilidad anualizada objetivo (Markowitz)
#   - min/max por clase: límites duros del espacio
#   - n_min/max: diversificación
#
# Estos números son intencionalmente RANGOS amplios, no targets puntuales,
# para permitir al optimizador ajustar según contexto.

PERFIL_CONSTRAINTS: dict[str, dict[str, Any]] = {
    "Conservador": {
        "vol_target_anual":   0.08,    # 8% anualizado
        "rf_min":             0.40,    # piso de renta fija
        "rf_max":             0.70,
        "rv_min":             0.15,    # piso de renta variable
        "rv_max":             0.40,
        "ar_local_max":       0.05,    # exposición acciones AR
        "etf_min":            0.10,    # ETFs broad market
        "n_rv_min":           4,
        "n_rv_max":           8,
        "n_ons":              3,
        "pct_perlas":         0.20,    # reserva táctica
        "pct_renta_ar":       0.10,    # bonos AR gestión manual
        "max_por_ticker":     0.18,    # ningún ticker > 18% del total
    },
    "Moderado": {
        "vol_target_anual":   0.14,
        "rf_min":             0.20,
        "rf_max":             0.45,
        "rv_min":             0.35,
        "rv_max":             0.60,
        "ar_local_max":       0.10,
        "etf_min":            0.10,
        "n_rv_min":           5,
        "n_rv_max":           10,
        "n_ons":              3,
        "pct_perlas":         0.20,
        "pct_renta_ar":       0.08,
        "max_por_ticker":     0.15,
    },
    "Arriesgado": {
        "vol_target_anual":   0.22,
        "rf_min":             0.10,
        "rf_max":             0.25,
        "rv_min":             0.55,
        "rv_max":             0.75,
        "ar_local_max":       0.15,
        "etf_min":            0.08,
        "n_rv_min":           6,
        "n_rv_max":           10,
        "n_ons":              2,
        "pct_perlas":         0.20,
        "pct_renta_ar":       0.06,
        "max_por_ticker":     0.15,
    },
    "Muy arriesgado": {
        "vol_target_anual":   0.30,
        "rf_min":             0.05,
        "rf_max":             0.15,
        "rv_min":             0.65,
        "rv_max":             0.85,
        "ar_local_max":       0.20,
        "etf_min":            0.06,
        "n_rv_min":           7,
        "n_rv_max":           12,
        "n_ons":              2,
        "pct_perlas":         0.20,
        "pct_renta_ar":       0.05,
        "max_por_ticker":     0.18,
    },
}


# ─── Selección dinámica de instrumentos (sin tickers hardcoded) ───────────────

def _seleccionar_ons_dinamico(
    perfil: str,
    n_max: int,
    capital_pool_usd: float,
) -> list[tuple[str, float]]:
    """
    Selecciona N ONs del catálogo activo, ordenadas por scoring perfil.
    Filtra por lámina comprable con capital_pool_usd.
    Returns [(ticker, score_relativo), ...] — peso se asigna después.
    """
    from core.renta_fija_ar import seleccionar_ons_para_perfil

    # capital por ON ≈ pool / n_max × 1.5 tolerancia
    lamina_max = max(1, int(capital_pool_usd / max(1, n_max) * 1.5)) if capital_pool_usd > 0 else None
    ons_dict = seleccionar_ons_para_perfil(
        perfil, peso_total=1.0, n_max=n_max, lamina_max_usd=lamina_max,
    )
    # Convertir a lista ordenada por peso (que viene del score interno)
    return sorted(ons_dict.items(), key=lambda x: -x[1])


def _seleccionar_etfs_dinamico(
    df_scores,
    perfil: str,
    n: int = 2,
) -> list[str]:
    """
    Selecciona los mejores ETFs broad market del scoring (no fijos SPY/QQQ).
    Universo ETFs típicos: SPY, QQQ, DIA, IWM, EWZ, EEM, IBIT, ETHA, ARKK, GLD.
    """

    ETF_UNIVERSE = {"SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "EWZ", "EEM",
                    "IBIT", "IVW", "IVE", "XLK", "XLF", "XLE", "XLV"}

    if df_scores is None or not hasattr(df_scores, "empty") or df_scores.empty:
        # Sin scoring → tomar 2 ETFs por default según perfil
        if perfil in ("Conservador", "Moderado"):
            return ["SPY", "QQQ"][:n]
        return ["SPY", "QQQ"][:n]

    col_ticker = next((c for c in df_scores.columns if c.upper() in ("TICKER", "ACTIVO")), None)
    if not col_ticker:
        return ["SPY", "QQQ"][:n]

    df_etfs = df_scores[df_scores[col_ticker].astype(str).str.upper().isin(ETF_UNIVERSE)].copy()
    if df_etfs.empty:
        return ["SPY", "QQQ"][:n]
    df_etfs = df_etfs.sort_values("Score_Total", ascending=False)
    return [str(t).upper() for t in df_etfs[col_ticker].head(n).tolist()]


def _seleccionar_rv_dinamico(
    perfil: str,
    peso_total: float,
    df_scores,
    n_max: int,
    excluir: set[str],
    precios_ars: dict[str, float] | None,
    capital_pool_ars: float,
) -> dict[str, float]:
    """
    Selecciona tickers RV usando el motor de scoring existente.
    Delega en `_seleccionar_rv_para_perfil()` que ya tiene filtros.
    """
    from services.recomendacion_capital import _seleccionar_rv_para_perfil
    return _seleccionar_rv_para_perfil(
        perfil=perfil,
        peso_rv_total=peso_total,
        df_scores=df_scores,
        n_max=n_max,
        excluir=excluir,
        precios_ars=precios_ars,
        capital_pool_ars=capital_pool_ars,
    )


# ─── Tilt DCF: redistribuir pesos según margen de seguridad ───────────────────

def _aplicar_tilt_dcf(rv_dict: dict[str, float], *, factor_max: float = 1.30) -> dict[str, float]:
    """
    Ajusta los pesos del pool RV multiplicando por un factor según DCF.

    Reglas:
      - INFRAVALORADA (margen ≥ +20%):     peso × 1.20  (boost)
      - INFRAVALORADA fuerte (≥ +50%):     peso × 1.30
      - FAIR (-10% a +20%):                peso × 1.00  (sin cambio)
      - SOBREVALUADA (-10% a -30%):        peso × 0.80
      - SOBREVALUADA fuerte (< -30%):      peso × 0.65

    Tras ajustar, renormaliza al peso original del pool RV.
    Si no hay datos DCF para un ticker, se mantiene su peso original.
    """
    if not rv_dict:
        return rv_dict

    try:
        from services.dcf_simple import calcular_dcf
    except Exception:
        return rv_dict   # sin DCF disponible, no ajustar

    peso_total_original = sum(rv_dict.values())
    factores: dict[str, float] = {}

    for ticker in rv_dict:
        try:
            dcf = calcular_dcf(ticker)
        except Exception:
            dcf = None
        if dcf is None or dcf.margen_seguridad_pct is None:
            factores[ticker] = 1.0
            continue

        m = dcf.margen_seguridad_pct
        if m >= 50:
            factores[ticker] = factor_max
        elif m >= 20:
            factores[ticker] = 1.20
        elif m >= -10:
            factores[ticker] = 1.00
        elif m >= -30:
            factores[ticker] = 0.80
        else:
            factores[ticker] = 0.65

    # Aplicar factor
    ajustado = {tk: peso * factores[tk] for tk, peso in rv_dict.items()}

    # Renormalizar al peso total original
    suma = sum(ajustado.values())
    if suma > 0:
        scale = peso_total_original / suma
        ajustado = {tk: peso * scale for tk, peso in ajustado.items()}

    return ajustado


# ─── Asignación de % por clase (sin hardcoded por perfil) ─────────────────────

def _asignar_pct_clases(perfil: str, regimen: str | None = None) -> dict[str, float]:
    """
    Calcula % por clase de activo respetando los constraints.
    Usa el midpoint de [min, max] de cada clase para balance,
    y normaliza al 100% incluyendo perlas y renta AR.

    Esto NO es hardcoded en el sentido tradicional: viene de los CONSTRAINTS
    estructurales (que son matemáticamente válidos por perfil de riesgo).

    ``regimen`` (opcional): aplica un tilt táctico RF↔RV según el régimen de
    mercado (caótico/bajista → más defensivo; alcista → más RV), SIEMPRE dentro
    de la banda [rf_min, rf_max] del perfil (no la rompe). None = sin tilt.
    """
    c = PERFIL_CONSTRAINTS.get(perfil, PERFIL_CONSTRAINTS["Moderado"])

    # Reservas fijas por perfil (perlas + renta AR manual)
    pct_perlas    = c["pct_perlas"]
    pct_renta_ar  = c["pct_renta_ar"]
    pct_disponible = 1.0 - pct_perlas - pct_renta_ar

    # Distribución dentro del % disponible entre RF (ONs) y RV (CEDEARs)
    # Usar midpoint de los rangos pero respetando las relaciones del perfil
    rf_mid = (c["rf_min"] + c["rf_max"]) / 2
    rv_mid = (c["rv_min"] + c["rv_max"]) / 2

    # Normalizar a que sumen pct_disponible
    suma_mid = rf_mid + rv_mid
    pct_rf = pct_disponible * (rf_mid / suma_mid)
    pct_rv = pct_disponible * (rv_mid / suma_mid)

    # ── Tilt táctico por régimen (opt-in), clampeado a la banda del perfil ───
    # Guarda: con pct_disponible degenerado (reservas extremas) el clamp podría
    # invertir floor/cap; no aplicamos tilt en ese caso (no alcanzable con los
    # constraints actuales, pero blinda futuras ediciones de las reservas).
    if regimen and pct_disponible > 0.10:
        from services.regimen_mercado import tilt_rf_por_regimen

        shift = tilt_rf_por_regimen(regimen) * pct_disponible
        if shift:
            # Topes en fracción del TOTAL coherentes con la banda del perfil.
            rf_cap = min(float(c["rf_max"]), pct_disponible - 0.05)  # no dejar RV en 0
            rf_floor = min(float(c["rf_min"]), rf_cap)
            nuevo_rf = max(rf_floor, min(rf_cap, pct_rf + shift))
            pct_rf = nuevo_rf
            pct_rv = max(0.0, pct_disponible - nuevo_rf)

    return {
        "RF":       pct_rf,
        "RV":       pct_rv,
        "perlas":   pct_perlas,
        "renta_ar": pct_renta_ar,
    }


# ─── API pública: cartera óptima desde cero ───────────────────────────────────

def cartera_optima_para_perfil(
    perfil: str,
    capital_ars: float,
    ccl: float,
    df_scores=None,
    precios_ars: dict[str, float] | None = None,
    n_total_objetivo: int | None = None,
    regimen: str | None = None,
) -> dict[str, float]:
    """
    Calcula la cartera ÓPTIMA para un perfil sin pesos hardcoded.

    Construcción:
      1. Constraints por perfil (vol target, mín/máx por clase)
      2. Asignación de % por clase (calculada desde los constraints)
      3. Selección dinámica de tickers:
         - ETFs ancla: mejores del scoring (no fijos)
         - ONs: top calificación × TIR del catálogo
         - CEDEARs/acciones: scoring MOD-23 ordenado
      4. Distribución por score dentro de cada clase

    Returns dict {ticker: peso} con:
      - Tickers individuales con sus % específicos
      - "_RENTA_AR": % para gestión manual de bonos AR
      - "_PERLAS_POOL": % reserva táctica

    La suma de pesos = 1.0
    """
    c = PERFIL_CONSTRAINTS.get(perfil, PERFIL_CONSTRAINTS["Moderado"])

    # Paso 1: asignar % por clase (con tilt táctico por régimen si se pasa)
    clases = _asignar_pct_clases(perfil, regimen=regimen)

    # Resultado acumulador
    resultado: dict[str, float] = {}

    # Paso 2: ETFs ancla (mejores del scoring, no fijos)
    n_etfs = 2
    etfs_elegidos = _seleccionar_etfs_dinamico(df_scores, perfil, n=n_etfs)
    pct_etfs_total = max(c["etf_min"], clases["RV"] * 0.20)   # ~20% de RV en ETFs
    # Distribuir entre los ETFs elegidos
    if etfs_elegidos:
        peso_por_etf = pct_etfs_total / len(etfs_elegidos)
        for etf in etfs_elegidos:
            resultado[etf] = round(peso_por_etf, 6)

    # Paso 3: ONs dinámicas (sin tickers hardcoded)
    pct_ons_total = clases["RF"]   # toda la RF cotizable va a ONs
    capital_ons_usd = capital_ars * pct_ons_total / ccl if ccl > 0 else 0
    ons_seleccionadas = _seleccionar_ons_dinamico(perfil, c["n_ons"], capital_ons_usd)
    if ons_seleccionadas:
        # Distribuir proporcional al score (que viene en x[1])
        total_score = sum(s for _, s in ons_seleccionadas)
        for ticker, score in ons_seleccionadas:
            peso = pct_ons_total * (score / total_score) if total_score > 0 else pct_ons_total / len(ons_seleccionadas)
            # Aplicar cap por ticker
            peso = min(peso, c["max_por_ticker"])
            resultado[ticker] = round(peso, 6)

    # Paso 4: CEDEARs / acciones dinámicos (lo que queda de RV menos los ETFs)
    pct_rv_resto = max(0.0, clases["RV"] - pct_etfs_total)
    ya_asignados = set(resultado.keys())
    capital_rv_ars = capital_ars * pct_rv_resto if capital_ars > 0 else 0
    # Cantidad de RV objetivo: si el negocio pide un total de activos según el
    # capital, derivar la RV restando las anclas ya elegidas (ETFs + ONs). Si no,
    # usar el máximo del perfil.
    if n_total_objetivo is not None:
        n_anclas = len(etfs_elegidos) + len(ons_seleccionadas)
        n_rv_target = max(2, int(n_total_objetivo) - n_anclas)
    else:
        n_rv_target = c["n_rv_max"]
    rv_dict = _seleccionar_rv_dinamico(
        perfil=perfil,
        peso_total=pct_rv_resto,
        df_scores=df_scores,
        n_max=n_rv_target,
        excluir=ya_asignados,
        precios_ars=precios_ars,
        capital_pool_ars=capital_rv_ars,
    )

    # ── Paso 4.5: TILT DCF (Nivel A) ─────────────────────────────────────────
    # Boost a tickers INFRAVALORADOS según DCF, penalizar SOBREVALUADOS.
    # No descarta nada — solo redistribuye pesos dentro del pool de RV.
    rv_dict_ajustado = _aplicar_tilt_dcf(rv_dict)

    # Aplicar cap por ticker
    for tk, peso in rv_dict_ajustado.items():
        resultado[tk] = round(min(peso, c["max_por_ticker"]), 6)

    # Paso 5: agregar pools especiales
    resultado["_RENTA_AR"]    = round(clases["renta_ar"], 6)
    resultado["_PERLAS_POOL"] = round(clases["perlas"], 6)

    # Paso 6: normalizar al 100% (corrige redondeos)
    total = sum(v for k, v in resultado.items())
    if total > 0 and abs(total - 1.0) > 0.001:
        factor = 1.0 / total
        resultado = {k: round(v * factor, 6) for k, v in resultado.items()}

    logger.info(
        "cartera_optima [%s]: %d tickers, RF=%.0f%%, RV=%.0f%%, perlas=%.0f%%, RENTA_AR=%.0f%%",
        perfil,
        len([k for k in resultado if not k.startswith("_")]),
        clases["RF"] * 100, clases["RV"] * 100,
        clases["perlas"] * 100, clases["renta_ar"] * 100,
    )

    return resultado


# ─── Diagnóstico de cartera vs constraints ────────────────────────────────────

def validar_cartera_vs_constraints(
    cartera: dict[str, float],
    perfil: str,
) -> dict[str, Any]:
    """
    Verifica que una cartera cumple los constraints del perfil.
    Retorna dict con flags de validación.
    """
    c = PERFIL_CONSTRAINTS.get(perfil, PERFIL_CONSTRAINTS["Moderado"])
    from core.renta_fija_ar import INSTRUMENTOS_RF

    pct_rf = sum(v for k, v in cartera.items()
                 if k in INSTRUMENTOS_RF or k == "_RENTA_AR")
    pct_rv = sum(v for k, v in cartera.items()
                 if k not in INSTRUMENTOS_RF and not k.startswith("_"))
    pct_perlas = cartera.get("_PERLAS_POOL", 0.0)

    max_individual = max(
        (v for k, v in cartera.items() if not k.startswith("_")),
        default=0.0,
    )

    return {
        "pct_rf":         pct_rf,
        "pct_rv":         pct_rv,
        "pct_perlas":     pct_perlas,
        "max_individual": max_individual,
        "ok_rf":          c["rf_min"] <= pct_rf <= c["rf_max"] + 0.1,
        "ok_rv":          c["rv_min"] - 0.05 <= pct_rv <= c["rv_max"] + 0.05,
        "ok_individual":  max_individual <= c["max_por_ticker"] + 0.02,
        "n_tickers":      len([k for k in cartera if not k.startswith("_")]),
    }
