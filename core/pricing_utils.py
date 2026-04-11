"""
core/pricing_utils.py — Utilidades de precios, ratios y CCL (fuente única de verdad)
MQ26-DSS | Funciones puras sin side effects ni dependencias de UI.

Centraliza la lógica que antes estaba duplicada en:
  - libro_mayor.parsear_ppc_usd
  - data_engine.limpiar_ppc / parse_ratio
  - gmail_reader.limpiar_ars / ars_to_usd / RATIOS
  - broker_importer.limpiar_precio_ars / precio_ars_to_ppc_usd / RATIOS_CONOCIDOS
"""
import math
import re
import sys
from pathlib import Path

# Importar configuración de ratios y sectores desde config raíz
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import RATIOS_CEDEAR, SECTORES

# ─── CCL HISTÓRICO ESTIMADO POR MES ───────────────────────────────────────────
# Actualizar cuando llegue el resumen mensual de Balanz.
# Fuente: rava.com / ambito.com / BCRA
CCL_HISTORICO: dict[str, float] = {
    # ── 2021 ──────────────────────────────────────────────────────────────────
    "2021-01": 160, "2021-02": 163, "2021-03": 146, "2021-04": 150,
    "2021-05": 162, "2021-06": 168, "2021-07": 170, "2021-08": 172,
    "2021-09": 180, "2021-10": 187, "2021-11": 195, "2021-12": 198,
    # ── 2022 ──────────────────────────────────────────────────────────────────
    "2022-01": 200, "2022-02": 208, "2022-03": 215, "2022-04": 222,
    "2022-05": 232, "2022-06": 237, "2022-07": 255, "2022-08": 282,
    "2022-09": 298, "2022-10": 308, "2022-11": 318, "2022-12": 336,
    # ── 2023 ──────────────────────────────────────────────────────────────────
    "2023-01": 358, "2023-02": 380, "2023-03": 398, "2023-04": 422,
    "2023-05": 472, "2023-06": 495, "2023-07": 548, "2023-08": 658,
    "2023-09": 760, "2023-10": 825, "2023-11": 900, "2023-12": 950,
    # ── 2024 ──────────────────────────────────────────────────────────────────
    "2024-01": 980,  "2024-02": 1000, "2024-03": 1020, "2024-04": 1050,
    "2024-05": 1100, "2024-06": 1130, "2024-07": 1150, "2024-08": 1160,
    "2024-09": 1170, "2024-10": 1170, "2024-11": 1170, "2024-12": 1180,
    # ── 2025 ──────────────────────────────────────────────────────────────────
    "2025-01": 1180, "2025-02": 1180, "2025-03": 1180, "2025-04": 1180,
    "2025-05": 1195, "2025-06": 1220, "2025-07": 1250, "2025-08": 1290,
    "2025-09": 1320, "2025-10": 1345, "2025-11": 1375, "2025-12": 1400,
    # ── 2026 ──────────────────────────────────────────────────────────────────
    "2026-01": 1420, "2026-02": 1450, "2026-03": 1465,
}

# ─── CLASIFICACIÓN DE INSTRUMENTOS BYMA ──────────────────────────────────────
# Todos los instrumentos en este bloque se cotizan directamente en ARS en BYMA.
# Para ellos: INV_ARS = CANTIDAD × PPC_ARS (sin CCL, sin ratio).

# Acciones del panel general BYMA
ACCIONES_LOCALES: set[str] = {
    "CEPU", "TGNO4", "YPFD", "PAMP", "ECOG", "GGAL", "BMA",
    "MIRG", "LOMA", "AGRO", "SAMI", "TXAR", "ALUA", "BYMA",
    "CRES", "IRSA", "MOLI", "SUPV", "TECO2", "CARC", "BOLT",
    "COME", "HAVA", "LONG", "FERR", "VALO", "INTR", "GARO",
    "GCDI", "INVJ", "DGCU2", "EDN", "METR", "GBAN",
}

# Tipos de instrumento que se cotizan en ARS sin conversión USD
TIPOS_LOCALES_ARS: set[str] = {
    "ACCION_LOCAL", "ACCION", "BONO", "BONO_ARS", "BONO_USD",
    "LETRA", "LETE", "LEDES", "LECAP", "LECER", "LEDE",
    "FCI", "CUOTA_PARTE", "ON", "ON_ARS", "ON_USD",
    "BONO_CORP", "FIDEICOMISO", "CHEQUE", "CAUCIONES",
}

# Renta fija local: convención BYMA suele ser precio por lámina de nominal (p. ej. 100 o 1.000 VN).
# Para que la barra Progreso sea correcta, PPC y cotización deben estar en la misma unidad
# (misma lámina y mismo tipo de nominal). Acciones locales y CEDEARs cotizan en ARS por unidad
# negociada; CEDEARs llevan ratio al subyacente solo como referencia, no para el progreso en pesos.
TIPOS_RENTA_FIJA_LOCAL: set[str] = {
    "BONO", "BONO_ARS", "BONO_USD", "LETRA", "LETE", "LEDES", "LECAP", "LECER", "LEDE",
    "BONO_CORP", "ON", "ON_ARS", "ON_USD",
}


