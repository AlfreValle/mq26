"""
core/renta_fija_catalogo.py — catálogo de instrumentos de renta fija AR (datos puros).

Extraído de core/renta_fija_ar.py (Fase 2.1): solo datos y su merge de extras
(P2-RF-05). La lógica (TIR, fichas, selección por perfil) sigue en
renta_fija_ar, que re-exporta estos nombres para compatibilidad total.

Mantenimiento: skill actualizar-datos-referencia (paridad_ref/tir_ref/fecha_ref).
"""
from __future__ import annotations

from typing import Any

# Base nominal (USD) respecto a la cual se interpreta la paridad % en ON dólar cable.
# Coincide con la cotización típica "por cada 100 nominales" en ARS.
ON_USD_PARIDAD_BASE_VN = 100.0

# BONCER/BOPREAL/DUAL/USD_LINKED: familias panel BYMA (ver core/rf_panel_taxonomy.py).
TIPOS_RF = frozenset({
    "ON", "ON_USD", "BONO", "BONO_USD", "LETRA", "LECAP", "LEDE",
    "BONCER", "BOPREAL", "DUAL", "USD_LINKED", "CAUCION",
})

INSTRUMENTOS_RF: dict[str, dict[str, Any]] = {

    # ══════════════════════════════════════════════════════════════════════════
    # OBLIGACIONES NEGOCIABLES en USD (ON_USD) — Hard Dollar / Cable
    # Convención: paridad_ref = % de VN USD; precio ARS/100VN ≈ paridad × CCL
    # CCL referencia: AR$ 1.511,27 (2026-06-18). Paridades de precio ARS live (data912)
    # / CCL; tir_ref = YTM por DCF con interés corrido (validado vs DNC7O 7.76≈7.73).
    # RUCDO actualizado con IOL 2026-06-22 (con volumen). MGCEO sin actualizar (IOL stale,
    # 0 volumen). MRCAO/YCA6O siguen activas (vencen 01/07 — las flaggea el monitor).
    # MGCHO/RCCJO sin dato (no figuran en IOL). MD sin recalcular.
    # DV01 = modified_duration × paridad_ref / 10000  (USD por bp por 100 VN)
    # ══════════════════════════════════════════════════════════════════════════

    "PN43O": {
        "emisor":      "Pan American Energy",
        "descripcion": "PAE ON Clase 3 7.375% 2037",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2037-12-01",
        "cupon_anual":  0.07375,         # 7.375% (cupón fijo, Ley Argentina)
        "frecuencia":   2,
        "calificacion": "AA+", "ley": "Argentina",
        "tir_ref":      6.31,            # YTM DCF 2026-06-18 (rally: paridad 103→108.5)
        "paridad_ref":  108.50,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    163_970.0,  # 108.50 × 1511.27 por 100 VN (data912)
        "modified_duration": 8.20,
        "dv01_por_100vn":    0.0847,
    },
    "YM34O": {
        "emisor":      "YPF S.A.",
        "descripcion": "YPF ON 8.5% 2034",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2034-07-01",
        "cupon_anual":  0.085,           # 8.5% — cupón verificado prospecto
        "frecuencia":   2,
        "calificacion": "AA", "ley": "Nueva York",
        "tir_ref":      6.78,            # YTM DCF 2026-06-18 (paridad 105.5→110.47)
        "paridad_ref":  110.47,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   1, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    166_950.0,  # 110.47 × 1511.27 por 100 VN (data912)
        "modified_duration": 6.00,
        "dv01_por_100vn":    0.0633,
    },
    "TLCTO": {
        "emisor":      "Telecom Argentina",
        "descripcion": "Telecom ON 8.5% VT 20/01/36",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2036-01-20",
        "cupon_anual":  0.085,           # 8.5% nominal anual
        "frecuencia":   2,
        "calificacion": "AA", "ley": "Nueva York",
        "tir_ref":      6.88,            # YTM DCF 2026-06-18 (rally: paridad 102.5→111.16)
        "paridad_ref":  111.16,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   1, "callable": True,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    167_990.0,  # 111.16 × 1511.27 por 100 VN (data912)
        "modified_duration": 7.00,
        "dv01_por_100vn":    0.0718,
    },
    "TSC4O": {
        "emisor":      "TGS (Transportadora Gas del Sur)",
        "descripcion": "TGS ON 6.6% 2035",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2035-05-14",
        "cupon_anual":  0.066,           # 6.6% — por debajo del mercado, cotiza bajo par
        "frecuencia":   2,
        "calificacion": "AA+", "ley": "Nueva York",
        "tir_ref":      5.53,            # YTM DCF 2026-06-18 (rally fuerte: paridad 97.8→107.39)
        "paridad_ref":  107.39,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   10_000, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    162_300.0,  # 107.39 × 1511.27 por 100 VN (data912)
        "modified_duration": 6.80,
        "dv01_por_100vn":    0.0665,
    },
    "IRCPO": {
        "emisor":      "IRSA Inversiones y Representaciones",
        "descripcion": "IRSA ON 8.75% 2035",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2035-02-08",
        "cupon_anual":  0.0875,          # 8.75% — verificado, no 8.5%
        "frecuencia":   2,
        "calificacion": "AA-", "ley": "Nueva York",
        "tir_ref":      7.59,            # YTM DCF 2026-06-18 (cupón 8.75% a paridad 107.19)
        "paridad_ref":  107.19,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   1, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    162_000.0,  # 107.19 × 1511.27 por 100 VN (data912)
        "modified_duration": 6.50,
        "dv01_por_100vn":    0.0692,
    },
    "DNC7O": {
        "emisor":      "Edenor (Distribuidora Norte)",
        "descripcion": "Edenor ON Clase 7 9.75% 2030",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2030-10-25",
        "cupon_anual":  0.0975,          # 9.75% nominal anual — confirmado por usuario
        "frecuencia":   2,               # semestral: abril y octubre
        "calificacion": "A+", "ley": "Nueva York",
        "tir_ref":      7.76,            # YTM DCF 2026-06-18 (≈7.73 previo: paridad estable)
        "paridad_ref":  107.19,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   100, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    161_990.0,  # 107.19 × 1511.27 por 100 VN (data912)
        "modified_duration": 3.64,
        "dv01_por_100vn":    0.0391,
    },
    "YMCXO": {
        "emisor":      "YPF S.A.",
        "descripcion": "YPF ON 9.0% 2031 (Serie YMCX)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2031-06-16",
        "cupon_anual":  0.090,           # 9.0% nominal anual
        "frecuencia":   2,
        "calificacion": "AA", "ley": "Nueva York",
        "tir_ref":      6.13,            # YTM DCF 2026-06-18 (rally fuerte: paridad 103→112.16)
        "paridad_ref":  112.16,
        "fecha_ref":    "2026-06-18",
        "activo": True,
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    169_500.0,  # 112.16 × 1511.27 por 100 VN (data912)
        "modified_duration": 4.00,
        "dv01_por_100vn":    0.0412,
    },
    "RUCDO": {
        "emisor":      "Raghsa S.A.",
        "descripcion": "Raghsa ON 8.5% 2026 (Serie D)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-11-30",
        "cupon_anual":  0.085,
        "frecuencia":   2,
        "calificacion": "A", "ley": "Argentina",
        "tir_ref":      1.81,            # YTM DCF 2026-06-22 (premium a ~5m del vto; IOL con volumen)
        "paridad_ref":  102.89,
        "fecha_ref":    "2026-06-22",
        "activo": True,
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1511.27,
        "precio_ars_ref":    155_500.0,  # 102.89 × 1511.27 por 100 VN (IOL)
        "modified_duration": 0.47,
        "dv01_por_100vn":    0.0048,
    },
    "MGCEO": {
        "emisor":      "MercadoLibre Inc.",
        "descripcion": "MercadoLibre ON 6.375% 2030 (Serie E)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2030-01-14",
        "cupon_anual":  0.06375,         # 6.375% exacto (era 0.0638)
        "frecuencia":   2,
        "calificacion": "BBB+", "ley": "Nueva York",
        "tir_ref":      5.8,             # MELI investment grade, spread ajustado
        "paridad_ref":  102.8,
        # 2026-06-22: IOL muestra $142.000 con monto operado 0 (quote stale, no reflejó
        # el rally). Implicaría paridad 94 / TIR 8.4% — inconsistente para BBB+. Sin actualizar.
        "fecha_ref":    "2026-05-27",
        "activo": True,
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1429.0,
        "precio_ars_ref":    146_901.0,  # 102.8 × 1429 por 100 VN
        "modified_duration": 3.20,
        "dv01_por_100vn":    0.0329,
    },
    "MRCAO": {
        "emisor":      "Mastellone Hermanos S.A.",
        "descripcion": "Mastellone ON 7.5% 2026 (Serie A)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-07-01",
        "cupon_anual":  0.075,
        "frecuencia":   2,
        "calificacion": "A-", "ley": "Argentina",
        "tir_ref":      5.8,             # ~35 días restantes → spread mínimo
        "paridad_ref":  100.8,
        "fecha_ref":    "2026-05-27",
        "activo": True,                  # vence 01/07/2026 — el monitor lo flaggea como crítico
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1429.0,
        "precio_ars_ref":    144_043.0,  # 100.8 × 1429 por 100 VN
        "modified_duration": 0.12,
        "dv01_por_100vn":    0.0012,
    },
    "YCA6O": {
        "emisor":      "YPF S.A.",
        "descripcion": "YPF ON 8.5% 2026 (corta)",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-07-01",
        "cupon_anual":  0.085,
        "frecuencia":   2,
        "calificacion": "AA", "ley": "Nueva York",
        "tir_ref":      5.8,             # ~35 días restantes → precio cercano a par+accrued
        "paridad_ref":  101.0,
        "fecha_ref":    "2026-05-27",
        "activo": True,                  # vence 01/07/2026 — el monitor lo flaggea como crítico
        "lamina_min":   1, "callable": False,
        "ccl_ref":           1429.0,
        "precio_ars_ref":    144_329.0,  # 101.0 × 1429 por 100 VN
        "modified_duration": 0.12,
        "dv01_por_100vn":    0.0012,
    },
    "CSO2O": {
        "emisor":      "Cresud S.A.",
        "descripcion": "Cresud ON 9.0% 2026",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2026-02-08",
        "cupon_anual":  0.090,
        "frecuencia":   2,
        "calificacion": "A+", "ley": "Argentina",
        "tir_ref":      6.5,             # último valor conocido (ref pre-vencimiento)
        "paridad_ref":  100.0,           # al par en el período final
        "fecha_ref":    "2026-02-08",    # fecha de vencimiento = última fecha de referencia
        "activo": False,                 # venció 2026-02-08 → inactiva
        "lamina_min":   1_000, "callable": False,
    },
    "MGCHO": {
        "emisor":      "MercadoLibre Inc.",
        "descripcion": "MercadoLibre ON 6.25% 2028",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2028-01-14",
        "cupon_anual":  0.0625,          # 6.25% nominal anual
        "frecuencia":   2,
        "calificacion": "BBB+", "ley": "Nueva York",
        "tir_ref":      5.6,
        "paridad_ref":  101.8,
        "fecha_ref":    "2026-05-27",
        "activo": True,
        "lamina_min":   1_000, "callable": False,
        "ccl_ref":           1429.0,
        "precio_ars_ref":    145_471.0,  # 101.8 × 1429 por 100 VN
        "modified_duration": 1.90,
        "dv01_por_100vn":    0.0193,
    },
    "RCCJO": {
        "emisor":      "Pampa Energía S.A.",
        "descripcion": "Pampa Energía ON 7.5% 2027",
        "tipo": "ON_USD", "moneda": "USD",
        "vencimiento": "2027-07-21",
        "cupon_anual":  0.075,
        "frecuencia":   2,
        "calificacion": "AA-", "ley": "Nueva York",
        "tir_ref":      6.5,
        "paridad_ref":  102.5,
        "fecha_ref":    "2026-05-27",
        "activo": True,
        "lamina_min":   1, "callable": False,
        "ccl_ref":           1429.0,
        "precio_ars_ref":    146_473.0,  # 102.5 × 1429 por 100 VN
        "modified_duration": 1.00,
        "dv01_por_100vn":    0.0103,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # BONOS SOBERANOS USD — Ley Argentina (AL) y Ley Nueva York (GD)
    # Cupón step-up (ver prospecto reestructuración 2020); cupon_anual = 0.0
    # en el motor de cashflow ilustrativo (flujos reales en calendario oficial).
    # TIR, paridad y MD actualizados al 2026-06-18 (informe diario Banco Hipotecario,
    # CCL AR$ 1.511,27; cruzado con informe Banco Provincia 19-jun-26). MD = Duration Modificada.
    # ══════════════════════════════════════════════════════════════════════════

    "GD29": {
        "emisor": "República Argentina", "descripcion": "Global 2029",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2029-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,   # step-up; ver prospecto 2020
        "calificacion": "CCC", "ley": "Nueva York",
        "tir_ref":   5.41,  "paridad_ref":  93.70,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 1.46,
    },
    "AL29": {
        "emisor": "República Argentina", "descripcion": "Bonar 2029",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2029-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   6.78,  "paridad_ref":  91.91,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 1.44,
    },
    "GD30": {
        "emisor": "República Argentina", "descripcion": "Global 2030",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2030-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York",
        "tir_ref":   6.25,  "paridad_ref":  90.95,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 1.90,
    },
    "AL30": {
        "emisor": "República Argentina", "descripcion": "Bonar 2030",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2030-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   7.37,  "paridad_ref":  89.12,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 1.87,
    },
    "GD35": {
        "emisor": "República Argentina", "descripcion": "Global 2035",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2035-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York",
        "tir_ref":   8.45,  "paridad_ref":  82.54,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 5.38,
    },
    "AL35": {
        "emisor": "República Argentina", "descripcion": "Bonar 2035",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2035-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   9.12,  "paridad_ref":  79.74,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 5.33,
    },
    "AE38": {
        "emisor": "República Argentina", "descripcion": "Bonar 2038",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2038-01-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   9.85,  "paridad_ref":  80.12,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 4.53,
    },
    "GD41": {
        "emisor": "República Argentina", "descripcion": "Global 2041",
        "tipo": "BONO_USD", "moneda": "USD",
        "vencimiento": "2041-07-09",
        "cupon_anual": 0.0, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Nueva York",
        "tir_ref":   8.57,  "paridad_ref":  77.20,
        "fecha_ref": "2026-06-18", "activo": True,
        "modified_duration": 5.96,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # BOPREAL — Bono para la Reconstrucción de una Argentina Libre (BCRA)
    # ══════════════════════════════════════════════════════════════════════════

    "BPA27": {
        "emisor": "BCRA",
        "descripcion": "BOPREAL Serie 1-A 2027",
        "tipo": "BOPREAL", "moneda": "USD",
        "vencimiento": "2027-01-31",
        "cupon_anual": 0.05, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   6.5,   "paridad_ref":  98.2,
        # 2026-06-22: ticker BPA27 no cotiza en IOL. BOPREAL vigentes 2027 = BPOA7/BPOB7/
        # BPOC7/BPOD7 (ver task reconciliación). Inactivo hasta re-mapear con cupón/ISIN.
        "fecha_ref": "2026-05-27", "activo": False,
        "lamina_min": 1,
        "forma_amortizacion": "Bullet al vencimiento",
        "modified_duration": 0.65,
    },
    "BPJ27": {
        "emisor": "BCRA",
        "descripcion": "BOPREAL Serie 3 2027",
        "tipo": "BOPREAL", "moneda": "USD",
        "vencimiento": "2027-05-31",
        "cupon_anual": 0.03, "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":   7.5,   "paridad_ref":  95.5,
        # 2026-06-22: ticker BPJ27 no cotiza en IOL (ver BPA27). Inactivo hasta re-mapear.
        "fecha_ref": "2026-05-27", "activo": False,
        "lamina_min": 1,
        "forma_amortizacion": "Bullet al vencimiento",
        "modified_duration": 0.95,
    },

    # ══════════════════════════════════════════════════════════════════════════
    # BONCER — Bonos ajustables por CER (inflación AR)
    # cupon_anual = spread_real sobre CER; tir_ref = TIR real anual en %
    # duration_real = años (nominal sobre flujos reales)
    # ══════════════════════════════════════════════════════════════════════════

    "TX26": {
        "emisor": "Tesoro Nacional",
        "descripcion": "Bonte CER+2% Nov 2026 (TX26)",
        "tipo": "BONCER", "moneda": "ARS_CER",
        "vencimiento": "2026-11-09",     # ISIN ARARGE3209W8 (informe BP) — no 30/06
        "cupon_anual": 0.02,             # CER + 2% (informe BP "Bonte 2026 CER+2%")
        "frecuencia": 2,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref":    0.47,  "paridad_ref": 100.59,  # informe Banco Hipotecario 2026-06-18 (TIR real)
        "fecha_ref":  "2026-06-18", "activo": True,
        "lamina_min":    1,
        "spread_real":   0.02,
        "duration_real": 0.39,          # MD informe (≈143 días al vto)
    },
    "TX28": {
        "emisor": "Tesoro Nacional",
        "descripcion": "Bonte CER+2.25% Nov 2028 (TX28)",
        "tipo": "BONCER", "moneda": "ARS_CER",
        "vencimiento": "2028-11-09",     # ISIN ARARGE3209X6 (informe BP)
        "cupon_anual": 0.0225,           # CER + 2.25% (informe BP)
        "frecuencia": 2,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref":    5.41,  "paridad_ref": 95.95,  # informe Banco Hipotecario 2026-06-18 (TIR real)
        "fecha_ref":  "2026-06-18", "activo": True,
        "lamina_min":    1,
        "spread_real":   0.0225,
        "duration_real": 1.32,          # MD informe
    },
    "TZXD7": {
        "emisor": "Tesoro Nacional",
        "descripcion": "Boncer Dic 2027 (TZXD7)",
        "tipo": "BONCER", "moneda": "ARS_CER",
        "vencimiento": "2027-12-15",     # informe BH/BP — no 31/12
        "cupon_anual": 0.005,            # CER + 0.5% (sin fuente nueva — sin cambiar)
        "frecuencia": 2,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref":    5.43,  "paridad_ref": 92.42,  # informe Banco Hipotecario 2026-06-18 (TIR real)
        "fecha_ref":  "2026-06-18", "activo": True,
        "lamina_min":    1,
        "spread_real":   0.005,
        "duration_real": 1.45,          # MD informe
    },
    "DICP": {
        "emisor": "República Argentina",
        "descripcion": "Discount Peso CER 2033 (DICP)",
        "tipo": "BONCER", "moneda": "ARS_CER",
        "vencimiento": "2033-12-31",
        "cupon_anual": 0.08,             # CER + 8% real (bono legacy reestructuración)
        "frecuencia": 2,
        "calificacion": "CCC", "ley": "Argentina",
        "tir_ref":    7.49,  "paridad_ref": 95.34,  # informe Banco Hipotecario 2026-06-18 (TIR real)
        "fecha_ref":  "2026-06-18", "activo": True,
        "lamina_min":    1,
        "spread_real":   0.08,
        "duration_real": 3.05,
        "forma_amortizacion": "Amortización trimestral sobre VN ajustado por CER",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # LECAP / LEDE — Letras del Tesoro Nacional en ARS
    # S17A6, S30A6, S15Y6: VENCIDAS (activo: False) — ref histórica
    # S30J6, S29L6: vigentes al 2026-05-27
    # tir_ref = TNA % (tasa nominal anual de descuento)
    # ══════════════════════════════════════════════════════════════════════════

    "S17A6": {
        "emisor": "Ministerio de Economía AR", "descripcion": "LEDE 17/04/2026",
        "tipo": "LETRA", "moneda": "ARS",
        "vencimiento": "2026-04-17",
        "cupon_anual": 0.0, "frecuencia": 0,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref": 24.59, "paridad_ref": 97.8,
        "fecha_ref": "2026-04-01",
        "activo": False,                 # VENCIDA — 17/04/2026
    },
    "S30A6": {
        "emisor": "Ministerio de Economía AR", "descripcion": "LEDE 30/04/2026",
        "tipo": "LETRA", "moneda": "ARS",
        "vencimiento": "2026-04-30",
        "cupon_anual": 0.0, "frecuencia": 0,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref": 25.3, "paridad_ref": 97.2,
        "fecha_ref": "2026-04-01",
        "activo": False,                 # VENCIDA — 30/04/2026
    },
    "S15Y6": {
        "emisor": "Ministerio de Economía AR", "descripcion": "LEDE 15/05/2026",
        "tipo": "LETRA", "moneda": "ARS",
        "vencimiento": "2026-05-15",
        "cupon_anual": 0.0, "frecuencia": 0,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref": 25.6, "paridad_ref": 95.8,
        "fecha_ref": "2026-04-01",
        "activo": False,                 # VENCIDA — 15/05/2026
    },
    "S30J6": {
        "emisor": "Ministerio de Economía AR",
        "descripcion": "LECAP 30/06/2026",
        "tipo": "LETRA", "moneda": "ARS",   # LETRA es el tipo genérico; LECAP es subtipo
        "vencimiento": "2026-06-30",
        "cupon_anual": 0.0, "frecuencia": 0,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref":    29.5,              # TNA efectiva jun-26 (capitalización mensual)
        "paridad_ref": 96.8,
        "fecha_ref":  "2026-05-27", "activo": True,
        "lamina_min": 1,
        "forma_amortizacion": "Pago único al vencimiento (LECAP — capitaliza tasa mensual)",
    },
    "S29L6": {
        "emisor": "Ministerio de Economía AR",
        "descripcion": "LECAP 29/07/2026",
        "tipo": "LETRA", "moneda": "ARS",   # LETRA es el tipo genérico; LECAP es subtipo
        "vencimiento": "2026-07-29",
        "cupon_anual": 0.0, "frecuencia": 0,
        "calificacion": "AA-AR", "ley": "Argentina",
        "tir_ref":    29.0,              # TNA efectiva jul-26
        "paridad_ref": 94.8,
        "fecha_ref":  "2026-05-27", "activo": True,
        "lamina_min": 1,
        "forma_amortizacion": "Pago único al vencimiento (LECAP — capitaliza tasa mensual)",
    },
}

# P2-RF-05: campos opcionales por instrumento — `isin`, `lamina_min` / `denominacion_min`, `forma_amortizacion`.
# ISIN solo donde hay referencia pública estable; el resto queda ausente (UI muestra "—").
# Fuentes típicas: prospecto, página emisor, BYMA / agente de custodia.
_EXTRAS_CATALOGO_P2_RF5: dict[str, dict[str, Any]] = {
    # ── Bonos soberanos ─────────────────────────────────────────────────────
    "AL30": {
        "isin": "ARARGE3209S6",
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; amortización programada (ver prospecto reestructuración 2020)",
    },
    "GD30": {
        "isin": "US040114HS26",
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; amortización en cuotas (ver prospecto reestructuración 2020)",
    },
    "AE38": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; ver calendario oficial prospecto 2020",
    },
    "GD35": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; ver prospecto reestructuración 2020",
    },
    "AL35": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; ver prospecto reestructuración 2020",
    },
    "GD41": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; ver prospecto reestructuración 2020",
    },
    "GD29": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; amortización en cuotas (ver prospecto 2020)",
    },
    "AL29": {
        "lamina_min": 1,
        "forma_amortizacion": "Step-up cupón semestral; ver prospecto reestructuración 2020",
    },
    # ── ON USD corporativas ─────────────────────────────────────────────────
    "PN43O": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales (jun/dic); principal bullet al vencimiento",
    },
    "YM34O": {
        "lamina_min": 1,
        "forma_amortizacion": "Cupones semestrales (ene/jul); principal bullet al vencimiento",
    },
    "TLCTO": {
        "lamina_min": 1,
        "forma_amortizacion": "Cupones semestrales (ene/jul); principal bullet al vencimiento; callable",
    },
    "TSC4O": {
        "lamina_min": 10_000,
        "forma_amortizacion": "Cupones semestrales (may/nov); principal bullet al vencimiento",
    },
    "IRCPO": {
        "lamina_min": 1,
        "forma_amortizacion": "Cupones semestrales (feb/ago); principal bullet al vencimiento",
    },
    "DNC7O": {
        "lamina_min": 100,
        "forma_amortizacion": "Cupones semestrales (abr/oct); principal bullet al vencimiento",
    },
    "YMCXO": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales (jun/dic); principal bullet al vencimiento",
    },
    "RUCDO": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales; principal bullet al vencimiento (nov-2026)",
    },
    "MGCEO": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales (ene/jul); principal bullet al vencimiento",
    },
    "MRCAO": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales; principal bullet al vencimiento (jul-2026)",
    },
    "YCA6O": {
        "lamina_min": 1,
        "forma_amortizacion": "Cupón semestral; principal bullet al vencimiento (jul-2026)",
    },
    "MGCHO": {
        "lamina_min": 1_000,
        "forma_amortizacion": "Cupones semestrales (ene/jul); principal bullet al vencimiento",
    },
    "RCCJO": {
        "lamina_min": 1,
        "forma_amortizacion": "Cupones semestrales (ene/jul); principal bullet al vencimiento",
    },
    # ── Letras ─────────────────────────────────────────────────────────────
    "S17A6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (LEDE descuento) — VENCIDA"},
    "S30A6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (LEDE descuento) — VENCIDA"},
    "S15Y6": {"lamina_min": 1, "forma_amortizacion": "Pago único al vencimiento (LEDE descuento) — VENCIDA"},
    "S30J6": {"lamina_min": 1},  # forma_amortizacion ya en instrumento principal
    "S29L6": {"lamina_min": 1},
}

for _tk, _add in _EXTRAS_CATALOGO_P2_RF5.items():
    if _tk in INSTRUMENTOS_RF:
        INSTRUMENTOS_RF[_tk].update(_add)

