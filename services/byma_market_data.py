"""
services/byma_market_data.py — Listas de instrumentos BYMA en tiempo real.

Documentación de mapeo campo API → MQ26 y escalas ON: docs/product/BYMA_CAMPOS_Y_ESCALAS_MQ26.md

Fuente: BYMA Open Data (https://open.bymadata.com.ar)
  POST /vanoms-be-core/rest/api/bymadata/free/<tipo>
  Body: {"excludeZeroPxAndQty": true, "T2": true, "T1": false, "T0": false}

Tipos disponibles:
  equities         → Acciones argentinas
  cedears          → CEDEARs
  government-bonds → Bonos soberanos
  lebac-notes      → Letras (LETES, LECAP, LECER, etc.)
  corporate-bonds  → Obligaciones Negociables (ONs)

Funciones públicas sin dependencia de Streamlit:
  fetch_on_byma_live()              → dict[str, dict] con datos crudos de ONs
  enriquecer_on_desde_byma(ccl)     → dict[str, dict] con paridad%, var%, fecha
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

_BASE_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"
_TIMEOUT  = 15
_TTL      = 300  # segundos de caché (5 minutos)

# Precio BYMA ON Hard Dollar: puede venir como (a) % par directo, (b) ARS por VN USD 1,
# o (c) ARS por cada 100 nominales USD (típico prospecto / pantallas).
# Además, el feed Open Data de corporate-bonds a veces trae el último en **escala ×100**
# respecto del ARS por 1 USD nominal (ej. 148500 → 1485, alineado con pantallas tipo Balanz).
# Paridad % del motor = siempre % sobre nominal USD (100 % = al par).
_PRECIO_UMBRAL_ARS = 500.0  # por debajo → asumir precio ya en % par


def normalizar_precio_ars_on_usd_desde_feed_o_broker(px_raw: float, ccl: float) -> float:
    """
    P2-BYMA-02: misma heurística que el procesamiento del feed Open Data para ON USD,
    aplicable a precios crudos ingestados desde BD/ETL/broker (escala ×100 → ARS por 1 VN).

    Delega en `_normalizar_lastprice_on_byma` (única fuente de verdad de escala).
    """
    return _normalizar_lastprice_on_byma_meta(px_raw, ccl)[0]


def _normalizar_lastprice_on_byma_meta(px_raw: float, ccl: float) -> tuple[float, bool]:
    """
    Convierte lastPrice crudo de BYMA al **ARS por 1 USD nominal** cuando viene en escala ×100.

    Heurística: si el precio “completo” implica paridad absurda (>500 %) pero precio/100 implica
    paridad típica ON (35–220 %), se usa precio/100.

    Returns:
        (precio_ars_por_unidad, True) si se aplicó ÷100; (precio, False) si no.
    """
    if ccl <= 0 or px_raw <= 0:
        return float(px_raw), False
    px = float(px_raw)
    ccl_f = float(ccl)
    par_full = (px / ccl_f) * 100.0
    par_scaled = (px / 100.0 / ccl_f) * 100.0
    if 35.0 <= par_scaled <= 220.0 and par_full > 500.0:
        return px / 100.0, True
    return px, False


def _normalizar_lastprice_on_byma(px_raw: float, ccl: float) -> float:
    """Retrocompatibilidad tests y callers que solo necesitan el precio."""
    return _normalizar_lastprice_on_byma_meta(px_raw, ccl)[0]


def _paridad_pct_desde_precio_on(px: float, ccl: float) -> float:
    """
    Infiere paridad % (50–140 típico ON) desde último precio BYMA y CCL.

    - px < _PRECIO_UMBRAL_ARS → ya es % par.
    - Si px/CCL está en rango ON → px es ARS por cada **100** VN USD.
    - Si (px/CCL)×100 está en rango → px es ARS por **1** VN USD.
    - Si no, conserva el comportamiento histórico (×100).
    """
    if ccl <= 0:
        ccl = 1.0
    if px < _PRECIO_UMBRAL_ARS:
        return round(float(px), 2)
    r1 = float(px) / float(ccl)
    r2 = r1 * 100.0
    _lo, _hi = 35.0, 160.0
    if _lo <= r1 <= _hi:
        return round(r1, 2)
    if _lo <= r2 <= _hi:
        return round(r2, 2)
    return round(r2, 2)

_ENDPOINTS: dict[str, str] = {
    "Acciones Arg.":  "equities",
    "CEDEARs":        "cedears",
    "Bonos":          "government-bonds",
    "Letras":         "lebac-notes",
    "Oblig. Neg.":    "corporate-bonds",
}

_COLS_DISPLAY = {
    "symbol":        "Ticker",
    "description":   "Descripción",
    "lastPrice":     "Último",
    "variationRate": "Var. %",
    "openingPrice":  "Apertura",
    "max":           "Máximo",
    "min":           "Mínimo",
    "volumeAmount":  "Vol. Nominal",
    "quantityBuy":   "Comp.",
    "quantitySell":  "Venta",
    "closingPrice":  "Cierre ant.",
    "settlementType":"Plazo",
}


def _fetch_tipo(endpoint: str) -> list[dict[str, Any]]:
    url  = f"{_BASE_URL}/{endpoint}"
    body = json.dumps({
        "excludeZeroPxAndQty": True,
        "T2": True, "T1": False, "T0": False,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "User-Agent":   "MQ26Terminal/1.0",
    }
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, OSError):
        return []

    data = raw if isinstance(raw, list) else raw.get("data", [])
    return data if isinstance(data, list) else []


# ─── FUNCIONES PURAS (sin dependencia Streamlit) ────────────────────────────

def fetch_on_byma_live() -> dict[str, dict[str, Any]]:
    """
    Devuelve dict {ticker_upper: {lastPrice, variationRate, closingPrice, description}}
    con los datos crudos de ONs (corporate-bonds) desde BYMA Open Data.
    Retorna {} si la consulta falla.
    """
    rows = _fetch_tipo("corporate-bonds")
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        sym = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
        if not sym:
            continue
        out[sym] = {
            "lastPrice":     r.get("lastPrice"),
            "closingPrice":  r.get("closingPrice"),
            "variationRate": r.get("variationRate"),
            "volumeAmount":  r.get("volumeAmount"),
            "description":   r.get("description") or r.get("descripcion") or "",
            "settlementType":r.get("settlementType", ""),
        }
    return out


def enriquecer_on_desde_byma(ccl: float) -> dict[str, dict[str, Any]]:
    """
    Obtiene datos en vivo de ONs desde BYMA y los convierte a métricas
    utilizables por el motor de renta fija.

    Retorna dict {ticker: {paridad_ref, var_diaria_pct, fecha_ref, precio_ars,
                            descripcion_byma, volumen}}
    donde paridad_ref está expresada en % par (ej: 101.5 = 101.5%).

    Lógica de conversión (ver `_paridad_pct_desde_precio_on`): distingue % par, ARS/VN y ARS/(100 VN).
    """
    if not ccl or ccl <= 0:
        ccl = 1.0

    raw = fetch_on_byma_live()
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M")
    resultado: dict[str, dict[str, Any]] = {}

    for ticker, datos in raw.items():
        try:
            px_raw = datos.get("lastPrice")
            if px_raw is None or str(px_raw).strip() in ("", "None"):
                continue
            px = float(px_raw)
            if px <= 0:
                continue

            px_u, div_ult = _normalizar_lastprice_on_byma_meta(px, ccl)
            paridad_pct = _paridad_pct_desde_precio_on(px_u, ccl)
            # ARS por 1 USD nominal (misma escala que brokers tipo Balanz / “último operado”)
            precio_unit_ars = round(px_u, 2)

            # Variación %
            var_pct: float | None = None
            var_raw = datos.get("variationRate")
            if var_raw is not None and str(var_raw).strip() not in ("", "None"):
                try:
                    var_pct = round(float(var_raw), 2)
                except (TypeError, ValueError):
                    pass

            # Si no hay variación del día, calcularla vs cierre anterior
            div_cierre = False
            if var_pct is None:
                cierre_raw = datos.get("closingPrice")
                if cierre_raw and str(cierre_raw).strip() not in ("", "None"):
                    try:
                        cierre = float(cierre_raw)
                        if cierre > 0:
                            cierre_u, div_cierre = _normalizar_lastprice_on_byma_meta(cierre, ccl)
                            if cierre_u > 0:
                                var_pct = round((px_u / cierre_u - 1) * 100, 2)
                    except (TypeError, ValueError):
                        pass

            resultado[ticker] = {
                "paridad_ref":     paridad_pct,
                "var_diaria_pct":  var_pct,
                "precio_ars":      precio_unit_ars,
                "volumen":         datos.get("volumeAmount"),
                "descripcion_byma": datos.get("description", ""),
                "fecha_ref":       ts,
                "fuente":          "BYMA_LIVE",
                # P2-RF-04: trazabilidad UI — feed a veces trae escala ×100
                "escala_div100":   bool(div_ult or div_cierre),
            }
        except (TypeError, ValueError, ZeroDivisionError):
            continue

    return resultado


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_on_byma(ccl: float) -> dict[str, dict[str, Any]]:
    """Versión cacheada (5 min) de enriquecer_on_desde_byma para uso en UI."""
    return enriquecer_on_desde_byma(ccl)


# ─── FUNCIONES STREAMLIT ────────────────────────────────────────────────────

@st.cache_data(ttl=_TTL, show_spinner=False)
def _cached_byma(tipo_label: str, endpoint: str) -> pd.DataFrame:
    rows = _fetch_tipo(endpoint)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    rename = {k: v for k, v in _COLS_DISPLAY.items() if k in df.columns}
    df = df.rename(columns=rename)
    keep = [v for v in _COLS_DISPLAY.values() if v in df.columns]
    df = df[keep].copy()
    for col in ("Último", "Apertura", "Máximo", "Mínimo", "Cierre ant."):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Var. %" in df.columns:
        df["Var. %"] = pd.to_numeric(df["Var. %"], errors="coerce")
    if "Vol. Nominal" in df.columns:
        df["Vol. Nominal"] = pd.to_numeric(df["Vol. Nominal"], errors="coerce")
    return df.sort_values("Ticker") if "Ticker" in df.columns else df


def render_byma_mercado() -> None:
    """Renderiza las listas de mercado BYMA dentro de un tab de Streamlit."""
    st.subheader("📋 Mercado BYMA — Instrumentos en tiempo real")
    st.caption(
        "Fuente: BYMA Open Data · actualización automática cada 5 minutos. "
        "Instrumentos con operaciones en el día (T+2 por defecto)."
    )

    _col_sel, _col_btn = st.columns([3, 1])
    with _col_sel:
        tipo_sel = st.selectbox(
            "Tipo de instrumento:",
            list(_ENDPOINTS.keys()),
            key="byma_tipo_sel",
        )
    with _col_btn:
        st.write("")
        st.write("")
        if st.button("🔄 Actualizar", key="byma_refresh"):
            st.cache_data.clear()

    endpoint = _ENDPOINTS[tipo_sel]

    with st.spinner(f"Consultando BYMA — {tipo_sel}..."):
        df = _cached_byma(tipo_sel, endpoint)

    if df.empty:
        st.warning(
            f"No se pudieron obtener datos de BYMA para **{tipo_sel}**. "
            "Verificá la conexión a internet o intentá más tarde."
        )
        return

    # Búsqueda rápida por ticker o descripción
    _busq = st.text_input(
        "🔍 Filtrar por ticker o nombre:", key="byma_filtro", placeholder="ej: GGAL, AL30, LECAP..."
    )
    if _busq:
        mask = pd.Series([False] * len(df))
        for col in ("Ticker", "Descripción"):
            if col in df.columns:
                mask = mask | df[col].astype(str).str.upper().str.contains(_busq.upper(), na=False)
        df = df[mask]

    st.caption(f"**{len(df)}** instrumentos encontrados")

    # Colorear variación
    def _color_var(val):
        try:
            v = float(val)
            if v > 0:
                return "color:#27AE60;font-weight:bold"
            if v < 0:
                return "color:#E74C3C;font-weight:bold"
        except Exception:
            pass
        return ""

    styler = df.style
    if "Var. %" in df.columns:
        styler = styler.map(_color_var, subset=["Var. %"])
    fmt: dict[str, str] = {}
    for col in ("Último", "Apertura", "Máximo", "Mínimo", "Cierre ant."):
        if col in df.columns:
            fmt[col] = "{:,.2f}"
    if "Var. %" in df.columns:
        fmt["Var. %"] = "{:+.2f}%"
    if "Vol. Nominal" in df.columns:
        fmt["Vol. Nominal"] = "{:,.0f}"
    if fmt:
        styler = styler.format(fmt, na_rep="—")

    st.dataframe(styler, use_container_width=True, hide_index=True, height=520)

    # Timestamp
    st.caption(f"🕐 Última consulta: {pd.Timestamp.now().strftime('%H:%M:%S')}")
