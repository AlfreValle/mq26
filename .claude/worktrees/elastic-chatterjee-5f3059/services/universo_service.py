"""
services/universo_service.py — Servicio centralizado del universo de activos
MQ2-A3: Elimina los RATIOS_CEDEAR.get() dispersos en 6+ archivos.

Expone:
    listar_tickers()        → list[str]
    obtener_ratio(ticker)   → float
    obtener_sector(ticker)  → str
    buscar_ticker(query)    → list[dict]
    obtener_tipo(ticker)    → str  ("CEDEAR" | "ACCION_LOCAL" | "BONO_USD" | ...)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RATIOS_CEDEAR, SECTORES

_universo_df: pd.DataFrame | None = None


def set_universo_df(df: pd.DataFrame) -> None:
    """Registra el DataFrame de universo cargado por DataEngine."""
    global _universo_df
    _universo_df = df


def obtener_ratio(ticker: str) -> float:
    """Ratio CEDEAR para el ticker. Orden: universo_df → RATIOS_CEDEAR → 1.0"""
    t = ticker.upper().strip()
    if _universo_df is not None and not _universo_df.empty:
        row = _universo_df[_universo_df["Ticker"].str.upper() == t]
        if not row.empty and "Ratio" in row.columns:
            try:
                r = float(str(row["Ratio"].iloc[0]).split(":")[0].strip())
                if r > 0:
                    return r
            except (ValueError, AttributeError):
                pass
    return float(RATIOS_CEDEAR.get(t, 1.0))


def obtener_sector(ticker: str) -> str:
    """Sector del ticker. Orden: universo_df → SECTORES → 'Otros'"""
    t = ticker.upper().strip()
    if _universo_df is not None and not _universo_df.empty:
        row = _universo_df[_universo_df["Ticker"].str.upper() == t]
        if not row.empty and "Sector" in row.columns:
            sec = str(row["Sector"].iloc[0])
            if sec and sec != "nan":
                return sec
    return SECTORES.get(t, "Otros")


def obtener_tipo(ticker: str) -> str:
    """Tipo de instrumento BYMA."""
    t = ticker.upper().strip()
    if _universo_df is not None and not _universo_df.empty:
        row = _universo_df[_universo_df["Ticker"].str.upper() == t]
        if not row.empty and "Tipo" in row.columns:
            tipo = str(row["Tipo"].iloc[0])
            if tipo and tipo != "nan":
                return tipo
    if t in RATIOS_CEDEAR:
        return "CEDEAR"
    return "CEDEAR"


def listar_tickers(tipo: str | None = None) -> list[str]:
    """Lista todos los tickers del universo, opcionalmente filtrados por tipo."""
    if _universo_df is not None and not _universo_df.empty and "Ticker" in _universo_df.columns:
        df = _universo_df.copy()
        if tipo and "Tipo" in df.columns:
            df = df[df["Tipo"].str.upper().str.contains(tipo.upper(), na=False)]
        return sorted(df["Ticker"].str.upper().dropna().tolist())
    return sorted(RATIOS_CEDEAR.keys())


def buscar_ticker(query: str) -> list[dict]:
    """
    Busca tickers que coincidan con la query (por ticker o nombre).
    Devuelve lista de dicts con {ticker, nombre, sector, ratio, tipo}.
    """
    q = query.upper().strip()
    if not q:
        return []

    resultados: list[dict] = []

    if _universo_df is not None and not _universo_df.empty:
        mask_ticker = _universo_df["Ticker"].str.upper().str.contains(q, na=False)
        mask_nombre = pd.Series(False, index=_universo_df.index)
        if "Nombre" in _universo_df.columns:
            mask_nombre = _universo_df["Nombre"].str.upper().str.contains(q, na=False)

        matches = _universo_df[mask_ticker | mask_nombre].head(10)
        for _, row in matches.iterrows():
            t = str(row.get("Ticker", "")).upper()
            resultados.append({
                "ticker":  t,
                "nombre":  str(row.get("Nombre", t)),
                "sector":  str(row.get("Sector", obtener_sector(t))),
                "ratio":   obtener_ratio(t),
                "tipo":    str(row.get("Tipo", "CEDEAR")),
            })
        return resultados

    for t in RATIOS_CEDEAR:
        if q in t:
            resultados.append({
                "ticker": t,
                "nombre": t,
                "sector": obtener_sector(t),
                "ratio":  obtener_ratio(t),
                "tipo":   "CEDEAR",
            })
    return resultados[:10]
