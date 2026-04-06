"""
services/precio_cache_service.py
MQ2-A4: Caché en disco de precios históricos yfinance (TTL 24h)
MQ2-A9: Circuit breaker para yfinance — 3 fallos en 60s → modo degradado

Uso:
    from services.precio_cache_service import get_historico_cacheado, registrar_fallo_yf, yfinance_disponible
"""
from __future__ import annotations

import hashlib
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ─── RUTAS ────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parent.parent
_CACHE_DIR = _BASE / "0_Data_Maestra" / "cache_precios"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_TTL_HORAS = 24

# ─── CIRCUIT BREAKER (en memoria de proceso) ──────────────────────────────────
_fallos: list[float] = []           # timestamps de fallos recientes
_VENTANA_S  = 60                    # ventana de 60 segundos
_MAX_FALLOS = 3                     # umbral de fallos
_COOLDOWN_S = 120                   # 2 minutos de bloqueo tras umbral


def registrar_fallo_yf() -> None:
    """Registra un fallo de descarga de yfinance."""
    ahora = time.monotonic()
    _fallos.append(ahora)
    # Limpiar fallos fuera de la ventana
    while _fallos and _fallos[0] < ahora - _VENTANA_S:
        _fallos.pop(0)


def yfinance_disponible() -> bool:
    """True si el circuit breaker permite usar yfinance."""
    ahora = time.monotonic()
    # Limpiar fallos viejos
    while _fallos and _fallos[0] < ahora - _VENTANA_S:
        _fallos.pop(0)
    if len(_fallos) >= _MAX_FALLOS:
        # Bloquear si el último fallo fue hace menos del cooldown
        if _fallos and ahora - _fallos[-1] < _COOLDOWN_S:
            return False
        else:
            _fallos.clear()
    return True


def estado_circuit_breaker() -> dict:
    """Devuelve el estado actual del circuit breaker para mostrar en UI."""
    ahora = time.monotonic()
    while _fallos and _fallos[0] < ahora - _VENTANA_S:
        _fallos.pop(0)
    activo = len(_fallos) >= _MAX_FALLOS and _fallos and (ahora - _fallos[-1] < _COOLDOWN_S)
    restante = max(0, int(_COOLDOWN_S - (ahora - _fallos[-1]))) if activo and _fallos else 0
    return {
        "degradado": activo,
        "fallos_recientes": len(_fallos),
        "segundos_restantes": restante,
    }


# ─── CACHÉ EN DISCO ───────────────────────────────────────────────────────────

def _clave_cache(tickers: tuple[str, ...], periodo: str) -> Path:
    h = hashlib.md5("|".join(sorted(tickers)).encode() + periodo.encode()).hexdigest()[:12]
    return _CACHE_DIR / f"hist_{h}.pkl"


def get_historico_cacheado(
    tickers: tuple[str, ...],
    periodo: str = "90d",
    forzar: bool = False,
) -> pd.DataFrame | None:
    """
    Devuelve el DataFrame histórico desde caché en disco si está vigente (< TTL_HORAS).
    Devuelve None si no existe o venció, para que el caller descargue con yfinance.
    """
    ruta = _clave_cache(tickers, periodo)
    if ruta.exists() and not forzar:
        mtime = datetime.fromtimestamp(ruta.stat().st_mtime)
        if datetime.now() - mtime < timedelta(hours=_TTL_HORAS):
            try:
                with open(ruta, "rb") as f:
                    return pickle.load(f)
            except Exception:
                ruta.unlink(missing_ok=True)
    return None


def guardar_historico_cache(
    tickers: tuple[str, ...],
    periodo: str,
    df: pd.DataFrame,
) -> None:
    """Persiste el DataFrame histórico en disco."""
    if df is None or df.empty:
        return
    ruta = _clave_cache(tickers, periodo)
    try:
        with open(ruta, "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass


def limpiar_cache_expirado() -> int:
    """Elimina archivos de caché con más de TTL_HORAS. Devuelve cantidad eliminada."""
    eliminados = 0
    limite = datetime.now() - timedelta(hours=_TTL_HORAS)
    for p in _CACHE_DIR.glob("hist_*.pkl"):
        if datetime.fromtimestamp(p.stat().st_mtime) < limite:
            p.unlink(missing_ok=True)
            eliminados += 1
    return eliminados
