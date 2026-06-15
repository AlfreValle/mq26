"""
Motor de variables macroeconómicas argentinas.

Funciones
---------
calcular_ccl_implicito_cedear()
    Detecta arbitraje entre el CCL implícito de un CEDEAR individual
    y el CCL promedio del mercado (``MACRO_AR["ccl_promedio"]``).

calcular_tasa_exigida_local()
    CAPM ajustado por Riesgo País para acciones argentinas.
    Ke (USD) = Rf_US + β × ERP_global + EMBI_AR

calcular_tasa_descuento_on()
    Tasa de corte para descontar flujos de ONs corporativas argentinas.
    TIR_mínima = Rf_US + EMBI_AR + spread_sector

tem_a_tna() / tna_a_tem()
    Conversiones entre Tasa Efectiva Mensual y Tasa Nominal Anual.

inflacion_anualizada()
    Convierte IPC mensual a inflación anualizada compuesta.

Todos los parámetros de mercado se leen de ``config.MACRO_AR`` —
modificar ese dict es suficiente para que todos los motores se actualicen.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


# ── Carga lazy de MACRO_AR ────────────────────────────────────────────────────
def _macro() -> dict[str, Any]:
    """Importación late para evitar circulares y permitir mock en tests."""
    from config import MACRO_AR
    return MACRO_AR


# ═════════════════════════════════════════════════════════════════════════════
#  CONVERSIONES DE TASAS
# ═════════════════════════════════════════════════════════════════════════════

def tna_a_tem(tna: float, dias_periodo: int = 30) -> float:
    """
    Convierte Tasa Nominal Anual (base 365) a Tasa Efectiva Mensual.

    TEM = (1 + TNA × días / 365) - 1  [capitalización simple dentro del período]
    """
    return round(tna * dias_periodo / 365, 6)


def tem_a_tna(tem: float, dias_periodo: int = 30) -> float:
    """Inversa de tna_a_tem. TNA = TEM × 365 / días."""
    return round(tem * 365 / dias_periodo, 6)


def tna_a_tea(tna: float, n_periodos: int = 12) -> float:
    """
    Tasa Nominal Anual → Tasa Efectiva Anual compuesta.

    TEA = (1 + TNA / n) ^ n - 1
    """
    return round((1 + tna / n_periodos) ** n_periodos - 1, 6)


def inflacion_anualizada(ipc_mensual: float | None = None) -> float:
    """
    Convierte IPC mensual (decimal) a inflación anualizada compuesta.

    Parámetros
    ----------
    ipc_mensual : float, opcional
        Si es None usa ``MACRO_AR["inflacion_mensual_ipc"]``.

    Retorna
    -------
    float — inflación anual compuesta (decimal)
    """
    m = ipc_mensual if ipc_mensual is not None else _macro()["inflacion_mensual_ipc"]
    return round((1 + m) ** 12 - 1, 6)


# ═════════════════════════════════════════════════════════════════════════════
#  ARBITRAJE CEDEAR — CCL implícito
# ═════════════════════════════════════════════════════════════════════════════

def calcular_ccl_implicito_cedear(
    precio_ars: float,
    precio_usd_exterior: float,
    ratio_cedear: float,
    *,
    umbral_alerta: float = 0.015,
) -> dict[str, Any]:
    """
    Detecta si un CEDEAR individual está cara o barata respecto al CCL macro.

    Fórmula
    -------
    CCL_implícito = (precio_ARS × ratio) / precio_USD_exterior

    donde ``ratio`` = número de CEDEARs que equivalen a 1 acción extranjera.
    Si ratio=2 (AAPL): 2 CEDEARs = 1 AAPL → precio_1_accion_ARS = precio_CEDEAR × 2.

    Parámetros
    ----------
    precio_ars          : precio de mercado del CEDEAR en BYMA (ARS)
    precio_usd_exterior : precio de la acción subyacente en el exterior (USD)
    ratio_cedear        : ratio de conversión del dict RATIOS_CEDEAR
    umbral_alerta       : desvío porcentual que activa la alerta de arbitraje (default 1.5 %)

    Retorna
    -------
    dict con:
        ccl_implicito       : float — CCL calculado para ese CEDEAR
        ccl_referencia      : float — CCL promedio del mercado (MACRO_AR)
        desvio_arbitraje    : float — (ccl_implícito / ccl_ref) - 1
        alerta_ejecucion    : bool  — True si |desvio| > umbral
        señal               : str   — "CARO" | "BARATO" | "EQUILIBRIO"
    """
    macro = _macro()
    ccl_ref = float(macro["ccl_promedio"])

    if precio_usd_exterior <= 0 or ratio_cedear <= 0:
        log.warning("calcular_ccl_implicito_cedear: parámetros inválidos (≤0)")
        return {"ccl_implicito": None, "desvio_arbitraje": None, "alerta_ejecucion": False}

    # Precio de 1 acción completa expresado en ARS
    precio_accion_ars  = float(precio_ars) * float(ratio_cedear)
    ccl_implicito      = precio_accion_ars / float(precio_usd_exterior)
    desvio             = (ccl_implicito / ccl_ref) - 1.0

    if desvio > umbral_alerta:
        senal = "CARO"       # CEDEAR cotiza más caro que el CCL de mercado
    elif desvio < -umbral_alerta:
        senal = "BARATO"     # oportunidad de compra por debajo del CCL
    else:
        senal = "EQUILIBRIO"

    return {
        "ccl_implicito":    round(ccl_implicito, 2),
        "ccl_referencia":   round(ccl_ref, 2),
        "desvio_arbitraje": round(desvio, 4),
        "alerta_ejecucion": abs(desvio) > umbral_alerta,
        "senal":            senal,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  CAPM AJUSTADO — Ke para acciones argentinas
# ═════════════════════════════════════════════════════════════════════════════

def calcular_tasa_exigida_local(
    beta_activo: float,
    prima_riesgo_global: float | None = None,
) -> dict[str, float]:
    """
    Costo del capital exigido (Ke) en USD para una acción argentina.

    Fórmula
    -------
    Ke = Rf_US + (β × ERP_global) + EMBI_AR

    Parámetros
    ----------
    beta_activo         : beta del activo vs su benchmark (^GSPC o ^MERV)
    prima_riesgo_global : ERP Damodaran (default: MACRO_AR["prima_riesgo_global"])

    Retorna
    -------
    dict con desglose de componentes y Ke final en USD y en ARS (inflación ajustada).
    """
    macro = _macro()
    rf_us        = float(macro["risk_free_rate_us"])
    embi_decimal = float(macro["embi_arg_bps"]) / 10_000.0
    erp          = float(prima_riesgo_global or macro["prima_riesgo_global"])

    componente_rf    = rf_us
    componente_prima = float(beta_activo) * erp
    componente_embi  = embi_decimal

    ke_usd = componente_rf + componente_prima + componente_embi

    # Ke en ARS: ajuste por inflación esperada (Fisher equation)
    inflacion_anual = inflacion_anualizada()
    ke_ars = (1 + ke_usd) * (1 + inflacion_anual) - 1

    return {
        "ke_usd":            round(ke_usd, 4),
        "ke_ars":            round(ke_ars, 4),
        "componente_rf_us":  round(componente_rf, 4),
        "componente_prima":  round(componente_prima, 4),
        "componente_embi":   round(componente_embi, 4),
        "beta":              round(float(beta_activo), 4),
        "erp_global":        round(erp, 4),
        "embi_bps":          int(macro["embi_arg_bps"]),
    }


# ═════════════════════════════════════════════════════════════════════════════
#  TASA DE CORTE PARA ONs CORPORATIVAS
# ═════════════════════════════════════════════════════════════════════════════

# Spread típico adicional según sector/calificación crediticia (sobre EMBI)
_SPREAD_SECTOR: dict[str, float] = {
    "oil_gas":      0.010,   # +100 bps — energía (YPF, Vista, Pluspetrol)
    "utilities":    0.015,   # +150 bps — utilities reguladas (PAMP, CEPU)
    "telecom":      0.020,   # +200 bps — telecom (Telecom AR, Cablevisión)
    "real_estate":  0.025,   # +250 bps — real estate (IRSA)
    "financiero":   0.030,   # +300 bps — financiero subordinado
    "default":      0.020,   # fallback neutro
}


def calcular_tasa_descuento_on(
    sector: str = "default",
    tir_mercado: float | None = None,
) -> dict[str, float]:
    """
    Tasa de descuento mínima para descontar flujos de ONs corporativas argentinas.

    Si se provee ``tir_mercado`` (TIR observable en pantalla), la usa directamente.
    Si no, la construye como: Rf_US + EMBI_AR + spread_sector.

    Parámetros
    ----------
    sector      : clave de ``_SPREAD_SECTOR`` ("oil_gas", "utilities", …)
    tir_mercado : TIR de mercado observable (decimal). Si se provee, ignora sector.

    Retorna
    -------
    dict con tir_aplicada, fuente y desglose de componentes.
    """
    macro  = _macro()
    rf_us  = float(macro["risk_free_rate_us"])
    embi   = float(macro["embi_arg_bps"]) / 10_000.0

    if tir_mercado is not None:
        return {
            "tir_aplicada":  round(float(tir_mercado), 4),
            "fuente":        "mercado_observable",
            "rf_us":         round(rf_us, 4),
            "embi":          round(embi, 4),
            "spread_sector": None,
        }

    spread = _SPREAD_SECTOR.get(sector, _SPREAD_SECTOR["default"])
    tir    = rf_us + embi + spread

    return {
        "tir_aplicada":  round(tir, 4),
        "fuente":        "construida",
        "rf_us":         round(rf_us, 4),
        "embi":          round(embi, 4),
        "spread_sector": round(spread, 4),
        "sector":        sector,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  RESUMEN DE CONTEXTO MACRO — Para reportes y logs del optimizador
# ═════════════════════════════════════════════════════════════════════════════

def resumen_macro() -> dict[str, Any]:
    """
    Devuelve un snapshot del contexto macroeconómico actual con métricas derivadas.
    Útil para cabecera de reportes y auditoría del optimizador.
    """
    macro = _macro()
    tem_pf  = tna_a_tem(float(macro["tna_plazo_fijo_30d"]))
    tem_bcra = tna_a_tem(float(macro["tasa_politica_monetaria"]))
    inf_anual = inflacion_anualizada()
    spread_ccl_mep = float(macro["spread_ccl_mep"]) * 100

    return {
        "fecha":               macro["fecha_actualizacion"],
        "ccl":                 macro["ccl_promedio"],
        "mep":                 macro["mep_promedio"],
        "spread_ccl_mep_pct":  round(spread_ccl_mep, 2),
        "embi_bps":            macro["embi_arg_bps"],
        "rf_us_pct":           round(float(macro["risk_free_rate_us"]) * 100, 2),
        "inflacion_mensual_pct": round(float(macro["inflacion_mensual_ipc"]) * 100, 2),
        "inflacion_anual_pct": round(inf_anual * 100, 2),
        "tem_plazo_fijo_pct":  round(tem_pf * 100, 4),
        "tem_bcra_pct":        round(tem_bcra * 100, 4),
        "tasa_real_mensual_pct": round(
            ((1 + tem_pf) / (1 + float(macro["inflacion_mensual_ipc"])) - 1) * 100, 4
        ),
        "fuente":              macro["fuente_datos"],
    }
