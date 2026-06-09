"""
services/portfolio_optimizer.py — Motor multi-objetivo CP/MP/LP para MQ26.

Arquitectura
============
Plan multifuncional = N tramos (CP / MP / LP) activados por el usuario.
Cada tramo tiene un objetivo concreto (emergencia, renta, crecimiento, etc.),
un monto de capital inicial y un flujo mensual recurrente.

Catálogo de 9 objetivos (3 por horizonte):
  CP1 — Fondo de Emergencia (3–6 meses de gastos en ARS / USD estable)
  CP2 — Capital de Trabajo (30–90 días, máxima liquidez)
  CP3 — Reserva de Oportunidad (90 días, cash disponible para CEDEAR)
  MP1 — Renta Semestral (ON USD corp., TIR 7-9%)
  MP2 — Cobertura Inflación (BONCER/LECAP, retorno real ≥ CPI)
  MP3 — Diversificación Internacional (CEDEARs growth, S&P 500 exposure)
  LP1 — Acumulación Patrimonial (ON largas 10y+, TIR ≥ 7%)
  LP2 — Jubilación/FIRE (HRP portfolio, 15-20y, máx diversificación)
  LP3 — Crecimiento USD (acciones value/growth, retorno USD esperado ≥ 12%)

Flujo de cálculo:
  1. Usuario activa objetivos (e.g. CP2, MP1, LP3).
  2. Motor asigna capital inicial y flujo mensual proporcional a cada tramo.
  3. Por tramo: selecciona instrumentos del catálogo + proyecta valor futuro.
  4. Devuelve PlanMultifuncional con lista de TramoResult serializable.

SIN streamlit, SIN yfinance. Sólo stdlib + pandas + numpy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTES POR DEFECTO
# ──────────────────────────────────────────────────────────────────────────────

CCL_DEFAULT = 1_429.0           # ARS/USD referencia 2026-05-27
INFLACION_MENSUAL_DEFAULT = 0.03  # 3 % mensual (INDEC abr-26 ~3.4%, tendencia baja)
TNA_CAUCION_DEFAULT = 0.34       # 34 % TNA caución BCRA


# ──────────────────────────────────────────────────────────────────────────────
#  DATACLASSES — contratos de dominio (serializables a dict)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ObjetivoConfig:
    """Metadatos estáticos de un objetivo del catálogo."""
    codigo: str                     # "CP1", "MP2", etc.
    nombre: str
    horizonte: str                  # "CP" | "MP" | "LP"
    horizonte_meses: int            # duración típica del tramo en meses
    descripcion: str
    perfil_minimo: str              # "Conservador" | "Moderado" | "Arriesgado"
    tipo_instrumento_primario: str  # tipo principal de activo del catálogo RF
    retorno_esperado_usd_anual: float  # % anual esperado en USD (referencia)
    liquidez: str                   # "alta" | "media" | "baja"
    moneda_objetivo: str            # "USD" | "ARS" | "ARS_CER"


@dataclass
class AsignacionInstrumento:
    """Un instrumento concreto asignado a un tramo."""
    ticker: str
    nombre: str
    tipo: str
    peso_pct: float             # % del capital del tramo
    capital_usd: float          # USD asignados
    capital_ars: float          # ARS equivalentes al CCL
    tir_ref: float | None       # TIR / retorno esperado anual %
    vencimiento: str | None     # YYYY-MM-DD
    calificacion: str | None
    razon: str                  # motivo de selección (string libre)


@dataclass
class ProyeccionFV:
    """Proyección de valor futuro del tramo al horizonte."""
    mes: int
    fecha: str              # YYYY-MM-DD
    valor_usd: float
    valor_ars: float


@dataclass
class TramoResult:
    """Resultado completo de un tramo del plan."""
    objetivo: str                               # código objetivo
    nombre: str
    horizonte_meses: int
    capital_inicial_usd: float
    flujo_mensual_usd: float
    capital_inicial_ars: float
    instrumentos: list[AsignacionInstrumento]
    proyeccion: list[ProyeccionFV]
    tir_ponderada_pct: float                    # TIR promedio ponderada por peso
    valor_final_usd: float                      # FV al horizonte
    valor_final_ars: float
    advertencias: list[str] = field(default_factory=list)


@dataclass
class PlanMultifuncional:
    """Plan multi-objetivo completo."""
    objetivos_activos: list[str]
    capital_total_usd: float
    flujo_mensual_total_usd: float
    ccl: float
    fecha_plan: str                 # YYYY-MM-DD
    tramos: list[TramoResult]
    capital_no_asignado_usd: float  # residual por redondeo
    advertencias_globales: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialización plana para JSON / Streamlit."""
        return {
            "objetivos_activos": self.objetivos_activos,
            "capital_total_usd": self.capital_total_usd,
            "flujo_mensual_total_usd": self.flujo_mensual_total_usd,
            "ccl": self.ccl,
            "fecha_plan": self.fecha_plan,
            "capital_no_asignado_usd": self.capital_no_asignado_usd,
            "advertencias_globales": self.advertencias_globales,
            "tramos": [
                {
                    "objetivo": t.objetivo,
                    "nombre": t.nombre,
                    "horizonte_meses": t.horizonte_meses,
                    "capital_inicial_usd": t.capital_inicial_usd,
                    "flujo_mensual_usd": t.flujo_mensual_usd,
                    "tir_ponderada_pct": t.tir_ponderada_pct,
                    "valor_final_usd": t.valor_final_usd,
                    "valor_final_ars": t.valor_final_ars,
                    "advertencias": t.advertencias,
                    "instrumentos": [
                        {
                            "ticker": i.ticker,
                            "nombre": i.nombre,
                            "tipo": i.tipo,
                            "peso_pct": i.peso_pct,
                            "capital_usd": i.capital_usd,
                            "tir_ref": i.tir_ref,
                            "vencimiento": i.vencimiento,
                            "calificacion": i.calificacion,
                            "razon": i.razon,
                        }
                        for i in t.instrumentos
                    ],
                }
                for t in self.tramos
            ],
        }


