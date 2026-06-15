"""
scripts/etl_alfredo_excel.py
============================
ETL: importa la "Super Plantilla - Finanzas - Inversiones.xlsx" de Alfredo
y crea/actualiza el cliente "Alfredo Vallejos" con todos sus datos en el sistema MQ26.

Qué importa:
  1. Cliente "Alfredo Vallejos" con perfil Moderado
  2. Ingresos y gastos mensuales (Enero-Diciembre 2026) → transacciones_dss
  3. Servicios fijos recurrentes → servicios_fijos
  4. 3 objetivos de inversión → objetivos_inversion
  5. Posiciones activas de CARTERA RETIRO → Maestra_Transaccional.csv
"""
import csv
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT.parent / "Alfre 2026 - Super Plantilla - Finanzas - Inversiones.xlsx"

sys.path.insert(0, str(ROOT))
import pandas as pd

import core.db_manager as dbm

# ── Asegurar que las tablas existan ──────────────────────────────────────────
dbm.init_db()

print()
print("=" * 70)
print("  ETL: Alfredo Vallejos ← Super Plantilla Finanzas 2026")
print("=" * 70)

if not EXCEL.exists():
    print(f"  ERROR: no se encontró el Excel en {EXCEL}")
    print("  Verificá la ruta y volvé a ejecutar.")
    sys.exit(1)

xl = pd.ExcelFile(str(EXCEL))
CCL_REF = 1465.0  # CCL promedio mar-2026

# ════════════════════════════════════════════════════════════════════════════
# 1. REGISTRAR CLIENTE
# ════════════════════════════════════════════════════════════════════════════
print("\n[1/5] Registrando cliente Alfredo Vallejos...")

# Patrimonio actual USD = 6894 (de la hoja Objetivos)
cliente_id = dbm.registrar_cliente(
    nombre         = "Alfredo Vallejos",
    perfil_riesgo  = "Moderado",
    capital_usd    = 6894.70,
    tipo_cliente   = "Persona",
    horizonte_label= "3 años",
)
print(f"  Cliente ID: {cliente_id} — Alfredo Vallejos")

# ════════════════════════════════════════════════════════════════════════════
# 2. IMPORTAR INGRESOS Y GASTOS 2026
# ════════════════════════════════════════════════════════════════════════════
print("\n[2/5] Importando ingresos y gastos 2026...")

MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Setiembre","Octubre","Noviembre","Diciembre"]
MESES_N = {m: i+1 for i, m in enumerate(MESES)}

df_ig = pd.read_excel(xl, sheet_name="Ingresos y Gastos", nrows=200)

