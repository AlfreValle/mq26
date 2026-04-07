"""
Contenido educativo para redes (Admin Growth). Sin Streamlit.
Entrada: universo_df con columnas de score/precio; salida texto + disclaimer.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


DISCLAIMER_REDES = (
    "Contenido educativo y de divulgación general. No constituye recomendación "
    "personalizada de inversión, oferta pública ni asesoramiento financiero. "
    "Consultá a un asesor calificado antes de operar."
)


def _col(df: Any, candidates: tuple[str, ...]) -> str | None:
    if df is None:
        return None
    try:
        cols = list(df.columns)
    except Exception:
        return None
    for c in candidates:
        if c in cols:
            return c
    for c in cols:
        u = str(c).upper()
        for cand in candidates:
            if u == cand.upper():
                return c
    return None


def generar_top3_redes(
    universo_df: Any,
    *,
    n: int = 3,
    titulo_semana: str = "Ideas de la semana",
) -> dict[str, Any]:
    """
    Devuelve dict con titulo, bullets, texto_plano, disclaimer.
    No recalcula scores: ordena por columna numérica existente (Score_Total, PUNTAJE, etc.).
    """
    out: dict[str, Any] = {
        "titulo": titulo_semana,
        "bullets": [],
        "texto_plano": "",
        "disclaimer": DISCLAIMER_REDES,
        "tickers": [],
    }
    if universo_df is None:
        out["texto_plano"] = f"{titulo_semana}\n\nSin datos de universo cargados.\n\n{DISCLAIMER_REDES}"
        return out
    try:
        df = universo_df
        if hasattr(df, "empty") and df.empty:
            out["texto_plano"] = f"{titulo_semana}\n\nUniverso vacío.\n\n{DISCLAIMER_REDES}"
            return out
    except Exception:
        out["texto_plano"] = f"{titulo_semana}\n\nNo se pudo leer el universo.\n\n{DISCLAIMER_REDES}"
        return out

    tcol = _col(df, ("TICKER", "Ticker", "ticker"))
    scol = _col(df, ("Score_Total", "SCORE_TOTAL", "PUNTAJE_TECNICO", "Score", "score"))
    if not tcol or not scol:
        out["texto_plano"] = (
            f"{titulo_semana}\n\nFaltan columnas TICKER y score en el universo.\n\n{DISCLAIMER_REDES}"
        )
        return out

    try:
        dfx = df[[tcol, scol]].copy()
        dfx["_s"] = pd.to_numeric(dfx[scol], errors="coerce").fillna(0)
        dfx = dfx.sort_values("_s", ascending=False).head(max(1, min(n, 20)))
    except Exception:
        out["texto_plano"] = f"{titulo_semana}\n\nNo se pudo ordenar el universo.\n\n{DISCLAIMER_REDES}"
        return out

    bullets: list[str] = []
    tickers: list[str] = []
    for _, row in dfx.iterrows():
        tk = str(row[tcol]).upper().strip()
        if not tk:
            continue
        sc = row.get(scol, "")
        bullets.append(f"{tk} — referencia de score {sc} (contexto educativo).")
        tickers.append(tk)
        if len(bullets) >= n:
            break

    body = "\n".join(f"• {b}" for b in bullets) if bullets else "• Sin activos elegibles."
    texto = f"{titulo_semana}\n\n{body}\n\n{DISCLAIMER_REDES}"
    out["bullets"] = bullets
    out["tickers"] = tickers
    out["texto_plano"] = texto
    return out