def es_renta_fija_local(tipo: str) -> bool:
    """True si el instrumento es bono/letra/ON negociada en BYMA (reglas de lámina / nominal)."""
    return str(tipo).upper().strip() in TIPOS_RENTA_FIJA_LOCAL


def lamina_vn_es_valida(val) -> bool:
    """True si LAMINA_VN es un nominal por lámina coherente (> 0), p. ej. 100 o 1000."""
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return False
        return float(val) > 0
    except (TypeError, ValueError):
        return False


def mensaje_validacion_lamina(ticker: str, tipo: str, lamina_vn) -> str | None:
    """
    Si es renta fija y falta lámina, devuelve texto de advertencia para logs/UI.
    None si no aplica o si está bien cargada.
    """
    if not es_renta_fija_local(tipo or ""):
        return None
    if lamina_vn_es_valida(lamina_vn):
        return None
    return (
        f"Renta fija {ticker} (tipo={tipo}): falta LAMINA_VN (>0). "
        "Usá la misma convención que BYMA (precio por 100/1000 VN) para PPC y cotización."
    )

# Prefijos típicos de bonos soberanos y provinciales argentinos
_PREFIJOS_BONOS = (
    "AL", "GD", "AE", "TX", "PAR", "DISC", "AA", "A2E",
    "PBA", "BPBA", "BPCO", "BONAR", "PMY", "PR1",
)
# Prefijos de letras del tesoro
_PREFIJOS_LETRAS = ("S", "LEDES", "LECAP", "LECER", "LEDE", "X")


def es_instrumento_local_ars(ticker: str, tipo: str = "") -> bool:
    """
    Retorna True si el instrumento se cotiza directamente en ARS en BYMA.
    No aplica CCL ni ratio para estos activos.

    Criterios (en orden de prioridad):
    1. TIPO declarado en la transacción (más confiable).
    2. Ticker en ACCIONES_LOCALES.
    3. Patrón de ticker que corresponde a bono/letra argentino.
    """
    t = str(ticker).upper().strip()
    tp = str(tipo).upper().strip()

    # 1. Por tipo de instrumento
    if tp in TIPOS_LOCALES_ARS:
        return True

    # 2. Acciones locales conocidas
    if t in ACCIONES_LOCALES:
        return True

    # 3. Bonos soberanos (ej: AL30, GD30, AE38, TX25, PAR, DISC, AA17)
    if any(t.startswith(p) for p in _PREFIJOS_BONOS):
        # Descartar si está en RATIOS_CEDEAR (podría haber colisión de nombres)
        if t not in RATIOS_CEDEAR:
            return True

    # 4. Letras del tesoro: Snnnnn (ej: S31E5, S14F5, X18F5)
    #    Patrón: 1 letra + dígito(s) + 2 letras + dígito (código ROFEX/BYMA)
    import re as _re
    if _re.match(r'^[SX]\d{2}[A-Z]\d[A-Z0-9]*$', t):
        return True

    return False


# ─── PARSEO DE PRECIOS ────────────────────────────────────────────────────────

def parsear_ppc_usd(valor) -> float:
    """
    Convierte cualquier representación de PPC a float en USD.
    Formatos soportados: "usd 1,60" | "$34,58" | "1.60" | 34.58 | "1.234,56"
    Resultado siempre en USD por nominal de CEDEAR.
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return 0.0 if math.isnan(float(valor)) else float(valor)
    v = re.sub(r'[usd$u\$s\s]', '', str(valor).strip(), flags=re.IGNORECASE)
    if ',' in v and '.' in v:
        v = v.replace('.', '').replace(',', '.')
    elif ',' in v:
        v = v.replace(',', '.')
    try:
        return float(v)
    except ValueError:
        return 0.0


def parsear_precio_ars(valor) -> float:
    """
    Convierte un precio en ARS en cualquier formato a float.
    Soporta: '$49.180,00' | '49180.00' | 49180 | '49,180.00'
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return 0.0 if math.isnan(float(valor)) else float(valor)
    v = re.sub(r'[\$\s]', '', str(valor).strip())
    if ',' in v and '.' in v:
        # Formato argentino: "49.180,00" → punto=miles, coma=decimal
        if v.index('.') < v.index(','):
            v = v.replace('.', '').replace(',', '.')
        else:
            v = v.replace(',', '')
    elif ',' in v:
        # "49180,00" o "49,180" → determinar si es decimal o miles
        partes = v.split(',')
        if len(partes) == 2 and len(partes[1]) <= 2:
            v = v.replace(',', '.')
        else:
            v = v.replace(',', '')
    try:
        return float(v)
    except ValueError:
        return 0.0


