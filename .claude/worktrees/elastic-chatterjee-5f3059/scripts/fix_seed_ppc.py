"""
scripts/fix_seed_ppc.py
========================
Reemplaza las 3 carteras de ejemplo en el CSV con datos corregidos y variados.

Mezcla de instrumentos BYMA: CEDEARs, acciones locales, bonos soberanos (AL30,
GD30, GD35), letras del tesoro (S31E5, S14F5), ONs corporativas y FCIs.

Convención de almacenamiento por tipo de instrumento:
  CEDEAR       → PPC_USD = US_price / ratio²   |  PPC_ARS = 0
  ACCION_LOCAL → PPC_USD = 0                   |  PPC_ARS = precio pagado en ARS
  BONO/LETRA   → PPC_USD = 0                   |  PPC_ARS = precio por VN en ARS
  FCI/ON       → PPC_USD = 0                   |  PPC_ARS = precio por cuota/VN en ARS
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import csv

RUTA_CSV = ROOT / "0_Data_Maestra" / "Maestra_Transaccional.csv"

# ── Ratios del config ─────────────────────────────────────────────────────────
RATIOS = {
    "AAPL": 20, "MSFT": 30, "GOOGL": 58, "AMZN": 144, "META": 24,
    "NVDA": 240, "KO": 5, "GLD": 10, "SPY": 20, "QQQ": 20,
    "XOM": 8,   "JNJ": 7, "MELI": 1, "TSLA": 6,  "YPFD": 1,
    "MO": 1,    "PG": 1,  "LMT": 10, "ABBV": 10,  "CVX": 16,
}

def ppc_usd_cedear(us_price: float, ticker: str) -> float:
    """PPC_USD correcto para CEDEAR = US_price / ratio²."""
    r = RATIOS.get(ticker.upper(), 1)
    return round(us_price / (r * r), 6)

# ── CCL histórico simplificado ────────────────────────────────────────────────
CCL = {
    "2022-03": 215, "2022-06": 237, "2022-09": 280, "2022-10": 308,
    "2022-12": 336, "2023-01": 358, "2023-02": 380, "2023-04": 422,
    "2023-06": 495, "2023-07": 548, "2023-09": 760, "2023-11": 900,
    "2024-01": 980, "2024-03": 1020, "2024-06": 1130, "2024-09": 1170,
    "2024-10": 1170, "2025-01": 1180, "2025-02": 1180, "2025-03": 1465,
}

# ── CARTERAS DE EJEMPLO ───────────────────────────────────────────────────────
# Formato: (CARTERA, FECHA, TICKER, CANTIDAD, PPC_USD, PPC_ARS, TIPO)
#
# CANT negativa = VENTA  |  PPC_ARS de ventas es referencia (no afecta INV)
# ─────────────────────────────────────────────────────────────────────────────
FILAS = [

    # ═══════════════════════════════════════════════════════════════════════════
    # CONSERVADORA — María Fernández | Ahorro Familiar
    # Objetivo: preservación + renta. Mix: CEDEAR defensivos + bonos + letras + local
    # ═══════════════════════════════════════════════════════════════════════════

    # ── CEDEARs defensivos ──────────────────────────────────────────────────
    # KO (Coca-Cola) ratio=5  →  PPC_USD = US_price / 25
    ("María Fernández | Ahorro Familiar", "2023-02-15", "KO",  100, ppc_usd_cedear(56.80,"KO"), 0.0, "CEDEAR"),
    # PG (P&G) ratio=1
    ("María Fernández | Ahorro Familiar", "2023-09-05", "PG",   8,  ppc_usd_cedear(142.50,"PG"), 0.0, "CEDEAR"),
    # KO segunda compra Oct 2023
    ("María Fernández | Ahorro Familiar", "2023-10-12", "KO",   50, ppc_usd_cedear(57.20,"KO"), 0.0, "CEDEAR"),

    # ── Acción local ────────────────────────────────────────────────────────
    # GGAL (Grupo Financiero Galicia) — precio directo ARS
    ("María Fernández | Ahorro Familiar", "2023-04-10", "GGAL", 500, 0.0, 310.0,  "ACCION_LOCAL"),
    ("María Fernández | Ahorro Familiar", "2024-09-15", "GGAL", 200, 0.0, 4_800.0,"ACCION_LOCAL"),

    # ── Bono soberano ARS — AL30 (Dual Bond CER/USD, venc. 2030) ────────────
    # Precio por $1 VN en ARS: en sep-2023 ~ARS 355, en jun-2024 ~ARS 610
    ("María Fernández | Ahorro Familiar", "2023-09-05", "AL30",  3_000, 0.0, 355.0, "BONO"),
    ("María Fernández | Ahorro Familiar", "2024-06-10", "AL30",  1_000, 0.0, 610.0, "BONO"),
    ("María Fernández | Ahorro Familiar", "2025-02-20", "AL30", -1_500, 0.0, 850.0, "BONO"),  # venta parcial

    # ── Bono USD (Global 2030) via BYMA ─────────────────────────────────────
    # GD30: precio ~$0.71/VN × CCL 1130 = ARS 802/VN en jun-2024
    ("María Fernández | Ahorro Familiar", "2024-06-10", "GD30",  2_000, 0.0, 802.0, "BONO_USD"),

    # ── Letras del Tesoro LECAP ──────────────────────────────────────────────
    # S31E5 (venc. 31/01/2025): precio ~ARS 94 por $1 VN en mar-2024
    ("María Fernández | Ahorro Familiar", "2024-03-15", "S31E5", 20_000, 0.0, 94.0, "LETRA"),
    # S14F5 (venc. 14/02/2025): ARS 96 por $1 VN en ene-2025
    ("María Fernández | Ahorro Familiar", "2025-01-10", "S14F5", 15_000, 0.0, 96.0, "LETRA"),


    # ═══════════════════════════════════════════════════════════════════════════
    # MODERADA — Carlos Rodríguez | Crecimiento
    # Objetivo: crecimiento equilibrado. Mix: CEDEAR crecimiento + bono USD + acción local + FCI + ON
    # ═══════════════════════════════════════════════════════════════════════════

    # ── CEDEARs de crecimiento ───────────────────────────────────────────────
    # SPY ratio=20
    ("Carlos Rodríguez | Crecimiento", "2022-09-15", "SPY",   50, ppc_usd_cedear(385.40,"SPY"), 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2024-06-12", "SPY",   30, ppc_usd_cedear(529.80,"SPY"), 0.0, "CEDEAR"),
    # AAPL ratio=20
    ("Carlos Rodríguez | Crecimiento", "2022-12-05", "AAPL", 200, ppc_usd_cedear(148.80,"AAPL"), 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2024-10-20", "AAPL",-100, ppc_usd_cedear(226.40,"AAPL"), 0.0, "CEDEAR"),  # venta
    # MSFT ratio=30
    ("Carlos Rodríguez | Crecimiento", "2023-09-10", "MSFT",  50, ppc_usd_cedear(285.60,"MSFT"), 0.0, "CEDEAR"),

    # ── Acciones locales ─────────────────────────────────────────────────────
    # PAMP (Pampa Energía): ARS 185 en ene-2023, ARS 3200 en mar-2024
    ("Carlos Rodríguez | Crecimiento", "2023-01-20", "PAMP", 5_000, 0.0, 185.0,  "ACCION_LOCAL"),
    ("Carlos Rodríguez | Crecimiento", "2024-03-08", "PAMP",   500, 0.0, 3_200.0,"ACCION_LOCAL"),

    # ── Bono USD Global 2030 ─────────────────────────────────────────────────
    # GD30: $0.52/VN × CCL 495 = ARS 257/VN en jun-2023
    ("Carlos Rodríguez | Crecimiento", "2023-06-15", "GD30", 10_000, 0.0, 257.0, "BONO_USD"),

    # ── ON corporativa — YPF (ON USD 2025/2028) ──────────────────────────────
    # Ticker BYMA "YMCHO": precio ARS 900/VN (≈ $0.95/VN × CCL 900)
    ("Carlos Rodríguez | Crecimiento", "2023-11-08", "YMCHO", 2_000, 0.0, 900.0, "ON_USD"),

    # ── Bono CER — TX28 (Boncer 2028) ────────────────────────────────────────
    # TX28: precio ARS 145 por $1 VN en sep-2024
    ("Carlos Rodríguez | Crecimiento", "2024-09-20", "TX28", 25_000, 0.0, 145.0, "BONO"),

    # ── FCI Renta Fija — Fima Premium ────────────────────────────────────────
    # FIMAFX: ARS 380 por cuota-parte en feb-2025
    ("Carlos Rodríguez | Crecimiento", "2025-02-10", "FIMAFX", 10_000, 0.0, 380.0, "FCI"),


    # ═══════════════════════════════════════════════════════════════════════════
    # AGRESIVA — Diego Martínez | Alta Rentabilidad
    # Objetivo: máximo crecimiento. Mix: CEDEAR tech + acciones locales volátiles + bono USD largo + ON + FCI
    # ═══════════════════════════════════════════════════════════════════════════

    # ── CEDEARs tech volátiles ───────────────────────────────────────────────
    # NVDA ratio=240 — precios split-adjusted (÷10 post junio-2024)
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "NVDA", 200, ppc_usd_cedear(16.50,"NVDA"),  0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2023-06-05", "NVDA", 200, ppc_usd_cedear(40.00,"NVDA"),  0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2024-06-17", "NVDA", 100, ppc_usd_cedear(67.00,"NVDA"),  0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2025-01-08", "NVDA", 100, ppc_usd_cedear(135.00,"NVDA"), 0.0, "CEDEAR"),
    # META ratio=24
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "META",  30, ppc_usd_cedear(199.00,"META"), 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2022-10-18", "META",  20, ppc_usd_cedear(97.00,"META"),  0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2024-02-26", "META",  15, ppc_usd_cedear(486.20,"META"), 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2025-03-01", "META",  10, ppc_usd_cedear(600.00,"META"), 0.0, "CEDEAR"),

    # ── Acciones locales volátiles ───────────────────────────────────────────
    # YPFD (YPF): ARS 900 en jun-2022, ARS 10500 en sep-2023
    ("Diego Martínez | Alta Rentabilidad", "2022-06-08", "YPFD", 100, 0.0, 900.0,   "ACCION_LOCAL"),
    ("Diego Martínez | Alta Rentabilidad", "2023-09-11", "YPFD", 100, 0.0, 10_500.0,"ACCION_LOCAL"),
    # ALUA (Aluar): ARS 195 en jun-2022, ARS 210 en sep-2023, venta en jun-2024
    ("Diego Martínez | Alta Rentabilidad", "2022-06-08", "ALUA", 3_000, 0.0, 195.0,  "ACCION_LOCAL"),
    ("Diego Martínez | Alta Rentabilidad", "2023-09-11", "ALUA", 2_000, 0.0, 210.0,  "ACCION_LOCAL"),
    ("Diego Martínez | Alta Rentabilidad", "2024-06-17", "ALUA",-2_000, 0.0, 1_950.0,"ACCION_LOCAL"),  # venta

    # ── Bono USD largo — GD35 (Global 2035) ─────────────────────────────────
    # GD35: $0.33/VN × CCL 358 = ARS 118/VN en ene-2023
    ("Diego Martínez | Alta Rentabilidad", "2023-01-09", "GD35", 15_000, 0.0, 118.0, "BONO_USD"),

    # ── ON corporativa — YCA6O (ON Arcor USD) ────────────────────────────────
    # Precio ~ARS 820/VN ($0.91/VN × CCL 900) en nov-2023
    ("Diego Martínez | Alta Rentabilidad", "2023-11-15", "YCA6O", 3_000, 0.0, 820.0, "ON_USD"),

    # ── FCI de alta rentabilidad — Balanz ────────────────────────────────────
    # BALANZR: ARS 1200/cuota-parte en sep-2024
    ("Diego Martínez | Alta Rentabilidad", "2024-09-10", "BALANZR", 3_000, 0.0, 1_200.0, "FCI"),
]

# ── Carteras a reemplazar ─────────────────────────────────────────────────────
CARTERAS_SEED = {
    "María Fernández | Ahorro Familiar",
    "Carlos Rodríguez | Crecimiento",
    "Diego Martínez | Alta Rentabilidad",
}


def main():
    print("\n" + "═" * 70)
    print("  Rehaciendo 3 carteras de ejemplo con mix completo BYMA")
    print("═" * 70)

    with open(RUTA_CSV, encoding="utf-8") as f:
        reader = csv.reader(f)
        filas_originales = list(reader)

    if not filas_originales:
        print("  ❌ CSV vacío.")
        return

    header = filas_originales[0]
    filas_sin_seed = [header]
    removidas = 0
    for row in filas_originales[1:]:
        if row and row[0].strip() not in CARTERAS_SEED:
            filas_sin_seed.append(row)
        else:
            removidas += 1
    print(f"  Filas eliminadas (seed anterior): {removidas}")

    # Construir nuevas filas CSV
    filas_nuevas = []
    for cartera, fecha, ticker, cant, ppc_usd, ppc_ars, tipo in FILAS:
        filas_nuevas.append([cartera, fecha, ticker, cant, round(ppc_usd, 6), round(ppc_ars, 2), tipo])

    # Resumen por cartera
    resumen = {}
    for row in filas_nuevas:
        c = row[0]
        resumen.setdefault(c, {"operaciones": 0, "tipos": set()})
        resumen[c]["operaciones"] += 1
        resumen[c]["tipos"].add(row[6])

    for cartera, info in resumen.items():
        print(f"\n  📁 {cartera}")
        print(f"     Operaciones : {info['operaciones']}")
        print(f"     Tipos BYMA  : {', '.join(sorted(info['tipos']))}")

    todas = filas_sin_seed + filas_nuevas
    with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(todas)

    print(f"\n  ✅ CSV actualizado: {len(todas) - 1} filas totales ({len(filas_nuevas)} de ejemplos)")
    print("═" * 70 + "\n")

    # Verificación KO para CEDEAR
    ko = next(r for r in filas_nuevas if "Fernández" in r[0] and r[2] == "KO" and float(r[3]) > 0)
    ppc_usd_ko = float(ko[4])
    inv_ars_ko = 100 * ppc_usd_ko * CCL["2023-02"] * 5
    print("  Verificación KO (CEDEAR ratio=5):")
    print(f"    PPC_USD = {ppc_usd_ko:.6f} (= 56.80/25)")
    print(f"    INV_ARS 100u × {CCL['2023-02']} CCL × 5 ratio = ARS {inv_ars_ko:,.0f}")

    # Verificación AL30 para BONO local
    al30 = next(r for r in filas_nuevas if "Fernández" in r[0] and r[2] == "AL30" and float(r[3]) > 0)
    ppc_ars_al30 = float(al30[5])
    inv_ars_al30 = 3000 * ppc_ars_al30
    print("\n  Verificación AL30 (BONO local ARS):")
    print(f"    PPC_ARS = {ppc_ars_al30:.2f}")
    print(f"    INV_ARS 3000 VN = ARS {inv_ars_al30:,.0f}")

    # Verificación GGAL para acción local
    ggal = next(r for r in filas_nuevas if "Fernández" in r[0] and r[2] == "GGAL" and float(r[3]) > 0)
    ppc_ars_ggal = float(ggal[5])
    inv_ars_ggal = 500 * ppc_ars_ggal
    print("\n  Verificación GGAL (ACCION_LOCAL):")
    print(f"    PPC_ARS = {ppc_ars_ggal:.2f}")
    print(f"    INV_ARS 500 acciones = ARS {inv_ars_ggal:,.0f}")


if __name__ == "__main__":
    main()
