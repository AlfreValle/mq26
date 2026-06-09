#!/usr/bin/env python3
"""
cron_update_macro.py — Actualiza MACRO_AR en config.py con datos de mercado frescos.

Fuentes automáticas:
  - CCL / MEP    : dolarapi.com (contadoconliqui / bolsa)   — primario
                   yfinance GGAL.BA / GGAL                  — fallback
  - IPC mensual  : datos.gob.ar → serie 103.1_I2N_2016_M_19 (variación vs mes anterior)
  - TC oficial   : BCRA estadisticascambiarias API (USD BNA)

Campos con actualización manual (sin API pública fiable):
  - embi_arg_bps         → publicado por JP Morgan / ambito.com
  - tna_plazo_fijo_30d   → BCRA v2 deprecado; ver bcra.gob.ar
  - tasa_politica_monetaria → ídem

Uso:
  python scripts/cron_update_macro.py
  python scripts/cron_update_macro.py --dry-run       # muestra sin escribir
  python scripts/cron_update_macro.py --verbose

Retorna 0 si actualizó al menos un campo, 1 si no actualizó nada.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import warnings
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = ROOT / "config.py"

# ─── CONSTANTES ───────────────────────────────────────────────────────────────
RATIO_GGAL   = 10        # 10 acciones GGAL.BA = 1 ADR GGAL NYSE
MEP_CCL_DISC = 0.985     # MEP ≈ CCL * (1 - spread CCL/MEP ~1.5 %) — solo si dolarapi falla
HTTP_TIMEOUT = 10

DOLAR_API_URL = "https://dolarapi.com/v1/dolares"
IPC_SERIES    = "103.1_I2N_2016_M_19"   # Nivel general IPC INDEC (datos.gob.ar)
BCRA_FX_URL   = "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones"
IPC_URL       = (
    "https://apis.datos.gob.ar/series/api/series/"
    f"?ids={IPC_SERIES}&format=json&limit=3&sort=desc"
)


# ─── FUENTES DE DATOS ─────────────────────────────────────────────────────────

def _fx_desde_dolarapi() -> tuple[float | None, float | None]:
    """
    CCL = contadoconliqui (venta), MEP = bolsa (venta) desde dolarapi.com.
    Retorna (ccl, mep) en ARS/USD o (None, None) si falla.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(DOLAR_API_URL, timeout=HTTP_TIMEOUT, verify=False)
        resp.raise_for_status()
        tipos = resp.json()
        ccl = mep = None
        for t in tipos:
            casa = str(t.get("casa", "")).lower()
            venta = t.get("venta")
            if casa == "contadoconliqui" and venta:
                ccl = round(float(venta), 1)
            elif casa == "bolsa" and venta:
                mep = round(float(venta), 1)
        if ccl and mep:
            spread = round(ccl / mep - 1.0, 4)
            logger.info("dolarapi.com → CCL=%.1f  MEP=%.1f  spread=%.4f", ccl, mep, spread)
        elif ccl:
            mep = round(ccl * MEP_CCL_DISC, 1)
            logger.info("dolarapi.com → CCL=%.1f  MEP~%.1f (estimado)", ccl, mep)
        return ccl, mep
    except Exception as exc:
        logger.warning("dolarapi.com: %s", exc)
    return None, None


def _ccl_desde_yfinance() -> tuple[float | None, float | None]:
    """
    CCL = (GGAL.BA * ratio) / GGAL_NYSE  — fallback si dolarapi falla.
    Retorna (ccl_ars_usd, mep_estimado_ars_usd) o (None, None) si falla.
    """
    try:
        import yfinance as yf  # noqa: PLC0415

        ggal_ba = yf.Ticker("GGAL.BA").fast_info.get("lastPrice")
        ggal_us = yf.Ticker("GGAL").fast_info.get("lastPrice")
        if ggal_ba and ggal_us and ggal_us > 0:
            ccl = round(float(ggal_ba) * RATIO_GGAL / float(ggal_us), 1)
            mep = round(ccl * MEP_CCL_DISC, 1)
            logger.info(
                "yfinance fallback → GGAL.BA=%.2f  GGAL=%.2f  CCL=%.1f  MEP~%.1f",
                ggal_ba, ggal_us, ccl, mep,
            )
            return ccl, mep
    except Exception as exc:
        logger.warning("CCL yfinance fallback: %s", exc)
    return None, None


def _ipc_mensual() -> float | None:
    """
    Variación mensual IPC nivel general (INDEC vía datos.gob.ar).
    Retorna float como decimal (ej. 0.034 = 3.4 %) o None si falla.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(IPC_URL, timeout=HTTP_TIMEOUT, verify=False)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if len(data) >= 2:
            nivel_actual = float(data[0][1])
            nivel_prev   = float(data[1][1])
            variacion    = round((nivel_actual / nivel_prev) - 1.0, 4)
            logger.info(
                "IPC: %s=%.4f  %s=%.4f  var=%.4f (%.2f%%)",
                data[0][0], nivel_actual, data[1][0], nivel_prev,
                variacion, variacion * 100,
            )
            return variacion
    except Exception as exc:
        logger.warning("IPC datos.gob.ar: %s", exc)
    return None


def _tc_oficial_usd() -> float | None:
    """TC oficial BNA USD de BCRA estadisticascambiarias (informativo)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resp = requests.get(BCRA_FX_URL, timeout=HTTP_TIMEOUT, verify=False)
        resp.raise_for_status()
        detalle = resp.json().get("results", {}).get("detalle", [])
        for item in detalle:
            if item.get("codigoMoneda") == "USD":
                tc = float(item.get("tipoCotizacion", 0))
                if tc > 0:
                    logger.info("TC oficial USD BNA: %.2f", tc)
                    return round(tc, 2)
    except Exception as exc:
        logger.warning("TC oficial BCRA: %s", exc)
    return None