# ──────────────────────────────────────────────────────────────────────────────
#  CATÁLOGO DE 9 OBJETIVOS
# ──────────────────────────────────────────────────────────────────────────────

CATALOGO_OBJETIVOS: dict[str, ObjetivoConfig] = {
    "CP1": ObjetivoConfig(
        codigo="CP1",
        nombre="Fondo de Emergencia",
        horizonte="CP",
        horizonte_meses=6,
        descripcion=(
            "Capital líquido equivalente a 3–6 meses de gastos. "
            "Prioridad: preservación y acceso inmediato. "
            "Instrumentos: caución/LECAP corta; dolares bajo el colchón digital (Money Market)."
        ),
        perfil_minimo="Conservador",
        tipo_instrumento_primario="LETRA",
        retorno_esperado_usd_anual=2.5,
        liquidez="alta",
        moneda_objetivo="ARS",
    ),
    "CP2": ObjetivoConfig(
        codigo="CP2",
        nombre="Capital de Trabajo",
        horizonte="CP",
        horizonte_meses=3,
        descripcion=(
            "Liquidez operativa de 30–90 días. Giro corriente, pagos, gastos imprevistos. "
            "Instrumentos: caución BYMA 7d o LECAP más corta disponible."
        ),
        perfil_minimo="Conservador",
        tipo_instrumento_primario="CAUCION",
        retorno_esperado_usd_anual=2.0,
        liquidez="alta",
        moneda_objetivo="ARS",
    ),
    "CP3": ObjetivoConfig(
        codigo="CP3",
        nombre="Reserva de Oportunidad",
        horizonte="CP",
        horizonte_meses=3,
        descripcion=(
            "Dry powder en USD/ARS para aprovechar caídas de CEDEARs o aperturas de spread en ONs. "
            "Instrumentos: LECAP, FCI money market USD."
        ),
        perfil_minimo="Moderado",
        tipo_instrumento_primario="LETRA",
        retorno_esperado_usd_anual=3.0,
        liquidez="alta",
        moneda_objetivo="USD",
    ),
    "MP1": ObjetivoConfig(
        codigo="MP1",
        nombre="Renta Semestral ON USD",
        horizonte="MP",
        horizonte_meses=24,
        descripcion=(
            "Generación de flujo semestral en dólares hard. "
            "Instrumentos: ON USD corporativas AA/AA+ con TIR 7–9%, vto 2+años."
        ),
        perfil_minimo="Moderado",
        tipo_instrumento_primario="ON_USD",
        retorno_esperado_usd_anual=7.5,
        liquidez="media",
        moneda_objetivo="USD",
    ),
    "MP2": ObjetivoConfig(
        codigo="MP2",
        nombre="Cobertura Inflación CER",
        horizonte="MP",
        horizonte_meses=18,
        descripcion=(
            "Preservación del poder adquisitivo en ARS. "
            "Instrumentos: BONCER TX28/TZXD7, LECAP corta."
        ),
        perfil_minimo="Conservador",
        tipo_instrumento_primario="BONCER",
        retorno_esperado_usd_anual=4.0,
        liquidez="media",
        moneda_objetivo="ARS_CER",
    ),
    "MP3": ObjetivoConfig(
        codigo="MP3",
        nombre="Diversificación Internacional CEDEAR",
        horizonte="MP",
        horizonte_meses=24,
        descripcion=(
            "Exposición a S&P 500 / Nasdaq vía CEDEARs de alta liquidez. "
            "Retorno esperado USD 10-12% anual (largo plazo histórico). "
            "Instrumentos: SPY, QQQ, AAPL, MSFT, GOOGL CEDEARs."
        ),
        perfil_minimo="Moderado",
        tipo_instrumento_primario="CEDEAR",
        retorno_esperado_usd_anual=11.0,
        liquidez="alta",
        moneda_objetivo="USD",
    ),
    "LP1": ObjetivoConfig(
        codigo="LP1",
        nombre="Acumulación Patrimonial ON Largas",
        horizonte="LP",
        horizonte_meses=60,
        descripcion=(
            "Crecimiento patrimonial en USD via ONs largas de alta calidad crediticia. "
            "Instrumentos: ON USD vto 2030+, TIR ≥ 7%, calificación AA o superior."
        ),
        perfil_minimo="Moderado",
        tipo_instrumento_primario="ON_USD",
        retorno_esperado_usd_anual=7.2,
        liquidez="baja",
        moneda_objetivo="USD",
    ),
    "LP2": ObjetivoConfig(
        codigo="LP2",
        nombre="Jubilación / FIRE",
        horizonte="LP",
        horizonte_meses=180,
        descripcion=(
            "Construcción de patrimonio para independencia financiera (FIRE) o retiro. "
            "Horizonte 10-20 años. Diversificación máxima: ON largas + CEDEARs + bonos soberanos."
        ),
        perfil_minimo="Moderado",
        tipo_instrumento_primario="ON_USD",
        retorno_esperado_usd_anual=8.5,
        liquidez="baja",
        moneda_objetivo="USD",
    ),
    "LP3": ObjetivoConfig(
        codigo="LP3",
        nombre="Crecimiento USD Acciones",
        horizonte="LP",
        horizonte_meses=60,
        descripcion=(
            "Máximo crecimiento en USD via acciones growth/value. "
            "Retorno esperado 12-15% anual (largo plazo). "
            "Instrumentos: CEDEARs tech + finanzas + consumo discrecional."
        ),
        perfil_minimo="Arriesgado",
        tipo_instrumento_primario="CEDEAR",
        retorno_esperado_usd_anual=13.0,
        liquidez="alta",
        moneda_objetivo="USD",
    ),
}

