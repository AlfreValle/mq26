"""
Módulo de cálculo de riesgo estructurado — enfoque dual RV / RF.

Metodología
-----------
* Renta Variable (CEDEARs + Acciones AR):
    Beta individual = Cov(Activo, Benchmark) / Var(Benchmark)
    - CEDEARs  → benchmark: S&P 500 (^GSPC) configurable en PARAMETROS_HISTORICO
    - Acciones BYMA → benchmark: Merval (^MERV) configurable en PARAMETROS_HISTORICO
    El cálculo usa ``df_retornos`` (ya descargado por ``historico_retornos``) y
    descarga los benchmarks sólo si no están en ese DataFrame, evitando doble I/O.

* Renta Fija (ONs):
    Duration Modificada = Duration Macaulay / (1 + TIR/frecuencia)
    Flujos generados por ``core.renta_fija_ar.generar_vector_flujos``.
    TIR analítica de fallback: 8.5 % Ley NY, 10.5 % Ley Local.

Salida unificada por ticker
----------------------------
{
    "metrica_riesgo_tipo": "BETA" | "DURATION_MODIFICADA",
    "valor_riesgo":        float,          # β o DM en años
    "benchmark_asignado":  str,            # "^GSPC" | "^MERV" | "CURVA_CORPORATIVA_USD"
    "exposicion_moneda":   str | None,     # "USD" | "ARS" | "BRL" …
}

Integración con el optimizador
-------------------------------
``validar_riesgo_perfil`` consume la salida de ``calcular_metricas_riesgo_universo``
y valida contra ``RESTRICCIONES_POR_PERFIL`` (keys: max_duration_modificada,
max_beta_ponderado_rv).  Devuelve (bool, dict_detalle).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Lazy imports ──────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False
    log.warning("yfinance no instalado — betas no calculables")

try:
    from core.renta_fija_ar import generar_vector_flujos
    _RF_OK = True
except ImportError:
    _RF_OK = False
    log.warning("core.renta_fija_ar no disponible — durations no calculables")

# ── TIR analítica de fallback por ley ─────────────────────────────────────────
_TIR_FALLBACK: dict[str, float] = {
    "Nueva York": 0.085,
    "Local":      0.105,
}
_TIR_DEFAULT = 0.090   # para leyes no mapeadas

# Benchmarks por tipo de instrumento RF (para el campo benchmark_asignado)
_BENCH_RF: dict[str, str] = {
    "BONO_USD": "CURVA_SOBERANA_USD",
    "BOPREAL":  "CURVA_BOPREAL_USD",
    "BONCER":   "CER_BCRA",
    "CAUCION":  "BYMA_CAUCIONES",
    "ON_USD":   "CURVA_CORPORATIVA_USD",
}


# ═════════════════════════════════════════════════════════════════════════════
#  BLOQUE 1 — Descarga de benchmarks (reutiliza df_retornos si ya los contiene)
# ═════════════════════════════════════════════════════════════════════════════

def _obtener_retornos_benchmarks(
    parametros: dict[str, Any],
    df_retornos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve DataFrame de retornos logarítmicos diarios para los dos benchmarks
    configurados.  Si ya están en ``df_retornos``, los reutiliza directamente
    (evita doble descarga).
    """
    bench_global = parametros["benchmark_global"]   # "^GSPC"
    bench_local  = parametros["benchmark_local"]    # "^MERV"
    ventana      = int(parametros["ventana_dias"])

    presentes = [b for b in [bench_global, bench_local] if b in df_retornos.columns]
    faltantes  = [b for b in [bench_global, bench_local] if b not in df_retornos.columns]

    partes: list[pd.DataFrame] = []

    # Reutilizar los que ya viajan en df_retornos
    if presentes:
        partes.append(df_retornos[presentes].copy())

    # Descargar sólo los que faltan
    if faltantes and _YF_OK:
        fecha_fin    = datetime.now()
        fecha_inicio = fecha_fin - timedelta(days=int(ventana * 1.5))
        try:
            raw = yf.download(
                tickers=faltantes,
                start=fecha_inicio.strftime("%Y-%m-%d"),
                end=fecha_fin.strftime("%Y-%m-%d"),
                interval=parametros.get("frecuencia", "1d"),
                auto_adjust=True,
                progress=False,
            )
            if isinstance(raw.columns, pd.MultiIndex):
                cierre = raw["Close"].copy()
            else:
                cierre = raw[["Close"]].rename(columns={"Close": faltantes[0]})

            retornos_bench = np.log(cierre.ffill() / cierre.shift(1)).dropna(how="all")
            retornos_bench = retornos_bench.tail(ventana)
            partes.append(retornos_bench)
        except Exception as exc:
            log.error("Error descargando benchmarks %s: %s", faltantes, exc)

    if not partes:
        return pd.DataFrame()

    df_bench = pd.concat(partes, axis=1)
    # Asegurar que ambos benchmarks tengan columna (NaN si descarga falló)
    for b in [bench_global, bench_local]:
        if b not in df_bench.columns:
            df_bench[b] = np.nan

    return df_bench


