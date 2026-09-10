"""
Purga cachés de *mercado* (precios, scores, fundamentales, CCL).

No toca carteras, transaccional ni la BD de clientes.
Usar cuando la decisión de inversión no puede basarse en fallbacks/hardcode.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "0_Data_Maestra"


def _borrar_archivo(path: Path) -> int:
    try:
        if path.is_file():
            path.unlink(missing_ok=True)
            return 1
    except OSError:
        return 0
    return 0


def _borrar_glob(directorio: Path, patron: str) -> int:
    n = 0
    try:
        if not directorio.is_dir():
            return 0
        paths = list(directorio.glob(patron))
    except OSError:
        return 0
    for p in paths:
        n += _borrar_archivo(p)
    return n


def purgar_caches_mercado() -> dict[str, int]:
    """
    Borra pickle/JSON/sqlite de mercado y vacía cachés in-process.

    Returns:
        Conteos por origen (archivos o entradas).
    """
    borrados: dict[str, int] = {}

    borrados["fundamentales_json"] = _borrar_archivo(_DATA / "fundamentales_cache.json")
    borrados["scores_pkl"] = _borrar_archivo(_DATA / "scores_universo_cache.pkl")
    borrados["cache_precios_pkl"] = _borrar_glob(_DATA / "cache_precios", "*.pkl")
    borrados["yfinance_sqlite"] = 0
    for cand in (_ROOT, Path.cwd()):
        borrados["yfinance_sqlite"] += _borrar_glob(cand, "yfinance_cache*")

    try:
        from core.historical_cache import historico_cache_clear

        historico_cache_clear()
        borrados["historico_mem"] = 1
    except Exception:
        borrados["historico_mem"] = 0

    try:
        from services.diagnostico_cache import invalidar_cache_total

        borrados["diagnostico"] = int(invalidar_cache_total() or 0)
    except Exception:
        borrados["diagnostico"] = 0

    try:
        import services.fundamentals_cache as _fc

        n_mem = len(getattr(_fc, "_MEM_CACHE", {}) or {})
        getattr(_fc, "_MEM_CACHE", {}).clear()
        borrados["fundamentals_mem"] = n_mem
    except Exception:
        borrados["fundamentals_mem"] = 0

    try:
        import services.market_connector as mc

        n_fun = len(getattr(mc, "_fundamentales_cache", {}) or {})
        getattr(mc, "_fundamentales_cache", {}).clear()
        borrados["market_connector_mem"] = n_fun
    except Exception:
        borrados["market_connector_mem"] = 0

    try:
        import services.tipos_cambio_ar as tca

        tca._cache_val = None
        tca._cache_mono = 0.0
        borrados["ccl_proceso"] = 1
    except Exception:
        borrados["ccl_proceso"] = 0

    try:
        import services.cartera_service as cs

        cs._fallback_cargado = False
        borrados["fallback_lazy_reset"] = 1
    except Exception:
        borrados["fallback_lazy_reset"] = 0

    return borrados
