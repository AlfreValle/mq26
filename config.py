"""
config.py — Configuración Central del Proyecto
Master Quant 26 | Estrategia Capitales
"""
import logging
import os
from pathlib import Path

_log = logging.getLogger(__name__)

# ─── RUTAS ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
DATA_DIR  = BASE_DIR / "0_Data_Maestra"
MOTOR_DIR = BASE_DIR / "1_Scripts_Motor"

RUTA_MAESTRA     = DATA_DIR / "Maestra_Inversiones.xlsx"
RUTA_TRANSAC     = DATA_DIR / "Maestra_Transaccional.csv"
RUTA_ANALISIS    = DATA_DIR / "Analisis_Empresas.xlsx"
RUTA_UNIVERSO    = DATA_DIR / "Universo_120_CEDEARs.xlsx"
RUTA_DB          = DATA_DIR / "master_quant.db"

# ─── SEGURIDAD Y VARIABLES DE ENTORNO (E3) ────────────────────────────────────
# No abortar el proceso si falta: en Docker/Railway el import ocurre antes de que
# Streamlit abra el puerto; un OSError aquí tumba el healthcheck /_stcore/health.
# La entrada bloquea en la UI si el modo legacy no tiene contraseña (mq26_main / app_main).
APP_PASSWORD = os.environ.get("MQ26_PASSWORD", "").strip()
if not APP_PASSWORD:
    _log.warning(
        "MQ26_PASSWORD no definida: definila en Railway → Variables o en .env para poder "
        "iniciar sesión (modo legacy). El servidor puede arrancar igual."
    )

# Opcional: contraseña de solo lectura (exportación deshabilitada en UI). Si coincide primero con MQ26_PASSWORD, el rol sigue siendo admin salvo que uses otro hash distinto.
MQ26_VIEWER_PASSWORD = os.environ.get("MQ26_VIEWER_PASSWORD", "").strip()
MQ26_INVESTOR_PASSWORD = os.environ.get("MQ26_INVESTOR_PASSWORD", "").strip()
MQ26_ADVISOR_PASSWORD = os.environ.get("MQ26_ADVISOR_PASSWORD", "").strip()
# Usuarios de login (modo legacy usuario+contraseña). Minúsculas al comparar.
MQ26_USER_ADMIN = (os.environ.get("MQ26_USER_ADMIN", "admin").strip().lower() or "admin")
MQ26_USER_ESTUDIO = (os.environ.get("MQ26_USER_ESTUDIO", "estudio").strip().lower() or "estudio")
MQ26_USER_INVERSOR = (os.environ.get("MQ26_USER_INVERSOR", "inversor").strip().lower() or "inversor")
MQ26_USER_ASESOR = (os.environ.get("MQ26_USER_ASESOR", "asesor").strip().lower() or "asesor")
MQ26_TIER = os.environ.get("MQ26_TIER", "super_admin").strip().lower()

# Telegram: si no está configurado, las alertas quedan silenciadas (no crashea)
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# ─── PARÁMETROS MOD-23 ────────────────────────────────────────────────────────
SMA_VENTANA   = 150
RSI_VENTANA   = 14
RSI_COMPRA    = 40
RSI_VENTA     = 70
NOTA_MIN_ELITE = 7.0
NOTA_ALERTA   = 4.0
PESO_MAX_CARTERA = 18.0   # % máximo por activo en cartera real

# ─── OPTIMIZADOR ──────────────────────────────────────────────────────────────
PESO_MIN_OPT         = 0.02   # 2% mínimo por activo en todos los modelos
PESO_MAX_OPT         = 0.25   # 25% máximo por activo en todos los modelos
PESO_MIN_CONVICCION  = 0.01   # B9: umbral mínimo de convicción (1%) — configurable
RISK_FREE_RATE       = 0.043  # T-Bill 3M USA — actualizar trimestralmente
N_SIM_DEFAULT        = 10_000 # Simulaciones Montecarlo

# ─── CONSTANTES FINANCIERAS CENTRALES ─────────────────────────────────────────
DIAS_TRADING     = 252          # Días hábiles de trading por año
COMISION_DEFAULT = 0.006        # Comisión default de broker (0.6%)
CCL_FACTOR_GGAL  = 10           # Factor de conversión GGAL.BA / GGAL para CCL
CCL_FALLBACK     = 1500.0       # Valor fallback del CCL cuando yfinance falla
INFLACION_MENSUAL_ARG = 0.04    # Inflación mensual Argentina (configurable)

# ─── MODO DEMO ────────────────────────────────────────────────────────────────
# DEMO_MODE=true arranca la app con 3 clientes sintéticos sin necesidad de datos reales.
# Útil para demos a prospects en cualquier máquina en menos de 1 minuto.
DEMO_MODE = os.environ.get("DEMO_MODE", "false").strip().lower() in ("true", "1", "yes")
import tempfile as _tempfile
DEMO_DB_PATH = os.environ.get(
    "DEMO_DB_PATH",
    str(Path(_tempfile.gettempdir()) / "mq26_demo.db")
)
CONCENTRACION_SECTOR_ALERTA = 0.40   # 40% en un sector = alerta
CONCENTRACION_ACTIVO_ALERTA = 0.30   # 30% en un activo = alerta
CONCENTRACION_PAIS_ALERTA   = 0.60   # 60% en un país = alerta

# ─── UNIVERSO DE ACTIVOS ──────────────────────────────────────────────────────
UNIVERSO_BASE = [
    "AAPL","MSFT","GOOGL","AMZN","META","NVDA","VIST","KO","PEP",
    "COST","V","CAT","LMT","GLD","SPY","QQQ","UNH","ABBV","CVX","VALE",
    "MELI","BRKB","OKLO","CEG","YPFD","CEPU","TGNO4","PAMP",
]

