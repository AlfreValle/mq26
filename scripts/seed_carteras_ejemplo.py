"""
scripts/seed_carteras_ejemplo.py
=================================
Crea 3 carteras de ejemplo en MQ26-DSS para testear todas las funciones:

  1. María Fernández  | Ahorro Familiar       → Conservadora  | 1 año
  2. Carlos Rodríguez | Crecimiento           → Moderada       | 3 años
  3. Diego Martínez   | Alta Rentabilidad     → Agresiva        | +5 años

Cada cartera tiene:
  - Cliente registrado en SQLite (perfil, horizonte, capital)
  - 2-3 objetivos de inversión con plazos distintos
  - Operaciones históricas reales en Maestra_Transaccional.csv

Uso:
    cd c:\\Users\\alfredo.vallejos\\Documents\\Alfredo\\PROYECTOS\\MQ26_v17
    python scripts/seed_carteras_ejemplo.py
"""

import sys
from pathlib import Path

# ── path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── imports ─────────────────────────────────────────────────────────────────
import csv

from core import db_manager as dbm

# ── configuración ────────────────────────────────────────────────────────────
RUTA_CSV = ROOT / "0_Data_Maestra" / "Maestra_Transaccional.csv"
MARCADOR  = "# SEED_CARTERAS_EJEMPLO"   # línea marcadora para evitar duplicados

# ── Transacciones de ejemplo ─────────────────────────────────────────────────
# Columnas: CARTERA, FECHA_COMPRA, TICKER, CANTIDAD, PPC_USD, PPC_ARS, TIPO
# PPC_USD = precio subyacente en USD (precio_mercado / ratio_CEDEAR)

