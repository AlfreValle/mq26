"""
services/mod23_service.py — Servicio de dominio para el Motor MOD-23
MQ26-DSS | Sin dependencias de Streamlit.

Encapsula:
  - Recalcular el universo completo de scores MOD-23.
  - Filtrar scores de la cartera activa.
  - Detectar alertas de venta (score < umbral).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logging_config import get_logger

logger = get_logger(__name__)


def recalcular_universo(universo_df: pd.DataFrame, ruta_salida: Path) -> pd.DataFrame:
    """
    Ejecuta el escaneo MOD-23 completo sobre todos los tickers del universo.
    Guarda el resultado en ruta_salida (Excel).
    Devuelve el DataFrame con columnas: TICKER, PUNTAJE_TECNICO, ESTADO.

    Delega en alpha_engine.escanear_universo para mantener la lógica central.
    """
    if universo_df.empty:
        logger.warning("mod23_service.recalcular_universo: universo vacío, nada que escanear.")
        return pd.DataFrame(columns=["TICKER", "PUNTAJE_TECNICO", "ESTADO"])

    try:
        from alpha_engine import escanear_universo
        logger.info("Iniciando escaneo MOD-23 para %d activos...", len(universo_df))
        df = escanear_universo(universo_df, ruta_salida)
        n_alcistas = (df["ESTADO"] == "ALCISTA").sum()
        logger.info(
            "Escaneo MOD-23 completado: %d alcistas / %d bajistas",
            n_alcistas, len(df) - n_alcistas,
        )
        return df
    except Exception as exc:
        logger.error("mod23_service.recalcular_universo: %s", exc)
        return pd.DataFrame(columns=["TICKER", "PUNTAJE_TECNICO", "ESTADO"])


def scores_cartera(
    df_analisis: pd.DataFrame,
    tickers_cartera: list[str],
) -> pd.DataFrame:
    """
    Filtra el DataFrame de análisis para devolver solo los tickers de la cartera activa.
    Devuelve subset ordenado por puntaje descendente.
    """
    if df_analisis.empty or not tickers_cartera:
        return pd.DataFrame(columns=["TICKER", "PUNTAJE_TECNICO", "ESTADO"])

    tickers_upper = [t.upper() for t in tickers_cartera]
    return (
        df_analisis[df_analisis["TICKER"].isin(tickers_upper)]
        .sort_values("PUNTAJE_TECNICO", ascending=False)
        .reset_index(drop=True)
    )


def detectar_alertas_venta(
    df_analisis: pd.DataFrame,
    tickers_cartera: list[str],
    umbral: float = 4.0,
) -> list[dict]:
    """
    Devuelve lista de dicts con tickers de la cartera que tienen score < umbral.
    Cada dict: {'ticker': str, 'score': float, 'estado': str}
    """
    df_cartera = scores_cartera(df_analisis, tickers_cartera)
    if df_cartera.empty:
        return []

    alertas = df_cartera[df_cartera["PUNTAJE_TECNICO"] < umbral]
    resultado = []
    for _, row in alertas.iterrows():
        resultado.append({
            "ticker": row["TICKER"],
            "score":  float(row["PUNTAJE_TECNICO"]),
            "estado": str(row.get("ESTADO", "BAJISTA")),
        })
        logger.warning(
            "Alerta venta MOD-23: %s score=%.1f estado=%s",
            row["TICKER"], row["PUNTAJE_TECNICO"], row.get("ESTADO", ""),
        )
    return resultado


def resumen_universo(df_analisis: pd.DataFrame) -> dict:
    """
    Calcula estadísticas del universo MOD-23.
    Devuelve dict con: n_elite, n_alcistas, n_alertas, total.
    """
    if df_analisis.empty:
        return {"n_elite": 0, "n_alcistas": 0, "n_alertas": 0, "total": 0}

    pt = df_analisis["PUNTAJE_TECNICO"]
    return {
        "n_elite":    int((pt >= 7).sum()),
        "n_alcistas": int(((pt >= 5) & (pt < 7)).sum()),
        "n_alertas":  int((pt < 4).sum()),
        "total":      len(df_analisis),
    }
