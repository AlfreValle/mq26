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

# Catálogo (datos) extraído a su propio módulo — re-export para compatibilidad.
from core.renta_fija_catalogo import (  # noqa: F401
    INSTRUMENTOS_RF,
    ON_USD_PARIDAD_BASE_VN,
    TIPOS_RF,
)

# Monitor ON + cashflow ilustrativo extraídos — re-export para compatibilidad.
from core.renta_fija_monitor import (  # noqa: F401
    _CALIF_RANK,
    _MESES_ES_VTO,
    DISCLAIMER_CASHFLOW_ILUSTRATIVO_RF,
    MONITOR_ON_USD_DISCLAIMER,
    _calif_rank,
    _frecuencia_cupon_label,
    _meses_calendario_pago_cupon,
    _meses_entre_cupones,
    bucket_riesgo_on_hd,
    cashflow_ilustrativo_por_100_vn,
    fecha_vencimiento_desde_meta,
    monitor_on_usd_panel_df,
    monitor_on_usd_vencimientos_por_mes_df,
)

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


def precio_referencia_ars_desde_catalogo(
    ticker: str,
    ccl: float,
    *,
    vn: float = 1.0,
) -> float:
    """
    A04: precio ARS de referencia por ``vn`` nominales desde ``paridad_ref``
    del catálogo. Normaliza la convención precio/VN en un solo lugar — antes
    esta aritmética vivía repetida en resolver_precios, resolver_precios_con_origen
    y PriceEngine, con el riesgo de divergir.

    - moneda USD: paridad% sobre VN USD × CCL → ARS por VN.
    - moneda ARS: ``paridad_ref`` ya es ARS por VN (BONCER/LECAP).

    Devuelve 0.0 si el ticker no está en catálogo, la paridad no es válida
    o falta CCL para instrumentos USD.
    """
    meta = get_meta(ticker)
    if meta is None:
        return 0.0
    try:
        paridad = float(meta.get("paridad_ref", 0) or 0)
        v = float(vn)
    except (TypeError, ValueError):
        return 0.0
    if paridad <= 0 or v <= 0:
        return 0.0
    if str(meta.get("moneda", "USD")).upper() == "USD":
        c = float(ccl or 0)
        if c <= 0:
            return 0.0
        return v * (paridad / 100.0) * c
    return v * paridad


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


# ── Selector dinámico de ONs para primera cartera ─────────────────────────────

# Puntos por calificación crediticia
_CAL_SCORE_RF: dict[str, float] = {
    "AAA": 10, "AA+": 9, "AA": 8, "AA-": 7,
    "A+": 6,  "A":  5, "A-": 4,
    "BBB+": 3, "BBB": 2, "BBB-": 1,
}

# Pesos (w_calificacion, w_tir) según perfil de riesgo
_PERFIL_PESOS_RF: dict[str, tuple[float, float]] = {
    "Conservador":    (3.0, 1.0),   # prioridad calidad crediticia
    "Moderado":       (2.0, 1.5),   # balance calificación / rendimiento
    "Arriesgado":     (1.0, 3.0),   # prioridad rendimiento
    "Muy arriesgado": (0.5, 4.0),   # máximo rendimiento
}


