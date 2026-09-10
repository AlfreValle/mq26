"""
retiro_proyeccion.py — Motor de planificación de retiro MQ26.

Fusiona las capacidades de la calculadora BDI (Clásica / Metas / Monte Carlo)
con los datos REALES de la cartera activa del cliente:
  · capital_inicial  ← valor actual USD de la cartera
  · retorno          ← CAGR histórico calculado por cartera_service
  · Monte Carlo      ← bootstrap sobre retornos diarios reales (no distribución normal)

Dependencias internas: core.retirement_goal (ya existente)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ─── TIPOS DE RESULTADO ───────────────────────────────────────────────────────

@dataclass
class ProyeccionClasica:
    """Proyección determinística año a año."""
    capital_final: float
    aportes_totales: float       # incluye capital_inicial
    intereses_ganados: float
    ingreso_mensual_4pct: float
    retorno_acumulado_pct: float
    df_anual: pd.DataFrame       # columnas: anio, saldo, aportes_acum, intereses_acum


@dataclass
class ResultadoMetas:
    """Modo Metas — regla del 4% de Bengen."""
    ingreso_meta_mensual: float
    tasa_retiro: float           # p.ej. 0.04
    capital_necesario: float     # = ingreso_meta * 12 / tasa_retiro
    capital_proyectado: float
    pct_meta_cubierta: float     # capital_proyectado / capital_necesario * 100
    meta_alcanzada: bool
    sugerencias: dict            # aporte_necesario, plazo_necesario, capital_ini_necesario


@dataclass
class ResultadoMonteCarlo:
    """Modo Monte Carlo — bootstrap sobre retornos reales."""
    p10: float
    p50: float
    p90: float
    pesimista: float             # media trayectorias cuartil inferior inicial
    base: float                  # saldo con retorno fijo (determinístico)
    optimista: float             # media trayectorias cuartil superior inicial
    prob_supera_meta: float      # 0–1
    prob_supera_base: float      # 0–1
    df_trayectorias: pd.DataFrame   # columnas: anio + sample paths (muestra 50)
    df_bandas: pd.DataFrame         # columnas: anio, p10, p25, p50, p75, p90


# ─── HELPERS INTERNOS ─────────────────────────────────────────────────────────

def _rm(retorno_anual: float) -> float:
    """Tasa mensual equivalente."""
    return (1.0 + float(retorno_anual)) ** (1.0 / 12.0) - 1.0


def _proyectar_mensual(
    capital_inicial: float,
    aporte_mensual: float,
    n_meses: int,
    retorno_anual: float,
) -> tuple[list[float], list[float], list[float]]:
    """
    Proyección determinística mensual.
    Retorna (saldos, aportes_acum, intereses_acum) de largo n_meses.
    """
    rm = _rm(retorno_anual)
    saldo = float(capital_inicial)
    aportes_acum = float(capital_inicial)
    intereses_acum = 0.0

    saldos: list[float] = []
    aps: list[float] = []
    ins: list[float] = []

    for _ in range(n_meses):
        aportes_acum += float(aporte_mensual)
        interes = saldo * rm
        saldo = saldo + float(aporte_mensual) + interes
        intereses_acum += interes
        saldos.append(saldo)
        aps.append(aportes_acum)
        ins.append(intereses_acum)

    return saldos, aps, ins


# ─── MODO 1: CLÁSICA ──────────────────────────────────────────────────────────

def proyeccion_clasica(
    capital_inicial: float,
    aporte_mensual: float,
    anios: int,
    retorno_anual: float,
) -> ProyeccionClasica:
    """
    Proyección determinística con capitalización mensual.
    Equivalente al Tab 1 de BDI, pero alimentado con datos reales del portfolio.
    """
    n_meses = int(anios) * 12
    saldos, aps, ins = _proyectar_mensual(capital_inicial, aporte_mensual, n_meses, retorno_anual)

    # Tabla anual (muestra datos al cierre de cada año)
    registros = []
    for anio in range(1, anios + 1):
        idx = anio * 12 - 1
        registros.append({
            "anio": anio,
            "saldo": saldos[idx],
            "aportes_acum": aps[idx],
            "intereses_acum": ins[idx],
        })
    df_anual = pd.DataFrame(registros)

    capital_final = saldos[-1]
    aportes_totales = aps[-1]
    intereses_ganados = ins[-1]
    ingreso_4pct = capital_final * 0.04 / 12.0
    base_inversion = capital_inicial + aporte_mensual * n_meses
    retorno_pct = (capital_final - base_inversion) / base_inversion * 100 if base_inversion > 0 else 0.0

    return ProyeccionClasica(
        capital_final=capital_final,
        aportes_totales=aportes_totales,
        intereses_ganados=intereses_ganados,
        ingreso_mensual_4pct=ingreso_4pct,
        retorno_acumulado_pct=retorno_pct,
        df_anual=df_anual,
    )


# ─── MODO 2: METAS (Regla del 4% de Bengen) ──────────────────────────────────

def _buscar_aporte_para_meta(
    capital_necesario: float,
    capital_inicial: float,
    retorno_anual: float,
    anios: int,
    paso: float = 50.0,
    max_iter: int = 500,
) -> float:
    """Binary-search: aporte mensual mínimo para alcanzar capital_necesario."""
    lo, hi = 0.0, capital_necesario / max(anios * 0.1, 1.0)
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        saldos, _, _ = _proyectar_mensual(capital_inicial, mid, anios * 12, retorno_anual)
        if saldos[-1] >= capital_necesario:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1.0:
            break
    return math.ceil(hi / paso) * paso


def _buscar_plazo_para_meta(
    capital_necesario: float,
    capital_inicial: float,
    aporte_mensual: float,
    retorno_anual: float,
    max_anios: int = 50,
) -> int:
    """Años mínimos para alcanzar capital_necesario con el aporte actual."""
    for a in range(1, max_anios + 1):
        saldos, _, _ = _proyectar_mensual(capital_inicial, aporte_mensual, a * 12, retorno_anual)
        if saldos[-1] >= capital_necesario:
            return a
    return max_anios


def _buscar_capital_ini_para_meta(
    capital_necesario: float,
    aporte_mensual: float,
    retorno_anual: float,
    anios: int,
    max_iter: int = 500,
) -> float:
    """Capital inicial mínimo para alcanzar capital_necesario."""
    lo, hi = 0.0, capital_necesario
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        saldos, _, _ = _proyectar_mensual(mid, aporte_mensual, anios * 12, retorno_anual)
        if saldos[-1] >= capital_necesario:
            hi = mid
        else:
            lo = mid
        if hi - lo < 100.0:
            break
    return math.ceil(hi / 100.0) * 100.0


def resultado_metas(
    capital_inicial: float,
    aporte_mensual: float,
    anios: int,
    retorno_anual: float,
    ingreso_meta_mensual: float,
    tasa_retiro: float = 0.04,
) -> ResultadoMetas:
    """
    Modo Metas: calcula cuánto capital se necesita para generar
    `ingreso_meta_mensual` USD/mes de retiro pasivo a la tasa de Bengen.
    Compara contra la proyección determinística y sugiere ajustes.
    """
    capital_necesario = (ingreso_meta_mensual * 12.0) / tasa_retiro if tasa_retiro > 0 else 0.0
    clasica = proyeccion_clasica(capital_inicial, aporte_mensual, anios, retorno_anual)
    capital_proyectado = clasica.capital_final
    pct_cubierta = (capital_proyectado / capital_necesario * 100.0) if capital_necesario > 0 else 100.0
    meta_alcanzada = capital_proyectado >= capital_necesario

    sugerencias: dict = {}
    if not meta_alcanzada:
        sugerencias["aporte_necesario"] = _buscar_aporte_para_meta(
            capital_necesario, capital_inicial, retorno_anual, anios
        )
        sugerencias["plazo_necesario"] = _buscar_plazo_para_meta(
            capital_necesario, capital_inicial, aporte_mensual, retorno_anual
        )
        sugerencias["capital_ini_necesario"] = _buscar_capital_ini_para_meta(
            capital_necesario, aporte_mensual, retorno_anual, anios
        )

    return ResultadoMetas(
        ingreso_meta_mensual=ingreso_meta_mensual,
        tasa_retiro=tasa_retiro,
        capital_necesario=capital_necesario,
        capital_proyectado=capital_proyectado,
        pct_meta_cubierta=min(pct_cubierta, 200.0),
        meta_alcanzada=meta_alcanzada,
        sugerencias=sugerencias,
    )


# ─── MODO 3: MONTE CARLO con retornos reales ──────────────────────────────────

def _daily_to_annual_returns(r_diarios: np.ndarray) -> np.ndarray:
    """
    Agrupa retornos diarios en retornos anuales compuestos (ventanas de ~252 días).
    """
    r = np.asarray(r_diarios, dtype=float)
    ventana = 252
    n_anios = len(r) // ventana
    if n_anios == 0:
        total = float((1.0 + r).prod() - 1.0) if r.size else 0.07
        return np.array([total])
    anios = []
    for i in range(n_anios):
        bloque = r[i * ventana:(i + 1) * ventana]
        anios.append(float((1.0 + bloque).prod() - 1.0))
    return np.array(anios, dtype=float)


def _daily_to_monthly(r_diarios: np.ndarray) -> np.ndarray:
    """Agrupa retornos diarios en retornos mensuales (ventanas de 21 días)."""
    r = np.asarray(r_diarios, dtype=float)
    ventana = 21
    n_meses = len(r) // ventana
    if n_meses == 0:
        return np.array([float((1.0 + r).prod() - 1.0)]) if r.size else np.array([0.006])
    out = []
    for i in range(n_meses):
        bloque = r[i * ventana:(i + 1) * ventana]
        out.append(float((1.0 + bloque).prod() - 1.0))
    return np.array(out, dtype=float)


def montecarlo_retiro(
    capital_inicial: float,
    aporte_mensual: float,
    anios: int,
    retornos_diarios: np.ndarray | None = None,
    retorno_anual_base: float = 0.08,
    sigma_anual: float = 0.15,
    n_sim: int = 1000,
    meta_capital: float = 0.0,
    seed: int = 42,
    n_anios_seq: int = 5,       # años iniciales para clasificar secuencia de retornos
) -> ResultadoMonteCarlo:
    """
    Monte Carlo con dos modos:
      · Si retornos_diarios disponibles → bootstrap sobre retornos REALES de la cartera.
        Ventaja sobre BDI: usa la distribución empírica, no una normal asumida.
      · Sin retornos_diarios → simula retornos normales (compatible con BDI standalone).

    Clasifica trayectorias por retorno promedio en los primeros `n_anios_seq` años
    para separar escenarios pesimista/optimista (sequence-of-returns risk).
    """
    rng = np.random.default_rng(seed=int(seed))
    n_meses = int(anios) * 12

    # ── Generar retornos mensuales para cada simulación ────────────────────────
    if retornos_diarios is not None and len(retornos_diarios) >= 21:
        r_mens_pool = _daily_to_monthly(np.asarray(retornos_diarios, dtype=float))
        # Bootstrap: muestrear con reemplazo del pool real
        sim_matrix = rng.choice(r_mens_pool, size=(n_sim, n_meses), replace=True)
    else:
        # Fallback: distribución normal
        mu_mens = retorno_anual_base / 12.0
        sg_mens = sigma_anual / math.sqrt(12.0)
        sim_matrix = rng.normal(loc=mu_mens, scale=sg_mens, size=(n_sim, n_meses))

    # ── Simular trayectorias ───────────────────────────────────────────────────
    trayectorias = np.empty((n_sim, n_meses + 1), dtype=float)
    trayectorias[:, 0] = float(capital_inicial)

    for t in range(n_meses):
        trayectorias[:, t + 1] = (trayectorias[:, t] + float(aporte_mensual)) * (1.0 + sim_matrix[:, t])

    finales = trayectorias[:, -1]

    # ── Percentiles globales ───────────────────────────────────────────────────
    p10 = float(np.percentile(finales, 10))
    p50 = float(np.percentile(finales, 50))
    p90 = float(np.percentile(finales, 90))

    # ── Sequence-of-returns: primeros n_anios_seq años ───────────────────────
    n_meses_seq = n_anios_seq * 12
    # Retorno promedio mensual en los primeros meses de cada trayectoria
    retorno_ini = sim_matrix[:, :n_meses_seq].mean(axis=1)
    q1_thresh = float(np.percentile(retorno_ini, 25))
    q3_thresh = float(np.percentile(retorno_ini, 75))
    idx_pesimista = np.where(retorno_ini <= q1_thresh)[0]
    idx_optimista = np.where(retorno_ini >= q3_thresh)[0]

    pesimista = float(np.median(finales[idx_pesimista])) if len(idx_pesimista) else p10
    optimista = float(np.median(finales[idx_optimista])) if len(idx_optimista) else p90

    # ── Base determinística ───────────────────────────────────────────────────
    saldos_base, _, _ = _proyectar_mensual(
        capital_inicial, aporte_mensual, n_meses, retorno_anual_base
    )
    base = saldos_base[-1]

    # ── Probabilidades ────────────────────────────────────────────────────────
    prob_meta = float(np.mean(finales >= float(meta_capital))) if meta_capital > 0 else 0.0
    prob_base = float(np.mean(finales >= base))

    # ── Bandas (por año, para gráfico de área) ────────────────────────────────
    meses_por_anio = [i * 12 for i in range(anios + 1)]
    bandas_rows = []
    for anio_i, mes_i in enumerate(meses_por_anio):
        col_data = trayectorias[:, mes_i]
        bandas_rows.append({
            "anio": anio_i,
            "p10": float(np.percentile(col_data, 10)),
            "p25": float(np.percentile(col_data, 25)),
            "p50": float(np.percentile(col_data, 50)),
            "p75": float(np.percentile(col_data, 75)),
            "p90": float(np.percentile(col_data, 90)),
        })
    df_bandas = pd.DataFrame(bandas_rows)

    # ── Muestra de 50 trayectorias para el gráfico ───────────────────────────
    sample_idx = rng.choice(n_sim, size=min(50, n_sim), replace=False)
    tray_sample = trayectorias[sample_idx][:, ::12]   # un punto por año
    df_tray = pd.DataFrame(tray_sample.T, columns=[f"sim_{i}" for i in range(len(sample_idx))])
    df_tray.insert(0, "anio", list(range(anios + 1)))

    return ResultadoMonteCarlo(
        p10=p10, p50=p50, p90=p90,
        pesimista=pesimista,
        base=base,
        optimista=optimista,
        prob_supera_meta=prob_meta,
        prob_supera_base=prob_base,
        df_trayectorias=df_tray,
        df_bandas=df_bandas,
    )


# ─── HELPER: extraer inputs desde métricas de cartera ────────────────────────

_MIN_ANIOS_TENENCIA = 90.0 / 365.25  # ~3 meses: menos no es CAGR usable
_RETORNO_DEFAULT = 0.08


def _anios_desde_fecha(fecha: object) -> float | None:
    ts = pd.to_datetime(fecha, errors="coerce")
    if pd.isna(ts):
        return None
    dias = (pd.Timestamp.today().normalize() - ts.normalize()).days
    anios = dias / 365.25
    return float(anios) if anios >= _MIN_ANIOS_TENENCIA else None


def _anios_tenencia_resuelto(
    metricas: dict,
    anios_tenencia: float | None,
    df_ag: pd.DataFrame | None,
) -> float | None:
    if anios_tenencia is not None:
        a = float(anios_tenencia)
        return a if a >= _MIN_ANIOS_TENENCIA else None
    for k in ("anios_tenencia", "años_tenencia"):
        if metricas.get(k) is not None:
            a = float(metricas[k])
            return a if a >= _MIN_ANIOS_TENENCIA else None
    dias = metricas.get("dias_cartera")
    if dias is not None:
        a = float(dias) / 365.25
        return a if a >= _MIN_ANIOS_TENENCIA else None
    fecha = metricas.get("fecha_primera_compra")
    if fecha is not None:
        a = _anios_desde_fecha(fecha)
        if a is not None:
            return a
    if df_ag is not None and not getattr(df_ag, "empty", True):
        col = next(
            (c for c in ("FECHA_PRIMERA_COMPRA", "FECHA_COMPRA") if c in df_ag.columns),
            None,
        )
        if col:
            fechas = pd.to_datetime(df_ag[col], errors="coerce").dropna()
            if not fechas.empty:
                a = (pd.Timestamp.today().normalize() - fechas.min().normalize()).days / 365.25
                return float(a) if a >= _MIN_ANIOS_TENENCIA else None
    return None


def _anualizar_pnl_total(pnl_total: float, anios: float) -> float:
    """CAGR a partir de P&L total. ``(1+r)^(1/n)-1``."""
    if pnl_total <= -0.999:
        return -0.90
    return (1.0 + pnl_total) ** (1.0 / anios) - 1.0


def inputs_desde_cartera(
    metricas: dict,
    ccl: float = 0.0,
    *,
    anios_tenencia: float | None = None,
    df_ag: pd.DataFrame | None = None,
) -> dict:
    """
    Extrae los inputs del retirement calculator desde las métricas de la cartera activa.
    Permite pre-llenar el formulario con datos REALES del portfolio.

    Campos resueltos desde metricas_resumen() (claves reales del dict):
      capital_inicial → total_valor (ARS) ÷ CCL  → USD
      retorno_anual   → CAGR explícito, o P&L total anualizado si hay tenencia;
                        si no hay antigüedad confiable → 8% (no el P&L acumulado)
      sigma_anual     → 0.15 default (no disponible en metricas_resumen)

    Compatibilidad: también acepta claves legacy (valor_usd, retorno_anualizado, cagr).

    El caller puede overridear cualquier campo con un slider.
    """
    # ── Capital inicial en USD ────────────────────────────────────────────────
    # Fuente 1: clave explícita en USD (legacy / cartera_service extendida)
    valor = float(
        metricas.get("valor_usd")
        or metricas.get("valor_total_usd")
        or metricas.get("capital_usd")
        or 0.0
    )
    # Fuente 2: total_valor (ARS) ÷ CCL — clave real de metricas_resumen()
    if valor <= 0 and ccl > 0:
        total_ars = float(metricas.get("total_valor") or 0.0)
        if total_ars > 0:
            valor = total_ars / ccl

    # ── Retorno anual ─────────────────────────────────────────────────────────
    # Orden: claves ya anualizadas → P&L total anualizado con tenencia → 8%
    retorno: float | None = None
    retorno_fuente = "default_sin_tenencia"
    for k in ("retorno_anualizado", "cagr", "retorno_anual"):
        v = metricas.get(k)
        if v is not None:
            retorno = float(v)
            if retorno > 1.0:
                retorno = retorno / 100.0
            retorno_fuente = "cagr"
            break
    if retorno is None:
        rp = metricas.get("retorno_anualizado_pct")
        if rp is not None:
            retorno = float(rp) / 100.0
            retorno_fuente = "cagr"
    if retorno is None:
        # pnl_pct_total_usd = fracción (0.45 = +45%). Nunca ÷100: +120% llega como 1.2.
        pnl_usd = metricas.get("pnl_pct_total_usd")
        anios = _anios_tenencia_resuelto(metricas, anios_tenencia, df_ag)
        if pnl_usd is not None and anios is not None:
            pnl_v = float(pnl_usd)
            if -0.9 < pnl_v < 5.0 and abs(pnl_v) > 0.001:
                retorno = _anualizar_pnl_total(pnl_v, anios)
                retorno_fuente = "cagr"
    if retorno is None:
        retorno = _RETORNO_DEFAULT
        retorno_fuente = "default_sin_tenencia"

    if retorno < -0.9:
        retorno = _RETORNO_DEFAULT
        retorno_fuente = "default_sin_tenencia"

    # ── Sigma anual ───────────────────────────────────────────────────────────
    sigma: float | None = None
    for k in ("volatilidad_anualizada", "sigma_anual", "vol_anual"):
        v = metricas.get(k)
        if v is not None:
            sigma = float(v)
            break
    if sigma is None:
        vp = metricas.get("volatilidad_anualizada_pct")
        if vp is not None:
            sigma = float(vp) / 100.0
    if sigma is None:
        sigma = 0.15
    if sigma > 1.0:
        sigma = sigma / 100.0

    return {
        "capital_inicial": max(0.0, valor),
        "retorno_anual":   max(0.0, min(retorno, 0.50)),
        "sigma_anual":     max(0.01, min(sigma, 0.80)),
        "fuente_capital":  "cartera_activa" if valor > 0 else "manual",
        "retorno_fuente":  retorno_fuente,
    }