# ─── RATIOS CEDEAR BYMA (fallback si no está en Universo_120) ────────────────
RATIOS_CEDEAR = {
    "AAPL":20,"MSFT":30,"GOOGL":58,"AMZN":144,"META":24,"NVDA":240,
    "VIST":3,"KO":5,"PEP":18,"COST":48,"V":18,"CAT":20,"LMT":10,
    "GLD":10,"SPY":20,"QQQ":20,"UNH":33,"ABBV":10,"CVX":16,"VALE":2,
    # MELI/BRKB: ratio BYMA típico (fallback si falla Universo_120 en deploy)
    "MELI":120,"BRKB":30,"OKLO":1,"CEG":1,"BA":24,"TSLA":6,"ADBE":44,
    "ASML":146,"AMD":10,"AMGN":30,"AXP":15,"GS":6,"JPM":9,"BAC":4,
    "BLK":1,"CRM":12,"XOM":8,"PBR":2,"SHEL":3,"JNJ":7,"LLY":2,
    "NVO":4,"PFE":3,"MRK":6,"TMO":3,"DHR":3,"ABT":4,"ISRG":1,
    "GILD":7,"BIIB":13,"SHOP":5,"NFLX":5,"UBER":5,"SQ":5,"PYPL":5,
    "XP":1,
}

# ─── SECTORES (para clasificación) ────────────────────────────────────────────
SECTORES = {
    "AAPL":"Tecnología","MSFT":"Tecnología","GOOGL":"Tecnología",
    "AMZN":"Tecnología","META":"Tecnología","NVDA":"Tecnología",
    "VIST":"Energía","CEG":"Energía","OKLO":"Energía",
    "CVX":"Energía","XOM":"Energía","PBR":"Energía",
    "KO":"Consumo Def.","PEP":"Consumo Def.","COST":"Consumo Def.",
    "WMT":"Consumo Def.","PG":"Consumo Def.",
    "CAT":"Industria","GE":"Industria","LMT":"Defensa","BA":"Industria",
    "UNH":"Salud","ABBV":"Salud","JNJ":"Salud","LLY":"Salud",
    "GLD":"Cobertura","SPY":"ETF","QQQ":"ETF","DIA":"ETF",
    "MELI":"E-Commerce","BRKB":"Financiero","AXP":"Financiero",
    "JPM":"Financiero","GS":"Financiero","V":"Financiero",
    "VALE":"Materiales","YPFD":"Energía Local","CEPU":"Energía Local",
    "TGNO4":"Energía Local","PAMP":"Energía Local",
}

# ─── UNIVERSO FCI (CAFCI) ────────────────────────────────────────────────────
# Fondos disponibles en brokers argentinos — actualizar desde cafci.gob.ar
UNIVERSO_FCI = {
    # Renta Fija ARS
    "MAF AHORRO ARS":       {"tipo":"FCI","subtipo":"Renta Fija ARS","riesgo":"Bajo"},
    "MEGAINVER RENTA FIJA": {"tipo":"FCI","subtipo":"Renta Fija ARS","riesgo":"Bajo"},
    "PIONEER PESOS":        {"tipo":"FCI","subtipo":"Renta Fija ARS","riesgo":"Bajo"},
    "BALANZ AHORRO":        {"tipo":"FCI","subtipo":"Renta Fija ARS","riesgo":"Bajo"},
    # Renta Fija USD / Dólar linked
    "FONDOS FIMA USD":      {"tipo":"FCI","subtipo":"Renta Fija USD","riesgo":"Bajo"},
    "BALANZ CAPITAL USD":   {"tipo":"FCI","subtipo":"Renta Fija USD","riesgo":"Bajo"},
    "MEGAINVER DOLAR":      {"tipo":"FCI","subtipo":"Renta Fija USD","riesgo":"Bajo"},
    # Renta Variable
    "BALANZ ACCIONES":      {"tipo":"FCI","subtipo":"Renta Variable","riesgo":"Alto"},
    "FIMA ACCIONES":        {"tipo":"FCI","subtipo":"Renta Variable","riesgo":"Alto"},
    "COMPASS GROWTH":       {"tipo":"FCI","subtipo":"Renta Variable","riesgo":"Alto"},
    # Renta Mixta
    "PIONEER MIXTO":        {"tipo":"FCI","subtipo":"Mixto","riesgo":"Moderado"},
    "MAF MIXTO":            {"tipo":"FCI","subtipo":"Mixto","riesgo":"Moderado"},
    # Infraestructura / Cerrados
    "PELLEGRINI INFRAESTR": {"tipo":"FCI","subtipo":"Infraestructura","riesgo":"Moderado"},
}

# ─── PRIORIDADES DEL OPTIMIZADOR ─────────────────────────────────────────────
# Definidas por el usuario en orden de importancia
PRIORIDADES_OPTIMIZADOR = [
    "sharpe",           # 1° Sharpe ratio (retorno/riesgo)
    "retorno_usd",      # 2° Retorno absoluto USD
    "preservacion_ars", # 3° Preservación de capital en ARS
    "dividendos",       # 4° Dividendos / flujo recurrente
]

# Pesos del optimizador multi-objetivo (suman 1.0)
PESOS_OPTIMIZADOR = {
    "sharpe":           0.40,
    "retorno_usd":      0.30,
    "preservacion_ars": 0.20,
    "dividendos":       0.10,
}

# ─── OBSERVABILIDAD ───────────────────────────────────────────────────────────
# LOG_LEVEL: DEBUG en dev, INFO en producción
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ENVIRONMENT: distingue dev local de producción Railway
ENVIRONMENT = os.environ.get("RAILWAY_ENVIRONMENT",
              os.environ.get("ENVIRONMENT", "development"))