# Mapeo: descripción en Excel → (tipo, categoría)
MAPA_TIPO = {
    # INGRESOS
    "Salario Alfredo":                  ("INGRESO", "Sueldo / Honorarios"),
    "Salario Andrea":                   ("INGRESO", "Sueldo / Honorarios"),
    "Aguinaldo":                        ("INGRESO", "Bono / Aguinaldo"),
    "Bono fin de Año":                  ("INGRESO", "Bono / Aguinaldo"),
    "Ventas de Acciones":               ("INGRESO", "Venta de activos"),
    "Venta de Usd":                     ("INGRESO", "Venta de activos"),
    "Rescates Fondo común de Inversiones": ("INGRESO", "Dividendos / Cupones"),
    "Reintegros":                       ("INGRESO", "Otros ingresos"),
    # EGRESOS — Tarjetas
    "00 - Claro":                       ("EGRESO", "Servicios (luz/gas/agua)"),
    "01 - Personal Flow - Departamento":("EGRESO", "Internet / Cable"),
    "Arreglos / service Peugeot":       ("EGRESO", "Transporte / Combustible"),
    "Colegio de los Chicos":            ("EGRESO", "Educación"),
    "Gastos Bancarios":                 ("EGRESO", "Otros egresos"),
    "Nafta / ypf":                      ("EGRESO", "Transporte / Combustible"),
    "Rio Uruguay Seguros":              ("EGRESO", "Seguros"),
    "Ropa Andrea":                      ("EGRESO", "Ropa / Indumentaria"),
    "SuperMercado":                     ("EGRESO", "Supermercado / Alimentos"),
    "UNIFORMES":                        ("EGRESO", "Educación"),
    "Ropa de los chicos":               ("EGRESO", "Ropa / Indumentaria"),
    # Servicios por Banco
    "Avesa":                            ("EGRESO", "Servicios (luz/gas/agua)"),
    "Claro":                            ("EGRESO", "Internet / Cable"),
    "Dpec Barrio":                      ("EGRESO", "Servicios (luz/gas/agua)"),
    "Dpec Departamento":                ("EGRESO", "Servicios (luz/gas/agua)"),
    "Expensas del Barrio":              ("EGRESO", "Alquiler pagado"),
    "Expensas del Departamento":        ("EGRESO", "Alquiler pagado"),
    "Jardinero":                        ("EGRESO", "Otros egresos"),
    # Gastos varios Andrea
    "Andrea Benchetrit":                ("EGRESO", "Medicina prepaga"),
    "Dentista Nicolàs":                 ("EGRESO", "Medicina prepaga"),
    "Dentista Santiago":                ("EGRESO", "Medicina prepaga"),
    "Gastos Médicos / Veterinarios":    ("EGRESO", "Medicina prepaga"),
    "Gastos para la Comida diaria":     ("EGRESO", "Supermercado / Alimentos"),
    "Gimnasio Andrea":                  ("EGRESO", "Entretenimiento"),
    "Recepción de 5to Año":             ("EGRESO", "Educación"),
    # Gastos Alfredo
    "1.1 Crèdito Hipotecario 1":        ("EGRESO", "Préstamo / Cuota"),
    "1.2 Crèdito Hipotecario 2":        ("EGRESO", "Préstamo / Cuota"),
    "1.3 Gastos de seguro Banco Hipot.1": ("EGRESO", "Seguros"),
    "1.4 Gastos de seguro Banco Hipot.2": ("EGRESO", "Seguros"),
    "1.5 Gastos seguro BanCo":          ("EGRESO", "Seguros"),
    "2 Alfredo Vallejos":               ("EGRESO", "Otros egresos"),
    "3 Santiago Vallejos":              ("EGRESO", "Otros egresos"),
    "4 Nicolas Vallejos":               ("EGRESO", "Otros egresos"),
    "Gimnasios Alfre, Nico y Santi":    ("EGRESO", "Entretenimiento"),
    "Reparaciones Automotor":           ("EGRESO", "Transporte / Combustible"),
    "Otros Gastos":                     ("EGRESO", "Otros egresos"),
    # Visa BH Alfredo
    "BHN SEGUROS GE00000448861-0-017-0": ("EGRESO", "Seguros"),
    "BHN VIDA SA-AC0002553-23959-018-0": ("EGRESO", "Seguros"),
    "CELU SANTI":                       ("EGRESO", "Internet / Cable"),
    "Claro Nicolàs":                    ("EGRESO", "Internet / Cable"),
    "MERPAGO / MERCADOLIBRE":           ("EGRESO", "Otros egresos"),
    "NETFLIX":                          ("EGRESO", "Entretenimiento"),
    "ROPA ALFREDO":                     ("EGRESO", "Ropa / Indumentaria"),
    # Visa BC Alfredo
    "DLO*IDACOM 01/06":                 ("EGRESO", "Otros egresos"),
    "FUNDACION NOBLE":                  ("EGRESO", "Otros egresos"),
    "GUITARRA":                         ("EGRESO", "Educación"),
    "GOOGLE *YouTube":                  ("EGRESO", "Entretenimiento"),
    "ROPA / ALFRE":                     ("EGRESO", "Ropa / Indumentaria"),
    "ROPA DE LOS CHICOS":               ("EGRESO", "Ropa / Indumentaria"),
    "STARLINK":                         ("EGRESO", "Internet / Cable"),
    # Ahorros (los tratamos como EGRESO/Inversiones)
    "Ahorro para emergencias":          ("EGRESO", "Inversiones (aporte)"),
    "Ahorro para jubilación":           ("EGRESO", "Inversiones (aporte)"),
    "Ahorro para inversiones":          ("EGRESO", "Inversiones (aporte)"),
}

