"""
alpha_engine.py — Motor MOD-23 de Señales y Scoring
Score técnico 1-10: SMA-150 (4 pts) + RSI-14 (3 pts) + Momentum 3M (3 pts)
"""
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RSI_COMPRA, RSI_VENTA, RSI_VENTANA, SMA_VENTANA
from core.logging_config import get_logger

_log = get_logger(__name__)

def calcular_score_mod23(ticker: str, tipo: str = "CEDEAR") -> tuple:
    """Calcula el score técnico MOD-23 (1-10) para un ticker. Retorna (score, estado)."""
    score = 0
    try:
        from data_engine import ticker_yahoo
        t_yf = ticker_yahoo(ticker)
        data = yf.Ticker(t_yf).history(period="1y")
        if data.empty or len(data) < 50:
            return 1.0, "SIN_DATOS"
        precio = float(data["Close"].iloc[-1])
        # Tendencia SMA150
        if len(data) >= SMA_VENTANA:
            sma = float(data["Close"].rolling(SMA_VENTANA).mean().dropna().iloc[-1])
            if precio > sma:
                score += 4
        # RSI
        delta = data["Close"].diff()
        gain  = delta.clip(lower=0).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1/RSI_VENTANA, min_periods=RSI_VENTANA, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        rsi_s = 100 - (100 / (1 + rs))
        rsi   = float(rsi_s.dropna().iloc[-1]) if not rsi_s.dropna().empty else 50.0
        if RSI_COMPRA <= rsi <= RSI_VENTA:
            score += 3
        elif rsi >= RSI_VENTA:
            score += 1
        # Momentum 3m
        if len(data) >= 60:
            if float((precio / data["Close"].iloc[-60]) - 1) > 0:
                score += 3
        score_final = round(max(1.0, min(10.0, float(score))), 1)
        return score_final, "ALCISTA" if score_final >= 5 else "BAJISTA"
    except Exception:
        return 1.0, "ERROR"

def escanear_universo(universo_df: pd.DataFrame, ruta_salida: Path) -> pd.DataFrame:
    """Escanea todos los activos del universo y guarda Analisis_Empresas.xlsx."""
    resultados = []
    total = len(universo_df)
    _log.info("MOD-23: iniciando escaneo de %d activos", total)
    for i, row in universo_df.iterrows():
        t    = str(row.get("Ticker", "")).strip().upper()
        tipo = str(row.get("Tipo", "CEDEAR"))
        _log.debug("MOD-23: [%d/%d] %s", i + 1, total, t)
        nota, estado = calcular_score_mod23(t, tipo)
        resultados.append({"TICKER": t, "PUNTAJE_TECNICO": nota, "ESTADO": estado})
        time.sleep(0.3)
    df = pd.DataFrame(resultados)
    df.to_excel(ruta_salida, index=False)
    alcistas = len(df[df["ESTADO"] == "ALCISTA"])
    _log.info("MOD-23: escaneo completado — %d alcistas / %d bajistas", alcistas, total - alcistas)
    return df
