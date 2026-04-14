from __future__ import annotations

import numpy as np


def calcular_aporte_necesario(
    capital_actual: float,
    objetivo_usd: float,
    n_años: int,
    rendimiento_anual: float,
) -> float:
    """
    Aporte mensual necesario para alcanzar objetivo_usd en n_años.
    Fórmula: despeja PMT de FV = PV*(1+rm)^n + PMT*((1+rm)^n - 1)/rm
    """
    rm  = (1.0 + float(rendimiento_anual)) ** (1.0 / 12.0) - 1.0
    n   = int(n_años * 12)
    fv  = float(capital_actual) * (1.0 + rm) ** n
    if objetivo_usd <= fv:
        return 0.0
    den = (1.0 + rm) ** n - 1.0
    return float((objetivo_usd - fv) * rm / den) if abs(den) > 1e-12 else 0.0


def _daily_to_monthly(r_diarios: np.ndarray) -> np.ndarray:
    """
    Agrupa retornos diarios en retornos mensuales compuestos
    usando ventanas de 21 días de trading.
    """
    r       = np.asarray(r_diarios, dtype=float)
    ventana = 21
    n_meses = len(r) // ventana
    if n_meses == 0:
        return np.array([(1.0 + r).prod() - 1.0]) if r.size else np.array([0.005])
    meses = []
    for i in range(n_meses):
        bloque = r[i * ventana:(i + 1) * ventana]
        meses.append((1.0 + bloque).prod() - 1.0)
    return np.array(meses, dtype=float)


def _simulate_retirement_montecarlo(
    aporte_mensual: float,
    n_meses_acum: int,
    retiro_mensual: float,
    n_meses_desacum: int,
    retornos_diarios: np.ndarray,
    n_sim: int = 5000,
    *,
    capital_inicial: float = 0.0,
    seed: int = 42,
    objetivo_umbral_usd: float | None = None,
) -> dict:
    """
    Simulación Montecarlo de retiro.
    p10/p50/p90 = patrimonio final al terminar la fase de desacumulación.
    prob_no_agotar = fracción de simulaciones con capital final > 0.
    Bootstrap sobre retornos MENSUALES (convertidos desde diarios con ventanas de 21 días).
    capital_inicial: patrimonio al inicio de la fase de acumulación (USD).
    objetivo_umbral_usd: si se informa, se calcula prob. de final >= umbral.
    """
    rng = np.random.default_rng(seed=int(seed))
    r_mensual = _daily_to_monthly(np.asarray(retornos_diarios, dtype=float))
    if r_mensual.size == 0:
        r_mensual = np.array([0.005])

    total_meses = n_meses_acum + n_meses_desacum
    vals = np.empty(n_sim, dtype=float)
    cap0 = float(capital_inicial)

    for i in range(n_sim):
        idx   = rng.integers(0, len(r_mensual), size=total_meses)
        draws = r_mensual[idx]
        cap   = cap0
        for t in range(n_meses_acum):
            cap = (cap + aporte_mensual) * (1.0 + draws[t])
        for t in range(n_meses_desacum):
            cap = (cap - retiro_mensual) * (1.0 + draws[n_meses_acum + t])
        vals[i] = cap

    out = {
        "p10":            float(np.percentile(vals, 10)),
        "p50":            float(np.percentile(vals, 50)),
        "p90":            float(np.percentile(vals, 90)),
        "prob_no_agotar": float(np.mean(vals > 0)),
    }
    if objetivo_umbral_usd is not None and float(objetivo_umbral_usd) > 0:
        out["prob_supera_objetivo"] = float(np.mean(vals >= float(objetivo_umbral_usd)))
    return out


def serie_patrimonio_mensual(
    capital_inicial_usd: float = 0.0,
    aporte_mensual_usd: float = 0.0,
    retorno_anual: float = 0.0,
    meses: int = 0,
) -> list[float]:
    """
    Patrimonio al cierre de cada mes (1..meses), determinístico, mismo compuesto que _simulate_retirement_simple.
    """
    rm = (1.0 + float(retorno_anual)) ** (1.0 / 12.0) - 1.0
    cap = float(capital_inicial_usd)
    ap = float(aporte_mensual_usd)
    out: list[float] = []
    for _ in range(int(max(0, meses))):
        cap = (cap + ap) * (1.0 + rm)
        out.append(float(cap))
    return out


def _simulate_retirement_simple(
    capital_inicial_usd: float = 0.0,
    aporte_mensual_usd: float = 0.0,
    retorno_anual: float = 0.0,
    meses: int = 0,
) -> dict:
    """Proyección determinística: aporte mensual + retorno anual compuesto mensual."""
    rm = (1.0 + float(retorno_anual)) ** (1.0 / 12.0) - 1.0
    cap = float(capital_inicial_usd)
    ap = float(aporte_mensual_usd)
    for _ in range(int(max(0, meses))):
        cap = (cap + ap) * (1.0 + rm)
    return {"capital_final_usd": float(cap)}


def simulate_retirement(
    aporte_mensual: float | None = None,
    n_meses_acum: int | None = None,
    retiro_mensual: float | None = None,
    n_meses_desacum: int | None = None,
    retornos_diarios: np.ndarray | None = None,
    n_sim: int = 5000,
    *,
    capital_inicial_usd: float | None = None,
    aporte_mensual_usd: float | None = None,
    retorno_anual: float | None = None,
    meses: int | None = None,
    objetivo_umbral_usd: float | None = None,
    mc_seed: int = 42,
) -> dict:
    """
    Montecarlo si `retornos_diarios` está presente; si no, proyección simple
    cuando se pasan los kwargs de capital/meses/retorno.
    """
    if retornos_diarios is not None:
        return _simulate_retirement_montecarlo(
            float(aporte_mensual or 0.0),
            int(n_meses_acum or 0),
            float(retiro_mensual or 0.0),
            int(n_meses_desacum or 0),
            retornos_diarios,
            n_sim=n_sim,
            capital_inicial=float(capital_inicial_usd or 0.0),
            seed=int(mc_seed),
            objetivo_umbral_usd=objetivo_umbral_usd,
        )
    simple_args = (
        capital_inicial_usd is not None
        or meses is not None
        or retorno_anual is not None
        or aporte_mensual_usd is not None
    )
    if simple_args:
        amu = float(
            aporte_mensual_usd
            if aporte_mensual_usd is not None
            else (aporte_mensual or 0.0)
        )
        return _simulate_retirement_simple(
            capital_inicial_usd=float(capital_inicial_usd or 0.0),
            aporte_mensual_usd=amu,
            retorno_anual=float(retorno_anual or 0.0),
            meses=int(meses or 0),
        )
    arr = np.asarray(retornos_diarios if retornos_diarios is not None else [], dtype=float)
    return _simulate_retirement_montecarlo(
        float(aporte_mensual or 0.0),
        int(n_meses_acum or 0),
        float(retiro_mensual or 0.0),
        int(n_meses_desacum or 0),
        arr,
        n_sim=n_sim,
        capital_inicial=float(capital_inicial_usd or 0.0),
        seed=int(mc_seed),
        objetivo_umbral_usd=objetivo_umbral_usd,
    )