# Filas que son totales/encabezados — ignorar
IGNORAR = {
    "Balance inicial", "Ingreso total", "Gastos totales", "(Ingreso – Gastos)",
    "Saldo", "Ingresos", "Ingresos Totales", "Ahorros e inversiones",
    "Ahorros e inversiones Totales", "Tarjetas de crédito (Andrea)",
    "Tarjetas de crédito (Andrea) Totales", "Servicios pagados por Banco (Andrea)",
    "Servicios pagados por Banco (Andrea) Totales", "Gastos Varios (Andrea)",
    "Gastos Varios (Alfredo)", "Visa Banco Hipotecario (Alfredo)",
    "Visa Banco Hipotecario (Alfredo) Totales", "Visa Banco de Corrientes (Alfredo)",
    "Visa Banco de Corrientes (Alfredo) Totales",
}

tx_importadas = 0
tx_omitidas   = 0

for _, row in df_ig.iterrows():
    desc_raw = str(row.get("Fecha", "")).strip()
    if not desc_raw or desc_raw in ("nan", "None") or desc_raw in IGNORAR:
        continue
    if len(desc_raw) < 3:
        continue

    tipo_cat = MAPA_TIPO.get(desc_raw)
    if tipo_cat is None:
        tx_omitidas += 1
        continue

    tipo_tx, categoria = tipo_cat

    for mes_nombre in MESES:
        if mes_nombre not in df_ig.columns:
            continue
        val = row.get(mes_nombre)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        monto = float(val)
        if monto == 0.0:
            continue

        mes_n = MESES_N[mes_nombre]
        fecha_tx = dt.date(2026, mes_n, 1)

        dbm.registrar_transaccion_dss(
            cliente_id   = cliente_id,
            fecha        = fecha_tx,
            descripcion  = desc_raw,
            monto        = abs(monto),
            tipo         = tipo_tx,
            categoria    = categoria,
            es_recurrente= True,
            moneda       = "ARS",
        )
        tx_importadas += 1

print(f"  Transacciones importadas : {tx_importadas}")
print(f"  Filas sin mapeo (omitidas): {tx_omitidas}")

# ════════════════════════════════════════════════════════════════════════════
# 3. SERVICIOS FIJOS RECURRENTES
# ════════════════════════════════════════════════════════════════════════════
print("\n[3/5] Registrando servicios fijos...")

# Primero limpiar servicios anteriores del cliente (evitar duplicados)
with dbm.get_session() as s:
    from core.db_manager import ServicioFijo
    s.query(ServicioFijo).filter(ServicioFijo.cliente_id == cliente_id).delete()