# ═════════════════════════════════════════════════════════════════════════════
#  BLOQUE 2 — Beta individual por activo de RV
# ═════════════════════════════════════════════════════════════════════════════

def _calcular_beta(
    serie_activo: pd.Series,
    serie_bench: pd.Series,
    min_obs: int,
) -> float | None:
    """
    Beta = Cov(activo, benchmark) / Var(benchmark).
    Alinea las series antes de calcular para eliminar descalces de feriados.
    Retorna None si no hay suficientes observaciones.
    """
    df_comp = pd.concat([serie_activo, serie_bench], axis=1).dropna()
    if len(df_comp) < min_obs:
        return None
    cov_mat = np.cov(df_comp.iloc[:, 0].values, df_comp.iloc[:, 1].values)
    var_bench = cov_mat[1, 1]
    if var_bench == 0.0:
        return None
    return float(cov_mat[0, 1] / var_bench)


# ═════════════════════════════════════════════════════════════════════════════
#  BLOQUE 3 — Duration Modificada — dispatcher unificado para todos los RF
# ═════════════════════════════════════════════════════════════════════════════

def _calcular_duration_modificada(
    on_data: dict[str, Any],
    fecha_liq: date,
) -> float | None:
    """
    Duration Modificada para cualquier instrumento de RF argentino.

    Dispatch por campo 'tipo':
        BONCER   → duration_real pre-calculada (campo duration_real_anos)
        CAUCION  → plazo_dias / 365
        BONO_USD / BOPREAL → cashflow con tir_mercado_ref; fallback duration_ref_anos
        ON_USD / default   → cashflow con tir por ley; fallback estatico

    Retorna None solo si el instrumento ya venció y no hay datos.
    """
    tipo = str(on_data.get("tipo", "")).upper()

    # ── BONCER: duration real directa ────────────────────────────────────────
    if tipo == "BONCER":
        dur = on_data.get("duration_real_anos") or on_data.get("duration_real")
        if dur is not None:
            return round(float(dur), 4)
        # Fallback: 2 años si no hay dato
        return 2.0

    # ── CAUCION: plazo / 365 ─────────────────────────────────────────────────
    if tipo == "CAUCION":
        dur_ref = on_data.get("duration_ref_anos")
        if dur_ref is not None:
            return round(float(dur_ref), 4)
        plazo = int(on_data.get("plazo_dias", 7))
        return round(plazo / 365.0, 4)

    # ── Soberanos (BONO_USD / BOPREAL): ref pre-calculada con prioridad ─────────
    # Los soberanos tienen amortizaciones complejas (step-up + quarterly principal).
    # duration_ref_anos (Bloomberg/MAE) es mas precisa que la aproximacion lineal.
    # Solo caemos al cashflow si explicitamente no hay ref disponible.
    if tipo in ("BONO_USD", "BOPREAL"):
        dur_ref = on_data.get("duration_ref_anos")

        # 1. Prioridad: duration_ref_anos pre-calculada (Bloomberg/MAE)
        if dur_ref is not None:
            return round(float(dur_ref), 4)

        # 2. Fallback: cashflow con TIR mercado (amortizacion linearizada)
        tir_ref = float(on_data.get("tir_mercado_ref", 0.0))
        if _RF_OK and tir_ref > 0:
            vector = generar_vector_flujos(on_data, fecha_liq)
            if vector:
                frecuencia = int(on_data.get("frecuencia_pago", 2))
                dur_mac = 0.0
                va_tot  = 0.0
                for flujo in vector:
                    fd = datetime.strptime(flujo["fecha"], "%Y-%m-%d").date()
                    t_a = (fd - fecha_liq).days / 365.0
                    if t_a <= 0:
                        continue
                    per = frecuencia * t_a
                    va = flujo["monto"] / (1.0 + tir_ref / frecuencia) ** per
                    va_tot  += va
                    dur_mac += t_a * va
                if va_tot > 0:
                    dm = (dur_mac / va_tot) / (1.0 + tir_ref / frecuencia)
                    return round(dm, 4)

        return 3.0  # soberano sin dato → default 3 años

    # ── ON corporativa (ON_USD / default): lógica original ───────────────────
    if not _RF_OK:
        return None

    vector = generar_vector_flujos(on_data, fecha_liq)
    if not vector:
        return None

    ley        = on_data.get("ley", "")
    tir        = _TIR_FALLBACK.get(ley, _TIR_DEFAULT)
    frecuencia = int(on_data.get("frecuencia_pago", 2))
    dur_macaulay       = 0.0
    valor_actual_total = 0.0

    for flujo in vector:
        fecha_flujo = datetime.strptime(flujo["fecha"], "%Y-%m-%d").date()
        t_anos      = (fecha_flujo - fecha_liq).days / 365.0
        if t_anos <= 0:
            continue
        periodos    = frecuencia * t_anos
        factor_desc = (1.0 + tir / frecuencia) ** periodos
        va_flujo    = flujo["monto"] / factor_desc
        valor_actual_total += va_flujo
        dur_macaulay       += t_anos * va_flujo

    if valor_actual_total <= 0:
        return None

    dur_mac = dur_macaulay / valor_actual_total
    dur_mod = dur_mac / (1.0 + tir / frecuencia)
    return round(dur_mod, 4)


