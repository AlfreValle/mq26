"""
importar_reto2026.py — ETL: RETO 2026.txt → Maestra_Transaccional.csv

Lee las 11 semanas de recomendaciones del RETO 2026 y las agrega como
portfolio "Alfredo | RETO 2026" al transaccional de MQ26.

Para las semanas 1-5 (sin precio especificado) recupera el precio histórico
de cierre desde yfinance y calcula el PPC_ARS a partir del subyacente USD.

Uso (desde la raíz del repo):
    python scripts/legacy/importar_reto2026.py
    python scripts/legacy/importar_reto2026.py --forzar
    python scripts/legacy/importar_reto2026.py --preview
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# Raíz del repositorio (este archivo está en scripts/legacy/)
_ROOT = Path(__file__).resolve().parent.parent.parent

# Cargar .env antes de importar módulos del proyecto
_env_path = _ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, str(_ROOT))
from core.pricing_utils import ccl_historico_por_fecha, ppc_usd_desde_precio_ars

# ─── CONSTANTES ───────────────────────────────────────────────────────────────
CARTERA  = "Alfredo | RETO 2026"
CSV_PATH = _ROOT / "0_Data_Maestra" / "Maestra_Transaccional.csv"
TIPO     = "CEDEAR"
COLUMNAS = ["CARTERA", "FECHA_COMPRA", "TICKER", "CANTIDAD", "PPC_USD", "PPC_ARS", "TIPO"]

# ─── DATOS DE LAS 11 SEMANAS ─────────────────────────────────────────────────
# Formato: (fecha, ticker, cantidad, ppc_ars)
# ppc_ars = 0.0 → precio histórico se recupera de yfinance
# ppc_ars > 0   → precio proviene del .txt de recomendación
TRANSACCIONES = [
    # ── Semana 1 — 06/01/2026 — $75.000 ARS ──────────────────────────────────
    ("2026-01-06", "AMZN",  15, 0.0),
    ("2026-01-06", "NVDA",   3, 0.0),

    # ── Semana 2 — 13/01/2026 — $75.000 ARS ──────────────────────────────────
    ("2026-01-13", "BRKB",   1, 0.0),
    ("2026-01-13", "AAPL",   2, 0.0),

    # ── Semana 3 — 20/01/2026 — $75.000 ARS ──────────────────────────────────
    ("2026-01-20", "BRKB",   1, 0.0),
    ("2026-01-20", "META",   1, 0.0),

    # ── Semana 4 — 26/01/2026 — $75.000 ARS ──────────────────────────────────
    ("2026-01-26", "GLD",    3, 0.0),
    ("2026-01-26", "UNH",    2, 0.0),

    # ── Semana 5 — 02/02/2026 — $75.000 ARS ──────────────────────────────────
    ("2026-02-02", "MSFT",   3, 0.0),
    ("2026-02-02", "NVDA",   1, 0.0),

    # ── Semana 6 — 09/02/2026 — $75.000 ARS ─────────────────────────────────
    ("2026-02-09", "MELI",   1, 24590.0),
    ("2026-02-09", "SPY",    1, 51000.0),

    # ── Semana 7 — 17/02/2026 — $100.000 ARS ────────────────────────────────
    ("2026-02-17", "SPY",    1, 50300.0),
    ("2026-02-17", "MELI",   1, 24200.0),
    ("2026-02-17", "MSFT",   1, 19750.0),
    ("2026-02-17", "AMZN",   3,  2041.0),

    # ── Semana 8 — 24/02/2026 — $100.000 ARS ────────────────────────────────
    ("2026-02-24", "SPY",    1, 50300.0),
    ("2026-02-24", "MELI",   1, 24000.0),
    ("2026-02-24", "MSFT",   3, 18677.0),
    ("2026-02-24", "AMZN",   7,  2104.0),

    # ── Semana 9 — 03/03/2026 — $100.000 ARS ────────────────────────────────
    ("2026-03-03", "LMT",    1, 48220.0),
    ("2026-03-03", "COST",   1, 30480.0),
    ("2026-03-03", "KO",     1, 19880.0),

    # ── Semana 10 — 10/03/2026 — $100.000 ARS ───────────────────────────────
    ("2026-03-10", "LMT",    1, 51000.0),
    ("2026-03-10", "VIST",   1, 31000.0),
    ("2026-03-10", "AMZN",   8,  2250.0),

    # ── Semana 11 — 17/03/2026 — ~$99.500 ARS ───────────────────────────────
    ("2026-03-17", "JNJ",    2, 23850.0),
    ("2026-03-17", "GOOGL",  2,  7750.0),
    ("2026-03-17", "XP",     2,  7050.0),
    ("2026-03-17", "VALE",   2, 11100.0),
]


# ─── RECUPERAR PRECIO HISTÓRICO YFINANCE ─────────────────────────────────────

_yf_cache: dict[tuple, float] = {}

# Mapeo de tickers CEDEAR → ticker real en yfinance (cuando difieren)
_TICKER_YF_MAP: dict[str, str] = {
    "BRKB": "BRK-B",   # Berkshire Hathaway B
    "GOOGL": "GOOGL",
}


def precio_historico_usd(ticker: str, fecha: str) -> float:
    """
    Obtiene el precio de cierre del subyacente en USD en la fecha dada.
    Si la fecha es feriado o fin de semana, busca el día hábil anterior.
    Usa caché en memoria para no consultar yfinance dos veces el mismo par.
    """
    key = (ticker, fecha)
    if key in _yf_cache:
        return _yf_cache[key]

    # Intentar hasta 3 variantes del ticker
    ticker_yf = _TICKER_YF_MAP.get(ticker.upper(), ticker)
    candidatos = list(dict.fromkeys([ticker_yf, ticker, f"{ticker}.BA"]))

    try:
        import pandas as pd
        import yfinance as yf
        _fecha_dt = pd.Timestamp(fecha)
        _desde    = (_fecha_dt - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        _hasta    = (_fecha_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        for tk in candidatos:
            try:
                hist = yf.Ticker(tk).history(start=_desde, end=_hasta, auto_adjust=True)
                if hist is None or hist.empty:
                    continue
                hist_f = hist[hist.index.strftime("%Y-%m-%d") <= fecha]
                if hist_f.empty:
                    continue
                precio = float(hist_f["Close"].iloc[-1])
                _yf_cache[key] = precio
                return precio
            except Exception:
                continue

        _yf_cache[key] = 0.0
        return 0.0
    except Exception as e:
        print(f"  [WARN] yfinance {ticker} {fecha}: {e}")
        _yf_cache[key] = 0.0
        return 0.0


# ─── LÓGICA DE PRECIOS ────────────────────────────────────────────────────────

def resolver_precios(fecha: str, ticker: str, ppc_ars_orig: float) -> tuple[float, float]:
    """
    Devuelve (ppc_ars, ppc_usd) resueltos.

    Si ppc_ars_orig > 0 → usa el precio del .txt (semanas 6-11).
    Si ppc_ars_orig == 0 → descarga el precio histórico USD desde yfinance
        y lo convierte a ARS usando CCL+ratio (semanas 1-5).
    """
    ccl = ccl_historico_por_fecha(fecha, fallback=1420.0)

    if ppc_ars_orig > 0:
        ppc_usd = ppc_usd_desde_precio_ars(ppc_ars_orig, ticker, ccl)
        return round(ppc_ars_orig, 2), round(ppc_usd, 6)

    # Precio histórico desde yfinance
    precio_usd = precio_historico_usd(ticker, fecha)
    if precio_usd <= 0:
        return 0.0, 0.0

    # PPC_USD del CEDEAR = precio subyacente USD (el ratio ya está en la fórmula inversa)
    # PPC_ARS del CEDEAR = (precio_USD / ratio) * CCL
    from config import RATIOS_CEDEAR
    ratio = float(RATIOS_CEDEAR.get(ticker.upper(), 1.0))
    ppc_ars = round((precio_usd / ratio) * ccl, 2)
    ppc_usd = ppc_usd_desde_precio_ars(ppc_ars, ticker, ccl)
    return ppc_ars, round(ppc_usd, 6)


# ─── CONSTRUIR FILAS ─────────────────────────────────────────────────────────

def construir_filas(verbose: bool = False) -> list[dict]:
    """Convierte TRANSACCIONES en dicts listos para CSV, resolviendo precios."""
    filas = []
    sem = 0
    fecha_anterior = ""
    for fecha, ticker, cantidad, ppc_ars_orig in TRANSACCIONES:
        if fecha != fecha_anterior:
            sem += 1
            fecha_anterior = fecha
        if ppc_ars_orig == 0.0 and verbose:
            print(f"  → Buscando precio histórico: {ticker} {fecha}...", end="", flush=True)
        ppc_ars, ppc_usd = resolver_precios(fecha, ticker, ppc_ars_orig)
        if ppc_ars_orig == 0.0 and verbose:
            src = f"yfinance → ${ppc_ars:,.2f} ARS" if ppc_ars > 0 else "sin datos"
            print(f" {src}")
        filas.append({
            "CARTERA":      CARTERA,
            "FECHA_COMPRA": fecha,
            "TICKER":       ticker,
            "CANTIDAD":     cantidad,
            "PPC_USD":      ppc_usd,
            "PPC_ARS":      ppc_ars,
            "TIPO":         TIPO,
        })
    return filas


# ─── UTILIDADES CSV ──────────────────────────────────────────────────────────

def ya_importado() -> bool:
    """Devuelve True si ya existe al menos una fila de RETO 2026 en el CSV."""
    if not CSV_PATH.exists():
        return False
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("CARTERA", "") == CARTERA:
                return True
    return False


def eliminar_filas_existentes() -> int:
    """Elimina del CSV todas las filas de RETO 2026. Retorna cantidad eliminada."""
    if not CSV_PATH.exists():
        return 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        todas = list(csv.DictReader(f))
    antes = len(todas)
    sin_reto = [r for r in todas if r.get("CARTERA", "") != CARTERA]
    eliminadas = antes - len(sin_reto)
    if eliminadas > 0:
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=todas[0].keys() if todas else COLUMNAS)
            writer.writeheader()
            writer.writerows(sin_reto)
    return eliminadas


def agregar_filas(filas: list[dict]) -> None:
    """Agrega filas al CSV sin encabezado duplicado."""
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS)
        for fila in filas:
            writer.writerow(fila)


# ─── RESUMEN IMPRESO ─────────────────────────────────────────────────────────

def _imprimir_resumen(filas: list[dict]) -> None:
    print()
    print("  SEM   FECHA        TICKER   CANT     PPC_ARS      PPC_USD    FUENTE")
    print("  " + "─" * 72)
    sem = 0
    fecha_anterior = ""
    orig_ppc = {(f, t): p for f, t, _, p in TRANSACCIONES}
    for fila in filas:
        f_key = (fila["FECHA_COMPRA"], fila["TICKER"])
        if fila["FECHA_COMPRA"] != fecha_anterior:
            sem += 1
            fecha_anterior = fila["FECHA_COMPRA"]
        ppc_orig = orig_ppc.get(f_key, -1.0)
        fuente = "reto.txt" if ppc_orig > 0 else ("yfinance" if fila["PPC_ARS"] > 0 else "sin datos")
        usd_str = f"{fila['PPC_USD']:>10.4f}" if fila["PPC_USD"] > 0 else "  (sin precio)"
        print(
            f"  S{sem:02d}  {fila['FECHA_COMPRA']}   {fila['TICKER']:<6}  "
            f"{fila['CANTIDAD']:>4}   {fila['PPC_ARS']:>10.2f}  {usd_str}   {fuente}"
        )

    _total_ars = sum(
        fila["PPC_ARS"] * fila["CANTIDAD"]
        for fila in filas if fila["PPC_ARS"] > 0
    )
    print("  " + "─" * 72)
    print(f"  Total invertido estimado: ${_total_ars:,.2f} ARS ({len(filas)} operaciones)")


# ─── IMPORTACIÓN PRINCIPAL ───────────────────────────────────────────────────

def importar(forzar: bool = False, preview: bool = False) -> None:
    if not CSV_PATH.exists():
        print(f"[ERROR] No se encuentra el CSV: {CSV_PATH}")
        sys.exit(1)

    if preview:
        print(f"[PREVIEW] Calculando precios para {len(TRANSACCIONES)} operaciones...")
        filas = construir_filas(verbose=True)
        _imprimir_resumen(filas)
        return

    if ya_importado() and not forzar:
        print(f"[SKIP] La cartera '{CARTERA}' ya existe en el CSV.")
        print("       Usá '--forzar' para re-importar con precios históricos de yfinance.")
        return

    if forzar and ya_importado():
        n_elim = eliminar_filas_existentes()
        print(f"[INFO] {n_elim} filas anteriores del RETO 2026 eliminadas.")

    print("[INFO] Resolviendo precios históricos con yfinance para semanas 1-5...")
    filas = construir_filas(verbose=True)
    agregar_filas(filas)

    sin_precio = sum(1 for f in filas if f["PPC_USD"] == 0.0)
    print(f"\n[OK] {len(filas)} filas importadas → {CSV_PATH}")
    print(f"     Cartera: {CARTERA}")
    if sin_precio:
        print(f"     ATENCIÓN: {sin_precio} operación(es) sin precio (yfinance sin datos).")
        print("               La app usará precio de mercado actual como fallback.")
    _imprimir_resumen(filas)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    forzar  = "--forzar"  in sys.argv
    preview = "--preview" in sys.argv
    importar(forzar=forzar, preview=preview)