SERVICIOS_FIJOS = [
    # (descripcion, monto_ars_enero, dia_debito, categoria)
    ("Expensas del Barrio",              137_630, 10, "Alquiler pagado"),
    ("Expensas del Departamento",        214_860, 10, "Alquiler pagado"),
    ("Claro (teléfono)",                  29_343,  5, "Internet / Cable"),
    ("Avesa (agua)",                      17_400,  5, "Servicios (luz/gas/agua)"),
    ("Dpec Barrio (electricidad)",        24_302,  5, "Servicios (luz/gas/agua)"),
    ("Dpec Departamento (electricidad)",  60_049,  5, "Servicios (luz/gas/agua)"),
    ("Jardinero",                         70_000, 15, "Otros egresos"),
    ("Crédito Hipotecario 1",                977,  5, "Préstamo / Cuota"),
    ("Crédito Hipotecario 2",             23_000,  5, "Préstamo / Cuota"),
    ("Seguro Banco Hipotecario 1",         1_035,  5, "Seguros"),
    ("Seguro Banco Hipotecario 2",         1_035,  5, "Seguros"),
    ("Rio Uruguay Seguros",               69_682,  5, "Seguros"),
    ("Personal Flow - Depto",             40_808,  5, "Internet / Cable"),
    ("NETFLIX",                           19_999, 15, "Entretenimiento"),
    ("STARLINK",                               0, 15, "Internet / Cable"),  # sin dato enero
    ("Colegio de los Chicos",            439_700, 10, "Educación"),
    ("Gimnasios (Alfre/Nico/Santi)",      25_000,  5, "Entretenimiento"),
    ("Gastos Bancarios (promedio)",       25_000,  1, "Otros egresos"),
]

sv_count = 0
for desc, monto, dia, cat in SERVICIOS_FIJOS:
    if monto > 0:
        dbm.registrar_servicio_fijo(cliente_id, desc, float(monto), dia, cat)
        sv_count += 1

print(f"  Servicios fijos registrados: {sv_count}")

# ════════════════════════════════════════════════════════════════════════════
# 4. OBJETIVOS DE INVERSIÓN
# ════════════════════════════════════════════════════════════════════════════
print("\n[4/5] Registrando objetivos de inversión...")

# Limpiar objetivos anteriores del cliente
with dbm.get_session() as s:
    from core.db_manager import ObjetivosInversion
    s.query(ObjetivosInversion).filter(ObjetivosInversion.cliente_id == cliente_id).delete()

OBJETIVOS = [
    # (label, plazo_label, monto_ars, meta_usd, motivo)
    (
        "Corto plazo 🐜",
        "1 año",
        6_894 * CCL_REF * 0.459,   # 46% del patrimonio actual
        15_000,
        "Objetivo corto plazo 2026: alcanzar USD 15,000 de patrimonio invertido",
    ),
    (
        "Medio plazo 🐅",
        "3 años",
        6_894 * CCL_REF * 0.276,
        25_000,
        "Objetivo medio plazo 2030: alcanzar USD 25,000 de patrimonio invertido",
    ),
    (
        "Largo plazo 🐘",
        "+5 años",
        6_894 * CCL_REF * 0.115,
        60_000,
        "Objetivo largo plazo 2035: alcanzar USD 60,000 de patrimonio total",
    ),
]

obj_count = 0
for label, plazo, monto, meta_usd, motivo in OBJETIVOS:
    dbm.registrar_objetivo(
        cliente_id  = cliente_id,
        monto_ars   = round(monto, 0),
        plazo_label = plazo,
        motivo      = f"{motivo} (meta: USD {meta_usd:,})",
        ticker      = "",
    )
    obj_count += 1
    print(f"  Objetivo '{label}' (plazo {plazo}, meta USD {meta_usd:,})")

print(f"  Total objetivos: {obj_count}")

# ════════════════════════════════════════════════════════════════════════════
# 5. POSICIONES ACTIVAS → Maestra_Transaccional.csv
# ════════════════════════════════════════════════════════════════════════════
print("\n[5/5] Importando posiciones activas (CARTERA RETIRO) al CSV...")

RUTA_CSV = ROOT / "0_Data_Maestra" / "Maestra_Transaccional.csv"
CARTERA_NOMBRE = "Alfredo Vallejos | Cartera Retiro"

df_inv = pd.read_excel(xl, sheet_name="Inversiones", header=4)
df_inv.columns = [str(c).strip() for c in df_inv.columns]

