from __future__ import annotations

import sys
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "1_Scripts_Motor"))
from risk_engine import RiskEngine  # noqa: E402

UNIVERSOS: dict[str, list[str]] = {
    "conservador": ["INCOME", "XLV", "XLU", "IVE", "GLD", "BRKB", "CAT", "KO", "PG", "HD"],
    "moderado":    ["SPY", "VEA", "FXI", "EWZ", "XLV", "XLE", "MSFT", "GOOGL", "AMZN", "META"],
    "arriesgado":  ["IVW", "SMH", "MELI", "NU", "MSFT", "GOOGL", "TSLA", "META", "PLTR", "VIST"],
    "ia_crypto":   ["NVDA", "IBIT", "SMH", "AMZN", "CEG", "TSLA", "META", "MSFT", "CRWV", "RGTI"],
}
MODELO_POR_PERFIL: dict[str, str] = {
    "conservador": "min_var",
    "moderado":    "max_sharpe",
    "arriesgado":  "max_sharpe",
    "ia_crypto":   "hrp",
}


def build_profile_proposal(perfil: str, periodo: str = "1y") -> dict:
    """
    Descarga precios, construye RiskEngine y corre el modelo del perfil.
    Retorna: {'pesos': dict, 'metricas': dict, 'perfil': str, 'modelo': str}
    Fallback a pesos igual-peso si yfinance falla o hay datos insuficientes.
    """
    if perfil not in UNIVERSOS:
        raise ValueError(f"Perfil desconocido: {perfil!r}. Válidos: {list(UNIVERSOS)}")

    tickers = UNIVERSOS[perfil]
    modelo  = MODELO_POR_PERFIL[perfil]
    n       = len(tickers)

    try:
        raw     = yf.download(tickers, period=periodo, progress=False, auto_adjust=True)
        precios = raw["Close"].dropna(axis=1, how="all").dropna()
    except Exception:
        return {
            "pesos":  {t: round(1 / n, 6) for t in tickers},
            "metricas": {},
            "perfil": perfil,
            "modelo": modelo,
            "error":  "yfinance no disponible — pesos igual-peso",
        }

    if precios.empty or precios.shape[1] < 2:
        return {
            "pesos":  {t: round(1 / n, 6) for t in tickers},
            "metricas": {},
            "perfil": perfil,
            "modelo": modelo,
            "error":  "datos insuficientes — pesos igual-peso",
        }

    eng   = RiskEngine(precios)
    pesos = eng.optimizar(modelo)
    _m    = eng.calcular_metricas(pesos)   # tuple (retorno, vol, sharpe)

    return {
        "pesos":  pesos,
        "metricas": {
            "retorno_anual":    _m[0],
            "volatilidad_anual": _m[1],
            "sharpe":           _m[2],
        },
        "perfil": perfil,
        "modelo": modelo,
    }
