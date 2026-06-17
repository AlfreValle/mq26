"""
core/regime_detection.py — Detección de régimen de volatilidad (crisis vs normal).

Metodología:
  - Volatilidad rolling en ventana corta (21 días) y larga (63 días).
  - Régimen se clasifica por terciles de la distribución histórica de vol rolling:
      tercil inferior  → LOW_VOL
      tercil medio     → NORMAL
      tercil superior  → CRISIS
  - Σ_crisis y Σ_normal se estiman por separado usando solo los días de cada régimen.
  - No usa modelos probabilísticos (no HMM, no GMM) — diseño deliberado para
    robustez con muestras cortas y reproducibilidad.

Contrato:
  - Entrada: DataFrame de retornos (T × n), ventana rolling, umbral de terciles.
  - Salida: serie de etiquetas por fecha + matrices Σ por régimen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

# ─── Tipos ────────────────────────────────────────────────────────────────────

class Regimen(str, Enum):
    LOW_VOL = "LOW_VOL"
    NORMAL  = "NORMAL"
    CRISIS  = "CRISIS"
    UNKNOWN = "UNKNOWN"   # períodos con datos insuficientes para calcular vol


@dataclass
class RegimeResult:
    """
    Resultado del análisis de régimen para una serie de retornos.

    etiquetas          : pd.Series[str] con régimen por fecha.
    vol_rolling        : pd.Series[float] de volatilidad rolling anualizada.
    tercil_bajo        : umbral inferior (Q33) de vol_rolling.
    tercil_alto        : umbral superior (Q67) de vol_rolling.
    sigma_normal       : Σ estimada con los retornos del régimen NORMAL (n × n).
    sigma_crisis       : Σ estimada con los retornos del régimen CRISIS (n × n).
    sigma_low_vol      : Σ estimada con los retornos del régimen LOW_VOL (n × n).
    n_dias_por_regimen : dict {regimen: conteo de días}.
    regimen_actual     : régimen del último dato disponible.
    params             : parámetros usados en el cálculo.
    """
    etiquetas:          pd.Series
    vol_rolling:        pd.Series
    tercil_bajo:        float
    tercil_alto:        float
    sigma_normal:       np.ndarray
    sigma_crisis:       np.ndarray
    sigma_low_vol:      np.ndarray
    n_dias_por_regimen: dict[str, int]
    regimen_actual:     Regimen
    tickers:            list[str]
    params:             dict[str, Any] = field(default_factory=dict)


# ─── Funciones internas ───────────────────────────────────────────────────────

def _vol_rolling_portfolio(
    returns: pd.DataFrame,
    ventana: int,
    annualization: int,
) -> pd.Series:
    """
    Volatilidad rolling del portafolio equiponderado (proxy de mercado).
    Anualizada con raíz del factor de anualización.
    """
    w = np.ones(returns.shape[1]) / returns.shape[1]
    r_p = returns.values @ w
    r_p_s = pd.Series(r_p, index=returns.index)
    vol = r_p_s.rolling(ventana, min_periods=max(ventana // 2, 5)).std() * np.sqrt(annualization)
    return vol


def _sigma_para_mascara(
    returns: pd.DataFrame,
    mascara: pd.Series,
    ridge: float = 1e-6,
) -> np.ndarray:
    """
    Calcula Σ de covarianza anualizada solo para los índices donde mascara==True.
    Si hay < 10 obs devuelve Σ = I (matriz identidad escalada).
    """
    sub = returns[mascara.reindex(returns.index, fill_value=False)]
    n = returns.shape[1]
    if len(sub) < 10:
        return np.eye(n) * 1e-4
    cov = np.cov(sub.values.T, bias=False) * 252.0 + ridge * np.eye(n)
    return cov


# ─── API pública ──────────────────────────────────────────────────────────────

def detectar_regimen(
    returns: pd.DataFrame,
    *,
    ventana_corta: int = 21,
    ventana_larga: int = 63,
    annualization: int = 252,
    q_bajo: float = 0.33,
    q_alto: float = 0.67,
    ridge: float = 1e-6,
    usar_ventana: str = "corta",
) -> RegimeResult:
    """
    Clasifica cada fecha en un régimen de volatilidad (LOW_VOL / NORMAL / CRISIS).

    Parámetros
    ----------
    returns       : DataFrame (T × n) de retornos diarios, columnas = tickers.
    ventana_corta : ventana corta para clasificación (default 21 días = 1 mes).
    ventana_larga : ventana larga para Σ por régimen (default 63 días = 1 trimestre).
    annualization : factor de anualización (default 252).
    q_bajo        : percentil inferior para tercil bajo (default 0.33).
    q_alto        : percentil superior para tercil alto (default 0.67).
    ridge         : regularización diagonal para Σ.
    usar_ventana  : "corta" usa ventana_corta para clasificar; "larga" usa ventana_larga.

    Retorna
    -------
    RegimeResult con etiquetas, umbrales, matrices Σ y régimen actual.
    """
    returns = returns.dropna(axis=0, how="any")
    tickers = list(returns.columns)

    ventana_clasif = ventana_corta if usar_ventana == "corta" else ventana_larga
    vol_rolling = _vol_rolling_portfolio(returns, ventana_clasif, annualization)

    # Terciles sobre valores válidos (no NaN)
    vol_valida = vol_rolling.dropna()
    if len(vol_valida) < 10:
        # Serie insuficiente — todo UNKNOWN
        n = len(tickers)
        sigma_eye = np.eye(n) * 1e-4
        etiq = pd.Series(Regimen.UNKNOWN.value, index=returns.index)
        return RegimeResult(
            etiquetas          = etiq,
            vol_rolling        = vol_rolling,
            tercil_bajo        = float("nan"),
            tercil_alto        = float("nan"),
            sigma_normal       = sigma_eye,
            sigma_crisis       = sigma_eye,
            sigma_low_vol      = sigma_eye,
            n_dias_por_regimen = {r.value: 0 for r in Regimen},
            regimen_actual     = Regimen.UNKNOWN,
            tickers            = tickers,
            params             = {"error": "insuficiente_datos"},
        )

    t_bajo = float(np.nanpercentile(vol_valida.values, q_bajo * 100))
    t_alto = float(np.nanpercentile(vol_valida.values, q_alto * 100))

    def _clasificar(v: float) -> str:
        if np.isnan(v):
            return Regimen.UNKNOWN.value
        if v <= t_bajo:
            return Regimen.LOW_VOL.value
        if v <= t_alto:
            return Regimen.NORMAL.value
        return Regimen.CRISIS.value

    etiquetas = vol_rolling.map(_clasificar)

    # Σ por régimen
    mask_normal   = etiquetas == Regimen.NORMAL.value
    mask_crisis   = etiquetas == Regimen.CRISIS.value
    mask_low      = etiquetas == Regimen.LOW_VOL.value

    sigma_normal   = _sigma_para_mascara(returns, mask_normal,  ridge)
    sigma_crisis   = _sigma_para_mascara(returns, mask_crisis,  ridge)
    sigma_low_vol  = _sigma_para_mascara(returns, mask_low,     ridge)

    n_por_regimen: dict[str, int] = {r.value: int((etiquetas == r.value).sum()) for r in Regimen}

    regimen_actual_str = etiquetas.iloc[-1] if len(etiquetas) > 0 else Regimen.UNKNOWN.value
    try:
        regimen_actual = Regimen(regimen_actual_str)
    except ValueError:
        regimen_actual = Regimen.UNKNOWN

    return RegimeResult(
        etiquetas          = etiquetas,
        vol_rolling        = vol_rolling,
        tercil_bajo        = t_bajo,
        tercil_alto        = t_alto,
        sigma_normal       = sigma_normal,
        sigma_crisis       = sigma_crisis,
        sigma_low_vol      = sigma_low_vol,
        n_dias_por_regimen = n_por_regimen,
        regimen_actual     = regimen_actual,
        tickers            = tickers,
        params             = {
            "ventana_clasif":  ventana_clasif,
            "ventana_larga":   ventana_larga,
            "annualization":   annualization,
            "q_bajo":          q_bajo,
            "q_alto":          q_alto,
            "ridge":           ridge,
            "usar_ventana":    usar_ventana,
            "T_total":         len(returns),
        },
    )


def sigma_segun_regimen(
    result: RegimeResult,
    regimen: Regimen | str | None = None,
) -> np.ndarray:
    """
    Devuelve la matriz Σ correspondiente al régimen indicado.
    Si regimen es None, usa result.regimen_actual.
    Útil para stress testing o proyecciones condicionadas al régimen.
    """
    if regimen is None:
        regimen = result.regimen_actual
    if isinstance(regimen, str):
        try:
            regimen = Regimen(regimen)
        except ValueError:
            regimen = Regimen.UNKNOWN

    if regimen == Regimen.CRISIS:
        return result.sigma_crisis
    if regimen == Regimen.LOW_VOL:
        return result.sigma_low_vol
    return result.sigma_normal  # NORMAL o UNKNOWN → usa sigma_normal


def resumen_regimen(result: RegimeResult) -> dict[str, Any]:
    """Dict plano para logs o tabla UI."""
    total = max(sum(result.n_dias_por_regimen.values()), 1)
    return {
        "regimen_actual":    result.regimen_actual.value,
        "vol_actual_ann":    round(float(result.vol_rolling.iloc[-1]), 4) if len(result.vol_rolling) > 0 else None,
        "tercil_bajo_ann":   round(result.tercil_bajo, 4),
        "tercil_alto_ann":   round(result.tercil_alto, 4),
        "pct_crisis":        round(result.n_dias_por_regimen.get(Regimen.CRISIS.value, 0) / total, 4),
        "pct_normal":        round(result.n_dias_por_regimen.get(Regimen.NORMAL.value, 0) / total, 4),
        "pct_low_vol":       round(result.n_dias_por_regimen.get(Regimen.LOW_VOL.value, 0) / total, 4),
        "n_dias_total":      total,
        **{f"n_{k.lower()}": v for k, v in result.n_dias_por_regimen.items()},
    }
