from __future__ import annotations

import time

import pandas as pd
import plotly.graph_objects as go
import requests

RIPTE_URL = (
    "https://apis.datos.gob.ar/series/api/series/"
    "?ids=140.2_BEN_RIPS_0_0_27&format=json"
)
HABER_URL = (
    "https://apis.datos.gob.ar/series/api/series/"
    "?ids=11.3_CF_2004_A_21&format=json"
)

_CACHE: dict[str, tuple[float, object]] = {}


def _cache_get(key: str, cache_hours: int):
    row = _CACHE.get(key)
    if not row:
        return None
    ts, val = row
    return val if (time.time() - ts) <= cache_hours * 3600 else None


def fetch_ripte(cache_hours: int = 24) -> pd.Series:
    """
    Descarga el RIPTE (Remuneración Imponible Promedio de los Trabajadores Estables)
    desde la API de datos.gob.ar. Fallback a serie sintética si la API falla.
    """
    c = _cache_get("ripte", cache_hours)
    if c is not None:
        return c
    try:
        data = requests.get(RIPTE_URL, timeout=10).json().get("data", [])
        if not data:
            raise ValueError("API retornó lista vacía")
        idx = pd.to_datetime([x[0] for x in data])
        s   = pd.Series([float(x[1]) for x in data], index=idx).sort_index()
    except Exception:
        s = pd.Series([1.0, 1.1], index=pd.to_datetime(["2024-01-01", "2024-02-01"]))
    _CACHE["ripte"] = (time.time(), s)
    return s


def fetch_haber_minimo(cache_hours: int = 24) -> pd.Series:
    """
    Descarga el haber mínimo jubilatorio de Argentina desde la API de datos.gob.ar.
    Fallback a serie sintética si la API falla.
    """
    c = _cache_get("haber", cache_hours)
    if c is not None:
        return c
    try:
        resp = requests.get(HABER_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            raise ValueError("API retornó lista vacía")
        idx = pd.to_datetime([x[0] for x in data])
        s   = pd.Series([float(x[1]) for x in data], index=idx).sort_index()
    except Exception:
        s = pd.Series(
            [100_000.0, 110_000.0],
            index=pd.to_datetime(["2024-01-01", "2024-02-01"]),
        )
    _CACHE["haber"] = (time.time(), s)
    return s


def fetch_aportantes_beneficiarios() -> pd.DataFrame:
    return pd.DataFrame({"fecha": ["2024-01-01"], "aportantes": [1], "beneficiarios": [1]})


def generar_figura_ripte_usd(ripte: pd.Series, ccl: pd.Series) -> go.Figure:
    c = ccl.reindex(ripte.index).ffill().bfill()
    fig = go.Figure()
    fig.add_scatter(x=ripte.index, y=(ripte / c).values, mode="lines", name="RIPTE USD")
    fig.update_layout(title="RIPTE en USD (ajustado por CCL)", margin={"l": 0, "r": 0, "t": 40, "b": 0})
    return fig


def generar_figura_pension_vs_ripte(pension: pd.Series, ripte: pd.Series) -> go.Figure:
    idx = pension.index.intersection(ripte.index)
    fig = go.Figure()
    fig.add_scatter(x=idx, y=pension.loc[idx].values, name="Haber mínimo", mode="lines")
    fig.add_scatter(x=idx, y=ripte.loc[idx].values, name="RIPTE", mode="lines")
    fig.update_layout(title="Haber mínimo vs RIPTE", margin={"l": 0, "r": 0, "t": 40, "b": 0})
    return fig
