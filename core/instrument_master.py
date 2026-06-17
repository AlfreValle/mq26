"""
core/instrument_master.py — A01: maestro único de instrumentos (Pilar 1, fundación de datos).

Consolida en una sola API las cuatro fuentes que hoy describen un instrumento:

1. Catálogo de renta fija (`core.renta_fija_ar.INSTRUMENTOS_RF` vía `get_meta`):
   ONs, bonos, letras — emisor, vencimiento, lámina, moneda, ISIN.
2. Universo dinámico (Excel cargado por DataEngine, registrado en runtime):
   Ticker, Ratio, Nombre, Sector, Tipo.
3. `config.RATIOS_CEDEAR`: ratios de conversión CEDEAR (~312 tickers).
4. `config.SECTORES` (data/sectores.csv): sector por ticker.

Reglas de consolidación:
- El catálogo RF manda sobre el universo para tickers de renta fija
  (corrige el bug histórico de ONs clasificadas "CEDEAR" si faltan en el Excel).
- El universo manda sobre config para ratio/sector/nombre de renta variable.

Sin Streamlit ni I/O de red: apto para services/, scripts/ y tests.
"""
from __future__ import annotations

import difflib
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.renta_fija_ar import INSTRUMENTOS_RF, TIPOS_RF, get_meta

# ─── Taxonomía canónica de tipos ──────────────────────────────────────────────

TIPOS_RENTA_VARIABLE = frozenset({"CEDEAR", "ACCION_LOCAL", "ETF", "FCI", "OTRO"})
TIPOS_CANONICOS = frozenset(TIPOS_RF) | TIPOS_RENTA_VARIABLE

_ALIAS_TIPO = {
    "ACCION": "ACCION_LOCAL",
    "ACCIÓN": "ACCION_LOCAL",
    "LOCAL": "ACCION_LOCAL",
    "ACCION LOCAL": "ACCION_LOCAL",
    "ACCIÓN LOCAL": "ACCION_LOCAL",
}


def normalizar_tipo(tipo_raw: str | None) -> str:
    """Tipo canónico desde cualquier variante histórica; '' si no se reconoce."""
    t = str(tipo_raw or "").strip().upper()
    if not t or t in ("NAN", "NONE"):
        return ""
    t = _ALIAS_TIPO.get(t, t)
    return t if t in TIPOS_CANONICOS else ""


# ─── Modelo ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Instrument:
    """Registro consolidado de un instrumento operable en BYMA."""

    ticker: str
    tipo: str                          # taxonomía canónica (TIPOS_CANONICOS)
    nombre: str = ""
    sector: str = ""
    moneda: str = "ARS"                # denominación (RF USD: "USD"; cotización local: ARS)
    ratio_cedear: float | None = None  # solo CEDEARs (subyacentes por 1 CEDEAR)
    emisor: str | None = None          # solo RF
    vencimiento: str | None = None     # solo RF (ISO yyyy-mm-dd)
    lamina_min: float | None = None    # solo RF (VN mínimo)
    isin: str | None = None
    fuentes: tuple[str, ...] = ()      # de qué fuentes se consolidó este registro

    @property
    def es_renta_fija(self) -> bool:
        return self.tipo in TIPOS_RF


@dataclass(frozen=True)
class ValidacionTicker:
    """Resultado estructurado de validar un ticker contra el maestro (A45)."""

    ticker: str
    valido: bool
    motivo: str = ""
    tipo_resuelto: str = ""
    sugerencias: tuple[str, ...] = ()


# ─── Maestro ──────────────────────────────────────────────────────────────────