# ──────────────────────────────────────────────────────────────────────────────
#  INSTRUMENTOS POR OBJETIVO (fallback cuando catálogo RF no provee)
# ──────────────────────────────────────────────────────────────────────────────

# CEDEARs reference para MP3 / LP3
_CEDEARS_MP3 = [
    ("SPY",  "S&P 500 ETF",              11.0, None, "Diversificación EE.UU. — core"),
    ("QQQ",  "Nasdaq 100 ETF",           12.0, None, "Exposición tech — satélite"),
    ("AAPL", "Apple Inc.",               11.5, None, "Blue chip tech defensivo"),
    ("MSFT", "Microsoft Corp.",          12.0, None, "Cloud + IA — crecimiento estable"),
]
_CEDEARS_LP3 = [
    ("GOOGL", "Alphabet Inc. (Google)",  13.0, None, "IA + search dominance"),
    ("AMZN",  "Amazon.com Inc.",         14.0, None, "Cloud (AWS) + ecommerce"),
    ("NVDA",  "NVIDIA Corp.",            18.0, None, "IA chips — alto crecimiento/riesgo"),
    ("BRK/B", "Berkshire Hathaway B",    11.0, None, "Value + diversificado — baja volatilidad"),
]

# LECAP/CAUCION para CP1/CP2/CP3
_LETRAS_CP = [
    ("S30J6", "LECAP 30/06/2026",  29.5, "2026-06-30"),
    ("S29L6", "LECAP 29/07/2026",  29.0, "2026-07-29"),
]
_CAUCION_CP2 = [
    ("CAUCION_7D", "Caución BYMA 7 días", 34.0, None),
]

