"""
Script de actualización nocturna de datos fundamentales.

Ejecutar una vez al día, fuera de la rueda bursátil (ej: 23:00 ART).
Descarga P/E, P/B, ROE, D/P, DivYield, RevGrowth de Yahoo Finance
para TODO el universo de CEDEARs + Acciones argentinas y guarda el
resultado en 0_Data_Maestra/fundamentales_cache.json.

Uso
---
    python scripts/cron_update_fundamentales.py
    python scripts/cron_update_fundamentales.py --pausa 1.0
    python scripts/cron_update_fundamentales.py --dry-run   # solo cuenta activos

Automatización con Windows Task Scheduler (sin cron nativo en Win):
    Programa: python.exe
    Argumentos: scripts\cron_update_fundamentales.py
    Inicio: C:\\Users\\...\\MQ26_V11
    Hora: 23:00
    Frecuencia: diario (lunes a viernes)

En Railway (Linux): agregar a Procfile o cron job del servidor:
    0 23 * * 1-5 cd /app && python scripts/cron_update_fundamentales.py
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Asegurar que el root del proyecto esté en sys.path ───────────────────────
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Logging a consola y archivo ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            _ROOT / "0_Data_Maestra" / "cron_fundamentales.log",
            mode="a",
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("cron_fundamentales")


def main() -> int:
    """Retorna 0 si todo OK, 1 si hay error crítico."""
    parser = argparse.ArgumentParser(description="Actualiza cache de fundamentales YF")
    parser.add_argument("--pausa",   type=float, default=0.5,
                        help="Segundos entre requests (default 0.5; usar 1.0 en produccion)")
    parser.add_argument("--reintentos", type=int, default=3,
                        help="Reintentos por ticker ante error de red (default 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra cuantos activos se procesarian, sin descargar")
    parser.add_argument("--forzar",  action="store_true",
                        help="Ignora el cache existente aunque este fresco")
    args = parser.parse_args()

    t_inicio = time.time()
    log.info("=" * 60)
    log.info("cron_update_fundamentales.py  —  %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 60)

    # ── 1. Importar universo ──────────────────────────────────────────────────
    try:
        from config import CEDEAR_INFO, ACCIONES_ARGENTINAS, FUNDAMENTALES_CACHE_PATH
    except ImportError as exc:
        log.error("No se puede importar config: %s", exc)
        return 1

    # Universo: sólo dicts con yf_ticker (excluye planos como RATIOS_CEDEAR)
    universo = {
        t: m for t, m in {**CEDEAR_INFO, **ACCIONES_ARGENTINAS}.items()
        if isinstance(m, dict) and m.get("yf_ticker")
    }
    log.info("Universo: %d activos con yf_ticker (CEDEAR_INFO + ACCIONES_ARGENTINAS)",
             len(universo))

    if args.dry_run:
        log.info("--dry-run activo: no se descarga nada")
        print(f"\n  dry-run: {len(universo)} activos listos para descarga")
        print(f"  Destino cache: {FUNDAMENTALES_CACHE_PATH}")
        return 0

    # ── 2. Verificar si el cache es fresco (salvo --forzar) ──────────────────
    if not args.forzar:
        from core.fetcher_fundamentales import cargar_fundamentales_cache
        cache_existente = cargar_fundamentales_cache()
        if cache_existente:
            log.info(
                "Cache fresco encontrado (%d tickers). "
                "Usar --forzar para re-descargar de todas formas.",
                len(cache_existente),
            )
            return 0

    # ── 3. Descarga ───────────────────────────────────────────────────────────
    from core.fetcher_fundamentales import descargar_fundamentales_universo, guardar_cache_json

    log.info("Iniciando descarga (pausa=%.1fs, reintentos=%d)...",
             args.pausa, args.reintentos)

    datos = descargar_fundamentales_universo(
        universo,
        pausa_seg=args.pausa,
        max_reintentos=args.reintentos,
        verbose=True,
    )

    # ── 4. Guardar ────────────────────────────────────────────────────────────
    if not datos:
        log.error("Descarga fallida: dict vacio. Revisa conectividad o rate-limit de YF.")
        return 1

    path_guardado = guardar_cache_json(datos, FUNDAMENTALES_CACHE_PATH)
    t_total = time.time() - t_inicio
    log.info("Completado: %d tickers descargados en %.1f s -> %s",
             len(datos), t_total, path_guardado)

    # ── 5. Reporte de cobertura ───────────────────────────────────────────────
    con_pe  = sum(1 for v in datos.values() if v.get("pe") is not None)
    con_roe = sum(1 for v in datos.values() if v.get("roe") is not None)
    con_dp  = sum(1 for v in datos.values() if v.get("deuda_patrimonio") is not None)
    total   = len(datos)
    log.info(
        "Cobertura: P/E=%.0f%%  ROE=%.0f%%  D/P=%.0f%%  (sobre %d tickers)",
        con_pe / total * 100, con_roe / total * 100, con_dp / total * 100, total,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
