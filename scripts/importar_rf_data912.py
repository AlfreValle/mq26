#!/usr/bin/env python3
"""
importar_rf_data912.py — Propone la actualización del catálogo de ONs USD desde data912.

Para cada ON_USD activa de ``core.renta_fija_catalogo.INSTRUMENTOS_RF``:
  1. Baja el último precio ARS por 100 VN de data912 (`/live/arg_corp`).
  2. Deriva paridad = precio_ARS / CCL.
  3. Calcula la TIR por DCF (YTM con interés corrido), usando cupón/frecuencia/
     vencimiento del catálogo. Método validado contra DNC7O (7.76% ≈ 7.73%).
  4. Marca quotes ilíquidos (volumen 0 → posiblemente stale, NO confiar).
  5. Imprime el diff vs. los valores actuales y los valores sugeridos para pegar.

NO escribe el catálogo: imprime la propuesta para revisión humana (los quotes
stale y los movimientos grandes requieren ojo — ver MGCEO jun-2026).

Soberanos / BONCER / BOPREAL / LECAP: NO se cubren acá. Su TIR/paridad sale de los
informes diarios de bancos (Hipotecario / Banco Provincia), no de data912.
CEDEARs (fallbacks): tampoco — los ratios de conversión son ambiguos; usar el
resumen del broker.

Uso:
  python scripts/importar_rf_data912.py                 # CCL automático (dolarapi)
  python scripts/importar_rf_data912.py --ccl 1511.27   # CCL manual
  python scripts/importar_rf_data912.py --umbral 1.0    # marca |Δparidad| ≥ 1.0 pp
  python scripts/importar_rf_data912.py --json          # salida JSON (machine)

Retorna 0 si pudo traer datos, 1 si falló la red / no encontró ninguna ON.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Consola Windows suele ser cp1252; evitar crash al imprimir caracteres no-ASCII.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from core.renta_fija_ar import INSTRUMENTOS_RF  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("importar_rf")

DATA912 = "https://data912.com/live/arg_corp"
DOLARAPI_CCL = "https://dolarapi.com/v1/dolares/contadoconliqui"
TIMEOUT = 15
HEADERS = {"User-Agent": "MQ26-importer/1.0"}


# ─── Red ──────────────────────────────────────────────────────────────────────

def fetch_arg_corp() -> dict[str, dict]:
    """Devuelve {symbol: {c, v, q_op, pct_change}} desde data912 /live/arg_corp."""
    r = requests.get(DATA912, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    out: dict[str, dict] = {}
    for it in r.json():
        sym = str(it.get("symbol", "")).upper().strip()
        if sym:
            out[sym] = it
    return out


def fetch_ccl() -> float | None:
    """CCL de dolarapi.com (promedio compra/venta). None si falla."""
    try:
        r = requests.get(DOLARAPI_CCL, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()
        compra, venta = float(d.get("compra") or 0), float(d.get("venta") or 0)
        vals = [x for x in (compra, venta) if x > 0]
        return round(sum(vals) / len(vals), 2) if vals else None
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.warning("No se pudo traer CCL de dolarapi: %s", e)
        return None


# ─── YTM por DCF (con interés corrido) ─────────────────────────────────────────

def _add_months(d: date, n: int) -> date:
    m, y = d.month + n, d.year
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    try:
        return date(y, m, d.day)
    except ValueError:
        return date(y, m, 28)


def _parse_vto(s: str) -> date | None:
    try:
        y, m, d = (int(x) for x in str(s).split("-"))
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


def ytm_dcf(clean: float, cupon_anual: float, freq: int, vto: date, hoy: date) -> float | None:
    """TIR anual (%) por bisección: PV(flujos futuros) = precio sucio (clean + corrido)."""
    if clean <= 0 or freq <= 0 or vto <= hoy:
        return None
    step = 12 // freq
    fechas = [vto]
    while fechas[0] > hoy:
        fechas.insert(0, _add_months(fechas[0], -step))
    futuras = [f for f in fechas if f > hoy]
    previas = [f for f in fechas if f <= hoy]
    if not futuras:
        return None
    ult = previas[-1] if previas else _add_months(futuras[0], -step)
    cup = cupon_anual / freq * 100.0
    dias_periodo = max((futuras[0] - ult).days, 1)
    corrido = cup * ((hoy - ult).days / dias_periodo)
    sucio = clean + corrido

    def pv(y: float) -> float:
        tot = 0.0
        for f in futuras:
            t = (f - hoy).days / 365.0
            flujo = cup + (100.0 if f == futuras[-1] else 0.0)
            tot += flujo / (1 + y / freq) ** (t * freq)
        return tot

    lo, hi = -0.9, 2.0
    for _ in range(300):
        mid = (lo + hi) / 2
        if pv(mid) > sucio:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2 * 100, 2)


# ─── Propuesta ─────────────────────────────────────────────────────────────────

def construir_propuesta(precios: dict[str, dict], ccl: float, hoy: date) -> list[dict]:
    """Una fila por ON_USD activa del catálogo con valores actuales vs. propuestos."""
    filas: list[dict] = []
    for ticker, meta in INSTRUMENTOS_RF.items():
        if str(meta.get("tipo", "")).upper() != "ON_USD" or not meta.get("activo"):
            continue
        q = precios.get(ticker)
        if not q:
            filas.append({"ticker": ticker, "estado": "sin_dato"})
            continue
        precio = float(q.get("c") or 0)
        vol = float(q.get("v") or 0)
        if precio <= 0:
            filas.append({"ticker": ticker, "estado": "precio_cero"})
            continue
        vto = _parse_vto(meta.get("vencimiento", ""))
        paridad = round(precio / ccl, 2)
        tir = ytm_dcf(paridad, float(meta.get("cupon_anual") or 0),
                      int(meta.get("frecuencia") or 2), vto, hoy) if vto else None
        par_cat = float(meta.get("paridad_ref") or 0)
        filas.append({
            "ticker": ticker,
            "estado": "stale" if vol == 0 else "ok",
            "precio_ars": precio,
            "paridad_cat": par_cat,
            "paridad_now": paridad,
            "delta_paridad": round(paridad - par_cat, 2),
            "tir_cat": float(meta.get("tir_ref") or 0),
            "tir_now": tir,
        })
    return filas


def imprimir_tabla(filas: list[dict], ccl: float, hoy: date, umbral: float) -> None:
    print(f"\nData912 ON_USD — CCL {ccl:.2f} — {hoy.isoformat()}\n")
    print(f"{'Ticker':7} {'estado':6} {'par_cat':>8} {'par_now':>8} {'d_par':>6} "
          f"{'tir_cat':>8} {'tir_now':>8}  notas")
    print("-" * 78)
    for f in filas:
        if f["estado"] in ("sin_dato", "precio_cero"):
            print(f"{f['ticker']:7} {f['estado']:6} {'—':>8} {'—':>8} {'—':>6} "
                  f"{'—':>8} {'—':>8}  (no se actualiza)")
            continue
        notas = []
        if f["estado"] == "stale":
            notas.append("[!] volumen 0 (posible stale, NO confiar)")
        if abs(f["delta_paridad"]) >= umbral:
            notas.append(f"d_paridad {f['delta_paridad']:+.2f} >= {umbral}")
        tir_now = f"{f['tir_now']:.2f}" if f["tir_now"] is not None else "n/a"
        print(f"{f['ticker']:7} {f['estado']:6} {f['paridad_cat']:8.2f} "
              f"{f['paridad_now']:8.2f} {f['delta_paridad']:+6.2f} "
              f"{f['tir_cat']:8.2f} {tir_now:>8}  {'; '.join(notas)}")

    aplicables = [f for f in filas if f["estado"] == "ok"]
    if aplicables:
        print("\nValores sugeridos para el catálogo (solo quotes con volumen):")
        for f in aplicables:
            tir = f["tir_now"] if f["tir_now"] is not None else f["tir_cat"]
            print(f'  {f["ticker"]}: paridad_ref {f["paridad_now"]}, tir_ref {tir}, '
                  f'ccl_ref {ccl}, precio_ars_ref {int(f["precio_ars"])}, '
                  f'fecha_ref "{hoy.isoformat()}"')
    print("\nRevisar a mano antes de aplicar (quotes stale y saltos grandes de paridad). "
          "Soberanos/BONCER/BOPREAL/LECAP: usar informe de banco, no este script.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Propone update de ONs USD desde data912.")
    ap.add_argument("--ccl", type=float, default=None, help="CCL manual (default: dolarapi).")
    ap.add_argument("--umbral", type=float, default=2.0,
                    help="Marca |Δparidad| ≥ umbral (pp). Default 2.0.")
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de tabla.")
    args = ap.parse_args()

    try:
        precios = fetch_arg_corp()
    except requests.exceptions.SSLError as e:
        logger.error("Falló data912 (SSL): %s", e)
        logger.error("Si estás detrás de un proxy corporativo, exportá la CA: "
                     "REQUESTS_CA_BUNDLE=/ruta/al/ca-bundle.pem")
        return 1
    except requests.RequestException as e:
        logger.error("Falló data912: %s", e)
        return 1
    if not precios:
        logger.error("data912 no devolvió instrumentos.")
        return 1

    ccl = args.ccl or fetch_ccl()
    if not ccl or ccl <= 0:
        logger.error("Sin CCL válido (pasá --ccl).")
        return 1

    hoy = date.today()
    filas = construir_propuesta(precios, ccl, hoy)
    if not any(f["estado"] in ("ok", "stale") for f in filas):
        logger.error("Ninguna ON del catálogo se encontró en data912.")
        return 1

    if args.json:
        print(json.dumps({"ccl": ccl, "fecha": hoy.isoformat(), "filas": filas},
                         ensure_ascii=False, indent=2))
    else:
        imprimir_tabla(filas, ccl, hoy, args.umbral)
    return 0


if __name__ == "__main__":
    sys.exit(main())