# ON_USD para LP1/LP2
_ON_LP1 = [
    ("PN43O", "PAE ON 7.375% 2037",  6.8,  "2037-12-01"),
    ("TLCTO", "Telecom ON 8.5% 2031", 7.5, "2031-01-14"),
    ("YM34O", "YPF ON 8.5% 2034",     7.0, "2034-07-01"),
]


# ──────────────────────────────────────────────────────────────────────────────
#  PESOS DE ASIGNACIÓN POR OBJETIVO (distribución entre instrumentos)
# ──────────────────────────────────────────────────────────────────────────────

def _distribuir_equitativamente(n: int) -> list[float]:
    """Distribución equitativa que suma 100.0 con corrección de redondeo."""
    if n <= 0:
        return []
    base = round(100.0 / n, 4)
    pesos = [base] * n
    diff = round(100.0 - sum(pesos), 4)
    pesos[0] = round(pesos[0] + diff, 4)
    return pesos


def _seleccionar_on_usd_para_objetivo(
    obj: ObjetivoConfig,
    lamina_max_usd: int | None = None,
) -> list[tuple[str, str, float, str | None, str]]:
    """
    Selecciona ON_USD del catálogo core/renta_fija_ar.py para objetivos MP1/LP1/LP2.

    Returns list of (ticker, nombre, tir_ref, vencimiento, razon).
    """
    from core.renta_fija_ar import INSTRUMENTOS_RF
    from datetime import timedelta

    hoy = date.today()
    # Horizonte mínimo: 12 meses para LP, 6 para MP
    min_meses = 12 if obj.horizonte in ("LP",) else 6
    fecha_corte = hoy + timedelta(days=min_meses * 30)
    # Para LP1/LP2: preferir vencimientos ≥ 36 meses
    fecha_larga = hoy + timedelta(days=36 * 30)

    candidatos: list[tuple[float, int, str, dict]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if not meta.get("activo", False):
            continue
        if str(meta.get("tipo", "")).upper() != "ON_USD":
            continue
        vcto_raw = meta.get("vencimiento", "")
        try:
            vcto = date.fromisoformat(str(vcto_raw)[:10])
        except (ValueError, TypeError):
            continue
        if vcto <= fecha_corte:
            continue
        lam = meta.get("lamina_min") or meta.get("lamina_vn") or 1
        try:
            lam_i = int(lam)
        except (TypeError, ValueError):
            lam_i = 1
        if lamina_max_usd is not None and lam_i > lamina_max_usd:
            continue
        tir = float(meta.get("tir_ref") or 0.0)
        # Bonus de 1 punto si es largo plazo y el objetivo es LP
        plazo_bonus = 1.0 if (obj.horizonte == "LP" and vcto >= fecha_larga) else 0.0
        candidatos.append((tir + plazo_bonus, lam_i, ticker, meta))

    candidatos.sort(key=lambda x: (-x[0], x[1], x[2]))
    n = 3 if obj.horizonte == "LP" else 2
    seleccionados = candidatos[:n]
    result = []
    for _score, _lam, ticker, meta in seleccionados:
        tir = float(meta.get("tir_ref") or 0.0)
        vcto = str(meta.get("vencimiento") or "")[:10]
        nombre = str(meta.get("descripcion") or ticker)
        razon = (
            f"Seleccionada por TIR {tir:.1f}% · "
            f"cal. {meta.get('calificacion','?')} · vto {vcto}"
        )
        result.append((ticker, nombre, tir, vcto, razon))
    return result


def _instrumentos_para_objetivo(
    obj: ObjetivoConfig,
    capital_usd: float,
    ccl: float,
) -> list[AsignacionInstrumento]:
    """
    Construye lista de AsignacionInstrumento para un objetivo dado.
    """
    instrumentos_raw: list[tuple[str, str, float | None, str | None, str]] = []
    # ticker, nombre, tir_ref, vencimiento, razon

    if obj.codigo in ("MP1",):
        # ON_USD de calidad — filtradas por lámina ≤ capital asignado al tramo
        _lam_max = int(capital_usd) if capital_usd > 0 else None
        raw = _seleccionar_on_usd_para_objetivo(obj, lamina_max_usd=_lam_max)
        instrumentos_raw = raw if raw else [
            (t, n, r, v, "Fallback catálogo") for t, n, r, v in _ON_LP1[:2]
        ]

    elif obj.codigo in ("LP1", "LP2"):
        _lam_max = int(capital_usd) if capital_usd > 0 else None
        raw = _seleccionar_on_usd_para_objetivo(obj, lamina_max_usd=_lam_max)
        instrumentos_raw = raw if raw else [
            (t, n, r, v, "Fallback catálogo") for t, n, r, v in _ON_LP1
        ]

    elif obj.codigo == "MP2":
        # BONCER
        from core.renta_fija_ar import INSTRUMENTOS_RF
        boncer = [
            (t, str(m.get("descripcion", t)), float(m.get("tir_ref") or 0.0),
             str(m.get("vencimiento") or "")[:10],
             f"BONCER CER+ spread real {float(m.get('spread_real', 0)) * 100:.2f}%")
            for t, m in INSTRUMENTOS_RF.items()
            if str(m.get("tipo", "")).upper() == "BONCER" and m.get("activo")
        ]
        boncer.sort(key=lambda x: -x[2])
        instrumentos_raw = boncer[:2] if len(boncer) >= 2 else boncer or [
            ("TX28", "Boncer Nov 2028", 0.3, "2028-11-30", "BONCER fallback")
        ]

    elif obj.codigo in ("MP3",):
        instrumentos_raw = [
            (t, n, ret, vto, razon)
            for t, n, ret, vto, razon in _CEDEARS_MP3
        ]

    elif obj.codigo == "LP3":
        instrumentos_raw = [
            (t, n, ret, vto, razon)
            for t, n, ret, vto, razon in _CEDEARS_LP3
        ]

    elif obj.codigo in ("CP1", "CP3"):
        # LECAP cortas
        from core.renta_fija_ar import INSTRUMENTOS_RF
        letras = [
            (t, str(m.get("descripcion", t)), float(m.get("tir_ref") or 0.0),
             str(m.get("vencimiento") or "")[:10],
             "LECAP ARS de alta liquidez")
            for t, m in INSTRUMENTOS_RF.items()
            if str(m.get("tipo", "")).upper() == "LETRA" and m.get("activo")
        ]
        letras.sort(key=lambda x: x[3] or "9999")   # las más cortas primero
        instrumentos_raw = letras[:2] if letras else [
            (t, n, tir, vcto, "LECAP fallback") for t, n, tir, vcto in _LETRAS_CP
        ]

    elif obj.codigo == "CP2":
        # Caución BYMA
        instrumentos_raw = [
            ("CAUCION_7D", "Caución BYMA 7 días", TNA_CAUCION_DEFAULT * 100, None,
             f"TNA {TNA_CAUCION_DEFAULT * 100:.1f}% — máxima liquidez operativa")
        ]

    else:
        instrumentos_raw = []

    if not instrumentos_raw:
        return []

    n = len(instrumentos_raw)
    pesos = _distribuir_equitativamente(n)

    result: list[AsignacionInstrumento] = []
    for i, (ticker, nombre, tir_ref, vcto, razon) in enumerate(instrumentos_raw):
        peso = pesos[i]
        cap_usd = round(capital_usd * peso / 100.0, 2)
        result.append(AsignacionInstrumento(
            ticker=ticker,
            nombre=nombre,
            tipo=obj.tipo_instrumento_primario,
            peso_pct=peso,
            capital_usd=cap_usd,
            capital_ars=round(cap_usd * ccl, 2),
            tir_ref=float(tir_ref) if tir_ref is not None else None,
            vencimiento=vcto,
            calificacion=None,  # enriquecido si se quiere
            razon=razon,
        ))
    return result


# ──────────────────────────────────────────────────────────────────────────────
#  PROYECCIÓN DE VALOR FUTURO
# ──────────────────────────────────────────────────────────────────────────────

def _proyectar_fv(
    capital_inicial: float,
    flujo_mensual: float,
    tir_anual_pct: float,
    horizonte_meses: int,
    *,
    ccl: float,
    fecha_inicio: date,
) -> list[ProyeccionFV]:
    """
    Proyección mensual de valor futuro (USD) usando capitalización compuesta.

    FV(m) = capital × (1 + r)^m + flujo × [(1 + r)^m − 1] / r
    donde r = tir_anual / 12 (tasa mensual).

    Si tir_anual_pct == 0, proyección lineal (solo acumulación de flujos).
    """
    r_mensual = tir_anual_pct / 100.0 / 12.0
    proyeccion: list[ProyeccionFV] = []
    for m in range(1, horizonte_meses + 1):
        if abs(r_mensual) < 1e-10:
            fv = capital_inicial + flujo_mensual * m
        else:
            factor = (1.0 + r_mensual) ** m
            fv = capital_inicial * factor + flujo_mensual * (factor - 1.0) / r_mensual
        fv = max(0.0, round(fv, 2))
        fecha = fecha_inicio + timedelta(days=m * 30)
        proyeccion.append(ProyeccionFV(
            mes=m,
            fecha=fecha.isoformat(),
            valor_usd=fv,
            valor_ars=round(fv * ccl, 2),
        ))
    return proyeccion


def _tir_ponderada(instrumentos: list[AsignacionInstrumento]) -> float:
    """TIR promedio ponderada por peso_pct."""
    total_peso = sum(i.peso_pct for i in instrumentos if i.tir_ref is not None)
    if total_peso <= 0:
        return 0.0
    return round(
        sum(i.tir_ref * i.peso_pct for i in instrumentos if i.tir_ref is not None)
        / total_peso,
        2,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  MOTOR PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

# Pesos relativos de asignación de capital por horizonte (cuando hay múltiples tramos)
# Suma = 1.0 si solo hay objetivos del mismo horizonte; la mezcla usa estos pesos base.
_PESO_HORIZONTE: dict[str, float] = {
    "CP": 0.15,   # colchón de liquidez — menor peso
    "MP": 0.40,   # renta y cobertura — peso principal
    "LP": 0.45,   # crecimiento largo plazo — mayor peso
}


def _asignar_capital_por_objetivos(
    objetivos: list[str],
    capital_total_usd: float,
) -> dict[str, float]:
    """
    Distribuye el capital total entre los objetivos activos.

    Lógica:
      1. Agrupa por horizonte.
      2. Asigna peso de horizonte proporcional a los horizontes presentes.
      3. Dentro del horizonte reparte equitativamente.

    Devuelve {codigo_objetivo: capital_usd}.
    """
    if not objetivos or capital_total_usd <= 0:
        return {}

    # Horizonte → lista objetivos activos
    por_horizonte: dict[str, list[str]] = {}
    for cod in objetivos:
        cfg = CATALOGO_OBJETIVOS.get(cod)
        if cfg is None:
            continue
        por_horizonte.setdefault(cfg.horizonte, []).append(cod)

    # Peso total de horizontes presentes
    peso_total = sum(_PESO_HORIZONTE.get(h, 0.3) for h in por_horizonte)
    if peso_total <= 0:
        # Reparto equitativo
        n = len(objetivos)
        return {cod: round(capital_total_usd / n, 2) for cod in objetivos}

    asignacion: dict[str, float] = {}
    capital_asignado = 0.0
    horizontes = list(por_horizonte.keys())
    for h in horizontes:
        peso_h = _PESO_HORIZONTE.get(h, 0.3) / peso_total
        capital_h = capital_total_usd * peso_h
        objs_h = por_horizonte[h]
        cap_por_obj = capital_h / len(objs_h)
        for cod in objs_h:
            asignacion[cod] = round(cap_por_obj, 2)
            capital_asignado += asignacion[cod]

    # Corrección del residuo al primer objetivo
    diff = round(capital_total_usd - capital_asignado, 2)
    if abs(diff) > 0.01 and objetivos:
        primer = objetivos[0]
        if primer in asignacion:
            asignacion[primer] = round(asignacion[primer] + diff, 2)

    return asignacion


def calcular_plan_multifuncional(
    objetivos: list[str],
    capital_inicial_usd: float,
    flujo_mensual_usd: float = 0.0,
    *,
    ccl: float = CCL_DEFAULT,
    fecha_inicio: date | None = None,
) -> PlanMultifuncional:
    """
    Motor multi-objetivo: genera un plan CP/MP/LP para los objetivos activos.

    Parámetros
    ----------
    objetivos           : Lista de códigos activos, e.g. ["CP2", "MP1", "LP3"]
    capital_inicial_usd : Capital disponible en USD
    flujo_mensual_usd   : Aporte mensual recurrente en USD (default 0)
    ccl                 : Tipo de cambio CCL ARS/USD
    fecha_inicio        : Fecha de inicio del plan (default: hoy)

    Devuelve
    --------
    PlanMultifuncional con tramos, proyecciones y advertencias.
    """
    if fecha_inicio is None:
        fecha_inicio = date.today()

    advertencias_globales: list[str] = []

    # Validar objetivos
    validos = [cod for cod in objetivos if cod in CATALOGO_OBJETIVOS]
    invalidos = [cod for cod in objetivos if cod not in CATALOGO_OBJETIVOS]
    if invalidos:
        advertencias_globales.append(f"Objetivos no reconocidos ignorados: {invalidos}")
    if not validos:
        advertencias_globales.append("No hay objetivos válidos — plan vacío.")
        return PlanMultifuncional(
            objetivos_activos=[],
            capital_total_usd=capital_inicial_usd,
            flujo_mensual_total_usd=flujo_mensual_usd,
            ccl=ccl,
            fecha_plan=fecha_inicio.isoformat(),
            tramos=[],
            capital_no_asignado_usd=capital_inicial_usd,
            advertencias_globales=advertencias_globales,
        )

    if capital_inicial_usd < 100:
        advertencias_globales.append(
            f"Capital inicial muy bajo (USD {capital_inicial_usd:.0f}). "
            "Algunas láminas mínimas de ON requieren USD 1,000+"
        )

    # Distribución de capital
    asignacion = _asignar_capital_por_objetivos(validos, capital_inicial_usd)

    # Distribución de flujo mensual proporcional al capital
    total_cap = sum(asignacion.values()) or 1.0
    flujo_por_obj: dict[str, float] = {
        cod: round(flujo_mensual_usd * (cap / total_cap), 2)
        for cod, cap in asignacion.items()
    }

    # Construir tramos
    tramos: list[TramoResult] = []
    capital_asignado_total = 0.0

    for cod in validos:
        cfg = CATALOGO_OBJETIVOS[cod]
        cap = asignacion.get(cod, 0.0)
        flujo = flujo_por_obj.get(cod, 0.0)
        capital_asignado_total += cap

        instrumentos = _instrumentos_para_objetivo(cfg, cap, ccl)
        advs: list[str] = []

        if not instrumentos:
            advs.append(f"No se encontraron instrumentos para {cod}. Revisar catálogo.")
            tir_pond = cfg.retorno_esperado_usd_anual
        else:
            tir_pond = _tir_ponderada(instrumentos)
            # Usar retorno esperado del catálogo si la TIR ponderada es 0 (CEDEARs, etc.)
            if tir_pond == 0.0:
                tir_pond = cfg.retorno_esperado_usd_anual

        proyeccion = _proyectar_fv(
            capital_inicial=cap,
            flujo_mensual=flujo,
            tir_anual_pct=tir_pond,
            horizonte_meses=cfg.horizonte_meses,
            ccl=ccl,
            fecha_inicio=fecha_inicio,
        )
        fv_usd = proyeccion[-1].valor_usd if proyeccion else cap
        fv_ars = proyeccion[-1].valor_ars if proyeccion else round(cap * ccl, 2)

        # Advertencias por lámina
        if cfg.tipo_instrumento_primario == "ON_USD" and cap < 1_000:
            advs.append(
                f"Capital asignado USD {cap:.0f} puede ser insuficiente para la lámina "
                "mínima de ONs USD (típicamente USD 1,000–10,000)."
            )

        tramos.append(TramoResult(
            objetivo=cod,
            nombre=cfg.nombre,
            horizonte_meses=cfg.horizonte_meses,
            capital_inicial_usd=cap,
            flujo_mensual_usd=flujo,
            capital_inicial_ars=round(cap * ccl, 2),
            instrumentos=instrumentos,
            proyeccion=proyeccion,
            tir_ponderada_pct=tir_pond,
            valor_final_usd=fv_usd,
            valor_final_ars=fv_ars,
            advertencias=advs,
        ))

    capital_no_asignado = round(capital_inicial_usd - capital_asignado_total, 2)

    return PlanMultifuncional(
        objetivos_activos=validos,
        capital_total_usd=capital_inicial_usd,
        flujo_mensual_total_usd=flujo_mensual_usd,
        ccl=ccl,
        fecha_plan=fecha_inicio.isoformat(),
        tramos=tramos,
        capital_no_asignado_usd=capital_no_asignado,
        advertencias_globales=advertencias_globales,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  HELPERS PARA UI
# ──────────────────────────────────────────────────────────────────────────────

def resumen_plan_df(plan: PlanMultifuncional) -> pd.DataFrame:
    """
    DataFrame resumen de tramos para tabla Streamlit.

    Columnas: Objetivo | Nombre | Horizonte | Capital USD | TIR % | FV USD | FV ARS
    """
    if not plan.tramos:
        return pd.DataFrame()
    rows = [
        {
            "Objetivo":        t.objetivo,
            "Nombre":          t.nombre,
            "Horizonte":       f"{t.horizonte_meses} meses",
            "Capital USD":     t.capital_inicial_usd,
            "Flujo mes. USD":  t.flujo_mensual_usd,
            "TIR pond. %":     t.tir_ponderada_pct,
            "FV USD":          t.valor_final_usd,
            "FV ARS":          t.valor_final_ars,
            "⚠️":              " | ".join(t.advertencias) if t.advertencias else "",
        }
        for t in plan.tramos
    ]
    return pd.DataFrame(rows)


def proyeccion_consolidada_df(plan: PlanMultifuncional) -> pd.DataFrame:
    """
    DataFrame con proyección mensual consolidada de todos los tramos.
    Útil para gráfico de líneas multi-tramo.

    Columnas: mes | fecha | objetivo | nombre | valor_usd
    """
    rows = []
    for t in plan.tramos:
        for p in t.proyeccion:
            rows.append({
                "mes":       p.mes,
                "fecha":     p.fecha,
                "objetivo":  t.objetivo,
                "nombre":    t.nombre,
                "valor_usd": p.valor_usd,
                "valor_ars": p.valor_ars,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def asignacion_pie_df(plan: PlanMultifuncional) -> pd.DataFrame:
    """
    DataFrame para gráfico torta: distribución de capital por objetivo.

    Columnas: objetivo | nombre | capital_usd | peso_pct
    """
    total = plan.capital_total_usd or 1.0
    rows = [
        {
            "objetivo":   t.objetivo,
            "nombre":     t.nombre,
            "capital_usd": t.capital_inicial_usd,
            "peso_pct":   round(t.capital_inicial_usd / total * 100, 2),
        }
        for t in plan.tramos
    ]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def objetivo_info(codigo: str) -> dict[str, Any] | None:
    """Devuelve metadatos del objetivo como dict, o None si no existe."""
    cfg = CATALOGO_OBJETIVOS.get(codigo)
    if cfg is None:
        return None
    return {
        "codigo":                     cfg.codigo,
        "nombre":                     cfg.nombre,
        "horizonte":                  cfg.horizonte,
        "horizonte_meses":            cfg.horizonte_meses,
        "descripcion":                cfg.descripcion,
        "perfil_minimo":              cfg.perfil_minimo,
        "tipo_instrumento_primario":  cfg.tipo_instrumento_primario,
        "retorno_esperado_usd_anual": cfg.retorno_esperado_usd_anual,
        "liquidez":                   cfg.liquidez,
        "moneda_objetivo":            cfg.moneda_objetivo,
    }
