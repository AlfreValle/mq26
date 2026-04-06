# ═══════════════════════════════════════════════════════════════════════
# Archivo: core/diagnostico_types.py
# Tipos compartidos entre diagnostico_cartera.py y recomendacion_capital.py
# SIN imports de streamlit. SIN imports de yfinance.
# ═══════════════════════════════════════════════════════════════════════
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Enums de dominio ──────────────────────────────────────────────────────────


class Semaforo(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"


class PrioridadAccion(str, Enum):
    CRITICA = "critica"
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"
    NINGUNA = "ninguna"


class CategoriaActivo(str, Enum):
    ANCLA_DURA = "ancla_dura"
    CUASI_DEFENSIVO = "cuasi_defensivo"
    RENTA_FIJA_AR = "renta_fija_ar"
    GROWTH_QUALITY = "growth_quality"
    GROWTH_AGRESIVO = "growth_agresivo"
    LATAM = "latam"
    ETF_MERCADO = "etf_mercado"
    OTRO = "otro"


def semaforo_desde_score(score_total: float) -> Semaforo:
    """Deriva semáforo: ≥80 verde, ≥60 amarillo, si no rojo."""
    if score_total >= 80.0:
        return Semaforo.VERDE
    if score_total >= 60.0:
        return Semaforo.AMARILLO
    return Semaforo.ROJO


def perfil_motor_salida(perfil: str) -> str:
    """
    Traduce etiquetas de BD/UI al perfil esperado por motor_salida.OBJETIVOS_PERFIL.
    """
    key = (perfil or "").strip()
    return {"Arriesgado": "Agresivo", "Muy arriesgado": "Agresivo"}.get(key, key)


def perfil_diagnostico_valido(perfil: str) -> str:
    """Fallback Moderado si el perfil no está en tablas S5."""
    p = (perfil or "").strip()
    if p in PISO_DEFENSIVO:
        return p
    return "Moderado"


# ── Observación individual del diagnóstico ───────────────────────────────────


@dataclass
class ObservacionDiagnostico:
    dimension: str
    icono: str
    titulo: str
    texto_corto: str
    cifra_clave: str
    accion_sugerida: str
    prioridad: PrioridadAccion
    score_dimension: float


# ── Resultado del diagnóstico completo ───────────────────────────────────────


@dataclass
class DiagnosticoResult:
    cliente_nombre: str
    perfil: str
    horizonte_label: str
    fecha_diagnostico: str

    score_total: float
    semaforo: Semaforo

    score_cobertura_defensiva: float
    score_concentracion: float
    score_rendimiento: float
    score_senales_salida: float

    observaciones: list[ObservacionDiagnostico] = field(default_factory=list)

    pct_defensivo_actual: float = 0.0
    pct_defensivo_requerido: float = 0.0
    deficit_defensivo_usd: float = 0.0
    activo_mas_concentrado: str = ""
    pct_concentracion_max: float = 0.0
    rendimiento_ytd_usd_pct: float = 0.0
    benchmark_ytd_pct: float = 0.0
    n_senales_salida_altas: int = 0
    n_senales_salida_medias: int = 0

    titulo_semaforo: str = ""
    resumen_ejecutivo: str = ""

    valor_cartera_usd: float = 0.0
    n_posiciones: int = 0
    modo_fallback: bool = False


# ── Ítem individual de recomendación ────────────────────────────────────────


@dataclass
class ItemRecomendacion:
    orden: int
    ticker: str
    nombre_legible: str
    categoria: CategoriaActivo
    unidades: int
    precio_ars_estimado: float
    monto_ars: float
    monto_usd: float
    justificacion: str
    impacto_en_balance: str
    prioridad: PrioridadAccion
    es_activo_nuevo: bool


# ── Resultado de la recomendación completa ───────────────────────────────────


@dataclass
class RecomendacionResult:
    cliente_nombre: str
    perfil: str
    capital_disponible_ars: float
    capital_disponible_usd: float
    ccl: float
    fecha_recomendacion: str

    compras_recomendadas: list[ItemRecomendacion] = field(default_factory=list)
    pendientes_proxima_inyeccion: list[dict] = field(default_factory=list)

    capital_usado_ars: float = 0.0
    capital_remanente_ars: float = 0.0
    n_compras: int = 0

    pct_defensivo_post: float = 0.0
    pct_defensivo_pre: float = 0.0
    delta_balance: str = ""

    alerta_mercado: bool = False
    mensaje_alerta: str = ""

    resumen_recomendacion: str = ""


# ── Clasificación de activos por categoría ──────────────────────────────────

CLASIFICACION_ACTIVOS: dict[str, CategoriaActivo] = {
    # Ancla dura
    "GLD": CategoriaActivo.ANCLA_DURA,
    "IAU": CategoriaActivo.ANCLA_DURA,
    "GOLD": CategoriaActivo.ANCLA_DURA,
    "DIA": CategoriaActivo.ANCLA_DURA,
    "IWM": CategoriaActivo.ANCLA_DURA,
    "SHY": CategoriaActivo.ANCLA_DURA,
    "BIL": CategoriaActivo.ANCLA_DURA,
    "INCOME": CategoriaActivo.ANCLA_DURA,
    "AGG": CategoriaActivo.ANCLA_DURA,
    "TLT": CategoriaActivo.ANCLA_DURA,
    # Cuasi-defensivo (consumo, salud, industrial, energía, telecom, sector ETFs)
    "BRKB": CategoriaActivo.CUASI_DEFENSIVO,
    "KO": CategoriaActivo.CUASI_DEFENSIVO,
    "PEP": CategoriaActivo.CUASI_DEFENSIVO,
    "PG": CategoriaActivo.CUASI_DEFENSIVO,
    "CL": CategoriaActivo.CUASI_DEFENSIVO,
    "KMB": CategoriaActivo.CUASI_DEFENSIVO,
    "K": CategoriaActivo.CUASI_DEFENSIVO,
    "GIS": CategoriaActivo.CUASI_DEFENSIVO,
    "HSY": CategoriaActivo.CUASI_DEFENSIVO,
    "MO": CategoriaActivo.CUASI_DEFENSIVO,
    "PM": CategoriaActivo.CUASI_DEFENSIVO,
    "WMT": CategoriaActivo.CUASI_DEFENSIVO,
    "COST": CategoriaActivo.CUASI_DEFENSIVO,
    "TGT": CategoriaActivo.CUASI_DEFENSIVO,
    "DE": CategoriaActivo.CUASI_DEFENSIVO,
    "ADM": CategoriaActivo.CUASI_DEFENSIVO,
    "JNJ": CategoriaActivo.CUASI_DEFENSIVO,
    "UNH": CategoriaActivo.CUASI_DEFENSIVO,
    "ABT": CategoriaActivo.CUASI_DEFENSIVO,
    "MRK": CategoriaActivo.CUASI_DEFENSIVO,
    "PFE": CategoriaActivo.CUASI_DEFENSIVO,
    "ABBV": CategoriaActivo.CUASI_DEFENSIVO,
    "GILD": CategoriaActivo.CUASI_DEFENSIVO,
    "CVS": CategoriaActivo.CUASI_DEFENSIVO,
    "AMGN": CategoriaActivo.CUASI_DEFENSIVO,
    "BIIB": CategoriaActivo.CUASI_DEFENSIVO,
    "ISRG": CategoriaActivo.CUASI_DEFENSIVO,
    "TMO": CategoriaActivo.CUASI_DEFENSIVO,
    "DHR": CategoriaActivo.CUASI_DEFENSIVO,
    "LMT": CategoriaActivo.CUASI_DEFENSIVO,
    "RTX": CategoriaActivo.CUASI_DEFENSIVO,
    "HON": CategoriaActivo.CUASI_DEFENSIVO,
    "CAT": CategoriaActivo.CUASI_DEFENSIVO,
    "MMM": CategoriaActivo.CUASI_DEFENSIVO,
    "GE": CategoriaActivo.CUASI_DEFENSIVO,
    "DD": CategoriaActivo.CUASI_DEFENSIVO,
    "DOW": CategoriaActivo.CUASI_DEFENSIVO,
    "HAL": CategoriaActivo.CUASI_DEFENSIVO,
    "SLB": CategoriaActivo.CUASI_DEFENSIVO,
    "BKR": CategoriaActivo.CUASI_DEFENSIVO,
    "XOM": CategoriaActivo.CUASI_DEFENSIVO,
    "CVX": CategoriaActivo.CUASI_DEFENSIVO,
    "BP": CategoriaActivo.CUASI_DEFENSIVO,
    "SHEL": CategoriaActivo.CUASI_DEFENSIVO,
    "TTE": CategoriaActivo.CUASI_DEFENSIVO,
    "VZ": CategoriaActivo.CUASI_DEFENSIVO,
    "T": CategoriaActivo.CUASI_DEFENSIVO,
    "XLV": CategoriaActivo.CUASI_DEFENSIVO,
    "XLU": CategoriaActivo.CUASI_DEFENSIVO,
    "IVE": CategoriaActivo.CUASI_DEFENSIVO,
    "HD": CategoriaActivo.CUASI_DEFENSIVO,
    # ETF mercado
    "SPY": CategoriaActivo.ETF_MERCADO,
    "QQQ": CategoriaActivo.ETF_MERCADO,
    "IVW": CategoriaActivo.ETF_MERCADO,
    "VEA": CategoriaActivo.ETF_MERCADO,
    "EWZ": CategoriaActivo.ETF_MERCADO,
    "FXI": CategoriaActivo.ETF_MERCADO,
    "EEM": CategoriaActivo.ETF_MERCADO,
    "SMH": CategoriaActivo.ETF_MERCADO,
    "XLE": CategoriaActivo.ETF_MERCADO,
    "XLF": CategoriaActivo.ETF_MERCADO,
    "RIO": CategoriaActivo.ETF_MERCADO,
    # Growth quality
    "MSFT": CategoriaActivo.GROWTH_QUALITY,
    "AAPL": CategoriaActivo.GROWTH_QUALITY,
    "GOOGL": CategoriaActivo.GROWTH_QUALITY,
    "AMZN": CategoriaActivo.GROWTH_QUALITY,
    "AVGO": CategoriaActivo.GROWTH_QUALITY,
    "TSM": CategoriaActivo.GROWTH_QUALITY,
    "V": CategoriaActivo.GROWTH_QUALITY,
    "MA": CategoriaActivo.GROWTH_QUALITY,
    "AXP": CategoriaActivo.GROWTH_QUALITY,
    "PYPL": CategoriaActivo.GROWTH_QUALITY,
    "CRM": CategoriaActivo.GROWTH_QUALITY,
    "ORCL": CategoriaActivo.GROWTH_QUALITY,
    "IBM": CategoriaActivo.GROWTH_QUALITY,
    "CSCO": CategoriaActivo.GROWTH_QUALITY,
    "ADBE": CategoriaActivo.GROWTH_QUALITY,
    "QCOM": CategoriaActivo.GROWTH_QUALITY,
    "TXN": CategoriaActivo.GROWTH_QUALITY,
    "BLK": CategoriaActivo.GROWTH_QUALITY,
    "GS": CategoriaActivo.GROWTH_QUALITY,
    "MS": CategoriaActivo.GROWTH_QUALITY,
    "JPM": CategoriaActivo.GROWTH_QUALITY,
    "BAC": CategoriaActivo.GROWTH_QUALITY,
    "WFC": CategoriaActivo.GROWTH_QUALITY,
    "C": CategoriaActivo.GROWTH_QUALITY,
    "MCD": CategoriaActivo.GROWTH_QUALITY,
    "SBUX": CategoriaActivo.GROWTH_QUALITY,
    "NKE": CategoriaActivo.GROWTH_QUALITY,
    "LOW": CategoriaActivo.GROWTH_QUALITY,
    "NFLX": CategoriaActivo.GROWTH_QUALITY,
    "CMCSA": CategoriaActivo.GROWTH_QUALITY,
    "DISN": CategoriaActivo.GROWTH_QUALITY,
    "BA": CategoriaActivo.GROWTH_QUALITY,
    "FCX": CategoriaActivo.GROWTH_QUALITY,
    # Growth agresivo
    "NVDA": CategoriaActivo.GROWTH_AGRESIVO,
    "AMD": CategoriaActivo.GROWTH_AGRESIVO,
    "INTC": CategoriaActivo.GROWTH_AGRESIVO,
    "MU": CategoriaActivo.GROWTH_AGRESIVO,
    "ASML": CategoriaActivo.GROWTH_AGRESIVO,
    "META": CategoriaActivo.GROWTH_AGRESIVO,
    "TSLA": CategoriaActivo.GROWTH_AGRESIVO,
    "ABNB": CategoriaActivo.GROWTH_AGRESIVO,
    "UBER": CategoriaActivo.GROWTH_AGRESIVO,
    "SHOP": CategoriaActivo.GROWTH_AGRESIVO,
    "SPOT": CategoriaActivo.GROWTH_AGRESIVO,
    "SNOW": CategoriaActivo.GROWTH_AGRESIVO,
    "SQ": CategoriaActivo.GROWTH_AGRESIVO,
    "F": CategoriaActivo.GROWTH_AGRESIVO,
    "GM": CategoriaActivo.GROWTH_AGRESIVO,
    "CEG": CategoriaActivo.GROWTH_AGRESIVO,
    "OKLO": CategoriaActivo.GROWTH_AGRESIVO,
    "PLTR": CategoriaActivo.GROWTH_AGRESIVO,
    "CRWV": CategoriaActivo.GROWTH_AGRESIVO,
    "RGTI": CategoriaActivo.GROWTH_AGRESIVO,
    "IBIT": CategoriaActivo.GROWTH_AGRESIVO,
    "DESP": CategoriaActivo.GROWTH_AGRESIVO,
    # LATAM / regional
    "MELI": CategoriaActivo.LATAM,
    "NU": CategoriaActivo.LATAM,
    "XP": CategoriaActivo.LATAM,
    "GLOB": CategoriaActivo.LATAM,
    "VALE": CategoriaActivo.LATAM,
    "PBR": CategoriaActivo.LATAM,
    "VIST": CategoriaActivo.LATAM,
    "PAMP": CategoriaActivo.LATAM,
    "YPFD": CategoriaActivo.LATAM,
    "GGAL": CategoriaActivo.LATAM,
    "CEPU": CategoriaActivo.LATAM,
    "TGNO4": CategoriaActivo.LATAM,
    "ECOG": CategoriaActivo.LATAM,
    "BABA": CategoriaActivo.LATAM,
    "JD": CategoriaActivo.LATAM,
    "PDD": CategoriaActivo.LATAM,
    "HMC": CategoriaActivo.LATAM,
    "TM": CategoriaActivo.LATAM,
    "X": CategoriaActivo.LATAM,
}

CATEGORIAS_DEFENSIVAS: frozenset[CategoriaActivo] = frozenset({
    CategoriaActivo.ANCLA_DURA,
    CategoriaActivo.CUASI_DEFENSIVO,
    CategoriaActivo.RENTA_FIJA_AR,
})

PISO_DEFENSIVO: dict[str, float] = {
    "Conservador": 0.50,
    "Moderado": 0.40,
    "Arriesgado": 0.30,
    "Muy arriesgado": 0.20,
}

LIMITE_CONCENTRACION: dict[str, float] = {
    "Conservador": 0.20,
    "Moderado": 0.25,
    "Arriesgado": 0.30,
    "Muy arriesgado": 0.35,
}

BENCHMARK_RENDIMIENTO: dict[str, float] = {
    "Conservador": 0.06,
    "Moderado": 0.09,
    "Arriesgado": 0.12,
    "Muy arriesgado": 0.15,
}

AJUSTE_HORIZONTE_CORTO: frozenset[str] = frozenset({"1 mes", "3 meses", "6 meses"})

CARTERA_IDEAL: dict[str, dict[str, float]] = {
    "Conservador": {
        "GLD": 0.15,
        "INCOME": 0.10,
        "SHY": 0.10,
        "_RENTA_AR": 0.15,
        "BRKB": 0.15,
        "KO": 0.10,
        "XOM": 0.10,
        "SPY": 0.15,
    },
    "Moderado": {
        "GLD": 0.10,
        "INCOME": 0.10,
        "_RENTA_AR": 0.20,
        "BRKB": 0.10,
        "SPY": 0.15,
        "MSFT": 0.10,
        "GOOGL": 0.10,
        "AMZN": 0.08,
        "MELI": 0.07,
    },
    "Arriesgado": {
        "GLD": 0.10,
        "BRKB": 0.05,
        "_RENTA_AR": 0.15,
        "SPY": 0.10,
        "MSFT": 0.10,
        "AMZN": 0.10,
        "NVDA": 0.10,
        "META": 0.10,
        "MELI": 0.10,
        "GOOGL": 0.10,
    },
    "Muy arriesgado": {
        "GLD": 0.10,
        "_RENTA_AR": 0.10,
        "SPY": 0.10,
        "MSFT": 0.10,
        "NVDA": 0.12,
        "META": 0.10,
        "MELI": 0.10,
        "AMZN": 0.08,
        "VIST": 0.10,
        "PLTR": 0.05,
        "IVW": 0.05,
    },
}

# Referencia de rentabilidad cartera modelo (YTD aprox., fracción). Actualizar periódicamente.
RENDIMIENTO_MODELO_YTD_REF: dict[str, float] = {
    "Conservador": 0.052,
    "Moderado": 0.0869,
    "Arriesgado": 0.110,
    "Muy arriesgado": 0.138,
}

# Universo renta fija AR (ON y soberanos). Precios/TIR referencia; sin yfinance.
UNIVERSO_RENTA_FIJA_AR: dict[str, dict[str, Any]] = {
    "PN43O": {
        "emisor": "Pan American Energy",
        "vencimiento": 2037,
        "tir_ref": 7.3,
        "calificacion": "AA+",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "Panamerican 2037",
        "cupon_pct": 8.75,
        "nominal_unidad": 100.0,
        "frecuencia_cupon": "trimestral",
    },
    "YM34O": {
        "emisor": "YPF S.A.",
        "vencimiento": 2034,
        "tir_ref": 7.1,
        "calificacion": "AA",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "YPF 2034",
    },
    "TLCTO": {
        "emisor": "Telecom Argentina",
        "vencimiento": 2036,
        "tir_ref": 8.0,
        "calificacion": "AA",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "Telecom 2036",
    },
    "TSC4O": {
        "emisor": "TGS",
        "vencimiento": 2035,
        "tir_ref": 7.1,
        "calificacion": "AA+",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "TGS 2035",
    },
    "IRCPO": {
        "emisor": "Irsa",
        "vencimiento": 2035,
        "tir_ref": 7.1,
        "calificacion": "AA-",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "Irsa 2035",
    },
    "DNC7O": {
        "emisor": "Edenor",
        "vencimiento": 2030,
        "tir_ref": 8.3,
        "calificacion": "A+",
        "tipo": "ON",
        "moneda": "USD",
        "descripcion": "Edenor 2030",
    },
    "AL30": {
        "emisor": "República Argentina",
        "vencimiento": 2030,
        "tir_ref": 9.23,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Bonar 2030",
        "cupon_pct": 0.75,
        "nominal_unidad": 100.0,
        "frecuencia_cupon": "semestral",
    },
    "GD30": {
        "emisor": "República Argentina",
        "vencimiento": 2030,
        "tir_ref": 8.8,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Global 2030",
    },
    "AE38": {
        "emisor": "República Argentina",
        "vencimiento": 2038,
        "tir_ref": 10.71,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Bonar 2038",
    },
    "GD35": {
        "emisor": "República Argentina",
        "vencimiento": 2035,
        "tir_ref": 9.1,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Global 2035",
    },
    "AL35": {
        "emisor": "República Argentina",
        "vencimiento": 2035,
        "tir_ref": 9.5,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Bonar 2035",
    },
    "GD41": {
        "emisor": "República Argentina",
        "vencimiento": 2041,
        "tir_ref": 10.1,
        "calificacion": "CCC",
        "tipo": "BONO_SOBERANO",
        "moneda": "USD",
        "descripcion": "Global 2041",
    },
}


def tir_ref_por_ticker(
    ticker: str,
    universo: dict[str, dict[str, Any]] | None = None,
) -> float | None:
    """TIR de referencia (%, ej. 7.3) si el ticker está en el universo renta fija AR."""
    u = universo if universo is not None else UNIVERSO_RENTA_FIJA_AR
    meta = u.get(str(ticker or "").strip().upper())
    if not meta:
        return None
    try:
        return float(meta["tir_ref"])
    except (KeyError, TypeError, ValueError):
        return None


RENTA_AR_PENDIENTE_MSG = "ON/Bonos AR — configurar manualmente con tu broker"
