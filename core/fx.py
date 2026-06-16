"""
core/fx.py — A13: multi-moneda formal con FX por fecha de operación.

Fachada única sobre la serie histórica mensual de CCL (core.pricing_utils.
CCL_HISTORICO, mantenida a mano desde resúmenes/BCRA) más el spot del día.
Hasta ahora cada caller decidía por su cuenta qué CCL usar — gmail_reader
usaba el histórico, calcular_posicion_neta el spot, y los motores de riesgo
no tenían una serie para pasar (P0-02). Este módulo define la semántica una
sola vez:

- Fechas hasta el último mes publicado (incluido el mes en curso) → CCL
  histórico del mes (sin look-ahead: si falta el mes, el último anterior
  conocido). El histórico mensual prima sobre el spot para no introducir
  drift intra-mes en costos históricos.
- Meses estrictamente posteriores al último publicado → spot si el caller
  lo tiene; si no, el último histórico publicado (no extrapola).

Sin Streamlit ni red: la serie es estática y el spot siempre lo trae el caller.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from core.pricing_utils import CCL_HISTORICO, ccl_historico_por_fecha

FUENTE_HISTORICO = "historico_mensual"
FUENTE_SPOT = "spot"


@dataclass(frozen=True)
class FXQuote:
    """Cotización CCL para una fecha, con trazabilidad de fuente."""

    valor: float
    fecha: date
    fuente: str  # FUENTE_HISTORICO | FUENTE_SPOT

    @property
    def es_valida(self) -> bool:
        return self.valor > 0


def _a_fecha(fecha: date | datetime | str | None) -> date | None:
    if fecha is None:
        return None
    if isinstance(fecha, datetime):
        return fecha.date()
    if isinstance(fecha, date):
        return fecha
    try:
        return pd.to_datetime(str(fecha)).date()
    except Exception:
        return None


def _ultimo_mes_publicado() -> str:
    return max(CCL_HISTORICO) if CCL_HISTORICO else ""


def ccl_para_fecha(
    fecha: date | datetime | str | None,
    *,
    spot: float | None = None,
) -> FXQuote:
    """
    CCL aplicable a una fecha de operación.

    Si la fecha cae después del último mes publicado de la serie histórica
    (o no se puede parsear) y hay ``spot``, devuelve el spot. Para fechas
    cubiertas por la serie devuelve el histórico del mes (último anterior
    si falta el mes exacto, sin look-ahead).
    """
    f = _a_fecha(fecha)
    spot_v = float(spot or 0)
    hoy = date.today()
    if f is None:
        if spot_v > 0:
            return FXQuote(valor=spot_v, fecha=hoy, fuente=FUENTE_SPOT)
        f = hoy
    key = f.strftime("%Y-%m")
    if key > _ultimo_mes_publicado() and spot_v > 0:
        return FXQuote(valor=spot_v, fecha=f, fuente=FUENTE_SPOT)
    valor = float(ccl_historico_por_fecha(key, fallback=spot_v if spot_v > 0 else None))
    return FXQuote(valor=valor, fecha=f, fuente=FUENTE_HISTORICO)


def ccl_series(
    fechas: Iterable[date | datetime | str],
    *,
    spot: float | None = None,
) -> dict[date, float]:
    """
    Serie fecha → CCL para los motores que necesitan FX alineado a operaciones
    (VaR/CVaR con FX, P0-02). Fechas no parseables se omiten.
    """
    out: dict[date, float] = {}
    for f in fechas:
        fd = _a_fecha(f)
        if fd is None:
            continue
        out[fd] = ccl_para_fecha(fd, spot=spot).valor
    return out


def ars_a_usd(
    monto_ars: float,
    fecha: date | datetime | str | None = None,
    *,
    spot: float | None = None,
) -> float:
    """Convierte ARS→USD al CCL de la fecha de operación. 0.0 si no hay FX."""
    q = ccl_para_fecha(fecha, spot=spot)
    return float(monto_ars) / q.valor if q.es_valida else 0.0


def usd_a_ars(
    monto_usd: float,
    fecha: date | datetime | str | None = None,
    *,
    spot: float | None = None,
) -> float:
    """Convierte USD→ARS al CCL de la fecha de operación. 0.0 si no hay FX."""
    q = ccl_para_fecha(fecha, spot=spot)
    return float(monto_usd) * q.valor if q.es_valida else 0.0