def seleccionar_ons_para_perfil(
    perfil: str,
    peso_total: float,
    n_max: int = 3,
    vencimiento_min_meses: int = 12,
    lamina_max_usd: int | None = None,
) -> dict[str, float]:
    """
    Selecciona las mejores ONs USD activas del catálogo para el perfil dado.

    Filtros duros:
      - tipo == "ON_USD", activo == True
      - vencimiento > hoy + vencimiento_min_meses (default 12 meses)
      - lamina_min ≤ lamina_max_usd si se especifica

    Scoring = w_cal × puntos_calificacion + w_tir × tir_ref  (pesos según perfil).
    Devuelve {ticker: peso} con los pesos sumando ≈ peso_total.
    Si no hay candidatos, devuelve dict vacío.
    """
    from datetime import timedelta

    hoy = date.today()
    fecha_corte = hoy + timedelta(days=int(vencimiento_min_meses) * 30)

    w_cal, w_tir = _PERFIL_PESOS_RF.get(perfil, (2.0, 1.5))

    candidatos: list[tuple[str, float]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if not meta.get("activo", False):
            continue
        if str(meta.get("tipo", "")).upper() != "ON_USD":
            continue
        vcto_str = str(meta.get("vencimiento", "") or "")
        try:
            vcto = date.fromisoformat(vcto_str[:10])
        except (ValueError, TypeError):
            continue
        if vcto <= fecha_corte:
            continue  # muy corto plazo

        lam = meta.get("lamina_min") if meta.get("lamina_min") is not None else meta.get("lamina_vn", 1)
        try:
            lam_i = int(lam) if lam is not None else 1
        except (TypeError, ValueError):
            lam_i = 1
        if lamina_max_usd is not None and lam_i > lamina_max_usd:
            continue

        tir = float(meta.get("tir_ref") or 0.0)
        cal_pts = _CAL_SCORE_RF.get(str(meta.get("calificacion", "") or "").strip(), 0)
        score = w_cal * cal_pts + w_tir * tir
        candidatos.append((ticker, score))

    if not candidatos:
        return {}

    candidatos.sort(key=lambda x: -x[1])
    seleccionados = candidatos[:n_max]

    total_score = sum(sc for _, sc in seleccionados)
    if total_score <= 0:
        # Reparto equitativo
        p_igual = round(float(peso_total) / len(seleccionados), 6)
        return {tk: p_igual for tk, _ in seleccionados}

    pesos: dict[str, float] = {}
    for tk, sc in seleccionados:
        pesos[tk] = round(float(peso_total) * sc / total_score, 6)

    # Corrección de redondeo al primer elemento
    diff = round(float(peso_total) - sum(pesos.values()), 6)
    if abs(diff) > 1e-7 and seleccionados:
        pesos[seleccionados[0][0]] = round(pesos[seleccionados[0][0]] + diff, 6)

    return pesos


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


# ── Sufijos de liquidación BYMA — normalización de tickers ON ─────────────────
# En BYMA el mismo instrumento cotiza con distintas letras finales según la
# modalidad de liquidación (vector de mercado secundario):
#   O  → cable / MEP (dólar hard)
#   D  → dólar MEP (T+2 en USD)
#   C  → contado con liqui
# El ticker base del prospecto (ej: "PNDCO") se mapea a cualquier variante.
# Uso: `normalizar_ticker_on("PNDCD")` → "PNDCO"
_ON_SUFIJOS_LIQUIDACION = {"O", "D", "C", "A"}   # letras finales reconocidas

def normalizar_ticker_on(ticker: str) -> str:
    """
    Devuelve el ticker ON con sufijo de liquidación canónico ('O' = cable/MEP).

    Ejemplo:
      normalizar_ticker_on("PNDCD") → "PNDCO"
      normalizar_ticker_on("YMCQOC") → "YMCQOO"   # raro pero posible
      normalizar_ticker_on("YMCQO") → "YMCQO"     # ya canónico
    """
    t = str(ticker or "").strip().upper()
    if len(t) >= 2 and t[-1] in _ON_SUFIJOS_LIQUIDACION and t[:-1]:
        return t[:-1] + "O"
    return t


# ── Interés corrido y vector de flujos (config.OBLIGACIONES_NEGOCIABLES) ──────
# Compatibles con la estructura enriquecida de config.py:
#   {"tasa_nominal_anual", "frecuencia_pago", "convencion_dias", "vn_residual",
#    "meses_cupon", "proximos_cupones_estimados", "esquema_amortizacion",
#    "fecha_vencimiento"}
#
# Diferenciación clave de Ley:
#   30/360  → Ley Nueva York (ON Hard Dollar): días = (Y2-Y1)*360 + (M2-M1)*30 + (D2-D1)
#   ACT/365 → Ley Local (ON Dólar MEP / ARS-linked): días = calendar.days reales
#
# vn_residual: fracción del nominal original aún pendiente.
#   Paridad real = precio_mercado / (100 × vn_residual).
#   Sin este ajuste el motor daría falsas alertas de arbitraje cuando la ON
#   ya amortizó parcialmente capital.

def _dias_corridos_30_360(d_inicio: date, d_fin: date) -> int:
    """Convención 30/360 (Ley Nueva York): cada mes = 30 días."""
    y1, m1, d1 = d_inicio.year, d_inicio.month, d_inicio.day
    y2, m2, d2 = d_fin.year,   d_fin.month,   d_fin.day
    d1 = min(d1, 30)
    if d1 == 30:
        d2 = min(d2, 30)
    return (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)


def _ultimo_cupon_anterior(on_data: dict, fecha_liq: date) -> date | None:
    """
    Devuelve la fecha del cupón inmediatamente anterior a `fecha_liq`
    usando `meses_cupon` (día coincide con el vencimiento final).
    """
    meses = on_data.get("meses_cupon", [])
    vto_str = on_data.get("fecha_vencimiento", "")
    try:
        vto = date.fromisoformat(vto_str)
    except (TypeError, ValueError):
        return None
    dia = vto.day
    candidatos: list[date] = []
    for anio in range(fecha_liq.year - 1, fecha_liq.year + 1):
        for mes in meses:
            try:
                import calendar as _cal
                ultimo = _cal.monthrange(anio, mes)[1]
                d = date(anio, mes, min(dia, ultimo))
                if d < fecha_liq:
                    candidatos.append(d)
            except ValueError:
                pass
    return max(candidatos) if candidatos else None


def calcular_interes_corrido(
    on_data: dict,
    fecha_liquidacion: date,
) -> float:
    """
    Interés corrido (accrued interest) por cada 1 unidad de VN residual.

    Flujo:
      1. Localiza el último cupón cobrado (usando ``meses_cupon`` y el día del vencimiento).
      2. Cuenta los días según la convención (30/360 o ACT/365).
      3. Aplica el ``vn_residual`` para reflejar que el nominal puede haberse reducido.

    Ejemplo:
      >>> on = OBLIGACIONES_NEGOCIABLES["YMCQO"]
      >>> calcular_interes_corrido(on, date(2026, 11, 15))
      0.02361...   # ≈ 7% / 2 períodos × (45 días / 180 días) × 1.0 VN
    """
    tna = float(on_data.get("tasa_nominal_anual", 0.0))
    freq = int(on_data.get("frecuencia_pago", 2))
    conv = str(on_data.get("convencion_dias", "30/360")).upper()
    vn_res = float(on_data.get("vn_residual", 1.0))

    ultimo_cupon = _ultimo_cupon_anterior(on_data, fecha_liquidacion)
    if ultimo_cupon is None:
        return 0.0

    if conv == "30/360":
        dias_corridos = _dias_corridos_30_360(ultimo_cupon, fecha_liquidacion)
        dias_periodo = 360 // freq
    else:  # ACT/365
        dias_corridos = (fecha_liquidacion - ultimo_cupon).days
        dias_periodo = 365 // freq

    if dias_periodo <= 0:
        return 0.0

    cupon_periodo = (tna / freq) * vn_res
    return cupon_periodo * (dias_corridos / dias_periodo)


def generar_vector_flujos(
    on_data: dict,
    fecha_liquidacion: date,
) -> list[dict]:
    """
    Vector de flujos futuros estimados por cada 1 unidad de VN residual.

    Para cada fecha en ``proximos_cupones_estimados`` mayor a ``fecha_liquidacion``:
      - Calcula cupón de interés ordinario sobre ``vn_residual``.
      - Si es BULLET: suma el capital solo en la fecha final de vencimiento.
      - Si es AMORTIZING: distribuye el capital restante linealmente entre los
        próximos cupones (aproximación; el prospecto puede diferir).

    Devuelve lista de dicts:
      [{"fecha": "YYYY-MM-DD", "monto": float, "tipo": str}, ...]

    Ejemplo:
      >>> on = OBLIGACIONES_NEGOCIABLES["TLCMO"]
      >>> flujos = generar_vector_flujos(on, date(2026, 5, 19))
      >>> flujos[0]
      {"fecha": "2026-06-15", "monto": 0.03621, "tipo": "Interés Puro"}
    """
    tna = float(on_data.get("tasa_nominal_anual", 0.0))
    freq = int(on_data.get("frecuencia_pago", 2))
    vn_res = float(on_data.get("vn_residual", 1.0))
    esquema = str(on_data.get("esquema_amortizacion", "BULLET")).upper()
    fecha_vto = on_data.get("fecha_vencimiento", "")
    cupones_str: list[str] = on_data.get("proximos_cupones_estimados", [])

    cupon_periodo = (tna / freq) * vn_res

    futuros: list[str] = [
        c for c in cupones_str
        if date.fromisoformat(c) > fecha_liquidacion
    ]

    if not futuros:
        return []

    flujos: list[dict] = []
    n_futuros = len(futuros)

    for _i, c_str in enumerate(futuros):
        es_ultimo = (c_str == futuros[-1])

        capital = 0.0
        if esquema == "BULLET":
            if c_str == fecha_vto:
                capital = vn_res
        else:  # AMORTIZING — distribución lineal sobre los períodos restantes
            capital = vn_res / n_futuros

        monto = cupon_periodo + capital
        tipo = "Interés+Amortización" if capital > 0 else "Interés Puro"

        flujos.append({
            "fecha": c_str,
            "monto": round(monto, 6),
            "tipo": tipo,
        })

    return flujos


# ═════════════════════════════════════════════════════════════════════════════
#  FUNCIONES DE PRICING CER / CAUCION
# ═════════════════════════════════════════════════════════════════════════════

def yield_caucion_tea(tna: float, plazo_dias: int) -> float:
    """
    Convierte TNA de caucion a TEA (Tasa Efectiva Anual) para el plazo dado.

    Formula: TEA = (1 + TNA * plazo/365)^(365/plazo) - 1

    Parametros
    ----------
    tna       : Tasa Nominal Anual (decimal — 0.34 = 34%)
    plazo_dias: dias del plazo de la caucion (1, 7, 30, etc.)

    Retorna
    -------
    TEA como decimal. Ejemplo: TNA=34%, 7 dias -> TEA ~= 40.3%
    """
    if plazo_dias <= 0 or tna <= 0:
        return max(float(tna), 0.0)
    factor = 1.0 + float(tna) * float(plazo_dias) / 365.0
    return round(float(factor ** (365.0 / float(plazo_dias)) - 1.0), 6)


def retorno_caucion_nominal(tna: float, plazo_dias: int, capital: float = 1.0) -> float:
    """
    Interes bruto a cobrar al vencimiento de una caucion.

    Formula: interes = capital * TNA * plazo / 365

    Ejemplo:
        retorno_caucion_nominal(0.34, 7, 1_000_000) -> ~6_520 ARS
    """
    return float(capital) * float(tna) * float(plazo_dias) / 365.0


def precio_cer_estimado(
    paridad_base_pct: float,
    cer_actual: float,
    cer_referencia: float,
) -> float:
    """
    Precio estimado (paridad %) de un bono CER ajustado por variacion del indice.

    Formula: precio_ajustado = paridad_base * (cer_actual / cer_referencia)
    Util cuando el bono fue marcado a mercado en una fecha anterior y se quiere
    proyectar la paridad a hoy asumiendo unicamente el ajuste CER (sin cambio de spread).

    Parametros
    ----------
    paridad_base_pct  : paridad de referencia (ej. 98.5 = 98.5% del VN)
    cer_actual        : valor CER del dia (publicado por BCRA)
    cer_referencia    : valor CER del dia en que se fijo paridad_base_pct

    Retorna
    -------
    Paridad estimada ajustada por CER (%).
    """
    if cer_referencia <= 0:
        return float(paridad_base_pct)
    return round(float(paridad_base_pct) * (float(cer_actual) / float(cer_referencia)), 4)


def retorno_esperado_cer_nominal_ars(
    spread_real: float,
    inflacion_mensual: float | None = None,
) -> float:
    """
    Retorno nominal esperado anual en ARS de un bono CER.

    Formula (Fisher): (1 + spread_real) * (1 + inflacion_anual) - 1

    Parametros
    ----------
    spread_real       : spread real anual del bono (decimal — 0.005 = 0.5%)
    inflacion_mensual : IPC mensual (si None, usa MACRO_AR["inflacion_mensual_ipc"])

    Retorna
    -------
    Retorno nominal anual esperado en ARS (decimal).
    """
    try:
        from config import MACRO_AR
        ipc_m = float(inflacion_mensual or MACRO_AR.get("inflacion_mensual_ipc", 0.03))
    except ImportError:
        ipc_m = float(inflacion_mensual or 0.03)

    inflacion_anual = (1.0 + ipc_m) ** 12 - 1.0
    return round((1.0 + float(spread_real)) * (1.0 + inflacion_anual) - 1.0, 4)


def tickers_rf_por_tipo_ampliado(tipo: str) -> list[str]:
    """
    Extiende tickers_por_tipo() incluyendo BOPREAL y BONCER.

    Tipos adicionales: "BOPREAL", "BONCER", "CAUCION"
    """
    tu = tipo.upper().strip()
    return [
        t for t, m in INSTRUMENTOS_RF.items()
        if str(m.get("tipo", "")).upper() == tu and m.get("activo", True)
    ]


def calcular_duration_rf_unificado(
    ticker: str,
    fecha_liq: date | None = None,
) -> dict[str, Any]:
    """
    Punto de entrada unificado de duration para todos los tipos de RF.

    Logica de despacho por tipo:
        BONCER  → usa duration_real (campo pre-calculado)
        CAUCION → usa plazo_dias / 365 (desde CAUCIONES_BYMA de config)
        BOPREAL, BONO_USD → intenta cashflow; fallback a duration_ref_anos
        ON_USD  → intenta cashflow; fallback a ley-based

    Retorna
    -------
    dict con:
        duration_anos : float (Duration Modificada en anos)
        tipo_metrica  : "real" | "nominal" | "plazo"
        fuente        : "cashflow" | "ref_precalculada" | "plazo_fijo"
    """
    if fecha_liq is None:
        fecha_liq = date.today()

    # 1. Buscar en INSTRUMENTOS_RF
    meta = INSTRUMENTOS_RF.get(ticker.upper())
    if meta is None:
        # 2. Intentar CAUCIONES_BYMA
        try:
            from config import CAUCIONES_BYMA
            cauc = CAUCIONES_BYMA.get(ticker)
            if cauc:
                return {
                    "duration_anos": float(cauc.get("duration_ref_anos", 0.082)),
                    "tipo_metrica":  "plazo",
                    "fuente":        "plazo_fijo",
                }
        except ImportError:
            pass
        return {"duration_anos": 2.5, "tipo_metrica": "nominal", "fuente": "default"}

    tipo = str(meta.get("tipo", "")).upper()

    # BONCER → duration real pre-calculada
    if tipo == "BONCER":
        dur = float(meta.get("duration_real", meta.get("duration_real_anos", 2.0)))
        return {"duration_anos": dur, "tipo_metrica": "real", "fuente": "ref_precalculada"}

    # BOPREAL / BONO_USD → intentar cashflow, fallback a ref
    if tipo in ("BOPREAL", "BONO_USD"):
        try:
            from config import BONOS_SOBERANOS
            ref = BONOS_SOBERANOS.get(ticker.upper(), {})
            dur_ref = float(ref.get("duration_ref_anos", 3.0))
        except ImportError:
            dur_ref = 3.0
        # Intentar calculo desde cashflows usando tir_mercado_ref como descuento
        flujos = cashflow_ilustrativo_por_100_vn(meta, hoy=fecha_liq, solo_futuros=True)
        if flujos.get("ok") and flujos.get("filas"):
            try:
                tir = float(meta.get("tir_ref", 8.8)) / 100.0  # era en pct
                freq = int(meta.get("frecuencia", 2))
                dur_mac = 0.0
                va_tot = 0.0
                for fila in flujos["filas"]:
                    fd = date.fromisoformat(fila["fecha"])
                    t_a = (fd - fecha_liq).days / 365.0
                    if t_a <= 0:
                        continue
                    per = freq * t_a
                    va = fila["monto_100vn"] / (1.0 + tir / freq) ** per
                    va_tot += va
                    dur_mac += t_a * va
                if va_tot > 0:
                    dm = (dur_mac / va_tot) / (1.0 + tir / freq)
                    return {"duration_anos": round(dm, 4),
                            "tipo_metrica": "nominal", "fuente": "cashflow"}
            except Exception:
                pass
        return {"duration_anos": dur_ref, "tipo_metrica": "nominal",
                "fuente": "ref_precalculada"}

    # ON_USD / default → cashflow con tir de ley
    return {"duration_anos": 2.5, "tipo_metrica": "nominal", "fuente": "default"}


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


# ═════════════════════════════════════════════════════════════════════════════
#  ALERTAS DE VENCIMIENTO PRÓXIMO
# ═════════════════════════════════════════════════════════════════════════════

def instrumentos_on_usd_proximos_vencer(dias: int = 90) -> list[dict[str, Any]]:
    """
    Instrumentos ON_USD activos cuyo vencimiento está dentro de los próximos ``dias`` días.

    Útil para alertas de gestión de cartera (reinversión, rolleo, cobro de principal).
    Los instrumentos devueltos siguen estando ``activo=True`` pero se aproximan al vencimiento.

    Parámetros
    ----------
    dias : int
        Ventana de alerta en días calendario (default 90).

    Devuelve
    --------
    Lista de dicts ordenados por ``dias_al_vto`` (ascendente), cada uno con:
        - ``ticker``         str   — código del instrumento
        - ``emisor``         str
        - ``descripcion``    str
        - ``vencimiento``    str   — YYYY-MM-DD
        - ``dias_al_vto``    int   — días hasta el vencimiento desde hoy
        - ``tir_ref``        float — TIR referencia del catálogo
        - ``calificacion``   str
        - ``lamina_min``     int   — lámina mínima USD VN
        - ``nivel_alerta``   str   — "CRITICO" (≤35 d) | "PROXIMO" (36-90 d) | "ATENCION" (resto)

    Ejemplo
    -------
    >>> proximos = instrumentos_on_usd_proximos_vencer(dias=90)
    >>> [p["ticker"] for p in proximos]
    ['MRCAO', 'YCA6O']   # ambos vencen jul-2026 (~35 días desde 2026-05-27)
    """
    hoy = date.today()
    resultado: list[dict[str, Any]] = []

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
        dias_al_vto = (vcto - hoy).days
        if dias_al_vto < 0 or dias_al_vto > int(dias):
            continue

        lam = meta.get("lamina_min") if meta.get("lamina_min") is not None else meta.get("lamina_vn", 1)
        try:
            lam_i = int(lam) if lam is not None else 1
        except (TypeError, ValueError):
            lam_i = 1

        if dias_al_vto <= 35:
            nivel = "CRITICO"
        elif dias_al_vto <= 90:
            nivel = "PROXIMO"
        else:
            nivel = "ATENCION"

        resultado.append({
            "ticker":       ticker,
            "emisor":       str(meta.get("emisor") or "—"),
            "descripcion":  str(meta.get("descripcion") or "—"),
            "vencimiento":  str(vcto_raw)[:10],
            "dias_al_vto":  dias_al_vto,
            "tir_ref":      float(meta.get("tir_ref") or 0.0),
            "calificacion": str(meta.get("calificacion") or "—"),
            "lamina_min":   lam_i,
            "nivel_alerta": nivel,
        })

    resultado.sort(key=lambda x: x["dias_al_vto"])
    return resultado


def resumen_alertas_vencimiento_on_usd(dias: int = 90) -> str:
    """
    Texto de alerta listo para mostrar en UI o logs.

    Devuelve string vacío si no hay instrumentos próximos a vencer.

    Ejemplo
    -------
    >>> print(resumen_alertas_vencimiento_on_usd())
    ⚠️  2 ON USD vencen en ≤90 días:
      🔴 MRCAO (Mastellone) — vence 2026-07-01 (35 días) — TIR 7.2% — CRÍTICO
      🔴 YCA6O (YPF Clase 6) — vence 2026-07-01 (35 días) — TIR 7.0% — CRÍTICO
    """
    proximos = instrumentos_on_usd_proximos_vencer(dias=dias)
    if not proximos:
        return ""

    lineas = [f"⚠️  {len(proximos)} ON USD vencen en ≤{dias} días:"]
    for p in proximos:
        icono = "🔴" if p["nivel_alerta"] == "CRITICO" else "🟡"
        lineas.append(
            f"  {icono} {p['ticker']} ({p['emisor']}) — "
            f"vence {p['vencimiento']} ({p['dias_al_vto']} días) — "
            f"TIR {p['tir_ref']:.1f}% — {p['nivel_alerta']}"
        )
    return "\n".join(lineas)


# ─── Utilidades de lámina y precio mínimo de compra ──────────────────────────

def lamina_min_on(ticker: str) -> int:
    """
    Devuelve la lámina mínima negociable en VN USD de una ON del catálogo.

    La lámina es la unidad mínima de negociación; cada compra debe ser un
    múltiplo entero de ella.

    Ejemplos de láminas habituales en BYMA:
      - 1 VN USD  : TLCTO, YM34O, IRCPO, RCCJO, YCA6O
      - 100 VN USD: DNC7O
      - 1.000 VN USD: PN43O, YMCXO, MRCAO, MGCHO, MGCEO, RUCDO
      - 10.000 VN USD: TSC4O  ← sólo grandes inversores institucionales

    Retorna 1 si el ticker no es ON_USD o no está en el catálogo.
    """
    meta = INSTRUMENTOS_RF.get(str(ticker).upper())
    if not meta or str(meta.get("tipo", "")).upper() != "ON_USD":
        return 1
    try:
        return max(1, int(meta.get("lamina_min") or 1))
    except (TypeError, ValueError):
        return 1


def completar_lamina_vn_filas(filas: list[dict]) -> list[str]:
    """
    M2: autocompleta LAMINA_VN de filas de renta fija desde el catálogo, in-place.

    Una ON cargada sin lámina se valúa mal (la prueba funcional lo expuso). Acá,
    antes de persistir, toda fila RF cuyo LAMINA_VN falte (NaN/None/≤0) toma la
    lámina del catálogo (``lamina_min_on``). Devuelve la lista de avisos legibles
    (autocompletadas + RF sin catálogo que el usuario debe completar a mano).

    No lanza; filas sin TICKER o no-RF se ignoran. Pura (sin Streamlit/red).
    """
    avisos: list[str] = []
    for f in filas:
        tk = str(f.get("TICKER", "") or "").strip().upper()
        if not tk:
            continue
        meta = get_meta(tk)
        tipo = str(f.get("TIPO", "") or "").strip().upper()
        es_rf = meta is not None or tipo in TIPOS_RF
        if not es_rf:
            continue
        lam = f.get("LAMINA_VN")
        try:
            lam_f = float(lam)
            falta = lam_f != lam_f or lam_f <= 0  # NaN o no-positivo
        except (TypeError, ValueError):
            falta = True
        if not falta:
            continue
        if meta is not None:
            lamina = lamina_min_on(tk)
            f["LAMINA_VN"] = float(lamina)
            avisos.append(
                f"**{tk}**: lámina autocompletada en {lamina:,} VN USD desde el catálogo."
            )
        else:
            avisos.append(
                f"**{tk}**: renta fija fuera del catálogo — especificá la lámina (VN) a mano."
            )
    return avisos


def monto_minimo_compra_on(ticker: str, ccl: float) -> dict[str, float]:
    """
    Devuelve el monto mínimo de compra para una ON dada la lámina y el CCL.

    Returns
    -------
    dict con:
      - lamina_vn_usd  : lámina mínima en VN USD
      - monto_min_usd  : inversión mínima en USD  = lamina × paridad_ref / 100
      - monto_min_ars  : inversión mínima en ARS  = monto_min_usd × CCL
      - paridad_ref    : paridad de referencia usada (puede estar desactualizada)
      - fecha_ref      : fecha de la paridad de referencia
    """
    meta = INSTRUMENTOS_RF.get(str(ticker).upper()) or {}
    lamina = lamina_min_on(ticker)
    paridad = float(meta.get("paridad_ref") or 100.0)
    fecha_r = str(meta.get("fecha_ref") or "")
    monto_usd = lamina * paridad / 100.0
    monto_ars = monto_usd * ccl if ccl > 0 else 0.0
    return {
        "lamina_vn_usd": lamina,
        "monto_min_usd": round(monto_usd, 2),
        "monto_min_ars": round(monto_ars, 2),
        "paridad_ref": paridad,
        "fecha_ref": fecha_r,
    }


def tir_estimada_con_ccl(ticker: str, ccl: float) -> float | None:
    """
    Reestima la TIR de una ON usando la paridad_ref del catálogo y el CCL actual.

    Equivale a ``tir_al_precio(ticker, paridad_ref)`` pero con trazabilidad
    explícita de que el precio usado es *paridad_ref × CCL* (no precio live BYMA).

    Retorna None si el ticker no está en el catálogo o si el cálculo falla.

    Nota: ``paridad_ref`` puede tener unos días de antigüedad (ver ``fecha_ref``
    en el catálogo).  Para decisiones de alta precisión, usar la paridad BYMA
    del momento.
    """
    meta = INSTRUMENTOS_RF.get(str(ticker).upper())
    if not meta or str(meta.get("tipo", "")).upper() != "ON_USD":
        return None
    paridad_pct = float(meta.get("paridad_ref") or 0)
    if paridad_pct <= 0 or ccl <= 0:
        return None
    return tir_al_precio(ticker, paridad_compra=paridad_pct)


def ons_comprables_para_capital(
    capital_usd: float,
    horizonte_meses: int = 12,
    *,
    solo_activas: bool = True,
) -> list[dict[str, Any]]:
    """
    Filtra las ONs del catálogo que un inversor puede efectivamente comprar con
    ``capital_usd`` USD, dado un horizonte mínimo de inversión.

    Reglas de elegibilidad:
      1. ``tipo == "ON_USD"``
      2. ``activo == True`` (si ``solo_activas``)
      3. ``vencimiento > hoy + horizonte_meses meses``
      4. ``lámina_min_usd ≤ capital_usd``  ← precio mínimo de entrada comprable

    Returns lista de dicts con campos:
      ticker, emisor, paridad_ref, tir_ref, lamina_min, monto_min_usd,
      vencimiento, dias_al_vto, calificacion, fecha_ref
    """
    from datetime import timedelta

    hoy = date.today()
    fecha_corte = hoy + timedelta(days=int(horizonte_meses) * 30)

    resultado: list[dict[str, Any]] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD":
            continue
        if solo_activas and not meta.get("activo", False):
            continue
        vcto_raw = str(meta.get("vencimiento") or "")
        try:
            vcto = date.fromisoformat(vcto_raw[:10])
        except (ValueError, TypeError):
            continue
        if vcto <= fecha_corte:
            continue
        lamina = lamina_min_on(ticker)
        paridad = float(meta.get("paridad_ref") or 100.0)
        # Monto mínimo de compra en USD = lámina × paridad / 100
        monto_min_usd = lamina * paridad / 100.0
        if monto_min_usd > capital_usd:
            continue  # no alcanza para el lote mínimo
        dias = (vcto - hoy).days
        resultado.append({
            "ticker":      ticker,
            "emisor":      str(meta.get("emisor") or ""),
            "paridad_ref": paridad,
            "tir_ref":     float(meta.get("tir_ref") or 0.0),
            "lamina_min":  lamina,
            "monto_min_usd": round(monto_min_usd, 2),
            "vencimiento": vcto_raw[:10],
            "dias_al_vto": dias,
            "calificacion": str(meta.get("calificacion") or ""),
            "fecha_ref":   str(meta.get("fecha_ref") or ""),
        })

    resultado.sort(key=lambda x: -x["tir_ref"])
    return resultado