# ═════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════

def calcular_metricas_riesgo_universo(
    universo_rv: dict[str, Any],
    universo_rf: dict[str, Any],
    parametros: dict[str, Any],
    df_retornos: pd.DataFrame,
    *,
    verbose: bool = True,
) -> dict[str, dict[str, Any]]:
    """
    Calcula dinámicamente las métricas de riesgo de todo el universo de activos.

    Parámetros
    ----------
    universo_rv  : CEDEAR_INFO + ACCIONES_ARGENTINAS (dict con keys exchange/currency)
    universo_rf  : OBLIGACIONES_NEGOCIABLES (dict con keys ley/frecuencia_pago/…)
    parametros   : PARAMETROS_HISTORICO
    df_retornos  : salida de ``obtener_matriz_retornos_limpios``
    verbose      : log de activos descartados o con fallback

    Retorna
    -------
    dict ticker → {metrica_riesgo_tipo, valor_riesgo, benchmark_asignado, exposicion_moneda}
    """
    riesgo_impacto: dict[str, dict[str, Any]] = {}
    min_obs = int(parametros.get("min_obs_validos", 120))

    # ── 1. Benchmarks ──────────────────────────────────────────────────────────
    bench_global = parametros["benchmark_global"]
    bench_local  = parametros["benchmark_local"]
    df_bench     = _obtener_retornos_benchmarks(parametros, df_retornos)

    # ── 2. Betas de Renta Variable ─────────────────────────────────────────────
    for ticker, meta in universo_rv.items():
        if not isinstance(meta, dict):
            continue

        exchange = meta.get("exchange", "")
        moneda   = meta.get("currency")
        es_local = (exchange == "BYMA")
        bench_col = bench_local if es_local else bench_global

        # Fallback desde DATOS_FUNDAMENTALES si el ticker no está en df_retornos
        beta_calculado: float | None = None

        if ticker in df_retornos.columns and bench_col in df_bench.columns:
            beta_calculado = _calcular_beta(
                df_retornos[ticker],
                df_bench[bench_col],
                min_obs,
            )

        if beta_calculado is not None:
            riesgo_impacto[ticker] = {
                "metrica_riesgo_tipo": "BETA",
                "valor_riesgo":        round(beta_calculado, 4),
                "benchmark_asignado":  bench_col,
                "exposicion_moneda":   moneda,
                "fuente":              "calculado",
            }
        else:
            # Fallback: intenta leer beta estático de DATOS_FUNDAMENTALES
            beta_fallback = _beta_fallback(ticker)
            riesgo_impacto[ticker] = {
                "metrica_riesgo_tipo": "BETA",
                "valor_riesgo":        beta_fallback,
                "benchmark_asignado":  bench_col,
                "exposicion_moneda":   moneda,
                "fuente":              "fallback_estatico",
            }
            if verbose:
                log.warning(
                    "Beta %s: datos insuficientes → fallback β=%.2f", ticker, beta_fallback
                )

    # ── 3. Duration Modificada — todos los tipos de RF ────────────────────────
    fecha_liq = date.today()

    # Enriquecer universo_rf con soberanos, CER y cauciones si no están ya
    _universo_rf_ext = dict(universo_rf)
    try:
        from config import BONOS_CER, BONOS_SOBERANOS, CAUCIONES_BYMA
        for _src in (BONOS_SOBERANOS, BONOS_CER, CAUCIONES_BYMA):
            for _t, _m in _src.items():
                if _t not in _universo_rf_ext:
                    _universo_rf_ext[_t] = _m
    except ImportError:
        pass

    for ticker, meta in _universo_rf_ext.items():
        if not isinstance(meta, dict):
            continue
        # Solo procesar si está en el universo de activos activo (tickers_activos)
        # universo_rf viene filtrado desde el pipeline; la extensión agrega los
        # que no estaban en OBLIGACIONES_NEGOCIABLES
        if ticker not in universo_rf:
            # Para soberanos/CER/cauciones que NO están en df_retornos aún,
            # calculamos su metrica de todas formas (útil para validar perfil)
            pass

        tipo   = str(meta.get("tipo", "ON_USD")).upper()
        moneda = meta.get("moneda_emision", meta.get("moneda", "USD"))
        ley    = meta.get("ley", "")
        dur_mod = _calcular_duration_modificada(meta, fecha_liq)

        bench_rf = _BENCH_RF.get(tipo, "CURVA_CORPORATIVA_USD")

        if dur_mod is not None:
            riesgo_impacto[ticker] = {
                "metrica_riesgo_tipo": "DURATION_MODIFICADA",
                "valor_riesgo":        dur_mod,
                "benchmark_asignado":  bench_rf,
                "exposicion_moneda":   moneda,
                "fuente":              "calculado",
            }
        else:
            # Vencido o sin flujos → fallback por tipo / ley
            if tipo == "BONCER":
                dur_fb = 1.5
            elif tipo == "CAUCION":
                dur_fb = 0.04
            elif tipo in ("BONO_USD", "BOPREAL"):
                dur_fb = 3.0
            else:
                dur_fb = 1.5 if ley == "Local" else 2.5

            riesgo_impacto[ticker] = {
                "metrica_riesgo_tipo": "DURATION_MODIFICADA",
                "valor_riesgo":        dur_fb,
                "benchmark_asignado":  bench_rf,
                "exposicion_moneda":   moneda,
                "fuente":              "fallback_sin_flujos",
            }
            if verbose:
                log.warning(
                    "Duration %s (%s): sin flujos futuros -> fallback DM=%.2f anos",
                    ticker, tipo, dur_fb
                )

    if verbose:
        n_beta = sum(1 for v in riesgo_impacto.values() if v["metrica_riesgo_tipo"] == "BETA")
        n_dur  = sum(1 for v in riesgo_impacto.values() if v["metrica_riesgo_tipo"] == "DURATION_MODIFICADA")
        log.info("Métricas de riesgo: %d betas RV + %d durations RF = %d total",
                 n_beta, n_dur, len(riesgo_impacto))

    return riesgo_impacto