def parsear_ratio(valor) -> float:
    """
    Parsea el ratio de un CEDEAR desde distintos formatos: '20', '20:1', 20.0
    Devuelve 1.0 si no puede parsear.
    """
    try:
        return float(str(valor).split(':')[0].strip())
    except (ValueError, AttributeError):
        return 1.0


# ─── CONVERSIONES CEDEAR ─────────────────────────────────────────────────────

def obtener_ratio(ticker: str, universo_df=None) -> float:
    """
    Obtiene el ratio CEDEAR para el ticker dado.
    Orden: universo_df (Excel), con corrección si el Excel trae 1 y config trae ratio BYMA > 1;
    si no hay fila, RATIOS_CEDEAR de config; 1.0 por defecto.
    """
    t = ticker.upper().strip()
    cfg = float(RATIOS_CEDEAR.get(t, 1.0))
    if universo_df is not None and not universo_df.empty:
        col_t = "Ticker" if "Ticker" in universo_df.columns else None
        if col_t:
            row = universo_df[universo_df[col_t].astype(str).str.strip().str.upper() == t]
            if not row.empty and "Ratio" in row.columns:
                r = parsear_ratio(row["Ratio"].iloc[0])
                if r > 0:
                    if r == 1.0 and cfg > 1.0:
                        return cfg
                    return r
    return cfg


def precio_cedear_ars(subyacente_usd: float, ratio: float, ccl: float) -> float:
    """
    Calcula el precio teórico del CEDEAR en ARS.
    precio_CEDEAR_ARS = (subyacente_USD / ratio) * CCL
    """
    if ratio <= 0 or ccl <= 0 or subyacente_usd <= 0:
        return 0.0
    return round((subyacente_usd / ratio) * ccl, 2)


def subyacente_usd_desde_cedear(precio_cedear_ars: float, ratio: float, ccl: float) -> float:
    """
    Recupera el precio del subyacente en USD desde el precio ARS del CEDEAR.
    subyacente_USD = precio_CEDEAR_ARS * ratio / CCL
    Inversa exacta de precio_cedear_ars().
    """
    if ccl <= 0 or precio_cedear_ars <= 0:
        return 0.0
    return round(precio_cedear_ars * ratio / ccl, 4)


def ppc_usd_desde_precio_ars(precio_ars: float, ticker: str, ccl: float) -> float:
    """
    Convierte un precio por CEDEAR en ARS a PPC en USD.
    PPC_USD = precio_ARS / (ccl * ratio)
    Para acciones locales: PPC_USD = precio_ARS / ccl
    """
    if ccl <= 0 or precio_ars <= 0:
        return 0.0
    ratio = float(RATIOS_CEDEAR.get(ticker.upper(), 1.0))
    return round(precio_ars / (ccl * ratio), 4)


# ─── CCL HISTÓRICO ────────────────────────────────────────────────────────────

def ccl_historico_por_fecha(fecha_str: str, fallback: float | None = None) -> float:
    """
    Retorna el CCL estimado para un mes dado (formato 'AAAA-MM' o 'AAAA-MM-DD').
    Si el mes no está en el historial, usa el último CCL con mes <= al pedido.
    Si el mes es **posterior** al último dato del dict: con ``fallback`` explícito devuelve
    ese valor; sin fallback, el último CCL publicado (no extrapola meses futuros).
    """
    key = str(fecha_str)[:7]
    if key in CCL_HISTORICO:
        return float(CCL_HISTORICO[key])

    keys_sorted = sorted(CCL_HISTORICO.keys())
    if not keys_sorted:
        raise ValueError("CCL_HISTORICO vacío")

    last_known = keys_sorted[-1]
    # Mes posterior al último dato publicado: no extrapolar; fallback explícito o último CCL.
    if key > last_known:
        if fallback is not None:
            return float(fallback)
        return float(CCL_HISTORICO[last_known])

    # Evita look-ahead: usa el último CCL conocido <= fecha solicitada.
    prev_keys = [k for k in keys_sorted if k <= key]
    if prev_keys:
        return float(CCL_HISTORICO[prev_keys[-1]])

    _default = fallback if fallback is not None else float(CCL_HISTORICO[keys_sorted[0]])
    return float(_default)


# ─── SECTORES ─────────────────────────────────────────────────────────────────

def asignar_sector(ticker: str) -> str:
    """Devuelve el sector del ticker. Fuente: config.SECTORES."""
    return SECTORES.get(ticker.upper(), "Otros")


def es_accion_local(ticker: str) -> bool:
    """Devuelve True si el ticker es una acción local argentina (no CEDEAR)."""
    return ticker.upper() in ACCIONES_LOCALES
