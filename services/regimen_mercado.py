"""
services/regimen_mercado.py — detección de régimen de mercado (H2).

Clasifica el contexto en: tendencial (alcista/bajista), lateral o caótico, a
partir de una serie de precios. Método transparente y sin ML (no caja negra):
- Volatilidad realizada anualizada → detecta "caótico".
- Efficiency Ratio de Kaufman (net move / camino total) → tendencia vs lateral.
- Signo del cambio neto → alcista vs bajista.

Es input para el recomendador y contexto para el usuario. `detectar_regimen` es
pura y testeable; `regimen_actual` trae la serie de un índice vía yfinance
(gratis) y degrada a None si no hay red.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Umbrales (heurísticos, documentados — ajustables):
VOL_CAOTICO_ANUAL = 0.40      # >40% vol anualizada → caótico
ER_TENDENCIAL = 0.30          # Efficiency Ratio >= 0.30 → hay tendencia
TENDENCIA_MIN_PCT = 0.03      # y el cambio neto supera 3%

_DESCRIPCION = {
    "tendencial_alcista": "El mercado viene en tendencia alcista sostenida.",
    "tendencial_bajista": "El mercado viene en tendencia bajista sostenida.",
    "lateral": "El mercado está lateral (sin dirección clara).",
    "caotico": "El mercado está muy volátil / caótico.",
    "indeterminado": "No hay datos suficientes para determinar el régimen.",
}

# Sugerencia de ajuste para el recomendador / contexto (no ejecuta nada).
_SUGERENCIA = {
    "tendencial_alcista": "Contexto favorable para renta variable; mantener el plan.",
    "tendencial_bajista": "Conviene mayor peso defensivo (renta fija) y cautela.",
    "lateral": "Sin viento de cola: priorizar selección por fundamentales.",
    "caotico": "Subir defensivos y evitar movimientos bruscos hasta que baje la volatilidad.",
    "indeterminado": "",
}


@dataclass
class RegimenMercado:
    """Resultado de la detección. `regimen` ∈ {tendencial_alcista, tendencial_bajista,
    lateral, caotico, indeterminado}."""

    regimen: str
    vol_anual: float
    tendencia_pct: float
    efficiency_ratio: float
    descripcion: str
    sugerencia: str


def _indeterminado() -> RegimenMercado:
    return RegimenMercado(
        regimen="indeterminado", vol_anual=0.0, tendencia_pct=0.0,
        efficiency_ratio=0.0, descripcion=_DESCRIPCION["indeterminado"],
        sugerencia="",
    )


def detectar_regimen(precios, *, periodos_anio: int = 252) -> RegimenMercado:
    """Clasifica el régimen desde una serie de precios (lista, np.array o pd.Series).
    Pura, sin red. Devuelve 'indeterminado' si la serie es muy corta."""
    try:
        vals = [float(x) for x in list(precios) if x is not None and not (isinstance(x, float) and math.isnan(x))]
    except (TypeError, ValueError):
        return _indeterminado()
    if len(vals) < 10:
        return _indeterminado()

    # Retornos simples y volatilidad anualizada.
    rets = [(vals[i] / vals[i - 1] - 1.0) for i in range(1, len(vals)) if vals[i - 1] > 0]
    if len(rets) < 5:
        return _indeterminado()
    media = sum(rets) / len(rets)
    var = sum((r - media) ** 2 for r in rets) / max(1, len(rets) - 1)
    vol_anual = math.sqrt(var) * math.sqrt(periodos_anio)

    # Efficiency Ratio de Kaufman: |cambio neto| / suma de movimientos absolutos.
    cambio_neto = abs(vals[-1] - vals[0])
    camino = sum(abs(vals[i] - vals[i - 1]) for i in range(1, len(vals)))
    er = (cambio_neto / camino) if camino > 0 else 0.0

    tendencia_pct = (vals[-1] / vals[0] - 1.0) if vals[0] > 0 else 0.0

    # Clasificación (la volatilidad extrema manda sobre la tendencia).
    if vol_anual >= VOL_CAOTICO_ANUAL:
        regimen = "caotico"
    elif er >= ER_TENDENCIAL and abs(tendencia_pct) >= TENDENCIA_MIN_PCT:
        regimen = "tendencial_alcista" if tendencia_pct > 0 else "tendencial_bajista"
    else:
        regimen = "lateral"

    return RegimenMercado(
        regimen=regimen,
        vol_anual=round(vol_anual, 4),
        tendencia_pct=round(tendencia_pct, 4),
        efficiency_ratio=round(er, 4),
        descripcion=_DESCRIPCION[regimen],
        sugerencia=_SUGERENCIA[regimen],
    )


def regimen_actual(ticker: str = "SPY", *, period: str = "6mo") -> RegimenMercado | None:
    """Régimen del índice indicado vía yfinance (gratis). None si no hay red/datos.
    Cachear en el caller (la descarga es lenta)."""
    try:
        import yfinance as yf

        h = yf.Ticker(ticker).history(period=period)
        if h is None or h.empty or "Close" not in h.columns:
            return None
        cierres = h["Close"].dropna().tolist()
        if len(cierres) < 10:
            return None
        return detectar_regimen(cierres)
    except Exception:
        return None