def fetch_macro_live() -> dict[str, Any]:
    """Consulta todas las fuentes y devuelve dict con nuevos valores."""
    logger.info("--- Consultando CCL/MEP (dolarapi.com) ---")
    ccl, mep = _fx_desde_dolarapi()

    if ccl is None:
        logger.info("--- dolarapi falló — fallback yfinance GGAL ---")
        ccl, mep = _ccl_desde_yfinance()

    logger.info("--- Consultando IPC (datos.gob.ar) ---")
    ipc = _ipc_mensual()

    logger.info("--- Consultando TC oficial (BCRA) ---")
    _tc_oficial_usd()   # informativo, no actualiza MACRO_AR

    spread = round((ccl / mep) - 1.0, 4) if (ccl and mep and mep > 0) else None

    resultado: dict[str, Any] = {
        "ccl_promedio":          ccl,
        "mep_promedio":          mep,
        "spread_ccl_mep":        spread,
        "inflacion_mensual_ipc": ipc,
        # campos sin API pública → None = conservar valor previo
        "embi_arg_bps":             None,
        "tna_plazo_fijo_30d":       None,
        "tasa_politica_monetaria":  None,
    }

    ok  = [k for k, v in resultado.items() if v is not None]
    err = [k for k, v in resultado.items() if v is None]
    logger.info("Campos actualizables: %s", ok)
    if err:
        logger.info("Sin fuente automática (conservar manual): %s", err)
    return resultado


# ─── PATCH DE config.py ───────────────────────────────────────────────────────

def _patch_config(nuevos: dict[str, Any], dry_run: bool = False) -> bool:
    """
    Actualiza los campos con valor no-None SOLO dentro del bloque MACRO_AR de config.py.
    Aísla el bloque antes de hacer reemplazos para evitar colisiones con otros dicts.
    Retorna True si se aplicó al menos un cambio.
    """
    texto_full = CONFIG_PATH.read_text(encoding="utf-8")

    # Localizar el bloque MACRO_AR para operar solo dentro de él
    m_bloque = re.search(
        r'(MACRO_AR\s*=\s*\{)(.+?)(\n\})',
        texto_full,
        re.DOTALL,
    )
    if not m_bloque:
        logger.error("Bloque MACRO_AR no encontrado en config.py")
        return False

    bloque_inicio = m_bloque.start(2)
    bloque_fin    = m_bloque.end(2)
    bloque        = texto_full[bloque_inicio:bloque_fin]
    cambios: list[str] = []

    for key, valor in nuevos.items():
        if valor is None:
            continue
        nuevo_val = str(valor) if isinstance(valor, (int, float)) else repr(valor)

        patron = re.compile(
            r'("' + re.escape(key) + r'"\s*:)\s*[0-9.]+([,\s])',
            re.MULTILINE,
        )
        bloque_nuevo, n = patron.subn(
            lambda m, v=nuevo_val: f'{m.group(1)} {v}{m.group(2)}',
            bloque,
        )
        if n == 0:
            logger.warning("Patrón numérico no encontrado en MACRO_AR para key: %s", key)
            continue

        bloque = bloque_nuevo
        cambios.append(f"  {key} -> {nuevo_val}")

    if not cambios:
        logger.info("Sin campos a actualizar.")
        return False

    # Actualizar fecha_actualizacion (también dentro del bloque)
    hoy = date.today().isoformat()
    patron_fecha = re.compile(
        r'("fecha_actualizacion"\s*:)\s*"[0-9-]+"([,\s])',
        re.MULTILINE,
    )
    bloque, n = patron_fecha.subn(
        lambda m: f'{m.group(1)} "{hoy}"{m.group(2)}',
        bloque,
    )
    if n:
        cambios.append(f'  fecha_actualizacion -> "{hoy}"')

    logger.info("Cambios a aplicar:\n%s", "\n".join(cambios))

    if dry_run:
        logger.info("[DRY-RUN] config.py NO fue modificado.")
        return True

    texto_final = texto_full[:bloque_inicio] + bloque + texto_full[bloque_fin:]
    CONFIG_PATH.write_text(texto_final, encoding="utf-8")
    logger.info("config.py actualizado correctamente.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Actualiza MACRO_AR en config.py")
    parser.add_argument("--dry-run", action="store_true", help="No escribe config.py")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=== cron_update_macro.py %s ===", datetime.now().strftime("%Y-%m-%d %H:%M"))

    nuevos = fetch_macro_live()
    exito  = _patch_config(nuevos, dry_run=args.dry_run)
    return 0 if exito else 1


if __name__ == "__main__":
    sys.exit(main())
