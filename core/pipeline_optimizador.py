"""
core/pipeline_optimizador.py — Orquestador del sistema de optimización de carteras.

Flujo completo en 10 etapas:
    1. Construir universo (CEDEAR_INFO + ACCIONES_ARGENTINAS + ON tickers)
    2. Filtrar por perfil del cliente (ética, tipo ETF, sectores)
    3. Descargar / recuperar retornos históricos (yfinance + caché)
    4. Estimar μ (Ledoit-Wolf) y ajustar por TER en ETFs
    5. Calcular métricas de riesgo (beta dual + duration modificada)
    6. Construir constraints SLSQP desde RESTRICCIONES_POR_PERFIL
    7. Ejecutar solver (max_sharpe | min_variance | hrp | erc)
    8. Validar resultado contra perfil (duration, beta, liquidez, vol)
    9. Calcular métricas finales de portafolio (Sharpe, VaR, CVaR, drawdown)
   10. Devolver ResultadoOptimizacion con pesos + métricas + auditoría

Métodos de optimización disponibles
-------------------------------------
    "max_sharpe"   : Tangency portfolio (SLSQP) con todas las restricciones duras
    "min_variance" : Mínima varianza global con restricciones del perfil
    "hrp"          : Hierarchical Risk Parity (sin restricciones SLSQP, post-processing)
    "erc"          : Equal Risk Contribution (SLSQP)
    "objetivo"     : Maximiza retorno sujeto a vol_max del perfil (útil para agresivo)

Clasificación de activos
-------------------------
    RV global  : tickers en CEDEAR_INFO (exchange != "BYMA")
    RV local   : tickers en ACCIONES_ARGENTINAS con exchange == "BYMA"
    RF         : tickers en OBLIGACIONES_NEGOCIABLES
    Los ETFs apalancados se tratan como RV global.

Constraints traducidos desde RESTRICCIONES_POR_PERFIL
-------------------------------------------------------
    max_renta_variable      → sum(w_rv) ≤ max_rv          [ineq]
    min_renta_fija          → sum(w_rf) ≥ min_rf           [ineq]
    max_por_ticker_rv       → bounds per RV ticker (0, max_rv_tick)
    max_por_ticker_rf       → bounds per RF ticker (0, max_rf_tick)
    max_exposicion_local_rv → sum(w_local) ≤ max_local     [ineq]
    volatilidad_max_anual   → w'Σw ≤ vol_max²             [ineq]
    objetivo_retorno_usd    → μ'w ≥ target (si datos_perfil)  [ineq]
    necesidad_liquidez_pct  → sum(w_liquido) ≥ liq_req     [ineq]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ── Tipo literal para métodos ─────────────────────────────────────────────────
MetodoOpt = Literal["max_sharpe", "min_variance", "hrp", "erc", "objetivo"]


# ═════════════════════════════════════════════════════════════════════════════
#  RESULTADO — Dataclass de salida del pipeline
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoOptimizacion:
    """Resultado completo del pipeline de optimización."""

    # ── Pesos ────────────────────────────────────────────────────────────────
    tickers:  list[str]
    pesos:    dict[str, float]          # ticker → peso (suma 1.0)
    metodo:   str
    perfil:   str

    # ── Métricas del portafolio ───────────────────────────────────────────────
    retorno_esperado_anual:   float = 0.0   # μ'w anualizado
    volatilidad_anual:        float = 0.0   # √(w'Σw) anualizado
    sharpe_ratio:             float = 0.0   # (μ - Rf) / σ
    var_95_diario:            float = 0.0   # VaR histórico 95 % diario (pérdida positiva)
    cvar_95_diario:           float = 0.0   # CVaR histórico 95 % diario
    max_drawdown_historico:   float = 0.0   # drawdown máximo en el período

    # ── Riesgo estructural ────────────────────────────────────────────────────
    beta_rv_ponderado:        float = 0.0   # beta promedio pond. de la parte RV
    duration_rf_ponderada:    float = 0.0   # DM promedio pond. de la parte RF

    # ── Descomposición por asset class ────────────────────────────────────────
    peso_rv_total:            float = 0.0
    peso_rf_total:            float = 0.0
    peso_local_rv:            float = 0.0   # fracción dentro de la parte RV

    # ── Validaciones ─────────────────────────────────────────────────────────
    valido_riesgo_perfil:     bool  = True
    valido_liquidez:          bool  = True
    razones_rechazo:          list[str] = field(default_factory=list)

    # ── Auditoría ─────────────────────────────────────────────────────────────
    fecha_optimizacion:       str  = ""
    universo_inicial:         int  = 0
    universo_elegible:        int  = 0
    activos_con_datos:        int  = 0
    solver_success:           bool = True
    solver_message:           str  = ""
    advertencias:             list[str] = field(default_factory=list)


# ═════════════════════════════════════════════════════════════════════════════
#  CLASIFICADOR DE ACTIVOS
# ═════════════════════════════════════════════════════════════════════════════

def _clasificar_activos(
    tickers: list[str],
) -> dict[str, dict[str, Any]]:
    """
    Clasifica cada ticker en:
      tipo: "rv_global" | "rv_local" | "rf"
      exchange, currency (si disponibles)

    Orden de lookup:
        OBLIGACIONES_NEGOCIABLES → BONOS_SOBERANOS → BONOS_CER → CAUCIONES_BYMA
        → ACCIONES_ARGENTINAS → CEDEAR_INFO → ETF_INFO
    """
    try:
        from config import (
            OBLIGACIONES_NEGOCIABLES, ACCIONES_ARGENTINAS,
            CEDEAR_INFO, ETF_INFO,
            BONOS_SOBERANOS, BONOS_CER, CAUCIONES_BYMA,
        )
    except ImportError:
        return {t: {"tipo": "rv_global"} for t in tickers}

    # Todos los tickers RF (corporativo + soberano + CER + cauciones)
    on_keys  = set(OBLIGACIONES_NEGOCIABLES.keys())
    sob_keys = set(BONOS_SOBERANOS.keys())
    cer_keys = set(BONOS_CER.keys())
    cau_keys = set(CAUCIONES_BYMA.keys())
    all_rf   = on_keys | sob_keys | cer_keys | cau_keys

    local_keys = {t for t, m in ACCIONES_ARGENTINAS.items()
                  if isinstance(m, dict) and m.get("exchange") == "BYMA"}

    result: dict[str, dict[str, Any]] = {}
    for t in tickers:
        if t in all_rf:
            # Buscar metadata en la fuente correcta
            if t in on_keys:
                meta = OBLIGACIONES_NEGOCIABLES[t]
                moneda = meta.get("moneda_emision", "USD")
                subtipo = "ON_corporativa"
            elif t in sob_keys:
                meta = BONOS_SOBERANOS[t]
                moneda = meta.get("moneda_emision", "USD")
                subtipo = meta.get("tipo", "BONO_USD")
            elif t in cer_keys:
                meta = BONOS_CER[t]
                moneda = "ARS_CER"
                subtipo = "BONCER"
            else:  # cau_keys
                meta = CAUCIONES_BYMA[t]
                moneda = meta.get("moneda_emision", "ARS")
                subtipo = "CAUCION"
            result[t] = {
                "tipo":     "rf",
                "subtipo":  subtipo,
                "exchange": "BYMA_RF",
                "currency": moneda,
            }
        elif t in local_keys:
            meta = ACCIONES_ARGENTINAS[t]
            result[t] = {
                "tipo":     "rv_local",
                "exchange": "BYMA",
                "currency": "ARS",
            }
        elif t in ACCIONES_ARGENTINAS:
            # ADR-linked (GGAL en NYSE p.ej.) → tratado como rv_global
            meta = ACCIONES_ARGENTINAS[t]
            result[t] = {
                "tipo":     "rv_global",
                "exchange": meta.get("exchange", "NYSE"),
                "currency": meta.get("currency", "USD"),
            }
        elif t in ETF_INFO:
            result[t] = {
                "tipo":     "rv_global",   # ETFs siempre RV global (incluso los sectoriales)
                "exchange": "NYSE_ARCA",
                "currency": "USD",
            }
        else:
            meta = CEDEAR_INFO.get(t, {}) if isinstance(CEDEAR_INFO.get(t), dict) else {}
            result[t] = {
                "tipo":     "rv_global",
                "exchange": meta.get("exchange", ""),
                "currency": meta.get("currency", "USD"),
            }
    return result


# ═════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTOR DE CONSTRAINTS SCIPY
# ═════════════════════════════════════════════════════════════════════════════

def _construir_constraints_perfil(
    tickers:         list[str],
    clasificacion:   dict[str, dict[str, Any]],
    Sigma:           np.ndarray,
    mu:              np.ndarray,
    restricciones:   dict[str, Any],
    datos_perfil:    dict[str, Any] | None,
    *,
    incluir_vol:     bool = True,
    incluir_retorno: bool = True,
    incluir_liquidez: bool = True,
) -> tuple[list[dict], list[tuple[float, float]]]:
    """
    Traduce RESTRICCIONES_POR_PERFIL a formato scipy.optimize.minimize.

    Retorna
    -------
    (constraints_list, bounds_list)
        constraints_list : lista de dicts {"type": "eq"|"ineq", "fun": callable}
        bounds_list      : lista de (lb, ub) por posición en tickers
    """
    n = len(tickers)

    max_rv       = float(restricciones.get("max_renta_variable",    0.80))
    min_rf       = float(restricciones.get("min_renta_fija",        0.20))
    max_tick_rv  = float(restricciones.get("max_por_ticker_rv",     0.15))
    max_tick_rf  = float(restricciones.get("max_por_ticker_rf",     0.15))
    max_local    = float(restricciones.get("max_exposicion_local_rv", 0.30))
    vol_max      = float(restricciones.get("volatilidad_max_anual", 0.99))

    # Índices por tipo
    idx_rv     = [i for i, t in enumerate(tickers) if clasificacion[t]["tipo"] != "rf"]
    idx_rf     = [i for i, t in enumerate(tickers) if clasificacion[t]["tipo"] == "rf"]
    idx_local  = [i for i, t in enumerate(tickers) if clasificacion[t]["tipo"] == "rv_local"]

    constraints: list[dict] = []

    # ── C1: sum(w) = 1 ───────────────────────────────────────────────────────
    constraints.append({
        "type": "eq",
        "fun":  lambda w: float(np.sum(w)) - 1.0,
    })

    # ── C2: RV total ≤ max_rv ────────────────────────────────────────────────
    if idx_rv:
        _idx_rv = list(idx_rv)
        constraints.append({
            "type": "ineq",
            "fun":  lambda w, _i=_idx_rv, _m=max_rv: _m - float(np.sum(w[_i])),
        })

    # ── C3: RF total ≥ min_rf ────────────────────────────────────────────────
    if idx_rf:
        _idx_rf = list(idx_rf)
        constraints.append({
            "type": "ineq",
            "fun":  lambda w, _i=_idx_rf, _m=min_rf: float(np.sum(w[_i])) - _m,
        })

    # ── C4: Local RV ≤ max_local ─────────────────────────────────────────────
    if idx_local:
        _idx_local = list(idx_local)
        constraints.append({
            "type": "ineq",
            "fun":  lambda w, _i=_idx_local, _m=max_local: _m - float(np.sum(w[_i])),
        })

    # ── C5: Volatilidad anual ≤ vol_max ──────────────────────────────────────
    if incluir_vol and vol_max < 0.99:
        _S    = Sigma
        _vmax = vol_max
        constraints.append({
            "type": "ineq",
            "fun":  lambda w, _S=_S, _vm=_vmax: _vm ** 2 - float(w @ _S @ w),
        })

    # ── C6: Retorno esperado ≥ objetivo (si lo define el perfil del cliente) ──
    if incluir_retorno and datos_perfil is not None:
        target = float(datos_perfil.get("objetivo_retorno_usd_anual", 0.0))
        if target > 0.0:
            _mu     = mu
            _target = target
            constraints.append({
                "type": "ineq",
                "fun":  lambda w, _m=_mu, _t=_target: float(_m @ w) - _t,
            })

    # ── C7: Liquidez ≥ necesidad_liquidez_pct ────────────────────────────────
    if incluir_liquidez and datos_perfil is not None:
        liq_req = float(datos_perfil.get("necesidad_liquidez_pct", 0.0))
        if liq_req > 0.0:
            try:
                from config import VOLUMEN_PROMEDIO_BYMA, ADV_LIQUIDEZ_MINIMA
                adv_umbral = float(ADV_LIQUIDEZ_MINIMA)
                idx_liq = [
                    i for i, t in enumerate(tickers)
                    if float(VOLUMEN_PROMEDIO_BYMA.get(t, 0.0)) >= adv_umbral
                ]
                if idx_liq:
                    _il    = list(idx_liq)
                    _lreq  = liq_req
                    constraints.append({
                        "type": "ineq",
                        "fun":  lambda w, _i=_il, _lr=_lreq: float(np.sum(w[_i])) - _lr,
                    })
            except ImportError:
                pass

    # ── Bounds por ticker ────────────────────────────────────────────────────
    bounds: list[tuple[float, float]] = []
    for t in tickers:
        tipo = clasificacion[t]["tipo"]
        ub   = max_tick_rv if tipo != "rf" else max_tick_rf
        bounds.append((0.0, min(ub, 1.0)))

    return constraints, bounds


# ═════════════════════════════════════════════════════════════════════════════
#  MÉTRICAS FINALES DEL PORTAFOLIO
# ═════════════════════════════════════════════════════════════════════════════

def _calcular_metricas_portafolio(
    w:              np.ndarray,
    tickers:        list[str],
    mu:             np.ndarray,
    Sigma:          np.ndarray,
    df_retornos:    pd.DataFrame,
    metricas_rv:    dict[str, Any],
    rf:             float,
) -> dict[str, float]:
    """Calcula Sharpe, VaR, CVaR, drawdown, beta, duration del portafolio."""
    from core.risk_metrics import (
        portfolio_vol_annual,
        historical_var_cvar,
        max_drawdown_from_returns,
    )

    # Retorno y vol del portafolio
    ret_p = float(mu @ w)
    vol_p = portfolio_vol_annual(w, Sigma)
    sharpe = (ret_p - rf) / vol_p if vol_p > 1e-10 else 0.0

    # Retornos históricos del portafolio ponderados
    ret_hist = pd.Series(dtype=float)
    common = [t for t in tickers if t in df_retornos.columns]
    if common:
        w_common = np.array([w[tickers.index(t)] for t in common])
        w_common = w_common / w_common.sum() if w_common.sum() > 0 else w_common
        ret_hist = df_retornos[common] @ w_common

    var_95, cvar_95 = (0.0, 0.0)
    dd = 0.0
    if len(ret_hist) > 10:
        var_95, cvar_95 = historical_var_cvar(ret_hist.values, alpha=0.05)
        dd = max_drawdown_from_returns(ret_hist.values)

    # Beta y duration ponderados
    beta_num, dur_num = 0.0, 0.0
    peso_rv, peso_rf  = 0.0, 0.0

    for i, t in enumerate(tickers):
        peso  = float(w[i])
        riesgo = metricas_rv.get(t, {})
        tipo  = riesgo.get("metrica_riesgo_tipo", "")
        valor = float(riesgo.get("valor_riesgo", 0.0))
        if tipo == "BETA":
            beta_num += peso * valor
            peso_rv  += peso
        elif tipo == "DURATION_MODIFICADA":
            dur_num  += peso * valor
            peso_rf  += peso

    beta_pond = beta_num / peso_rv if peso_rv > 0 else 0.0
    dur_pond  = dur_num  / peso_rf if peso_rf > 0 else 0.0

    return {
        "retorno_esperado_anual": round(ret_p, 4),
        "volatilidad_anual":      round(vol_p, 4),
        "sharpe_ratio":           round(sharpe, 4),
        "var_95_diario":          round(var_95,  4),
        "cvar_95_diario":         round(cvar_95, 4),
        "max_drawdown_historico": round(dd,      4),
        "beta_rv_ponderado":      round(beta_pond, 4),
        "duration_rf_ponderada":  round(dur_pond,  4),
        "peso_rv_total":          round(peso_rv, 4),
        "peso_rf_total":          round(peso_rf, 4),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  POST-PROCESADO HRP (constraints aproximados)
# ═════════════════════════════════════════════════════════════════════════════

def _postprocesar_hrp(
    w:            np.ndarray,
    tickers:      list[str],
    clasificacion: dict[str, dict[str, Any]],
    restricciones: dict[str, Any],
) -> np.ndarray:
    """
    Aplica restricciones del perfil a pesos HRP como post-processing.
    HRP no soporta SLSQP; este método es una aproximación iterativa:
      1. Clip de bounds por ticker
      2. Scale RV/RF para respetar max_rv/min_rf
      3. Renormalizar
    """
    w = w.copy()
    max_tick_rv = float(restricciones.get("max_por_ticker_rv", 0.15))
    max_tick_rf = float(restricciones.get("max_por_ticker_rf", 0.15))
    max_rv      = float(restricciones.get("max_renta_variable", 0.80))

    # 1. Clip por ticker
    for i, t in enumerate(tickers):
        ub = max_tick_rv if clasificacion[t]["tipo"] != "rf" else max_tick_rf
        w[i] = min(w[i], ub)

    w = np.maximum(w, 0.0)
    if w.sum() > 0:
        w = w / w.sum()

    # 2. Scale tramo RV si excede max_rv
    idx_rv = [i for i, t in enumerate(tickers) if clasificacion[t]["tipo"] != "rf"]
    idx_rf = [i for i, t in enumerate(tickers) if clasificacion[t]["tipo"] == "rf"]
    peso_rv_actual = float(np.sum(w[idx_rv])) if idx_rv else 0.0

    if peso_rv_actual > max_rv and idx_rv and idx_rf:
        exceso = peso_rv_actual - max_rv
        # Reducir RV proporcionalmente y trasladar exceso a RF
        factor_rv = max_rv / peso_rv_actual if peso_rv_actual > 0 else 1.0
        for i in idx_rv:
            w[i] *= factor_rv
        # Distribuir exceso en RF proporcionalmente
        w_rf_sum = float(np.sum(w[idx_rf]))
        for i in idx_rf:
            w[i] += exceso * (w[i] / w_rf_sum if w_rf_sum > 0 else 1.0 / len(idx_rf))

    w = np.maximum(w, 0.0)
    total = w.sum()
    return w / total if total > 0 else np.ones(len(tickers)) / len(tickers)


# ═════════════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════

def optimizar_cartera(
    perfil:          str,
    *,
    metodo:          MetodoOpt = "max_sharpe",
    datos_perfil:    dict[str, Any] | None = None,
    universo_override: list[str] | None = None,
    w_previo:        dict[str, float] | None = None,
    lambda_turnover: float = 0.0,
    max_turnover:    float | None = None,
    verbose:         bool = True,
) -> ResultadoOptimizacion:
    """
    Pipeline completo de optimización de carteras.

    Parámetros
    ----------
    perfil           : "CONSERVADOR" | "MODERADO" | "AGRESIVO" | "MUY AGRESIVO"
    metodo           : solver a utilizar (ver docstring del módulo)
    datos_perfil     : dict de PERFIL_INVERSOR_CODIFICADO.  Si None, usa restricciones
                       del perfil sin objetivos adicionales de retorno/liquidez.
    universo_override: lista de tickers a usar en lugar del universo completo.
    w_previo         : pesos actuales del cliente (dict ticker→float) para penalizar
                       turnover o usarlos como punto de partida.
    lambda_turnover  : penalización L1 por turnover en la función objetivo.
    max_turnover     : restricción dura de turnover L1 máximo.
    verbose          : imprime progreso de cada etapa.

    Retorna
    -------
    ResultadoOptimizacion
    """
    t_start = datetime.now(timezone.utc)
    advertencias: list[str] = []

    def _log(msg: str) -> None:
        if verbose:
            print(f"  [OPT] {msg}")
        log.info(msg)

    # ── Imports centralizados ─────────────────────────────────────────────────
    from config import (
        RESTRICCIONES_POR_PERFIL, PARAMETROS_HISTORICO, MACRO_AR,
        CEDEAR_INFO, ACCIONES_ARGENTINAS, OBLIGACIONES_NEGOCIABLES,
        BONOS_SOBERANOS, BONOS_CER, CAUCIONES_BYMA,
    )
    from core.filtros_cartera import filtrar_universo_por_perfil, ajustar_mu_por_ter
    from core.historico_retornos import obtener_matriz_retornos_limpios
    from core.metricas_riesgo import calcular_metricas_riesgo_universo, validar_riesgo_perfil
    from core.filtros_cartera import ajustar_restriccion_liquidez_por_cliente
    from core.portfolio_optimization import (
        OptimizationProblem,
        estimate_mu_sigma_mle,
        solve_max_sharpe,
        solve_minimum_variance,
        solve_equal_risk_contribution,
        solve_max_return_tracking_error,
    )
    from core.hrp_weights import hrp_weights

    restricciones = RESTRICCIONES_POR_PERFIL.get(perfil)
    if restricciones is None:
        raise ValueError(
            f"Perfil '{perfil}' no encontrado. "
            f"Opciones: {list(RESTRICCIONES_POR_PERFIL.keys())}"
        )

    rf = float(MACRO_AR.get("risk_free_rate_us", 0.04))

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 1 — Universo inicial
    # ═══════════════════════════════════════════════════════════════════════
    # Todas las fuentes RF disponibles (para lookup en override y clasificación)
    _ALL_RF: dict[str, Any] = {
        **OBLIGACIONES_NEGOCIABLES,
        **BONOS_SOBERANOS,
        **BONOS_CER,
        **CAUCIONES_BYMA,
    }

    if universo_override:
        universo_dict: dict[str, Any] = {}
        for t in universo_override:
            # Buscar en todas las fuentes: RV primero, luego RF
            for src in [CEDEAR_INFO, ACCIONES_ARGENTINAS, _ALL_RF]:
                if t in src and isinstance(src[t], dict):
                    universo_dict[t] = src[t]
                    break
            else:
                universo_dict[t] = {}
    else:
        universo_dict = {
            **{t: m for t, m in CEDEAR_INFO.items() if isinstance(m, dict)},
            **{t: m for t, m in ACCIONES_ARGENTINAS.items() if isinstance(m, dict)},
            # RF incluido solo si tiene retornos históricos disponibles en BYMA
            # (por defecto excluido del universo completo hasta integrar feed de precios BYMA)
            # Para incluir RF explicitamente: usar universo_override=["AL30","GD30",...]
        }

    universo_inicial = len(universo_dict)
    _log(f"Etapa 1: {universo_inicial} activos en el universo inicial")

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 2 — Filtro por perfil
    # ═══════════════════════════════════════════════════════════════════════
    elegibles, excluidos = filtrar_universo_por_perfil(
        list(universo_dict.keys()), datos_perfil or restricciones, verbose=False
    )
    universo_elegible = len(elegibles)
    _log(f"Etapa 2: {universo_elegible} elegibles, {len(excluidos)} excluidos "
         f"({', '.join(list(excluidos.keys())[:5])}{'...' if len(excluidos) > 5 else ''})")

    if universo_elegible < 3:
        raise ValueError(
            f"Solo {universo_elegible} activos elegibles tras filtros del perfil — "
            "universo insuficiente para optimización"
        )

    universo_elegible_dict = {t: universo_dict.get(t, {}) for t in elegibles}

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 3 — Retornos históricos
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 3: descargando retornos históricos...")
    df_retornos = obtener_matriz_retornos_limpios(
        universo_elegible_dict, PARAMETROS_HISTORICO, verbose=verbose
    )

    if df_retornos.empty or df_retornos.shape[1] < 3:
        raise ValueError(
            "Matriz de retornos vacía o con menos de 3 activos — "
            "verificar conectividad a Yahoo Finance"
        )

    tickers_activos = list(df_retornos.columns)
    activos_con_datos = len(tickers_activos)
    _log(f"Etapa 3: {activos_con_datos} activos con datos suficientes "
         f"({universo_elegible - activos_con_datos} descartados por min_obs)")

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 4 — μ y Σ (Ledoit-Wolf) + ajuste TER
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 4: estimando mu y Sigma (Ledoit-Wolf)...")
    mu_arr, Sigma_arr = estimate_mu_sigma_mle(
        df_retornos.values,
        annualization=int(PARAMETROS_HISTORICO.get("ventana_dias", 252)),
        ledoit_wolf=True,
    )
    mu_series = pd.Series(mu_arr, index=tickers_activos)

    # Deducir TER de ETFs del retorno esperado
    mu_series = ajustar_mu_por_ter(mu_series)
    mu_arr    = mu_series.values
    _log(f"Etapa 4: mu_medio={float(mu_arr.mean()):.2%}  vol_media={float(np.sqrt(np.diag(Sigma_arr)).mean()):.2%}")

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 5 — Métricas de riesgo (beta + duration)
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 5: calculando métricas de riesgo estructurado...")
    universo_rv = {t: universo_elegible_dict[t] for t in tickers_activos
                   if t not in _ALL_RF}
    universo_rf = {t: _ALL_RF[t] for t in tickers_activos
                   if t in _ALL_RF}

    metricas_riesgo = calcular_metricas_riesgo_universo(
        universo_rv, universo_rf,
        PARAMETROS_HISTORICO,
        df_retornos,
        verbose=False,
    )

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 6 — Constraints del perfil
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 6: construyendo constraints del perfil...")
    clasificacion = _clasificar_activos(tickers_activos)

    constraints, bounds = _construir_constraints_perfil(
        tickers=tickers_activos,
        clasificacion=clasificacion,
        Sigma=Sigma_arr,
        mu=mu_arr,
        restricciones=restricciones,
        datos_perfil=datos_perfil,
    )
    n = len(tickers_activos)
    _log(f"Etapa 6: {len(constraints)} constraints + {n} bounds generados")

    # Vector de pesos anteriores si se pasa histórico
    wp_arr: np.ndarray | None = None
    if w_previo:
        wp_arr = np.array([float(w_previo.get(t, 0.0)) for t in tickers_activos])
        s = wp_arr.sum()
        if s > 0:
            wp_arr = wp_arr / s

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 7 — Solver
    # ═══════════════════════════════════════════════════════════════════════
    _log(f"Etapa 7: ejecutando solver '{metodo}'...")

    problema = OptimizationProblem(
        mu=mu_arr,
        Sigma=Sigma_arr,
        rf=rf,
        long_only=True,
    )

    solver_success = True
    solver_message = ""
    w_opt          = np.ones(n, dtype=float) / n   # fallback: igual peso

    if metodo == "max_sharpe":
        # Inyectar constraints del perfil en el problema
        result_raw = _solve_max_sharpe_con_perfil(
            problema, constraints, bounds, wp_arr,
            lambda_turnover, max_turnover,
        )
        w_opt          = result_raw["weights"]
        solver_success = result_raw["success"]
        solver_message = result_raw["message"]

    elif metodo == "min_variance":
        result_raw = _solve_min_variance_con_perfil(
            problema, constraints, bounds,
        )
        w_opt          = result_raw["weights"]
        solver_success = result_raw["success"]
        solver_message = result_raw["message"]

    elif metodo == "hrp":
        w_hrp = hrp_weights(Sigma_arr)
        w_opt = _postprocesar_hrp(w_hrp, tickers_activos, clasificacion, restricciones)
        solver_success = True
        solver_message = "hrp + post-processing perfil"
        advertencias.append("HRP: restricciones aplicadas como post-processing (aproximación)")

    elif metodo == "erc":
        from core.hrp_weights import solve_erc
        w_erc  = solve_erc(Sigma_arr)
        w_opt  = _postprocesar_hrp(w_erc, tickers_activos, clasificacion, restricciones)
        solver_success = True
        solver_message = "erc + post-processing perfil"
        advertencias.append("ERC: restricciones aplicadas como post-processing (aproximación)")

    elif metodo == "objetivo":
        # Max retorno sujeto a vol_max del perfil como TE vs portafolio igual
        vol_max = float(restricciones.get("volatilidad_max_anual", 0.30))
        w_bench = np.ones(n) / n
        res_obj = solve_max_return_tracking_error(
            problema, w_bench, vol_max,
            w_prev=wp_arr,
            lambda_turnover_penalty=lambda_turnover,
            max_turnover_l1=max_turnover,
        )
        w_opt          = res_obj.weights
        solver_success = res_obj.success
        solver_message = res_obj.message

    else:
        raise ValueError(f"Método '{metodo}' no reconocido")

    # Fallback si el solver falló
    if not solver_success:
        advertencias.append(
            f"Solver '{metodo}' no convergió ({solver_message}). "
            "Intentando mínima varianza como fallback..."
        )
        log.warning("Solver %s falló. Fallback a min_variance.", metodo)
        res_mv = _solve_min_variance_con_perfil(problema, constraints, bounds)
        if res_mv["success"]:
            w_opt = res_mv["weights"]
            solver_message += " | fallback:min_variance"
        else:
            advertencias.append("Min variance también falló — usando pesos iguales")
            w_opt = np.ones(n) / n
            solver_message += " | fallback:equal_weight"

    _log(f"Etapa 7: solver {'OK' if solver_success else 'FALLBACK'}  "
         f"activos non-zero: {int((w_opt > 1e-4).sum())}")

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 8 — Validaciones
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 8: validando resultado...")
    valido_riesgo, detalle_riesgo = validar_riesgo_perfil(
        w_opt, tickers_activos, metricas_riesgo, perfil
    )
    valido_liquidez, detalle_liq = ajustar_restriccion_liquidez_por_cliente(
        w_opt, tickers_activos, datos_perfil or {}
    )

    razones_rechazo = list(detalle_riesgo.get("razones_rechazo", []))
    if not valido_liquidez and detalle_liq.get("deficit_pct", 0) > 0:
        razones_rechazo.append(
            f"Liquidez insuficiente: {detalle_liq['liquido_pct']:.1%} "
            f"< requerido {detalle_liq['necesidad_pct']:.1%}"
        )

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 9 — Métricas del portafolio
    # ═══════════════════════════════════════════════════════════════════════
    _log("Etapa 9: calculando métricas finales...")
    metricas = _calcular_metricas_portafolio(
        w_opt, tickers_activos, mu_arr, Sigma_arr,
        df_retornos, metricas_riesgo, rf,
    )

    # ── Peso local_rv como fracción del total RV ──────────────────────────────
    idx_local = [i for i, t in enumerate(tickers_activos)
                 if clasificacion[t]["tipo"] == "rv_local"]
    peso_local = float(np.sum(w_opt[[i for i in idx_local]])) if idx_local else 0.0

    # ═══════════════════════════════════════════════════════════════════════
    #  ETAPA 10 — Construir resultado
    # ═══════════════════════════════════════════════════════════════════════
    pesos_dict = {
        t: round(float(w_opt[i]), 6)
        for i, t in enumerate(tickers_activos)
        if float(w_opt[i]) > 1e-5      # filtrar posiciones despreciables
    }

    resultado = ResultadoOptimizacion(
        tickers=tickers_activos,
        pesos=pesos_dict,
        metodo=metodo,
        perfil=perfil,
        **metricas,
        peso_local_rv=round(peso_local, 4),
        valido_riesgo_perfil=valido_riesgo,
        valido_liquidez=valido_liquidez,
        razones_rechazo=razones_rechazo,
        fecha_optimizacion=t_start.strftime("%Y-%m-%d %H:%M UTC"),
        universo_inicial=universo_inicial,
        universo_elegible=universo_elegible,
        activos_con_datos=activos_con_datos,
        solver_success=solver_success,
        solver_message=solver_message,
        advertencias=advertencias,
    )

    _log(
        f"Etapa 10: DONE — Sharpe={resultado.sharpe_ratio:.3f}  "
        f"Vol={resultado.volatilidad_anual:.1%}  "
        f"Ret={resultado.retorno_esperado_anual:.1%}  "
        f"Valido={'SI' if (valido_riesgo and valido_liquidez) else 'CON ALERTAS'}"
    )
    return resultado


# ═════════════════════════════════════════════════════════════════════════════
#  SOLVERS INTERNOS CON CONSTRAINTS DEL PERFIL
# ═════════════════════════════════════════════════════════════════════════════

def _solve_max_sharpe_con_perfil(
    problema:       "OptimizationProblem",
    constraints:    list[dict],
    bounds:         list[tuple],
    wp:             "np.ndarray | None",
    lam:            float,
    max_turn:       "float | None",
) -> dict:
    """Max Sharpe con constraints completos del perfil inyectados en SLSQP."""
    from scipy.optimize import minimize
    from core.portfolio_optimization import regularize_sigma

    n   = problema.mu.shape[0]
    S   = regularize_sigma(problema.Sigma, problema.ridge)
    mu_ex = problema.mu - problema.rf

    # Agregar turnover como restricción dura si se pide
    cons = list(constraints)
    if wp is not None and max_turn is not None:
        _wp, _mt = wp, float(max_turn)
        cons.append({
            "type": "ineq",
            "fun": lambda w, _wp=_wp, _mt=_mt: _mt - float(np.sum(np.abs(w - _wp))),
        })

    def neg_sharpe(w: np.ndarray) -> float:
        w = np.maximum(w, 0.0)
        s = w.sum()
        if s <= 0:
            return 1e9
        w = w / s
        vol = float(np.sqrt(max(float(w @ S @ w), 1e-18)))
        ret = float(mu_ex @ w)
        if vol < 1e-12:
            return 1e9
        pen = 0.0
        if wp is not None and lam > 0:
            pen = lam * float(np.sum(np.abs(w - wp)))
        return -(ret / vol) + pen

    w0  = wp if wp is not None else np.ones(n) / n
    res = minimize(
        neg_sharpe, w0,
        method="SLSQP",
        bounds=bounds,
        constraints=tuple(cons),
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    w = np.maximum(np.asarray(res.x, dtype=float), 0.0)
    if w.sum() > 0:
        w = w / w.sum()
    return {"weights": w, "success": bool(res.success), "message": str(res.message)}


def _solve_min_variance_con_perfil(
    problema:    "OptimizationProblem",
    constraints: list[dict],
    bounds:      list[tuple],
) -> dict:
    """Mínima varianza con constraints del perfil."""
    from scipy.optimize import minimize
    from core.portfolio_optimization import regularize_sigma

    n = problema.mu.shape[0]
    S = regularize_sigma(problema.Sigma, problema.ridge)

    def objective(w: np.ndarray) -> float:
        return float(w @ S @ w)

    w0  = np.ones(n) / n
    res = minimize(
        objective, w0,
        method="SLSQP",
        bounds=bounds,
        constraints=tuple(constraints),
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    w = np.asarray(res.x, dtype=float)
    if w.sum() > 0:
        w = w / w.sum()
    return {"weights": w, "success": bool(res.success), "message": str(res.message)}


# ═════════════════════════════════════════════════════════════════════════════
#  REPORTE TABULAR
# ═════════════════════════════════════════════════════════════════════════════

def reporte_cartera(resultado: ResultadoOptimizacion) -> pd.DataFrame:
    """
    Convierte ResultadoOptimizacion en DataFrame tabular para visualización.
    Columnas: ticker, peso_pct, tipo_activo, retorno_contribucion.
    """
    clasificacion = _clasificar_activos(resultado.tickers)
    mu_total = resultado.retorno_esperado_anual

    rows = []
    for t, w in sorted(resultado.pesos.items(), key=lambda x: -x[1]):
        tipo = clasificacion.get(t, {}).get("tipo", "rv_global")
        tipo_label = {"rv_global": "RV Internacional",
                      "rv_local":  "RV Argentina",
                      "rf":        "Renta Fija"}.get(tipo, tipo)
        rows.append({
            "ticker":        t,
            "peso_pct":      round(w * 100, 2),
            "tipo_activo":   tipo_label,
        })

    df = pd.DataFrame(rows)
    return df


def resumen_ejecutivo(resultado: ResultadoOptimizacion) -> dict[str, Any]:
    """
    Resumen en un solo dict para cabecera de reporte o log de auditoría.
    """
    estado = "VALIDA" if (resultado.valido_riesgo_perfil and resultado.valido_liquidez) else "CON_ALERTAS"
    return {
        "perfil":              resultado.perfil,
        "metodo":              resultado.metodo,
        "estado":              estado,
        "n_activos":           len(resultado.pesos),
        "retorno_anual_pct":   round(resultado.retorno_esperado_anual * 100, 2),
        "volatilidad_anual_pct": round(resultado.volatilidad_anual * 100, 2),
        "sharpe":              round(resultado.sharpe_ratio, 3),
        "var_95_diario_pct":   round(resultado.var_95_diario * 100, 2),
        "max_drawdown_pct":    round(resultado.max_drawdown_historico * 100, 2),
        "beta_rv":             resultado.beta_rv_ponderado,
        "duration_rf_anos":    resultado.duration_rf_ponderada,
        "rv_pct":              round(resultado.peso_rv_total * 100, 1),
        "rf_pct":              round(resultado.peso_rf_total * 100, 1),
        "rv_local_pct":        round(resultado.peso_local_rv * 100, 1),
        "razones_rechazo":     resultado.razones_rechazo,
        "advertencias":        resultado.advertencias,
        "fecha":               resultado.fecha_optimizacion,
    }