class InstrumentMaster:
    """Índice consolidado ticker → Instrument. Inmutable tras construcción."""

    def __init__(self, universo_df: pd.DataFrame | None = None) -> None:
        self._index: dict[str, Instrument] = {}
        self._build(universo_df)

    # — construcción —

    def _build(self, universo_df: pd.DataFrame | None) -> None:
        from config import RATIOS_CEDEAR, SECTORES

        # 3+4) Base renta variable: ratios + sectores de config
        for t, ratio in RATIOS_CEDEAR.items():
            tu = str(t).strip().upper()
            if not tu:
                continue
            self._index[tu] = Instrument(
                ticker=tu,
                tipo="CEDEAR",
                sector=str(SECTORES.get(tu, "")),
                ratio_cedear=float(ratio) if ratio else None,
                fuentes=("ratios_config",),
            )

        # 2) Universo dinámico pisa/enriquece renta variable
        if universo_df is not None and not universo_df.empty:
            self._merge_universo(universo_df, SECTORES)

        # 1) Catálogo RF manda para sus tickers (corrige falsos CEDEAR)
        for t in INSTRUMENTOS_RF:
            tu = str(t).strip().upper()
            meta: dict[str, Any] = get_meta(tu) or {}
            previo = self._index.get(tu)
            self._index[tu] = Instrument(
                ticker=tu,
                tipo=normalizar_tipo(meta.get("tipo")) or "BONO",
                nombre=str(meta.get("descripcion", "") or ""),
                sector="Renta Fija",
                moneda=str(meta.get("moneda", "USD") or "USD"),
                emisor=str(meta.get("emisor", "") or "") or None,
                vencimiento=str(meta.get("vencimiento", "") or "") or None,
                lamina_min=float(meta["lamina_min"]) if meta.get("lamina_min") else None,
                isin=str(meta.get("isin", "") or "") or None,
                fuentes=(("catalogo_rf",) + (previo.fuentes if previo else ())),
            )

    def _merge_universo(self, df: pd.DataFrame, sectores: dict) -> None:
        cols = {c.lower(): c for c in df.columns}
        c_ticker = cols.get("ticker")
        if not c_ticker:
            return
        for _, row in df.iterrows():
            tu = str(row.get(c_ticker, "")).strip().upper()
            if not tu or tu in ("NAN", "NONE"):
                continue
            previo = self._index.get(tu)
            tipo = normalizar_tipo(row.get(cols.get("tipo", ""), "")) or (
                previo.tipo if previo else "CEDEAR"
            )
            ratio = None
            if cols.get("ratio") is not None:
                try:
                    r = float(str(row.get(cols["ratio"], "")).split(":")[0].strip())
                    ratio = r if r > 0 else None
                except (ValueError, TypeError):
                    ratio = None
            nombre = str(row.get(cols.get("nombre", ""), "") or "").strip()
            sector = str(row.get(cols.get("sector", ""), "") or "").strip()
            if not sector or sector.lower() == "nan":
                sector = str(sectores.get(tu, ""))
            self._index[tu] = Instrument(
                ticker=tu,
                tipo=tipo,
                nombre=nombre if nombre.lower() != "nan" else (previo.nombre if previo else ""),
                sector=sector,
                ratio_cedear=ratio or (previo.ratio_cedear if previo else None),
                fuentes=(("universo",) + (previo.fuentes if previo else ())),
            )

    # — consultas —

    def get(self, ticker: str) -> Instrument | None:
        return self._index.get(str(ticker or "").strip().upper())

    def existe(self, ticker: str) -> bool:
        return self.get(ticker) is not None

    def tipo(self, ticker: str) -> str:
        inst = self.get(ticker)
        return inst.tipo if inst else ""

    def ratio(self, ticker: str) -> float:
        inst = self.get(ticker)
        if inst and inst.ratio_cedear and inst.ratio_cedear > 0:
            return float(inst.ratio_cedear)
        return 1.0

    def tickers(self, tipo: str | None = None) -> list[str]:
        if tipo is None:
            return sorted(self._index)
        tn = normalizar_tipo(tipo)
        return sorted(t for t, i in self._index.items() if i.tipo == tn)

    def validar(self, ticker: str, tipo_declarado: str | None = None) -> ValidacionTicker:
        """
        Valida un ticker contra el maestro (A45). No bloquea por sí mismo:
        devuelve un veredicto estructurado para que el caller decida warn/block.
        """
        tu = str(ticker or "").strip().upper()
        if not tu or tu in ("NAN", "NONE"):
            return ValidacionTicker(ticker=tu, valido=False, motivo="Ticker vacío o inválido.")
        inst = self.get(tu)
        if inst is None:
            sugerencias = tuple(
                difflib.get_close_matches(tu, self._index.keys(), n=3, cutoff=0.75)
            )
            return ValidacionTicker(
                ticker=tu,
                valido=False,
                motivo="No está en el maestro de instrumentos (universo + catálogo RF).",
                sugerencias=sugerencias,
            )
        td = normalizar_tipo(tipo_declarado)
        if td and td != inst.tipo and not (td in TIPOS_RF and inst.tipo in TIPOS_RF):
            return ValidacionTicker(
                ticker=tu,
                valido=True,
                motivo=f"Tipo declarado «{td}» difiere del maestro «{inst.tipo}».",
                tipo_resuelto=inst.tipo,
            )
        return ValidacionTicker(ticker=tu, valido=True, tipo_resuelto=inst.tipo)

    def stats(self) -> dict[str, int]:
        """Cobertura del maestro por tipo (para panel admin / diagnóstico)."""
        out: dict[str, int] = {"total": len(self._index)}
        for inst in self._index.values():
            out[inst.tipo] = out.get(inst.tipo, 0) + 1
        return out


# ─── Singleton de módulo con refresh por universo ─────────────────────────────

_lock = threading.Lock()
_master: InstrumentMaster | None = None
_universo_fingerprint: int | None = None


def _fingerprint(df: pd.DataFrame | None) -> int | None:
    if df is None or df.empty:
        return None
    try:
        return int(pd.util.hash_pandas_object(df, index=False).sum())
    except Exception:
        return len(df)


def get_master(universo_df: pd.DataFrame | None = None) -> InstrumentMaster:
    """
    Maestro consolidado, cacheado a nivel módulo.
    Si llega un universo_df distinto al usado en la última construcción, rebuild.
    """
    global _master, _universo_fingerprint
    fp = _fingerprint(universo_df)
    with _lock:
        if _master is None or (fp is not None and fp != _universo_fingerprint):
            _master = InstrumentMaster(universo_df)
            _universo_fingerprint = fp if fp is not None else _universo_fingerprint
        return _master


def validar_ticker(ticker: str, tipo_declarado: str | None = None) -> ValidacionTicker:
    """Conveniencia: validación contra el maestro cacheado."""
    return get_master().validar(ticker, tipo_declarado)
