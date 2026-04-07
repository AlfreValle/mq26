"""
core/renta_fija_ar.py — Renta fija Argentina (ON, bonos USD, letras).

Metadatos INSTRUMENTOS_RF + compatibilidad con UNIVERSO_RENTA_FIJA_AR
(para diagnóstico, ladder, TIR ponderada).

SIN streamlit ni yfinance.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from core.diagnostico_types import UNIVERSO_RENTA_FIJA_AR

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
    },
    "YM34O": {
        "emisor": "YPF S.A.", "descripcion": "YPF 2034", "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2034-07-01", "cupon_anual": 0.085, "frecuencia": 2,
        "calificacion": "AA", "ley": "Nueva York", "tir_ref": 7.1, "paridad_ref": 104.2,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "TLCTO": {
        "emisor": "Telecom Argentina", "descripcion": "Telecom 2036", "tipo": "ON_USD",
        "moneda": "USD", "vencimiento": "2036-06-19", "cupon_anual": 0.080, "frecuencia": 2,
        "calificacion": "AA", "ley": "Nueva York", "tir_ref": 8.0, "paridad_ref": 100.8,
        "fecha_ref": "2026-03-31", "activo": True,
    },
    "TSC4O": {
        "emisor": "TGS (Transportadora Gas del Sur)", "descripcion": "TGS 2035",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2035-05-14", "cupon_anual": 0.066,
        "frecuencia": 2, "calificacion": "AA+", "ley": "Nueva York", "tir_ref": 7.1,
        "paridad_ref": 97.5, "fecha_ref": "2026-03-31", "activo": True,
    },
    "IRCPO": {
        "emisor": "Irsa Inversiones y Representaciones", "descripcion": "Irsa 2035",
        "tipo": "ON_USD", "moneda": "USD", "vencimiento": "2035-02-08", "cupon_anual": 0.085,
        "frecuencia": 2, "calificacion": "AA-", "ley": "Nueva York", "tir_ref": 7.1,
        "paridad_ref": 105.0, "fecha_ref": "2026-03-31", "activo": True,
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

_BONO_PREFIXES = ("AL", "GD", "TX", "PR")


def es_renta_fija(ticker: str) -> bool:
    return str(ticker or "").upper().strip() in INSTRUMENTOS_RF


def get_meta(ticker: str) -> dict[str, Any] | None:
    return INSTRUMENTOS_RF.get(str(ticker or "").upper().strip())


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
    "BBB+": 55, "BBB": 50, "CCC": 10,
}


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