# Columnas clave (por posición, tolerante a variaciones de nombre)
col_cartera = df_inv.columns[0]
col_ticker  = df_inv.columns[1]
col_tipo    = df_inv.columns[3]
col_fecha   = df_inv.columns[4]
col_estado  = df_inv.columns[5]
col_unidades= df_inv.columns[8]
col_precio_ars = df_inv.columns[9]
col_precio_usd = df_inv.columns[10]

compras = df_inv[
    df_inv[col_estado].astype(str).str.upper().str.contains("COMPRA", na=False)
].copy()

# Leer CSV actual
with open(RUTA_CSV, encoding="utf-8") as f:
    reader = csv.reader(f)
    filas_orig = list(reader)

header = filas_orig[0] if filas_orig else ["CARTERA","FECHA_COMPRA","TICKER","CANTIDAD","PPC_USD","PPC_ARS","TIPO"]

# Eliminar filas anteriores de esta cartera
filas_limpias = [header] + [
    r for r in filas_orig[1:] if r and r[0] != CARTERA_NOMBRE
]

nuevas_filas = []
for _, row in compras.iterrows():
    ticker   = str(row[col_ticker]).strip().upper()
    tipo_raw = str(row[col_tipo]).strip()
    tipo_inst = "CEDEAR" if "cedear" in tipo_raw.lower() else (
                "ACCION_LOCAL" if "accion" in tipo_raw.lower() or "acción" in tipo_raw.lower() else "CEDEAR")

    try:
        fecha_raw = row[col_fecha]
        if hasattr(fecha_raw, "date"):
            fecha_str = fecha_raw.date().strftime("%Y-%m-%d")
        else:
            fecha_str = str(fecha_raw)[:10]
    except Exception:
        fecha_str = "2026-01-01"

    try:
        cantidad = int(float(row[col_unidades]))
    except Exception:
        continue

    try:
        precio_ars = float(row[col_precio_ars])
        precio_usd = float(row[col_precio_usd])
    except Exception:
        continue

    if cantidad <= 0 or precio_ars <= 0:
        continue

    # PPC_USD correcto para CEDEAR = US_price / ratio²
    from config import RATIOS_CEDEAR
    ratio = RATIOS_CEDEAR.get(ticker, 1.0)
    # precio_usd en la planilla = precio del subyacente en USD
    ppc_usd_cedear = round(precio_usd / (ratio * ratio), 6) if ratio > 1 else precio_usd

    nuevas_filas.append([
        CARTERA_NOMBRE, fecha_str, ticker, cantidad,
        round(ppc_usd_cedear, 6), round(precio_ars, 2), tipo_inst
    ])
    print(f"  + {ticker:6s} {cantidad:4d}u  @ARS {precio_ars:,.0f}  (usd {precio_usd:.2f}, ratio={ratio})")

todas = filas_limpias + nuevas_filas
with open(RUTA_CSV, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(todas)

print(f"\n  Posiciones importadas al CSV: {len(nuevas_filas)}")
print(f"  Total filas en CSV: {len(todas) - 1}")

# ════════════════════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ════════════════════════════════════════════════════════════════════════════
print()
print("=" * 70)
print("  ETL COMPLETADO")
print("=" * 70)
print(f"  Cliente ID       : {cliente_id}")
print("  Nombre           : Alfredo Vallejos")
print(f"  Transacciones DSS: {tx_importadas}")
print(f"  Servicios fijos  : {sv_count}")
print(f"  Objetivos        : {obj_count}")
print(f"  Posiciones CSV   : {len(nuevas_filas)}")
print()
resumen = dbm.obtener_resumen_mes(cliente_id, 1, 2026)
print("  Resumen Enero 2026:")
print(f"    Ingresos       : ARS {resumen['ingresos']:>14,.0f}")
print(f"    Total egresos  : ARS {resumen['total_egresos']:>14,.0f}")
print(f"    Liquidez libre : ARS {resumen['liquidez_libre']:>14,.0f}  {resumen['semaforo']}")
print("=" * 70)
