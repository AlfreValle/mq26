"""
core/stale_policy.py — A15: política de datos viejos con umbral por tipo de activo.

Hasta hoy `PriceRecord.stale` existía pero nunca se calculaba: todo precio
parecía igual de fresco, fuera un CEDEAR líquido o una ON que opera por
ventanilla dos veces por semana. Esta política define cuánta antigüedad es
aceptable según el tipo de instrumento y clasifica la frescura en niveles
que la UI puede mostrar y los motores pueden usar para degradar con criterio.

Umbrales pensados para el mercado argentino:
- Renta variable líquida (CEDEAR/acción/ETF): minutos — hay feed intradiario.
- Renta fija (ONs, bonos, letras): horas/días — la referencia válida suele ser
  el cierre anterior o la paridad de catálogo.
- FCI: el VCP se publica una vez por día hábil.

Sin dependencias de Streamlit ni de red.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

# ─── Umbrales por tipo (minutos) ──────────────────────────────────────────────

_UMBRAL_DEFECTO_MIN = 30

# Por tipo canónico (ver core.instrument_master.TIPOS_CANONICOS).
# Dos niveles: hasta `fresco` es FRESCO; hasta `stale` es ACEPTABLE; después STALE.
_UMBRALES_MIN: dict[str, tuple[int, int]] = {
    # tipo: (fresco_hasta_min, aceptable_hasta_min)
    "CEDEAR":       (15, 60),
    "ACCION_LOCAL": (15, 60),
    "ETF":          (15, 60),
    "FCI":          (60 * 24, 60 * 48),       # VCP diario; 2 días hábiles tolerables
    "ON":           (60 * 4, 60 * 24),
    "ON_USD":       (60 * 4, 60 * 24),
    "BONO":         (60 * 4, 60 * 24),
    "BONO_USD":     (60 * 4, 60 * 24),
    "LETRA":        (60 * 4, 60 * 24),
    "LECAP":        (60 * 4, 60 * 24),
    "LEDE":         (60 * 4, 60 * 24),
    "BONCER":       (60 * 4, 60 * 24),
    "BOPREAL":      (60 * 4, 60 * 24),
    "DUAL":         (60 * 4, 60 * 24),
    "USD_LINKED":   (60 * 4, 60 * 24),
    "CAUCION":      (60 * 4, 60 * 24),
    "OTRO":         (_UMBRAL_DEFECTO_MIN, 60 * 24),
}


class Frescura(Enum):
    FRESCO = "fresco"          # dentro del umbral intradiario del tipo
    ACEPTABLE = "aceptable"    # usable con aviso (ej. cierre anterior en RF)
    STALE = "stale"            # mostrar con advertencia fuerte / degradar motor
    SIN_DATO = "sin_dato"      # no hay timestamp → no se puede afirmar nada

    @property
    def label(self) -> str:
        return {
            "fresco": "FRESCO",
            "aceptable": "ACEPTABLE",
            "stale": "STALE",
            "sin_dato": "SIN DATO",
        }[self.value]

    @property
    def usable_para_recomendacion(self) -> bool:
        """Los motores de recomendación solo deben usar FRESCO/ACEPTABLE."""
        return self in (Frescura.FRESCO, Frescura.ACEPTABLE)


@dataclass(frozen=True)
class EvaluacionFrescura:
    frescura: Frescura
    antiguedad_min: float | None     # None si no hay timestamp
    umbral_fresco_min: int
    umbral_stale_min: int
    tipo: str


def umbrales_minutos(tipo: str | None) -> tuple[int, int]:
    """(fresco_hasta, aceptable_hasta) en minutos para el tipo dado."""
    t = str(tipo or "").strip().upper()
    return _UMBRALES_MIN.get(t, (_UMBRAL_DEFECTO_MIN, 60 * 24))


def clasificar_frescura(
    tipo: str | None,
    timestamp: datetime | None,
    ahora: datetime | None = None,
) -> EvaluacionFrescura:
    """Clasifica la frescura de un precio según el tipo de instrumento."""
    fresco_max, stale_max = umbrales_minutos(tipo)
    t = str(tipo or "").strip().upper()
    if timestamp is None:
        return EvaluacionFrescura(Frescura.SIN_DATO, None, fresco_max, stale_max, t)
    now = ahora or datetime.now(tz=timestamp.tzinfo)
    edad = (now - timestamp) / timedelta(minutes=1)
    if edad < 0:
        # reloj adelantado del proveedor: tratarlo como fresco, no como error
        edad = 0.0
    if edad <= fresco_max:
        nivel = Frescura.FRESCO
    elif edad <= stale_max:
        nivel = Frescura.ACEPTABLE
    else:
        nivel = Frescura.STALE
    return EvaluacionFrescura(nivel, float(edad), fresco_max, stale_max, t)


def es_stale(
    tipo: str | None,
    timestamp: datetime | None,
    ahora: datetime | None = None,
) -> bool:
    """True si el precio superó el umbral de aceptabilidad de su tipo."""
    ev = clasificar_frescura(tipo, timestamp, ahora)
    return ev.frescura in (Frescura.STALE, Frescura.SIN_DATO)