TRANSACCIONES_CONSERVADORA = [
    # ── Cartera Conservadora | 2023 ──────────────────────────────────────────
    # Dividend blue-chips + ETF bonos + oro → baja volatilidad
    ("María Fernández | Ahorro Familiar", "2023-02-15", "KO",   50,  56.80, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-02-15", "MO",   30,  43.60, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-02-15", "PG",   12, 142.50, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-04-10", "XOM",  25, 112.40, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-04-10", "JNJ",  10, 155.20, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-07-03", "GLD",   6, 183.40, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-10-12", "KO",   30,  57.20, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2023-10-12", "XOM",  10, 108.90, 0.0, "CEDEAR"),
    # ── Refuerzo 2024 ─────────────────────────────────────────────────────────
    ("María Fernández | Ahorro Familiar", "2024-02-20", "PG",    8, 155.80, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2024-02-20", "MO",   15,  44.10, 0.0, "CEDEAR"),
    ("María Fernández | Ahorro Familiar", "2024-06-05", "KO",   25,  61.30, 0.0, "CEDEAR"),
    # ── Venta parcial KO (realizó ganancias) ──────────────────────────────────
    ("María Fernández | Ahorro Familiar", "2025-01-15", "KO",  -40,  63.80, 0.0, "CEDEAR"),
]

TRANSACCIONES_MODERADA = [
    # ── Cartera Moderada | 2022-2023 ─────────────────────────────────────────
    # Blend: ETFs + tech growth + MELI (LATAM) → riesgo-retorno equilibrado
    ("Carlos Rodríguez | Crecimiento", "2022-06-10", "SPY",     8, 385.40, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2022-09-15", "AAPL",   15, 148.80, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2022-09-15", "MSFT",    5, 237.60, 0.0, "CEDEAR"),
    # GOOGL ratio ~10 en BYMA → PPC_USD = precio_USA / 10
    ("Carlos Rodríguez | Crecimiento", "2022-12-05", "GOOGL",  50,  9.40,  0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2023-01-20", "MELI",    2, 920.00, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2023-03-08", "MSFT",    5, 285.60, 0.0, "CEDEAR"),
    # ── Refuerzo 2023-2024 ────────────────────────────────────────────────────
    ("Carlos Rodríguez | Crecimiento", "2023-06-20", "SPY",     5, 435.20, 0.0, "CEDEAR"),
    # NVDA ratio ~10 → PPC_USD = precio / 10
    ("Carlos Rodríguez | Crecimiento", "2024-01-10", "NVDA",   10,  49.60, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2024-01-10", "AAPL",    8, 183.40, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2024-06-12", "SPY",     3, 529.80, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2024-06-12", "GOOGL",  30,  18.60, 0.0, "CEDEAR"),
    # ── Venta parcial AAPL (rebalanceo) ──────────────────────────────────────
    ("Carlos Rodríguez | Crecimiento", "2024-10-20", "AAPL",  -10, 226.40, 0.0, "CEDEAR"),
    # ── Compra 2025 ───────────────────────────────────────────────────────────
    ("Carlos Rodríguez | Crecimiento", "2025-02-10", "MELI",    1,1640.00, 0.0, "CEDEAR"),
    ("Carlos Rodríguez | Crecimiento", "2025-02-10", "MSFT",    3, 408.20, 0.0, "CEDEAR"),
]

TRANSACCIONES_AGRESIVA = [
    # ── Cartera Agresiva | 2022-2024 ─────────────────────────────────────────
    # High-growth: semiconductores + IA + MELI + YPF Argentina
    # NVDA ratio ~10 → PPC_USD = precio / 10
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "NVDA",  30, 25.60, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2022-03-14", "META",  15, 198.80,0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2022-06-08", "TSLA",  20, 218.40,0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2022-10-18", "META",  20,  96.50, 0.0, "CEDEAR"),
    # AMZN ratio ~10 → PPC_USD = precio / 10
    ("Diego Martínez | Alta Rentabilidad", "2022-12-20", "AMZN",  80,  8.60, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2023-01-09", "MELI",   3, 870.00,0.0, "CEDEAR"),
    # ── Refuerzo pre-rally IA 2023 ────────────────────────────────────────────
    ("Diego Martínez | Alta Rentabilidad", "2023-06-05", "NVDA",  20, 38.50, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2023-06-05", "META",  10, 261.40,0.0, "CEDEAR"),
    # YPFD: acción local Argentina, no CEDEAR
    ("Diego Martínez | Alta Rentabilidad", "2023-09-11", "YPFD",  50, 14.80, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2023-09-11", "AMZN",  40, 13.20, 0.0, "CEDEAR"),
    # ── Refuerzo 2024 (rally IA) ──────────────────────────────────────────────
    ("Diego Martínez | Alta Rentabilidad", "2024-02-26", "NVDA",  15, 79.80, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2024-02-26", "META",   8, 486.20,0.0, "CEDEAR"),
    # ── Venta TSLA (stop loss por alta volatilidad) ───────────────────────────
    ("Diego Martínez | Alta Rentabilidad", "2024-04-22", "TSLA", -20, 142.60,0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2024-06-17", "MELI",   2,1940.00,0.0, "CEDEAR"),
    # ── Compra 2025 ───────────────────────────────────────────────────────────
    ("Diego Martínez | Alta Rentabilidad", "2025-01-08", "NVDA",  10,136.40, 0.0, "CEDEAR"),
    ("Diego Martínez | Alta Rentabilidad", "2025-03-01", "META",   5, 598.20,0.0, "CEDEAR"),
]

TODAS_LAS_TRANSACCIONES = (
    TRANSACCIONES_CONSERVADORA +
    TRANSACCIONES_MODERADA +
    TRANSACCIONES_AGRESIVA
)

# ── Clientes ─────────────────────────────────────────────────────────────────
CLIENTES = [
    {
        "nombre":          "María Fernández | Ahorro Familiar",
        "perfil_riesgo":   "Conservador",
        "horizonte_label": "1 año",
        "capital_usd":     18_000.0,
        "tipo_cliente":    "Persona",
    },
    {
        "nombre":          "Carlos Rodríguez | Crecimiento",
        "perfil_riesgo":   "Moderado",
        "horizonte_label": "3 años",
        "capital_usd":     45_000.0,
        "tipo_cliente":    "Persona",
    },
    {
        "nombre":          "Diego Martínez | Alta Rentabilidad",
        "perfil_riesgo":   "Agresivo",
        "horizonte_label": "+5 años",
        "capital_usd":     85_000.0,
        "tipo_cliente":    "Persona",
    },
]

# ── Objetivos de inversión ────────────────────────────────────────────────────
# {cliente_nombre → lista de objetivos}
OBJETIVOS = {
    "María Fernández | Ahorro Familiar": [
        {
            "monto_ars":  2_500_000.0,
            "plazo_label": "6 meses",
            "motivo":      "Fondo de emergencia familiar — equivalente a 6 meses de gastos",
            "ticker":      "KO",
            "target_pct":  0.10,
            "stop_pct":   -0.08,
        },
        {
            "monto_ars":  4_800_000.0,
            "plazo_label": "1 año",
            "motivo":      "Viaje de vacaciones familiares a Europa — verano 2027",
            "ticker":      "GLD",
            "target_pct":  0.15,
            "stop_pct":   -0.12,
        },
        {
            "monto_ars": 12_000_000.0,
            "plazo_label": "3 años",
            "motivo":      "Refacción y ampliación del hogar — ahorro en USD",
            "ticker":      "",
            "target_pct":  0.20,
            "stop_pct":   -0.15,
        },
    ],
    "Carlos Rodríguez | Crecimiento": [
        {
            "monto_ars":  3_500_000.0,
            "plazo_label": "1 año",
            "motivo":      "Auto 0km — Toyota Corolla Cross",
            "ticker":      "SPY",
            "target_pct":  0.12,
            "stop_pct":   -0.10,
        },
        {
            "monto_ars": 18_000_000.0,
            "plazo_label": "3 años",
            "motivo":      "Fondo universitario para los dos hijos",
            "ticker":      "AAPL",
            "target_pct":  0.35,
            "stop_pct":   -0.20,
        },
        {
            "monto_ars": 45_000_000.0,
            "plazo_label": "+5 años",
            "motivo":      "Retiro anticipado a los 55 años — cartera de rentas",
            "ticker":      "",
            "target_pct":  0.80,
            "stop_pct":   -0.25,
        },
    ],
    "Diego Martínez | Alta Rentabilidad": [
        {
            "monto_ars":  4_000_000.0,
            "plazo_label": "3 meses",
            "motivo":      "Capital de trabajo para trading activo — rotación rápida",
            "ticker":      "NVDA",
            "target_pct":  0.25,
            "stop_pct":   -0.15,
        },
        {
            "monto_ars": 12_000_000.0,
            "plazo_label": "1 año",
            "motivo":      "Capital semilla para startup de fintech",
            "ticker":      "META",
            "target_pct":  0.40,
            "stop_pct":   -0.25,
        },
        {
            "monto_ars": 60_000_000.0,
            "plazo_label": "+5 años",
            "motivo":      "Libertad financiera 2030 — cartera de crecimiento agresivo con IA",
            "ticker":      "",
            "target_pct":  1.50,
            "stop_pct":   -0.35,
        },
    ],
}


def _carteras_ya_existen_en_csv() -> bool:
    """Devuelve True si el CSV ya tiene datos de las carteras de ejemplo."""
    if not RUTA_CSV.exists():
        return False
    with open(RUTA_CSV, encoding="utf-8") as f:
        contenido = f.read()
    return "María Fernández | Ahorro Familiar" in contenido


def _agregar_transacciones_al_csv() -> int:
    """Agrega las transacciones al CSV. Devuelve cantidad de filas agregadas."""
    if _carteras_ya_existen_en_csv():
        print("  ⚠️  Las carteras de ejemplo ya existen en el CSV — se omite escritura.")
        return 0

    with open(RUTA_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in TODAS_LAS_TRANSACCIONES:
            writer.writerow(row)

    print(f"  ✅ {len(TODAS_LAS_TRANSACCIONES)} operaciones agregadas al CSV.")
    return len(TODAS_LAS_TRANSACCIONES)


def _registrar_clientes() -> dict:
    """Registra los 3 clientes en SQLite. Devuelve {nombre → id}."""
    ids = {}
    for c in CLIENTES:
        cid = dbm.registrar_cliente(
            nombre          = c["nombre"],
            perfil_riesgo   = c["perfil_riesgo"],
            capital_usd     = c["capital_usd"],
            tipo_cliente    = c["tipo_cliente"],
            horizonte_label = c["horizonte_label"],
        )
        ids[c["nombre"]] = cid
        print(f"  ✅ Cliente: {c['nombre']} (id={cid}) — {c['perfil_riesgo']} | {c['horizonte_label']}")
    return ids


def _registrar_objetivos(ids_clientes: dict) -> int:
    """Registra los objetivos de inversión. Devuelve cantidad creada."""
    total = 0
    for nombre_cliente, lista_obj in OBJETIVOS.items():
        cliente_id = ids_clientes.get(nombre_cliente)
        if not cliente_id:
            print(f"  ⚠️  No se encontró id para '{nombre_cliente}'")
            continue

        # Verificar si ya tiene objetivos para no duplicar
        df_existing = dbm.obtener_objetivos_cliente(cliente_id)
        if not df_existing.empty:
            print(f"  ⚠️  {nombre_cliente} ya tiene {len(df_existing)} objetivos — se omite.")
            continue

        for obj in lista_obj:
            try:
                oid = dbm.registrar_objetivo(
                    cliente_id  = cliente_id,
                    monto_ars   = obj["monto_ars"],
                    plazo_label = obj["plazo_label"],
                    motivo      = obj["motivo"],
                    ticker      = obj.get("ticker", ""),
                    target_pct  = obj.get("target_pct"),
                    stop_pct    = obj.get("stop_pct"),
                )
                total += 1
                print(
                    f"    📌 Objetivo creado (id={oid}): "
                    f"${obj['monto_ars']:>14,.0f} ARS | {obj['plazo_label']:10s} | {obj['motivo'][:55]}..."
                )
            except Exception as e:
                print(f"    ❌ Error creando objetivo: {e}")
    return total


def main():
    print("\n" + "═" * 65)
    print("  MQ26-DSS — Seed de 3 Carteras de Ejemplo")
    print("═" * 65)

    # 1. Inicializar BD (crea tablas si no existen)
    print("\n[1/3] Inicializando base de datos...")
    dbm.init_db()
    print("  ✅ BD inicializada correctamente.")

    # 2. Registrar clientes
    print("\n[2/3] Registrando clientes...")
    ids_clientes = _registrar_clientes()

    # 3. Registrar objetivos
    print("\n[3/3] Registrando objetivos de inversión...")
    n_obj = _registrar_objetivos(ids_clientes)

    # 4. Agregar transacciones al CSV
    print("\n[4/4] Agregando transacciones al CSV...")
    n_trans = _agregar_transacciones_al_csv()

    # ── Resumen ──────────────────────────────────────────────────────────────
    print("\n" + "─" * 65)
    print("  RESUMEN DEL SEED")
    print("─" * 65)
    print(f"  Clientes registrados : {len(ids_clientes)}")
    print(f"  Objetivos creados    : {n_obj}")
    print(f"  Transacciones CSV    : {n_trans}")
    print("\n  Carteras disponibles:")
    for c in CLIENTES:
        icono = {"Conservador": "🟢", "Moderado": "🟡", "Agresivo": "🔴"}[c["perfil_riesgo"]]
        print(
            f"    {icono} {c['nombre']:<42} "
            f"{c['perfil_riesgo']:12s} | {c['horizonte_label']}"
        )
    print("\n  ✅ Listo. Reiniciá la app (F5) y seleccioná cualquiera de los 3 clientes.")
    print("═" * 65 + "\n")


if __name__ == "__main__":
    main()
