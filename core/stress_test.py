"""
core/stress_test.py — Stress testing macro con cobertura RF completa.

Escenarios modelados:
  embi_300bps      : EMBI Argentina +300 bps (riesgo soberano)
  devaluacion_30   : Devaluación ARS -30 % (CCL sube +43 %)
  tasas_us_200bps  : Fed sube +200 bps (tasas globales, impacta ONs USD)
  inflacion_alta   : Inflación mensual pasa a 6 % (CER sube, RF nominal pierde)
  recesion_local   : Caída actividad -15 % (equities locales, ONs corporativas)
  stagflation      : Combinación EMBI+300 + devaluacion + inflacion alta
  crisis_2002      : EMBI+2000 + devaluacion 70 % + default parcial RF

Mecánica de impacto:
  RV CEDEARs   : delta_spy + apreciación CCL
  RV locales   : delta_local (correlacionado con CCL / caída actividad)
  RF USD       : ΔP/P ≈ -DM × Δspread (soberanos) | -DM × Δtasa_us (ONs)
  RF CER       : ΔP/P ≈ -DM_real × Δspread_real + efecto inflacion
  RF Cauciones : ≈ 0 (duration < 0.1a, sin impacto material)

Uso:
  from core.stress_test import StressTestMacro, ESCENARIOS_MACRO
  st = StressTestMacro()
  resultado = st.aplicar_escenario(portafolio, metricas_riesgo, ccl, "embi_300bps")
  df_todos  = st.todos_los_escenarios(portafolio, metricas_riesgo, ccl)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ─── DEFINICIÓN DE ESCENARIOS ─────────────────────────────────────────────────

@dataclass(frozen=True)
class EscenarioMacro:
    nombre:            str
    descripcion:       str
    delta_spy:         float = 0.0   # shock renta variable global (SPY)
    delta_ccl:         float = 0.0   # shock CCL en decimal (+ = devaluación ARS)
    delta_local_rv:    float = 0.0   # shock acciones locales (BYMA)
    delta_embi_bps:    float = 0.0   # shock spread soberano en bps
    delta_ig_bps:      float = 0.0   # shock spread IG/ON corporativas en bps
    delta_tasa_us_bps: float = 0.0   # shock tasa libre riesgo EE.UU. en bps
    delta_spread_cer:  float = 0.0   # shock spread real bonos CER en bps
    inflacion_mensual_nueva: float | None = None  # nuevo IPC si cambia


ESCENARIOS_MACRO: dict[str, EscenarioMacro] = {
    "embi_300bps": EscenarioMacro(
        nombre="embi_300bps",
        descripcion="EMBI Argentina +300 bps — riesgo soberano se dispara",
        delta_spy=-0.05,
        delta_local_rv=-0.12,
        delta_embi_bps=300.0,
        delta_ig_bps=80.0,    # contagio parcial a ONs corporativas
    ),
    "devaluacion_30": EscenarioMacro(
        nombre="devaluacion_30",
        descripcion="Devaluación ARS -30 % nominal (CCL sube ~43 %)",
        delta_spy=0.0,
        delta_ccl=0.43,        # CCL sube ~43 % cuando el oficial baja 30 %
        delta_local_rv=-0.15,  # acciones locales caen en USD pero suben en ARS
        delta_embi_bps=150.0,  # devaluación eleva riesgo soberano
        inflacion_mensual_nueva=0.08,   # devaluación pass-through
    ),
    "tasas_us_200bps": EscenarioMacro(
        nombre="tasas_us_200bps",
        descripcion="Fed +200 bps — tasas globales suben (estilo Fed 2022)",
        delta_spy=-0.20,
        delta_tasa_us_bps=200.0,
        delta_ig_bps=60.0,     # spreads corporativos se amplían
        delta_embi_bps=80.0,   # EMBI sube por suba de tasa libre
    ),
    "inflacion_alta": EscenarioMacro(
        nombre="inflacion_alta",
        descripcion="Inflación mensual sube a 6 % — CER sube, RF nominal pierde",
        delta_spy=0.0,
        delta_local_rv=-0.08,
        inflacion_mensual_nueva=0.06,
        delta_spread_cer=-50.0,   # spreads CER comprimen (bono CER más demandado)
        delta_embi_bps=50.0,
    ),
    "recesion_local": EscenarioMacro(
        nombre="recesion_local",
        descripcion="Recesión sectorial -15 % — caída actividad, ONs corporativas sufren",
        delta_spy=-0.10,
        delta_local_rv=-0.25,
        delta_ig_bps=150.0,    # mayor riesgo crédito empresas locales
        delta_embi_bps=100.0,
    ),
    "stagflation": EscenarioMacro(
        nombre="stagflation",
        descripcion="Estanflación — EMBI+300 + devaluación + inflación alta",
        delta_spy=-0.12,
        delta_ccl=0.35,
        delta_local_rv=-0.20,
        delta_embi_bps=300.0,
        delta_ig_bps=120.0,
        inflacion_mensual_nueva=0.07,
        delta_spread_cer=-30.0,
    ),
    "crisis_2002": EscenarioMacro(
        nombre="crisis_2002",
        descripcion="Crisis sistémica tipo 2002 — default soberano, devaluación masiva",
        delta_spy=-0.15,
        delta_ccl=1.80,         # CCL casi triplica (devaluación ~180 %)
        delta_local_rv=-0.50,
        delta_embi_bps=2000.0,  # default implica spread extremo
        delta_ig_bps=400.0,
        inflacion_mensual_nueva=0.15,
        delta_spread_cer=200.0,  # default hace que todo el mercado AR pierda
    ),
}


# ─── CLASIFICACIÓN DE ACTIVOS ─────────────────────────────────────────────────

def _tipo_activo(ticker: str, metricas: dict[str, dict]) -> str:
    """
    Devuelve: CEDEAR | LOCAL_RV | BONO_SOBERANO | BOPREAL | BONCER | ON_USD | CAUCION | DESCONOCIDO
    Infiere desde metricas_riesgo (benchmark_asignado + metrica_tipo).
    """
    m = metricas.get(ticker, {})
    if not m:
        return "DESCONOCIDO"

    bench = str(m.get("benchmark_asignado", "")).upper()
    tipo  = str(m.get("metrica_riesgo_tipo", "")).upper()

    if tipo == "BETA":
        if "MERVAL" in bench or "BYMA" in bench:
            return "LOCAL_RV"
        return "CEDEAR"

    # RF
    if "BOPREAL" in bench:
        return "BOPREAL"
    if "SOBERANA" in bench or "SOBERANO" in bench:
        return "BONO_SOBERANO"
    if "CER" in bench:
        return "BONCER"
    if "CAUCIONES" in bench:
        return "CAUCION"
    if "CORPORATIVA" in bench or "IG" in bench:
        return "ON_USD"
    return "DESCONOCIDO"


# ─── IMPACTO POR TIPO DE ACTIVO ───────────────────────────────────────────────

def _impacto_rv_cedear(beta: float, esc: EscenarioMacro, ccl_base: float) -> float:
    """
    Retorno en USD: beta × delta_spy.
    En ARS: (1 + ret_usd) × (1 + delta_ccl) - 1.
    """
    ret_usd = beta * esc.delta_spy
    return (1 + ret_usd) * (1 + esc.delta_ccl) - 1


def _impacto_rv_local(beta: float, esc: EscenarioMacro) -> float:
    """Acciones locales ARS: beta × delta_local_rv."""
    return beta * esc.delta_local_rv


def _impacto_rf_soberano(dm: float, esc: EscenarioMacro) -> float:
    """ΔP/P ≈ -DM × (Δembi_bps / 10000)."""
    return -dm * (esc.delta_embi_bps / 10_000)


def _impacto_rf_on_usd(dm: float, esc: EscenarioMacro) -> float:
    """ΔP/P ≈ -DM × (Δtasa_us + Δig) / 10000."""
    delta_total = (esc.delta_tasa_us_bps + esc.delta_ig_bps) / 10_000
    return -dm * delta_total


def _impacto_rf_bopreal(dm: float, esc: EscenarioMacro) -> float:
    """Similar a soberano pero con spread propio; contagio embi parcial (50 %)."""
    delta_bopreal = (esc.delta_embi_bps * 0.5 + esc.delta_ig_bps * 0.3) / 10_000
    return -dm * delta_bopreal


def _impacto_rf_cer(dm_real: float, esc: EscenarioMacro) -> float:
    """
    ΔP/P_real ≈ -DM_real × Δspread_cer / 10000.
    Si inflación sube, el CER sube también (put natural), pero el precio de mercado
    reacciona principalmente al spread real. Net: efecto moderadamente positivo o neutro.
    """
    delta_real = esc.delta_spread_cer / 10_000
    impacto_spread = -dm_real * delta_real
    # Inflación alta → accretion del CER beneficia al bonista (+)
    inflacion_bonus = 0.02 if (esc.inflacion_mensual_nueva or 0) > 0.05 else 0.0
    return impacto_spread + inflacion_bonus


def _impacto_caucion(_esc: EscenarioMacro) -> float:
    """Cauciones: duration ≈ 0, impacto precio ≈ 0. Sí pierde poder de compra vs inflación alta."""
    return 0.0


# ─── MOTOR PRINCIPAL ──────────────────────────────────────────────────────────

@dataclass
class ResultadoStress:
    escenario:       str
    descripcion:     str
    valor_base_ars:  float
    valor_stress_ars: float
    pct_cambio:      float
    pct_perdida:     float
    por_segmento:    dict[str, float] = field(default_factory=dict)
    por_ticker:      dict[str, float] = field(default_factory=dict)


class StressTestMacro:
    """
    Stress tester con cobertura RF completa.

    Parámetros
    ----------
    portafolio      : DataFrame con columnas TICKER, CANTIDAD, PRECIO_ARS, VALOR_ARS (opt)
    metricas_riesgo : salida de calcular_metricas_riesgo_universo
                      {ticker: {valor_riesgo, metrica_riesgo_tipo, benchmark_asignado, ...}}
    ccl             : CCL actual ARS/USD
    """

    def _valor_base(self, df: pd.DataFrame) -> float:
        if "VALOR_ARS" in df.columns:
            return float(df["VALOR_ARS"].sum())
        if "PRECIO_ARS" in df.columns and "CANTIDAD" in df.columns:
            return float((df["PRECIO_ARS"] * df["CANTIDAD"]).sum())
        return 0.0

    def _valor_pos(self, row: pd.Series) -> float:
        if "VALOR_ARS" in row.index:
            return float(row["VALOR_ARS"])
        cant  = float(row.get("CANTIDAD", 0))
        precio = float(row.get("PRECIO_ARS", 0))
        return cant * precio

    def aplicar_escenario(
        self,
        portafolio: pd.DataFrame,
        metricas_riesgo: dict[str, dict[str, Any]],
        ccl: float,
        nombre_escenario: str,
    ) -> ResultadoStress:
        if portafolio is None or portafolio.empty:
            return self._empty(nombre_escenario)

        esc = ESCENARIOS_MACRO.get(nombre_escenario)
        if esc is None:
            raise ValueError(f"Escenario desconocido: '{nombre_escenario}'. "
                             f"Disponibles: {list(ESCENARIOS_MACRO)}")

        valor_base = self._valor_base(portafolio)
        if valor_base <= 0:
            return self._empty(nombre_escenario)

        segmentos: dict[str, float] = {}
        por_ticker: dict[str, float] = {}

        for _, row in portafolio.iterrows():
            ticker   = str(row.get("TICKER", ""))
            val_ars  = self._valor_pos(row)
            if val_ars <= 0:
                continue

            m         = metricas_riesgo.get(ticker, {})
            tipo      = _tipo_activo(ticker, metricas_riesgo)
            riesgo    = float(m.get("valor_riesgo", 1.0))

            if tipo == "CEDEAR":
                ret = _impacto_rv_cedear(riesgo, esc, ccl)
            elif tipo == "LOCAL_RV":
                ret = _impacto_rv_local(riesgo, esc)
            elif tipo == "BONO_SOBERANO":
                ret = _impacto_rf_soberano(riesgo, esc)
            elif tipo == "ON_USD":
                ret = _impacto_rf_on_usd(riesgo, esc)
            elif tipo == "BOPREAL":
                ret = _impacto_rf_bopreal(riesgo, esc)
            elif tipo == "BONCER":
                ret = _impacto_rf_cer(riesgo, esc)
            elif tipo == "CAUCION":
                ret = _impacto_caucion(esc)
            else:
                ret = esc.delta_spy * 0.5   # proxy conservador

            impacto_ars = val_ars * ret
            por_ticker[ticker] = round(ret * 100, 2)   # en %

            seg = segmentos.get(tipo, 0.0)
            segmentos[tipo] = seg + impacto_ars

        valor_stress = valor_base + sum(segmentos.values())
        pct_cambio   = (valor_stress / valor_base - 1.0) * 100 if valor_base > 0 else 0.0
        pct_perdida  = -pct_cambio if pct_cambio < 0 else 0.0

        # Normalizar segmentos a % del portafolio
        seg_pct = {k: round(v / valor_base * 100, 2) for k, v in segmentos.items()}

        return ResultadoStress(
            escenario=nombre_escenario,
            descripcion=esc.descripcion,
            valor_base_ars=round(valor_base, 2),
            valor_stress_ars=round(valor_stress, 2),
            pct_cambio=round(pct_cambio, 2),
            pct_perdida=round(pct_perdida, 2),
            por_segmento=seg_pct,
            por_ticker=por_ticker,
        )

    def todos_los_escenarios(
        self,
        portafolio: pd.DataFrame,
        metricas_riesgo: dict[str, dict[str, Any]],
        ccl: float,
    ) -> pd.DataFrame:
        """DataFrame con una fila por escenario y columnas clave para UI."""
        rows = []
        for nombre in ESCENARIOS_MACRO:
            r = self.aplicar_escenario(portafolio, metricas_riesgo, ccl, nombre)
            row: dict[str, Any] = {
                "escenario":    r.escenario,
                "descripcion":  r.descripcion,
                "valor_base":   r.valor_base_ars,
                "valor_stress": r.valor_stress_ars,
                "pct_cambio":   r.pct_cambio,
                "pct_perdida":  r.pct_perdida,
            }
            # Añadir impacto por segmento como columnas
            for seg, pct in r.por_segmento.items():
                row[f"imp_{seg.lower()}"] = pct
            rows.append(row)
        return pd.DataFrame(rows)

    def peor_caso(
        self,
        portafolio: pd.DataFrame,
        metricas_riesgo: dict[str, dict[str, Any]],
        ccl: float,
    ) -> ResultadoStress:
        """Retorna el escenario con mayor pérdida porcentual."""
        df = self.todos_los_escenarios(portafolio, metricas_riesgo, ccl)
        if df.empty:
            return self._empty("sin_datos")
        peor = df.loc[df["pct_perdida"].idxmax(), "escenario"]
        return self.aplicar_escenario(portafolio, metricas_riesgo, ccl, peor)

    @staticmethod
    def _empty(nombre: str) -> ResultadoStress:
        return ResultadoStress(
            escenario=nombre,
            descripcion="Sin datos de portafolio",
            valor_base_ars=0.0,
            valor_stress_ars=0.0,
            pct_cambio=0.0,
            pct_perdida=0.0,
        )


# ─── ANÁLISIS DE BREAKEVEN CER ───────────────────────────────────────────────

def breakeven_inflacion_anual_cer(
    spread_real: float,
    tir_nominal_alternativa: float,
) -> float:
    """
    Inflación anual mínima para que un bono CER sea mejor que la alternativa nominal.
    Fisher: (1+spread_real)*(1+infl) - 1 = tir_nominal → infl = (1+TIR)/(1+spread) - 1
    """
    return (1 + tir_nominal_alternativa) / (1 + spread_real) - 1


def impacto_embi_sobre_soberanos(
    portafolio_rf: dict[str, dict],
    delta_embi_bps: float,
) -> dict[str, float]:
    """
    Calcula ΔP/P para cada bono soberano ante un shock EMBI.
    portafolio_rf: {ticker: {duration_ref_anos, tipo, ...}} (de BONOS_SOBERANOS)
    Retorna {ticker: pct_cambio}.
    """
    resultado: dict[str, float] = {}
    for ticker, meta in portafolio_rf.items():
        tipo = str(meta.get("tipo", "")).upper()
        if tipo not in ("BONO_USD", "BOPREAL"):
            continue
        dm  = meta.get("duration_ref_anos", 3.0)
        pct = -float(dm) * delta_embi_bps / 10_000 * 100
        resultado[ticker] = round(pct, 2)
    return resultado
