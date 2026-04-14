"""
core/renta_fija_ar.py — Renta fija Argentina (ON, bonos USD, letras).

Metadatos INSTRUMENTOS_RF + compatibilidad con UNIVERSO_RENTA_FIJA_AR
(para diagnóstico, ladder, TIR ponderada).

Campos **opcionales** por instrumento (P2-RF-05): ``isin``, ``lamina_min`` / ``denominacion_min``,
``forma_amortizacion``. Si faltan, la UI muestra ``—``.

**P2-RF-01:** ``ficha_rf_minima_bundle`` agrupa metadatos + TIR ref / TIR a precio + flags de escala para una sola ficha en pantalla (sin Streamlit).

Convención **obligaciones negociables en USD (ON_USD)** — misma para todo el catálogo:
  - `paridad_ref` y el `PPC_USD` operativo en transacciones = **% de paridad** sobre un
    nominal **USD** (100 % = al par).
  - La cotización de mercado y prospectos suele expresarse como **ARS por cada 100
    nominales USD**; en el motor: **precio ARS (lote 100 VN) ≈ paridad_% × CCL**.
  - **CANTIDAD** en cartera = nominales USD (múltiplos de la lámina mínima del instrumento).

SIN streamlit ni yfinance.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR

# Base nominal (USD) respecto a la cual se interpreta la paridad % en ON dólar cable.
# Coincide con la cotización típica "por cada 100 nominales" en ARS.
ON_USD_PARIDAD_BASE_VN = 100.0

# BONCER/BOPREAL/DUAL/USD_LINKED: familias panel BYMA (ver core/rf_panel_taxonomy.py).
TIPOS_RF = frozenset({
    "ON", "ON_USD", "BONO", "BONO_USD", "LETRA", "LECAP", "LEDE",
    "BONCER", "BOPREAL", "DUAL", "USD_LINKED",
})

INSTRUMENTOS_RF: dict[str, dict[str, Any]] = {
    "PN43O": {
        "emisor": "Pan American Energy", "descripcion": "Panamerican 2037",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2037-12-01",
        "cupon_anual": 0.073, "frecuencia": 2, "calificacion": "AA+", "ley": "Argentina",
        "tir_ref": 7.3, "paridad_ref": 100.5, "fecha_ref": "2026-03-31", "activo": True,
        "lamina_min": 1000, "callable": False,
    },
    "YM34O": {
        "emisor": "YPF S.A.", "descripcion": "YPF 2034", "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2034-07-01", "cupon_anual": 0.085, "frecuencia": 2,
        "calificacion": "AA", "ley": "Nueva York", "tir_ref": 7.1, "paridad_ref": 104.2,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "TLCTO": {
        "emisor": "Telecom Argentina",
        "descripcion": "ON 8,5% VT 20/01/36 (Telecom Argentina)",
        "tipo": "ON_USD",
        "moneda": "USD", "vencimiento": "2036-01-20", "cupon_anual": 0.085, "frecuencia": 2,
        "calificacion": "AA", "ley": "Nueva York", "tir_ref": 8.0, "paridad_ref": 100.8,
        "fecha_ref": "2026-03-31", "activo": True,
        "lamina_min": 1, "callable": True,
    },
    "TSC4O": {
        "emisor": "TGS (Transportadora Gas del Sur)", "descripcion": "TGS 2035",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2035-05-14", "cupon_anual": 0.066,
        "frecuencia": 2, "calificacion": "AA+", "ley": "Nueva York", "tir_ref": 7.1,
        "paridad_ref": 97.5, "fecha_ref": "2026-03-31", "activo": True,
        "lamina_min": 10_000, "callable": False,
    },
    "IRCPO": {
        "emisor": "Irsa Inversiones y Representaciones", "descripcion": "Irsa 2035",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2035-02-08", "cupon_anual": 0.085,
        "frecuencia": 2, "calificacion": "AA-", "ley": "Nueva York", "tir_ref": 7.1,
        "paridad_ref": 105.0, "fecha_ref": "2026-03-31", "activo": True,
        "lamina_min": 1, "callable": False,
    },
    "DNC7O": {
        "emisor": "Edenor (Distribuidora Norte)", "descripcion": "Edenor 2030",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2030-10-25", "cupon_anual": 0.095,
        "frecuencia": 2, "calificacion": "A+", "ley": "Nueva York", "tir_ref": 8.3,
        "paridad_ref": 103.5, "fecha_ref": "2026-03-31", "activo": True,
    },
    "AL30": {
        "emisor": "República Argentina", "descripcion": "Bonar 2030", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2030-07-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina", "tir_ref": 9.23, "paridad_ref": 63.5,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "GD30": {
        "emisor": "República Argentina", "descripcion": "Global 2030", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2030-07-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York", "tir_ref": 8.8, "paridad_ref": 66.0,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "AE38": {
        "emisor": "República Argentina", "descripcion": "Bonar 2038", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2038-01-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina", "tir_ref": 10.71, "paridad_ref": 78.0,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "GD35": {
        "emisor": "República Argentina", "descripcion": "Global 2035", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2035-07-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York", "tir_ref": 9.1, "paridad_ref": 75.2,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "AL35": {
        "emisor": "República Argentina", "descripcion": "Bonar 2035", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2035-07-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina", "tir_ref": 9.5, "paridad_ref": 73.8,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "GD41": {
        "emisor": "República Argentina", "descripcion": "Global 2041", "tipo": "BONO_USD",
        "moneda": "USD", "vencimiento": "2041-07-09", "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York", "tir_ref": 10.1, "paridad_ref": 70.5,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    # ── ONs legacy del scoring engine (YMCXO, RUCDO, MGCEO, MRCAO) ─────────
    "YMCXO": {
        "emisor": "YPF S.A.",
        "descripcion": "YPF 2031 (Serie YMCX)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2031-06-16",
        "cupon_anual": 0.090, "frecuencia": 2,
        "calificacion": "AA", "ley": "Nueva York",
        "tir_ref": 8.5, "paridad_ref": 101.5,
        "fecha_ref": "2026-04-01", "activo": True,
        "lamina_min": 1000, "callable": False,
    },
    "RUCDO": {
        "emisor": "Raghsa S.A.",
        "descripcion": "Raghsa 2026 (Serie D)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-11-30",
        "cupon_anual": 0.085, "frecuencia": 2,
        "calificacion": "A", "ley": "Argentina",
        "tir_ref": 7.8, "paridad_ref": 100.2,
        "fecha_ref": "2026-04-01", "activo": True,
        "lamina_min": 1000, "callable": False,
    },
    "MGCEO": {
        "emisor": "MercadoLibre Inc.",
        "descripcion": "MercadoLibre 2030 (Serie E)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2030-01-14",
        "cupon_anual": 0.0638, "frecuencia": 2,
        "calificacion": "BBB+", "ley": "Nueva York",
        "tir_ref": 7.0, "paridad_ref": 99.8,
        "fecha_ref": "2026-04-01", "activo": True,
        "lamina_min": 1000, "callable": False,
    },
    "MRCAO": {
        "emisor": "Mastellone Hermanos S.A.",
        "descripcion": "Mastellone 2026 (Serie A)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-07-01",
        "cupon_anual": 0.075, "frecuencia": 2,
        "calificacion": "A-", "ley": "Argentina",
        "tir_ref": 7.2, "paridad_ref": 99.5,
        "fecha_ref": "2026-04-01", "activo": True,
        "lamina_min": 1000, "callable": False,
    },
    # ── ONs adicionales de alta calidad ──────────────────────────────────────
    "YCA6O": {
        "emisor": "YPF S.A.",
        "descripcion": "YPF 2026 (corta)",
        "tipo": "ON_USD",
        "moneda": "USD",
        "vencimiento": "2026-07-01",
        "cupon_anual": 0.085,
        "frecuencia": 2,
        "calificacion": "AA",
        "ley": "Nueva York",
        "tir_ref": 5.8,
        "paridad_ref": 100.2,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "CSO2O": {
        "emisor": "Cresud S.A.",
        "descripcion": "Cresud 2026",
        "tipo": "ON_USD",
        "moneda": "USD",
        "vencimiento": "2026-02-08",
        "cupon_anual": 0.090,
        "frecuencia": 2,
        "calificacion": "A+",
        "ley": "Argentina",
        "tir_ref": 6.5,
        "paridad_ref": 101.0,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "MGCHO": {
        "emisor": "MercadoLibre Inc.",
        "descripcion": "MercadoLibre 2028",
        "tipo": "ON_USD",
        "moneda": "USD",
        "vencimiento": "2028-01-14",
        "cupon_anual": 0.0625,
        "frecuencia": 2,
        "calificacion": "BBB+",
        "ley": "Nueva York",
        "tir_ref": 7.2,
        "paridad_ref": 98.5,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "RCCJO": {
        "emisor": "Pampa Energía S.A.",
        "descripcion": "Pampa Energía 2027",
        "tipo": "ON_USD",
        "moneda": "USD",
        "vencimiento": "2027-07-21",
        "cupon_anual": 0.075,
        "frecuencia": 2,
        "calificacion": "AA-",
        "ley": "Nueva York",
        "tir_ref": 7.5,
        "paridad_ref": 99.8,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    # ── Bonos soberanos adicionales ─────────────────────────────────────────
    "GD29": {
        "emisor": "República Argentina",
        "descripcion": "Global 2029",
        "tipo": "BONO_USD",
        "moneda": "USD",
        "vencimiento": "2029-07-09",
        "cupon_anual": 0.0,
        "frecuencia": 2,
        "calificacion": "CCC",
        "ley": "Nueva York",
        "tir_ref": 8.5,
        "paridad_ref": 68.0,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "AL29": {
        "emisor": "República Argentina",
        "descripcion": "Bonar 2029",
        "tipo": "BONO_USD",
        "moneda": "USD",
        "vencimiento": "2029-07-09",
        "cupon_anual": 0.0,
        "frecuencia": 2,
        "calificacion": "CCC",
        "ley": "Argentina",
        "tir_ref": 8.9,
        "paridad_ref": 66.5,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    # ── Letras adicionales ─────────────────────────────────────────────────
    "S30A6": {
        "emisor": "Ministerio de Economía AR",
        "descripcion": "LEDE 30/04/2026",
        "tipo": "LETRA",
        "moneda": "ARS",
        "vencimiento": "2026-04-30",
        "cupon_anual": 0.0,
        "frecuencia": 0,
        "calificacion": "AA-AR",
        "ley": "Argentina",
        "tir_ref": 25.3,
        "paridad_ref": 97.2,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "S15Y6": {
        "emisor": "Ministerio de Economía AR",
        "descripcion": "LEDE 15/05/2026",
        "tipo": "LETRA",
        "moneda": "ARS",
        "vencimiento": "2026-05-15",
        "cupon_anual": 0.0,
        "frecuencia": 0,
        "calificacion": "AA-AR",
        "ley": "Argentina",
        "tir_ref": 25.6,
        "paridad_ref": 95.8,
        "fecha_ref": "2026-04-01",
        "activo": True,
    },
    "S17A6": {
        "emisor": "Ministerio de Economía AR", "descripcion": "LEDE 17/04/2026",
        "tipo": "LETRA", "moneda": "ARS", "vencimiento": "2026-04-17", "cupon_anual": 0.0,
        "frecuencia": 0, "calificacion": "AA-AR", "ley": "Argentina", "tir_ref": 24.59,
        "paridad_ref": 97.8, "fecha_ref": "2026-04-01", "activo": True,
    },
}

# P2-RF-05: campos opcionales por instrumento — `isin`, `lamina_min` / `denominacion_min`, `forma_amortizacion`.
# ISIN solo donde hay referencia pública estable; el resto queda ausente (UI muestra "—").
# Fuentes típicas: prospecto, página emisor, BYMA / agente de custodia.
_EXTRAS_CATALOGO_P2_RF5: dict[str, dict[str, Any]] = {
    "AL30": {
        "isin": "ARARGE3209S6",
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón; amortización programada (ver prospecto oficial)",
    },
    "GD30": {
        "isin": "US040114HS26",
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón; amortización en cuotas (ver prospecto oficial)",
    },
    "AE38": {"lamina_min": 1, "forma_amortizacion": "Cupón step-up; ver calendario en prospecto"},
    "GD35": {"lamina_min": 1, "forma_amortizacion": "Step-up cupón; ver prospecto oficial"},
    "AL35": {"lamina_min": 1, "forma_amortizacion": "Step-up cupón; ver prospecto oficial"},
    "GD41": {"lamina_min": 1, "forma_amortizacion": "Step-up cupón; ver prospecto oficial"},
    "AL29": {"lamina_min": 1, "forma_amortizacion": "Step-up cupón; ver prospecto oficial"},
    "TLCTO": {"forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "PN43O": {"forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "YM34O": {"lamina_min": 1, "forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "TSC4O": {"forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "IRCPO": {"forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "DNC7O": {"lamina_min": 1, "forma_amortizacion": "Cupones semestrales; principal al vencimiento (bullet)"},
    "S30A6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (letra descuento)"},
    "S15Y6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (letra descuento)"},
    "S17A6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (letra descuento)"},
}

for _tk, _add in _EXTRAS_CATALOGO_P2_RF5.items():
    if _tk in INSTRUMENTOS_RF:
        INSTRUMENTOS_RF[_tk].update(_add)

GUION_FICHA_RF = "—"


def ficha_rf_isin(meta: dict[str, Any] | None) -> str:
    """ISIN del instrumento o guión si no está en catálogo."""
    if not meta:
        return GUION_FICHA_RF
    v = meta.get("isin")
    if v is None or str(v).strip() == "":
        return GUION_FICHA_RF
    return str(v).strip()


def ficha_rf_denominacion_min(meta: dict[str, Any] | None) -> str:
    """
    Denominación mínima negociable: `denominacion_min` (texto libre) o `lamina_min` / `lamina_vn` en USD VN.
    """
    if not meta:
        return GUION_FICHA_RF
    dm = meta.get("denominacion_min")
    if dm is not None and str(dm).strip():
        return str(dm).strip()
    lam = meta.get("lamina_min")
    if lam is None:
        lam = meta.get("lamina_vn")
    try:
        if lam is not None and float(lam) > 0:
            return f"{int(float(lam)):,} USD VN".replace(",", ".")
    except (TypeError, ValueError):
        pass
    return GUION_FICHA_RF


def ficha_rf_forma_amortizacion(meta: dict[str, Any] | None) -> str:
    """Forma de amortización / cupones según catálogo; guión si no hay dato."""
    if not meta:
        return GUION_FICHA_RF
    fa = meta.get("forma_amortizacion")
    if fa is not None and str(fa).strip():
        return str(fa).strip()
    return GUION_FICHA_RF


_BONO_PREFIXES = ("AL", "GD", "TX", "PR")


def es_renta_fija(ticker: str) -> bool:
    return str(ticker or "").upper().strip() in INSTRUMENTOS_RF


def get_meta(ticker: str) -> dict[str, Any] | None:
    return INSTRUMENTOS_RF.get(str(ticker or "").upper().strip())


def precio_ars_on_usd_por_base_vn(
    paridad_pct: float,
    ccl: float,
    *,
    vn_usd: float = ON_USD_PARIDAD_BASE_VN,
) -> float:
    """
    Precio en ARS para `vn_usd` nominales USD, dado paridad % (100 = al par) y CCL.

    Caso típico BYMA/prospecto: vn_usd=100 → "ARS por cada 100 nominales USD"
    ≈ paridad_pct × CCL (ver álgebra en docstring del módulo).
    """
    p = float(paridad_pct)
    c = float(ccl)
    v = float(vn_usd)
    if p <= 0 or c <= 0 or v <= 0:
        return 0.0
    return v * (p / 100.0) * c


def meta_on_usd_unidades_resumen(ticker: str) -> dict[str, Any] | None:
    """
    Texto operativo único para alinear cartera, motor y pantallas (todas las ON USD del catálogo).
    """
    t = str(ticker or "").upper().strip()
    meta = get_meta(t)
    if meta is None or str(meta.get("tipo", "")).upper() != "ON_USD":
        return None
    lam = meta.get("lamina_min")
    if lam is None:
        lam = meta.get("lamina_vn")
    try:
        lamina_txt = f"{int(lam):,}".replace(",", ".") if lam is not None else "—"
    except (TypeError, ValueError):
        lamina_txt = "—"
    return {
        "ticker": t,
        "paridad_es_pct_sobre_nominal_usd": True,
        "base_vn_paridad_pct": ON_USD_PARIDAD_BASE_VN,
        "cantidad_significado": "Nominales USD en custodia (múltiplo de lámina mínima).",
        "ppc_usd_significado": (
            "Paridad de compra en % sobre nominal USD (misma unidad que paridad de mercado)."
        ),
        "precio_mercado_ars_formula": (
            f"ARS por {int(ON_USD_PARIDAD_BASE_VN)} VN USD ≈ (paridad_% / 100) × CCL × {int(ON_USD_PARIDAD_BASE_VN)} "
            f"= paridad_% × CCL"
        ),
        "lamina_min_vn_usd": lamina_txt,
        "emisor": meta.get("emisor"),
        "descripcion": meta.get("descripcion"),
    }


def analisis_obligaciones_negociables_usd_df(
    ccl: float,
    *,
    byma_live: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Una fila por cada ON_USD activa del catálogo: convención de unidades y precio referencia en ARS.

    `byma_live` opcional (mismo formato que `enriquecer_on_desde_byma`): si hay paridad en vivo,
    se usa para la columna de precio estimado; si no, `paridad_ref` del catálogo.
    """
    c = float(ccl)
    live = byma_live if isinstance(byma_live, dict) else {}
    rows: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue
        tu = ticker.upper()
        src = "Catálogo"
        try:
            p_live = live.get(tu, {}) if live else {}
            par = float(p_live.get("paridad_ref") or 0.0) if p_live else 0.0
            if par > 0:
                src = "BYMA (vivo)"
            else:
                par = float(meta.get("paridad_ref") or 0.0)
        except (TypeError, ValueError):
            par = float(meta.get("paridad_ref") or 0.0)
            src = "Catálogo"
        try:
            cup = float(meta.get("cupon_anual") or 0.0) * 100.0
        except (TypeError, ValueError):
            cup = 0.0
        lam = meta.get("lamina_min")
        if lam is None:
            lam = meta.get("lamina_vn")
        try:
            lam_i = int(lam) if lam is not None else None
        except (TypeError, ValueError):
            lam_i = None
        precio_100 = precio_ars_on_usd_por_base_vn(par, c, vn_usd=ON_USD_PARIDAD_BASE_VN) if par > 0 and c > 0 else None
        rows.append({
            "Ticker": tu,
            "Emisor": str(meta.get("emisor") or "—"),
            "Descripción": str(meta.get("descripcion") or "—"),
            "Vencimiento": str(meta.get("vencimiento") or "")[:10],
            "Cupón % nominal": round(cup, 2) if cup else None,
            "Paridad %": round(par, 2) if par > 0 else None,
            "Fuente paridad": src,
            f"ARS / {int(ON_USD_PARIDAD_BASE_VN)} VN USD (×CCL)": round(precio_100, 2) if precio_100 else None,
            "Lámina mín. VN USD": lam_i if lam_i is not None else "—",
            "CANTIDAD (significado)": "Nominales USD",
            "PPC_USD (significado)": "Paridad % sobre nominal USD",
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.sort_values("Ticker", ascending=True).reset_index(drop=True)


def tir_al_precio(
    ticker: str,
    paridad_compra: float,
    fecha_compra: str | None = None,
) -> float | None:
    del fecha_compra
    meta = get_meta(ticker)
    if meta is None or paridad_compra <= 0:
        return None
    tir_ref = float(meta["tir_ref"])
    paridad_ref = float(meta["paridad_ref"])
    if abs(paridad_compra - paridad_ref) < 0.1:
        return round(tir_ref, 2)
    delta_paridad = paridad_compra - paridad_ref
    tir_estimada = tir_ref - (delta_paridad * 0.08)
    return round(max(0.0, tir_estimada), 2)


def _unidad_precio_ficha_default(meta: dict[str, Any]) -> str:
    """Texto corto de unidad de precio para UI (P2-RF-01); sin lógica de cotización."""
    tipo = str(meta.get("tipo", "")).upper()
    mon = str(meta.get("moneda", "")).upper()
    if tipo in ("ON_USD", "BONO_USD") or mon == "USD":
        return (
            f"ARS por {int(ON_USD_PARIDAD_BASE_VN)} nominales USD (convención típica BYMA / prospecto)"
        )
    if mon == "ARS":
        return "Precio / cotización en ARS (validar unidad con fuente)."
    return "—"


def _cupon_pct_nominal_desde_meta(meta: dict[str, Any]) -> float | None:
    try:
        c = float(meta.get("cupon_anual") or 0.0)
    except (TypeError, ValueError):
        return None
    return round(c * 100.0, 4)


def ficha_rf_minima_bundle(
    ticker: str,
    meta: dict[str, Any] | None = None,
    *,
    paridad_pct: float | None = None,
    precio_mercado_ars: float | None = None,
    fuente_precio: str | None = None,
    unidad_precio: str | None = None,
    escala_div100_aplicada: bool = False,
    nota_escala: str | None = None,
) -> dict[str, Any]:
    """
    P2-RF-01: contrato único de dominio para la ficha RF mínima (serializable a JSON / tests).

    No duplica normalización BYMA (×100): se recibe con flags y texto ya interpretados en capa servicio/UI.
    """
    t = str(ticker or "").upper().strip()
    m: dict[str, Any] | None = dict(meta) if meta is not None else get_meta(t)
    if not m:
        return {
            "ticker": t,
            "ok": False,
            "motivo": "sin_meta_catalogo",
            "isin": GUION_FICHA_RF,
            "denominacion_min": GUION_FICHA_RF,
            "forma_amortizacion": GUION_FICHA_RF,
        }

    tir_ref_v: float | None = None
    try:
        if "tir_ref" in m and m.get("tir_ref") is not None:
            tir_ref_v = round(float(m["tir_ref"]), 2)
    except (TypeError, ValueError):
        tir_ref_v = None

    paridad_ref_v: float | None = None
    try:
        if "paridad_ref" in m and m.get("paridad_ref") is not None:
            paridad_ref_v = round(float(m["paridad_ref"]), 2)
    except (TypeError, ValueError):
        paridad_ref_v = None

    tir_a_precio: float | None = None
    tir_a_precio_motivo: str | None = None
    if tir_ref_v is None:
        tir_a_precio_motivo = "sin_tir_ref"
    elif paridad_pct is not None:
        try:
            pc = float(paridad_pct)
        except (TypeError, ValueError):
            pc = 0.0
        if pc > 0:
            tir_a_precio = tir_al_precio(t, pc)
        else:
            tir_a_precio_motivo = "sin_paridad_mercado"
    else:
        tir_a_precio_motivo = "sin_paridad_mercado"

    ven_d = fecha_vencimiento_desde_meta(m)
    ven_str = str(m.get("vencimiento") or "")[:10]
    try:
        cf_probe = cashflow_ilustrativo_por_100_vn(m, solo_futuros=True)
        cf_ok = bool(cf_probe.get("ok"))
    except Exception:
        cf_ok = False

    unit = unidad_precio if (unidad_precio and str(unidad_precio).strip()) else _unidad_precio_ficha_default(m)

    out: dict[str, Any] = {
        "ticker": t,
        "ok": True,
        "motivo": None,
        "emisor": str(m.get("emisor") or "—"),
        "descripcion": str(m.get("descripcion") or "—"),
        "tipo": str(m.get("tipo") or "—"),
        "moneda_emision": str(m.get("moneda") or "—"),
        "isin": ficha_rf_isin(m),
        "denominacion_min": ficha_rf_denominacion_min(m),
        "forma_amortizacion": ficha_rf_forma_amortizacion(m),
        "vencimiento": ven_str,
        "vencimiento_date_iso": ven_d.isoformat() if ven_d else None,
        "cupon_pct_nominal": _cupon_pct_nominal_desde_meta(m),
        "frecuencia_pagos": _frecuencia_cupon_label(m),
        "tir_ref_pct": tir_ref_v,
        "paridad_ref_pct": paridad_ref_v,
        "tir_a_precio_pct": tir_a_precio,
        "tir_a_precio_motivo": tir_a_precio_motivo,
        "precio_mercado_ars": float(precio_mercado_ars) if precio_mercado_ars is not None else None,
        "fuente_precio": str(fuente_precio).strip() if fuente_precio else None,
        "unidad_precio": unit,
        "escala_div100_aplicada": bool(escala_div100_aplicada),
        "nota_escala": str(nota_escala).strip() if nota_escala else None,
        "cashflow_ilustrativo_disponible": cf_ok,
    }
    return out


def valor_nominal_a_ars(valor_nominal_usd: float, paridad: float, ccl: float) -> float:
    return float(valor_nominal_usd) * (float(paridad) / 100.0) * float(ccl)


def descripcion_legible(ticker: str) -> str:
    meta = get_meta(ticker)
    if meta is None:
        return str(ticker or "")
    return f"{meta['emisor']} — {meta['descripcion']}"


def tickers_rf_activos() -> list[str]:
    activos = [(t, m) for t, m in INSTRUMENTOS_RF.items() if m.get("activo")]
    activos.sort(key=lambda x: str(x[1].get("vencimiento", "9999")))
    return [t for t, _ in activos]


def tickers_por_tipo(tipo: str) -> list[str]:
    tu = tipo.upper()
    return [
        t for t, m in INSTRUMENTOS_RF.items()
        if str(m.get("tipo", "")).upper() == tu and m.get("activo")
    ]


def _ano_vencimiento_meta(meta: dict[str, Any]) -> int | None:
    ven = meta.get("vencimiento")
    if ven is None:
        return None
    if isinstance(ven, int):
        return ven
    s = str(ven)
    try:
        return int(s[:4])
    except (TypeError, ValueError):
        return None


def _meta_unificado(ticker: str, universo: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    t = str(ticker or "").upper().strip()
    if t in INSTRUMENTOS_RF:
        m = dict(INSTRUMENTOS_RF[t])
        y = _ano_vencimiento_meta(m)
        if y is not None:
            m["vencimiento"] = y
        if "tir_ref" in m:
            m["tir_ref"] = float(m["tir_ref"])
        tipo = str(m.get("tipo", "")).upper()
        if tipo == "ON_USD":
            m["tipo"] = "ON"
        elif tipo == "BONO_USD":
            m["tipo"] = "BONO_SOBERANO"
        return m
    u = universo.get(t)
    return dict(u) if u else None


def _fraccion_peso_row(row: pd.Series) -> float:
    w = row.get("PESO_PCT", 0.0)
    try:
        f = float(w)
    except (TypeError, ValueError):
        f = 0.0
    if f > 1.0 + 1e-6:
        return f / 100.0
    return max(0.0, f)


def es_fila_renta_fija_ar(row: pd.Series, universo: dict[str, dict[str, Any]]) -> bool:
    t = str(row.get("TICKER", "")).strip().upper()
    tipo = str(row.get("TIPO", "")).strip().upper()
    if tipo in TIPOS_RF:
        return True
    if tipo in ("BONO_SOBERANO",):
        return True
    if t in INSTRUMENTOS_RF:
        return True
    if t in universo:
        return True
    for pref in _BONO_PREFIXES:
        if len(t) >= 4 and t.startswith(pref):
            return True
    return False


def tir_ponderada_cartera(
    df_ag: pd.DataFrame,
    universo_renta: dict[str, dict[str, Any]] | None = None,
) -> float | None:
    u = universo_renta if universo_renta is not None else UNIVERSO_RENTA_FIJA_AR
    if df_ag is None or df_ag.empty:
        return None
    num = 0.0
    den = 0.0
    for _, row in df_ag.iterrows():
        if not es_fila_renta_fija_ar(row, u):
            continue
        t = str(row.get("TICKER", "")).strip().upper()
        meta = _meta_unificado(t, u)
        if not meta or "tir_ref" not in meta:
            continue
        try:
            tir_f = float(meta["tir_ref"])
        except (TypeError, ValueError):
            continue
        w = _fraccion_peso_row(row)
        if w <= 0:
            continue
        num += w * tir_f
        den += w
    if den <= 1e-12:
        return None
    return num / den


_CALIF_RANK: dict[str, int] = {
    "AAA": 100, "AA+": 95, "AA": 90, "AA-": 85, "A+": 82, "A": 78, "A-": 75,
    "BBB+": 55, "BBB": 50, "BBB-": 48, "BB+": 40, "CCC+": 25, "CCC": 10,
}

MONITOR_ON_USD_DISCLAIMER = (
    "Todas las ON USD del catálogo usan la misma convención: paridad en % sobre nominal USD; "
    "el precio en pesos por cada 100 nominales USD ≈ paridad_% × CCL. "
    "Referencia educativa (paridad, TIR y cupón por instrumento). "
    "No reemplaza cotizaciones BYMA, láminas oficiales ni informes de custodio."
)


def bucket_riesgo_on_hd(meta: dict[str, Any]) -> str:
    """
    Banda tipo monitor HD: calificación (riesgo crédito) + TIR de referencia.
    Conservador: AA- o mejor y TIR ref. moderada (hasta 7,6 %).
    Agresivo: rating por debajo de BBB+ o TIR alta (más de 8,5 %).
    Moderado: casos intermedios.
    """
    try:
        tir = float(meta.get("tir_ref") or 0.0)
    except (TypeError, ValueError):
        tir = 0.0
    r = _calif_rank(str(meta.get("calificacion", "")))
    if r >= 85 and tir <= 7.6:
        return "conservador"
    if tir > 8.5 or r < 55:
        return "agresivo"
    return "moderado"


def _frecuencia_cupon_label(meta: dict[str, Any]) -> str:
    try:
        n = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 4:
        return "Trimestral"
    if n == 2:
        return "Semestral"
    if n == 1:
        return "Anual"
    if n <= 0:
        return "Al vencimiento"
    return str(n)


def monitor_on_usd_panel_df(
    byma_live: dict[str, dict[str, Any]] | None = None,
    *,
    ccl: float | None = None,
) -> pd.DataFrame:
    """
    Tabla tipo monitor ON en dólares (Hard Dollar / cable).
    Columnas alineadas a paneles de mercado; campos faltantes en metadatos → "—".

    Args:
        byma_live: dict opcional {ticker: {paridad_ref, var_diaria_pct, precio_ars,
                   fecha_ref, fuente, escala_div100}} proveniente de services.byma_market_data.
                   Cuando se provee, los campos de precio se actualizan con datos en vivo.
                   ``escala_div100`` indica si se aplicó heurística ÷100 al último/cierre (P2-RF-04).
    """
    _byma: dict[str, dict[str, Any]] = byma_live if byma_live else {}

    rows: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue

        # ── Datos de BYMA en vivo (tienen prioridad sobre metadatos estáticos) ──
        live = _byma.get(ticker.upper(), {})
        es_live = bool(live)

        try:
            paridad = float(live.get("paridad_ref") or meta.get("paridad_ref") or 0.0)
        except (TypeError, ValueError):
            paridad = 0.0
        try:
            tir = float(meta.get("tir_ref") or 0.0)
        except (TypeError, ValueError):
            tir = 0.0
        try:
            cupon = float(meta.get("cupon_anual") or 0.0) * 100.0
        except (TypeError, ValueError):
            cupon = 0.0

        # Variación diaria: BYMA primero, luego metadatos estáticos
        var_dia_raw = live.get("var_diaria_pct") if es_live else meta.get("var_diaria_pct")
        try:
            var_dia = round(float(var_dia_raw), 2) if var_dia_raw is not None else None
        except (TypeError, ValueError):
            var_dia = None

        # Precio en ARS (solo disponible vía BYMA)
        precio_ars_raw = live.get("precio_ars") if es_live else None
        try:
            precio_ars = round(float(precio_ars_raw), 2) if precio_ars_raw is not None else None
        except (TypeError, ValueError):
            precio_ars = None

        ven_raw = meta.get("vencimiento", "")
        ven_s = str(ven_raw)[:10] if ven_raw else "—"
        lamina = meta.get("lamina_min")
        if lamina is None:
            lamina = meta.get("lamina_vn")
        try:
            lamina_i = int(lamina) if lamina is not None else 1_000
        except (TypeError, ValueError):
            lamina_i = 1_000
        call_raw = meta.get("callable")
        if call_raw is None:
            callable_txt = "—"
        else:
            callable_txt = "Sí" if bool(call_raw) else "No"

        fecha_dato = (
            str(live.get("fecha_ref", ""))[:16]
            if es_live
            else str(meta.get("fecha_ref") or "—")[:10]
        )

        escala_div100 = bool(live.get("escala_div100")) if es_live else False

        ars_100_vn: float | None = None
        try:
            ccl_f = float(ccl) if ccl is not None else 0.0
        except (TypeError, ValueError):
            ccl_f = 0.0
        if paridad and ccl_f > 0:
            ars_100_vn = round(
                precio_ars_on_usd_por_base_vn(paridad, ccl_f, vn_usd=ON_USD_PARIDAD_BASE_VN),
                2,
            )

        rows.append({
            "Banda":           bucket_riesgo_on_hd(meta),
            "Ticker":          ticker,
            "Emisor":          str(meta.get("emisor") or "—"),
            "Tipo":            "Hard Dollar",
            "Paridad %":       round(paridad, 2) if paridad else None,
            f"ARS / {int(ON_USD_PARIDAD_BASE_VN)} VN USD": ars_100_vn,
            "Precio ARS":      precio_ars,
            "Var. % día":      var_dia,
            "Cupón %":         round(cupon, 2),
            "TIR ref. %":      round(tir, 2),
            "MD":              meta.get("modified_duration", "—"),
            "Vencimiento":     ven_s,
            "Moneda":          "CABLE",
            "Amortización":    str(meta.get("amortizacion") or "Bullet"),
            "Callable":        callable_txt,
            "Calificación":    str(meta.get("calificacion") or "—"),
            "Lámina mín.":     lamina_i,
            "ISIN":            str(meta.get("isin") or "—"),
            "Frecuencia cupón":_frecuencia_cupon_label(meta),
            "Ley":             str(meta.get("ley") or "—"),
            "Fecha dato":      fecha_dato,
            "Fuente":          "🟢 BYMA en vivo" if es_live else "📋 Catálogo",
            # P2-RF-04 — Sí = último/cierre BYMA normalizado ÷100 (feed en escala ×100)
            "Ajuste ×100 BYMA": "Sí" if escala_div100 else ("No" if es_live else "—"),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    _order = {"conservador": 0, "moderado": 1, "agresivo": 2}
    df["_sort_banda"] = df["Banda"].map(lambda b: _order.get(str(b), 9))
    df = df.sort_values(["_sort_banda", "TIR ref. %"], ascending=[True, False]).drop(
        columns=["_sort_banda"]
    )
    return df.reset_index(drop=True)


_MESES_ES_VTO = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF = (
    "Importes **por cada 100 unidades de valor nominal (VN)** en la **moneda de emisión** del catálogo. "
    "Las fechas se **aproximan** desde la fecha de vencimiento y la frecuencia de cupón de los metadatos "
    "internos (no desde el prospecto). **No** es un calendario legal de pagos: no sustituye prospecto, "
    "suplementos ni comunicación del emisor. Se asume cupón fijo y amortización **bullet** al vencimiento, "
    "sin impuestos ni comisiones."
)


def fecha_vencimiento_desde_meta(meta: dict[str, Any] | None) -> date | None:
    """Parsea `vencimiento` (YYYY-MM-DD u otras formas pandas) a `date`."""
    if not meta:
        return None
    ven_raw = meta.get("vencimiento")
    ts = pd.to_datetime(ven_raw, errors="coerce")
    if pd.isna(ts):
        return None
    d = ts.date()
    return d if isinstance(d, date) else None


def _meses_entre_cupones(frecuencia: int) -> int:
    """Meses entre fechas de pago aproximadas (1=año, 2=semestre, 4=trimestre)."""
    try:
        f = int(frecuencia)
    except (TypeError, ValueError):
        f = 0
    if f <= 0:
        return 12
    if f == 1:
        return 12
    if f == 2:
        return 6
    if f >= 4:
        return 3
    return max(1, 12 // f)


def cashflow_ilustrativo_por_100_vn(
    meta: dict[str, Any] | None,
    *,
    hoy: date | None = None,
    max_filas: int = 60,
    solo_futuros: bool = True,
) -> dict[str, Any]:
    """
    P2-RF-02: cashflow **ilustrativo** en base 100 VN y moneda de emisión.

    Calendario aproximado (hacia atrás desde el vencimiento con paso fijo según frecuencia).
    Cupón cero: un solo flujo al vencimiento con amortización del nominal.
    """
    from dateutil.relativedelta import relativedelta

    base = 100.0
    hoy_d = hoy or date.today()
    out: dict[str, Any] = {
        "ok": False,
        "base_vn": base,
        "moneda_emision": "",
        "disclaimer": DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF,
        "filas": [],
        "aviso": "",
    }
    if not meta:
        out["aviso"] = "Sin metadatos de instrumento."
        return out

    vm = fecha_vencimiento_desde_meta(meta)
    if vm is None:
        out["aviso"] = "Sin fecha de vencimiento parseable."
        return out

    moneda = str(meta.get("moneda") or "USD").strip()[:12] or "USD"
    out["moneda_emision"] = moneda

    try:
        cupon_anual = float(meta.get("cupon_anual") or 0.0)
    except (TypeError, ValueError):
        cupon_anual = 0.0
    try:
        freq = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        freq = 0

    if cupon_anual <= 1e-15:
        fila = {
            "fecha": vm.isoformat(),
            "concepto": "Amortización nominal al vencimiento (ilustrativo, sin cupones)",
            "monto_100vn": round(base, 4),
            "moneda": moneda,
        }
        if solo_futuros and vm < hoy_d:
            out["ok"] = True
            out["aviso"] = "Vencimiento ya ocurrió: no hay flujos futuros ilustrativos."
            out["filas"] = []
            return out
        out["ok"] = True
        out["filas"] = [fila]
        return out

    if freq <= 0:
        freq = 2

    meses = _meses_entre_cupones(freq)
    cupon_por_periodo = base * (cupon_anual / float(freq))

    fechas_rev: list[date] = []
    d = vm
    for _ in range(max(4, max_filas)):
        fechas_rev.append(d)
        d = d - relativedelta(months=meses)
        if len(fechas_rev) >= max_filas:
            break

    fechas = sorted(set(fechas_rev))
    if solo_futuros:
        fechas = [x for x in fechas if x >= hoy_d]
    fechas = [x for x in fechas if x <= vm]
    fechas.sort()

    if not fechas:
        out["ok"] = True
        out["aviso"] = "Sin fechas de pago ilustrativas en el rango (revisá vencimiento vs. hoy)."
        out["filas"] = []
        return out

    filas: list[dict[str, Any]] = []
    for fd in fechas:
        es_vto = fd == vm
        if es_vto:
            monto = cupon_por_periodo + base
            concepto = "Cupón + amortización VN (ilustrativo)"
        else:
            monto = cupon_por_periodo
            concepto = "Cupón (ilustrativo)"
        filas.append({
            "fecha": fd.isoformat(),
            "concepto": concepto,
            "monto_100vn": round(monto, 4),
            "moneda": moneda,
        })

    out["ok"] = True
    out["filas"] = filas
    return out


def _meses_calendario_pago_cupon(meta: dict[str, Any], fecha_vto: date) -> tuple[set[int], str]:
    """
    Meses del año (1–12) en que habitualmente hay pago de cupón, según frecuencia y fecha de vencimiento
    del catálogo (convención estándar: calendario alineado al último cupón en la fecha de vto).

    - Sin cupón periódico / al vencimiento: solo el mes del vencimiento (devolución de principal).
    - Semestral: mes del vto y mes opuesto (+6).
    - Trimestral: mes del vto y cada -3 meses (4 fechas/año).
    - Anual: solo mes del vto.
    """
    if not isinstance(fecha_vto, date):
        return set(), ""
    m = int(fecha_vto.month)
    try:
        cup = float(meta.get("cupon_anual") or 0.0)
    except (TypeError, ValueError):
        cup = 0.0
    try:
        freq = int(meta.get("frecuencia") or 0)
    except (TypeError, ValueError):
        freq = 0

    if cup <= 1e-12 or freq <= 0:
        s = {m}
        note = f"{_MESES_ES_VTO[m - 1].title()} (solo principal al venc.)"
        return s, note

    if freq == 1:
        s = {m}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    if freq == 2:
        o = ((m - 1 + 6) % 12) + 1
        s = {m, o}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    if freq >= 4:
        s = {((m - 1 - 3 * k) % 12) + 1 for k in range(4)}
        note = " · ".join(_MESES_ES_VTO[x - 1].title() for x in sorted(s))
        return s, note
    s = {m}
    note = _MESES_ES_VTO[m - 1].title()
    return s, note


def monitor_on_usd_vencimientos_por_mes_df() -> pd.DataFrame:
    """
    ON USD activas del catálogo: **calendario por mes de pago de cupón** (enero…diciembre).

    Cada fila es un (ticker, mes calendario): una misma ON puede repetirse en varios meses si paga
    varias veces al año. Referencia educativa: fechas inferidas desde vencimiento + frecuencia del catálogo.
    """
    rows: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue
        ven_raw = meta.get("vencimiento")
        ts = pd.to_datetime(ven_raw, errors="coerce")
        if pd.isna(ts):
            continue
        d = ts.date()
        if not isinstance(d, date):
            continue
        meses_cup, cal_label = _meses_calendario_pago_cupon(meta, d)
        lamina = meta.get("lamina_min")
        if lamina is None:
            lamina = meta.get("lamina_vn")
        try:
            lamina_i = int(lamina) if lamina is not None else 1_000
        except (TypeError, ValueError):
            lamina_i = 1_000
        try:
            tir = float(meta.get("tir_ref") or 0.0)
        except (TypeError, ValueError):
            tir = 0.0
        try:
            cupon = float(meta.get("cupon_anual") or 0.0) * 100.0
        except (TypeError, ValueError):
            cupon = 0.0
        ven_str = d.strftime("%d/%m/%Y")
        frec_lbl = _frecuencia_cupon_label(meta)
        emisor = str(meta.get("emisor") or "—")

        for mes_ord in sorted(meses_cup):
            mes_lab = _MESES_ES_VTO[mes_ord - 1].title()
            rows.append({
                "_mes_ord": mes_ord,
                "_vto_key": d.year * 10_000 + d.month * 100 + d.day,
                "Mes": mes_lab,
                "Vencimiento": ven_str,
                "Ticker": ticker,
                "Emisor": emisor,
                "TIR ref. %": round(tir, 2),
                "Cupón %": round(cupon, 2),
                "Frec. cupón": frec_lbl,
                "Pagos en el año (cupón)": cal_label,
                "Lámina mín.": lamina_i,
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values(["_mes_ord", "_vto_key", "Ticker"], ascending=[True, True, True]).reset_index(
        drop=True
    )
    return df.drop(columns=["_mes_ord", "_vto_key"])


def _calif_rank(cal: str) -> int:
    return _CALIF_RANK.get(str(cal or "").strip().upper(), 0)


def top_instrumentos_rf(
    n: int = 4,
    universo_renta: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    u = universo_renta if universo_renta is not None else UNIVERSO_RENTA_FIJA_AR
    cands: list[tuple[float, int, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD":
            continue
        try:
            tir = float(meta.get("tir_ref", 0.0))
        except (TypeError, ValueError):
            continue
        cands.append((tir, _calif_rank(str(meta.get("calificacion", ""))), ticker, meta))
        seen.add(ticker)
    for ticker, meta in u.items():
        if str(meta.get("tipo", "")).strip().upper() != "ON":
            continue
        if ticker in seen:
            continue
        try:
            tir = float(meta.get("tir_ref", 0.0))
        except (TypeError, ValueError):
            continue
        cands.append((tir, _calif_rank(str(meta.get("calificacion", ""))), ticker, meta))
    cands.sort(key=lambda x: (-x[0], -x[1], x[2]))
    out: list[dict[str, Any]] = []
    for tir, _rank, ticker, meta in cands[: max(0, n)]:
        ven = meta.get("vencimiento")
        out.append({
            "ticker": ticker, "tir_ref": tir, "calificacion": meta.get("calificacion", ""),
            "emisor": meta.get("emisor", ""), "vencimiento": ven,
        })
    return out


def ladder_vencimientos(
    df_ag: pd.DataFrame,
    universo_renta: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[int, float]]:
    u = universo_renta if universo_renta is not None else UNIVERSO_RENTA_FIJA_AR
    if df_ag is None or df_ag.empty:
        return []
    by_year: dict[int, float] = {}
    for _, row in df_ag.iterrows():
        if not es_fila_renta_fija_ar(row, u):
            continue
        t = str(row.get("TICKER", "")).strip().upper()
        meta = _meta_unificado(t, u)
        if not meta:
            continue
        y = _ano_vencimiento_meta(meta)
        if y is None:
            continue
        w = _fraccion_peso_row(row)
        by_year[y] = by_year.get(y, 0.0) + w
    return sorted(by_year.items(), key=lambda x: x[0])


RF_SCHEMA_KEYS: tuple[str, ...] = (
    "ticker", "cupon_pct", "vencimiento", "nominal_unidad", "moneda",
    "frecuencia_cupon", "tir_ref", "precio_mercado_ars", "spread_tir_pp",
)


def meta_rf_con_precio(
    ticker: str,
    precio_mercado_ars: float | None = None,
    universo_renta: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    u = universo_renta if universo_renta is not None else UNIVERSO_RENTA_FIJA_AR
    t = str(ticker or "").strip().upper()
    src: dict[str, Any] = dict(u.get(t, {}))
    ins = get_meta(t)
    if ins:
        if "cupon_pct" not in src and "cupon_anual" in ins:
            src["cupon_pct"] = float(ins["cupon_anual"]) * 100.0
        src.setdefault("emisor", ins.get("emisor"))
        src.setdefault("descripcion", ins.get("descripcion"))
        y = _ano_vencimiento_meta(ins)
        if y is not None and "vencimiento" not in src:
            src["vencimiento"] = y
        src.setdefault("tir_ref", ins.get("tir_ref"))
        src.setdefault("moneda", ins.get("moneda"))
        if "frecuencia_cupon" not in src and ins.get("frecuencia"):
            src["frecuencia_cupon"] = int(ins["frecuencia"])
    out: dict[str, Any] = {k: None for k in RF_SCHEMA_KEYS}
    out["ticker"] = t or None
    for k in RF_SCHEMA_KEYS:
        if k in ("ticker", "precio_mercado_ars", "spread_tir_pp"):
            continue
        if k == "nominal_unidad":
            out[k] = src.get("nominal_unidad")
            continue
        if k in src:
            out[k] = src[k]
    if precio_mercado_ars is not None:
        try:
            out["precio_mercado_ars"] = float(precio_mercado_ars)
        except (TypeError, ValueError):
            out["precio_mercado_ars"] = None
    return out
