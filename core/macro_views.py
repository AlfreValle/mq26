"""
core/macro_views.py — Views automáticas de Black-Litterman desde MACRO_AR (A15).

Convierte señales macro de MACRO_AR en retornos esperados por clase de activo,
listos para ser pasados como `views` a `black_litterman_with_absolute_views`.

Lógica por clase:
  CEDEAR / ETF_RV   : retorno USD = rf_us + ERP; en ARS += CCL drift (inflación)
  LOCAL_RV          : retorno ARS = (rf_us + embi + ERP_local) × (1+inf) [EM equity]
  BONO_USD_SOB      : retorno = tir_mercado_ref (de BONOS_SOBERANOS config)
  ON_USD            : retorno = rf_us + embi×0.35 + spread_corporativo (2%)
  BOPREAL           : retorno = rf_us + embi×0.20 (cuasi-soberano con colateral)
  BONO_CER          : retorno = inflacion_anual + spread_real_cer (2%)
  CAUCION_ARS       : retorno = tna_plazo_fijo_30d (proxy tasa corto ARS)
  FCI_ARS           : retorno = tna_plazo_fijo_30d × 0.95 (FCI cobra management fee)
  FCI_USD           : retorno = rf_us + embi×0.15

Todos los retornos están expresados en la moneda indicada por `moneda`:
  "ARS"  : incluye efecto CCL (default; alineado con retornos CEDEAR ARS históricos)
  "USD"  : retorno puro en dólares (para universos USD puros)

Uso:
  from core.macro_views import views_desde_macro, enriquecer_bl_con_macro
  from config import MACRO_AR, BONOS_SOBERANOS

  views = views_desde_macro(MACRO_AR, tipos_activos, moneda="ARS")
  result = black_litterman_with_absolute_views(..., views=views)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

# ─── Tipos canónicos de activo ─────────────────────────────────────────────────
# Usado en `tipos_activos` dict {ticker: TIPO}
TIPO_CEDEAR        = "CEDEAR"
TIPO_ETF_RV        = "ETF_RV"
TIPO_ETF_COBERTURA = "ETF_COBERTURA"   # GLD, VXX
TIPO_LOCAL_RV      = "LOCAL_RV"        # GGAL, YPFD, PAMP, BMA, etc.
TIPO_BONO_USD_SOB  = "BONO_USD_SOB"   # AL30, GD30, AL35, GD35, BOPREAL
TIPO_BOPREAL       = "BOPREAL"
TIPO_ON_USD        = "ON_USD"          # ONs corporativas USD
TIPO_BONO_CER      = "BONO_CER"        # TX28, PARP, CER-linked
TIPO_CAUCION_ARS   = "CAUCION_ARS"
TIPO_FCI_ARS       = "FCI_ARS"
TIPO_FCI_USD       = "FCI_USD"

# Agrupaciones de referencia
_TIPOS_RV_USD = {TIPO_CEDEAR, TIPO_ETF_RV}
_TIPOS_RF_USD = {TIPO_BONO_USD_SOB, TIPO_BOPREAL, TIPO_ON_USD}
_TIPOS_RF_ARS = {TIPO_BONO_CER, TIPO_CAUCION_ARS, TIPO_FCI_ARS}


def _inflacion_anual(macro: dict[str, Any]) -> float:
    """(1+IPC_mensual)^12 - 1; fallback 0.40 si no hay dato."""
    ipc_m = float(macro.get("inflacion_mensual_ipc") or 0.033)
    return round((1.0 + ipc_m) ** 12 - 1.0, 4)


def _ccl_drift_anual(macro: dict[str, Any]) -> float:
    """
    Proxy de apreciación/depreciación CCL anual.
    Bajo ancla: CCL drift ≈ inflación local - inflación EE.UU. (Fisher).
    Si inflación local desconocida usa 0.03 (3% US inflation).
    """
    inf_arg  = _inflacion_anual(macro)
    inf_us   = 0.030   # inflación EE.UU. estructural ~3%
    drift    = (1.0 + inf_arg) / (1.0 + inf_us) - 1.0
    return round(drift, 4)


def _view_cedear_ars(macro: dict[str, Any]) -> float:
    """Retorno ARS esperado para CEDEAR: (rf + ERP) compuesto con drift CCL."""
    rf       = float(macro.get("risk_free_rate_us", 0.0435))
    erp      = float(macro.get("prima_riesgo_global", 0.055))
    ret_usd  = rf + erp                     # ~9.85% en USD
    drift    = _ccl_drift_anual(macro)
    return round((1.0 + ret_usd) * (1.0 + drift) - 1.0, 4)


def _view_local_rv_ars(macro: dict[str, Any]) -> float:
    """
    Retorno ARS esperado para acciones locales (Merval).
    Prima de riesgo EM ampliada = ERP + EMBI.
    """
    rf       = float(macro.get("risk_free_rate_us", 0.0435))
    erp      = float(macro.get("prima_riesgo_global", 0.055))
    embi     = float(macro.get("embi_arg_bps", 580)) / 10_000
    inf_arg  = _inflacion_anual(macro)
    # EM equity premium ≈ ERP + EMBI × 0.5 (equity absorbe parte del riesgo soberano)
    ret_usd  = rf + erp + embi * 0.5
    # Retorno en ARS incluye efecto CCL
    return round((1.0 + ret_usd) * (1.0 + _ccl_drift_anual(macro)) - 1.0, 4)


def _view_bono_soberano_usd(macro: dict[str, Any], tir_ref: float | None) -> float:
    """
    Retorno USD de bono soberano: TIR de mercado referencia si está disponible,
    sino rf_us + embi (carry trade implícito).
    """
    if tir_ref and tir_ref > 0:
        return round(float(tir_ref), 4)
    rf   = float(macro.get("risk_free_rate_us", 0.0435))
    embi = float(macro.get("embi_arg_bps", 580)) / 10_000
    return round(rf + embi, 4)


def _view_on_usd(macro: dict[str, Any], spread_corporativo: float = 0.020) -> float:
    """
    Retorno USD para ONs corporativas.
    Menor exposición al soberano que los bonos del estado → embi × 0.35.
    """
    rf   = float(macro.get("risk_free_rate_us", 0.0435))
    embi = float(macro.get("embi_arg_bps", 580)) / 10_000
    return round(rf + embi * 0.35 + spread_corporativo, 4)


def _view_bopreal_usd(macro: dict[str, Any]) -> float:
    """BOPREAL: cuasi-soberano con colateral. embi × 0.20."""
    rf   = float(macro.get("risk_free_rate_us", 0.0435))
    embi = float(macro.get("embi_arg_bps", 580)) / 10_000
    return round(rf + embi * 0.20, 4)


def _view_bono_cer_ars(macro: dict[str, Any], spread_real: float = 0.020) -> float:
    """
    Retorno nominal ARS de bonos CER: inflación + spread real.
    Spread típico 2-4% para CER soberanos.
    """
    inf = _inflacion_anual(macro)
    return round((1.0 + inf) * (1.0 + spread_real) - 1.0, 4)


def _view_caucion_ars(macro: dict[str, Any]) -> float:
    """Caución ARS: proxy = TNA plazo fijo (ambas reflejan tasa corto ARS)."""
    return round(float(macro.get("tna_plazo_fijo_30d", 0.384)), 4)


def _view_fci_ars(macro: dict[str, Any]) -> float:
    """FCI ARS renta fija: TNA - fee gestión (~0.5%)."""
    return round(float(macro.get("tna_plazo_fijo_30d", 0.384)) * 0.95, 4)


def _view_fci_usd(macro: dict[str, Any]) -> float:
    """FCI USD: rf + spread mínimo soberano."""
    rf   = float(macro.get("risk_free_rate_us", 0.0435))
    embi = float(macro.get("embi_arg_bps", 580)) / 10_000
    return round(rf + embi * 0.15, 4)


def _view_etf_cobertura_ars(macro: dict[str, Any]) -> float:
    """GLD/VXX: retorno bajo pero descorrelacionado; usa rf_us solo."""
    rf   = float(macro.get("risk_free_rate_us", 0.0435))
    drift = _ccl_drift_anual(macro)
    return round((1.0 + rf) * (1.0 + drift) - 1.0, 4)


# ─── Conversión ARS → USD ─────────────────────────────────────────────────────

def _ars_to_usd(ret_ars: float, macro: dict[str, Any]) -> float:
    """Deflacta retorno ARS por drift CCL estimado."""
    drift = _ccl_drift_anual(macro)
    return round((1.0 + ret_ars) / (1.0 + drift) - 1.0, 4)


# ─── Fuente de TIR para bonos soberanos ───────────────────────────────────────

def _tir_soberano(ticker: str) -> float | None:
    """Lee tir_mercado_ref de BONOS_SOBERANOS si existe el ticker."""
    try:
        from config import BONOS_SOBERANOS  # noqa: PLC0415
        datos = BONOS_SOBERANOS.get(ticker.upper())
        if datos:
            return float(datos.get("tir_mercado_ref", 0) or 0) or None
    except Exception:
        pass
    return None


# ─── Interfaz pública ─────────────────────────────────────────────────────────

def views_desde_macro(
    macro: dict[str, Any],
    tipos_activos: dict[str, str],
    *,
    moneda: str = "ARS",
    spread_on_corporativo: float = 0.020,
    spread_cer_real: float = 0.020,
) -> dict[str, float]:
    """
    Genera views de retorno esperado para cada ticker según su tipo y MACRO_AR.

    Parámetros
    ----------
    macro               : dict MACRO_AR de config.py (o dict equivalente).
    tipos_activos       : {ticker: tipo} donde tipo es una constante TIPO_* de este módulo.
                          Ej: {"AAPL": TIPO_CEDEAR, "AL30": TIPO_BONO_USD_SOB, ...}
    moneda              : "ARS" (default) o "USD". Determina la denominación de las views.
    spread_on_corporativo: prima crediticia adicional para ONs (default 2%).
    spread_cer_real     : spread real para bonos CER sobre inflación (default 2%).

    Retorna
    -------
    dict {ticker: retorno_anual_decimal} — listo para pasar a
    `black_litterman_with_absolute_views(..., views=...)`.
    """
    out: dict[str, float] = {}
    moneda = moneda.upper()

    for ticker, tipo in tipos_activos.items():
        t = str(tipo).upper().strip()

        if t in (TIPO_CEDEAR, TIPO_ETF_RV):
            v = _view_cedear_ars(macro)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_ETF_COBERTURA:
            v = _view_etf_cobertura_ars(macro)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_LOCAL_RV:
            v = _view_local_rv_ars(macro)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_BONO_USD_SOB:
            tir = _tir_soberano(ticker)
            v   = _view_bono_soberano_usd(macro, tir)
            if moneda == "ARS":
                v = (1.0 + v) * (1.0 + _ccl_drift_anual(macro)) - 1.0
                v = round(v, 4)

        elif t == TIPO_BOPREAL:
            v = _view_bopreal_usd(macro)
            if moneda == "ARS":
                v = (1.0 + v) * (1.0 + _ccl_drift_anual(macro)) - 1.0
                v = round(v, 4)

        elif t == TIPO_ON_USD:
            v = _view_on_usd(macro, spread_on_corporativo)
            if moneda == "ARS":
                v = (1.0 + v) * (1.0 + _ccl_drift_anual(macro)) - 1.0
                v = round(v, 4)

        elif t == TIPO_BONO_CER:
            v = _view_bono_cer_ars(macro, spread_cer_real)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_CAUCION_ARS:
            v = _view_caucion_ars(macro)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_FCI_ARS:
            v = _view_fci_ars(macro)
            if moneda == "USD":
                v = _ars_to_usd(v, macro)

        elif t == TIPO_FCI_USD:
            v = _view_fci_usd(macro)
            if moneda == "ARS":
                v = (1.0 + v) * (1.0 + _ccl_drift_anual(macro)) - 1.0
                v = round(v, 4)

        else:
            # Tipo desconocido: usar retorno esperado genérico (rf + ERP)
            rf = float(macro.get("risk_free_rate_us", 0.0435))
            v  = rf + float(macro.get("prima_riesgo_global", 0.055))
            if moneda == "ARS":
                v = (1.0 + v) * (1.0 + _ccl_drift_anual(macro)) - 1.0
            v = round(v, 4)

        out[ticker] = v

    return out


def detectar_tipo_desde_ticker(ticker: str) -> str:
    """
    Heurística para detectar el tipo de activo a partir del ticker.
    Útil cuando no se dispone de un mapa explícito de tipos.

    Prioridad: BONOS_SOBERANOS → OBLIGACIONES_NEGOCIABLES → sufijo 'O' (ON)
               → acciones locales conocidas → default CEDEAR.
    """
    t = str(ticker).upper().strip()

    # Bonos soberanos
    try:
        from config import BONOS_SOBERANOS  # noqa: PLC0415
        if t in BONOS_SOBERANOS:
            meta = BONOS_SOBERANOS[t]
            if str(meta.get("tipo", "")).upper() == "BOPREAL":
                return TIPO_BOPREAL
            return TIPO_BONO_USD_SOB
    except Exception:
        pass

    # ONs: terminan en 'O' y tienen 5-6 chars
    if t.endswith("O") and 4 <= len(t) <= 6:
        return TIPO_ON_USD

    # Bonos CER: TX28, DICP, PARP, CUAP
    if t in {"TX28", "TX26", "DICP", "PARP", "CUAP", "PR13"}:
        return TIPO_BONO_CER

    # Cauciones
    if "CAUCION" in t or t.startswith("CAU"):
        return TIPO_CAUCION_ARS

    # Acciones locales (hardcoded de acciones Merval más comunes)
    _LOCALES = {
        "GGAL", "YPFD", "PAMP", "CEPU", "TGNO4", "ALUA", "TXAR", "LOMA",
        "BMA", "SUPV", "IRSA", "AGRO", "MOLI", "BYMA", "COME", "BOLT",
        "MIRG", "CRES", "VALO", "EDN",
    }
    if t in _LOCALES:
        return TIPO_LOCAL_RV

    # ETFs de cobertura
    if t in {"GLD", "SLV", "VXX", "SH", "SPXS"}:
        return TIPO_ETF_COBERTURA

    # Default: CEDEAR (activos US negociados en BYMA)
    return TIPO_CEDEAR


def enriquecer_bl_con_macro(
    macro: dict[str, Any],
    tickers: list[str],
    Sigma: np.ndarray,
    mu_sample: np.ndarray,
    w_mkt: np.ndarray | None = None,
    *,
    tau: float = 0.05,
    moneda: str = "ARS",
    tipos_activos: dict[str, str] | None = None,
    confianza_por_tipo: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Wrapper completo: genera views desde MACRO_AR y ejecuta BL en un solo paso.

    Parámetros
    ----------
    macro           : MACRO_AR dict
    tickers         : lista de tickers en el universo (n,)
    Sigma           : covarianza anualizada (n×n)
    mu_sample       : retornos históricos anualizados (n,)
    w_mkt           : pesos de mercado para prior (default: 1/n)
    tau             : incertidumbre del prior BL (default 0.05)
    moneda          : denominación de retornos "ARS" | "USD"
    tipos_activos   : {ticker: tipo}; si None, se infiere con detectar_tipo_desde_ticker
    confianza_por_tipo: confianza BL por tipo de activo (0-1); None → modo proporcional

    Retorna
    -------
    dict con:
      "mu_bl"        : np.ndarray (n,) retornos posteriores BL
      "views"        : dict {ticker: view}
      "result"       : BlackLittermanResult completo
      "tipos"        : tipos usados {ticker: tipo}
    """
    import numpy as np  # noqa: PLC0415

    from core.black_litterman import black_litterman_with_absolute_views  # noqa: PLC0415

    if tipos_activos is None:
        tipos_activos = {t: detectar_tipo_desde_ticker(t) for t in tickers}

    views = views_desde_macro(macro, tipos_activos, moneda=moneda)

    # Pesos de mercado default: cap-weight proxy = 1/n
    if w_mkt is None:
        n = len(tickers)
        w_mkt = np.ones(n) / n

    # Confianza por tipo (si se quiere diferenciar la certeza de cada view)
    confidence: dict[str, float] | None = None
    if confianza_por_tipo:
        confidence = {
            t: confianza_por_tipo.get(tipos_activos[t], 0.5)
            for t in tickers if t in views
        }

    result = black_litterman_with_absolute_views(
        mu_sample      = mu_sample,
        Sigma          = Sigma,
        w_mkt          = w_mkt,
        tau            = tau,
        views          = views,
        tickers_ordered= tickers,
        omega_mode     = "confidence" if confidence else "proportional",
        confidence     = confidence,
    )

    return {
        "mu_bl":  result.mu_posterior,
        "views":  views,
        "result": result,
        "tipos":  tipos_activos,
    }