def _beta_fallback(ticker: str) -> float:
    """Lee beta estático de DATOS_FUNDAMENTALES; retorna 1.0 si no existe."""
    try:
        from config import DATOS_FUNDAMENTALES  # import late para evitar circular
        return float(DATOS_FUNDAMENTALES.get(ticker, {}).get("beta") or 1.0)
    except Exception:
        return 1.0


# ═════════════════════════════════════════════════════════════════════════════
#  VALIDADOR DE RIESGO POR PERFIL
# ═════════════════════════════════════════════════════════════════════════════

def validar_riesgo_perfil(
    weights: list[float] | np.ndarray,
    tickers_cartera: list[str],
    riesgo_impacto: dict[str, dict[str, Any]],
    perfil_usuario: str,
) -> tuple[bool, dict[str, Any]]:
    """
    Valida que la asignación de pesos cumpla las restricciones de riesgo del perfil.

    Lee los límites directamente de ``RESTRICCIONES_POR_PERFIL`` (keys nuevas:
    ``max_duration_modificada`` y ``max_beta_ponderado_rv``).

    Parámetros
    ----------
    weights          : array de pesos (suma debe ser ≈ 1.0)
    tickers_cartera  : lista de tickers en el mismo orden que weights
    riesgo_impacto   : salida de ``calcular_metricas_riesgo_universo``
    perfil_usuario   : "CONSERVADOR" | "MODERADO" | "AGRESIVO" | "MUY AGRESIVO"

    Retorna
    -------
    (valido, detalle)
        valido  : True si la cartera cumple todos los límites del perfil
        detalle : dict con beta_rv, duration_rf, límites y razón de rechazo (si aplica)
    """
    from config import RESTRICCIONES_POR_PERFIL  # import late

    limites = RESTRICCIONES_POR_PERFIL.get(perfil_usuario, {})
    max_duration = float(limites.get("max_duration_modificada", 999.0))
    max_beta_rv  = float(limites.get("max_beta_ponderado_rv",  999.0))

    w = np.asarray(weights, dtype=float)

    beta_num    = 0.0   # numerador beta ponderado (× peso)
    dur_num     = 0.0   # numerador duration ponderada (× peso)
    peso_rv     = 0.0
    peso_rf     = 0.0

    for i, ticker in enumerate(tickers_cartera):
        peso  = float(w[i])
        datos = riesgo_impacto.get(ticker)
        if not datos:
            continue
        tipo  = datos["metrica_riesgo_tipo"]
        valor = float(datos["valor_riesgo"])

        if tipo == "BETA":
            beta_num += peso * valor
            peso_rv  += peso
        elif tipo == "DURATION_MODIFICADA":
            dur_num  += peso * valor
            peso_rf  += peso

    # Promedios ponderados (dentro de cada tramo)
    beta_pond_rv  = (beta_num  / peso_rv)  if peso_rv  > 0 else 0.0
    dur_pond_rf   = (dur_num   / peso_rf)  if peso_rf  > 0 else 0.0

    rechazo: list[str] = []

    if dur_pond_rf > max_duration:
        rechazo.append(
            f"Duration RF={dur_pond_rf:.2f} años > límite {max_duration:.1f} años "
            f"({perfil_usuario})"
        )

    if beta_pond_rv > max_beta_rv:
        rechazo.append(
            f"Beta RV ponderado={beta_pond_rv:.2f} > límite {max_beta_rv:.2f} "
            f"({perfil_usuario})"
        )

    valido = len(rechazo) == 0

    detalle: dict[str, Any] = {
        "beta_ponderado_rv":    round(beta_pond_rv, 4),
        "duration_ponderada_rf": round(dur_pond_rf, 4),
        "peso_rv_total":         round(peso_rv, 4),
        "peso_rf_total":         round(peso_rf, 4),
        "max_beta_rv":           max_beta_rv,
        "max_duration_rf":       max_duration,
        "valido":                valido,
        "razones_rechazo":       rechazo,
    }

    if not valido:
        log.warning(
            "Cartera RECHAZADA para %s: %s", perfil_usuario, " | ".join(rechazo)
        )

    return valido, detalle


# ═════════════════════════════════════════════════════════════════════════════
#  UTILIDADES DE REPORTE
# ═════════════════════════════════════════════════════════════════════════════

def resumen_riesgo_universo(
    riesgo_impacto: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """
    Convierte el dict de riesgo en un DataFrame tabular para visualización.

    Columnas: ticker, metrica, valor_riesgo, benchmark, moneda, fuente.
    Ordenado por tipo (BETA primero) y valor descendente.
    """
    rows = []
    for ticker, datos in riesgo_impacto.items():
        rows.append({
            "ticker":    ticker,
            "metrica":   datos.get("metrica_riesgo_tipo"),
            "valor":     datos.get("valor_riesgo"),
            "benchmark": datos.get("benchmark_asignado"),
            "moneda":    datos.get("exposicion_moneda"),
            "fuente":    datos.get("fuente", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    orden_metrica = {"BETA": 0, "DURATION_MODIFICADA": 1}
    df["_orden"] = df["metrica"].map(orden_metrica).fillna(9)
    df = (
        df.sort_values(["_orden", "valor"], ascending=[True, False])
          .drop(columns="_orden")
          .reset_index(drop=True)
    )
    return df
