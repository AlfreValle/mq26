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

# ─── REGLA CRÍTICA DE UNIVERSO ────────────────────────────────────────────────
# Todo activo comercializado en Argentina en ARS debe estar en el universo BYMA.
# El precio de mercado SIEMPRE viene de BYMA Open Data (services/byma_market_data.py).
# Nunca hardcodear precios. Nunca usar yfinance para precios de instrumentos AR.
UNIVERSO_FUENTE_CRITICA = "BYMA"  # sentinel — no borrar

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
    "COST","V","CAT","SPY","QQQ","UNH","ABBV","CVX","VALE",
    "MELI","BRKB","YPFD","CEPU","TGNO4","PAMP",
]

# ─── RATIOS CEDEAR BYMA (fallback si no está en Universo_120) ────────────────
RATIOS_CEDEAR = {
    # ── Fuente: PDF BYMA "CEDEARs Negociables" + Comafi (312 tickers) + Tablas Caja de Valores BYMA 17-04-2026
    # Tickers y ratios según BYMA/Comafi. Ratios inversos como fracción (1/X).
    # ── A ──────────────────────────────────────────────────────────────────────
    "MMM":10,"ABT":4,"ABBV":10,"ANF":1,"ACN":75,"ADGO":1,"ADS":22,
    "ADBE":44,"JMIA":1,"AAP":14,"AMD":10,"AEG":1,"AEM":6,
    "ABNB":15,"BABA":9,"GOOGL":58,"AABA":3,"MO":4,"ACHHY":1,
    "AMZN":144,"ABEV":0.333333,"AMX":1,"AAL":2,"AXP":15,"AIG":5,
    "AMGN":30,"ADI":15,"AAPL":20,"AMAT":5,"ARCO":0.5,"ARKK":10,
    "ARM":27,"AZN":2,"T":3,"ADP":6,"AVY":18,"CAR":26,"AKO.B":1,
    # ── B ──────────────────────────────────────────────────────────────────────
    "BIDU":11,"BKR":7,"BBD":1,"BSBR":1,"SAN":0.25,"BAC":4,
    "BCS":1,"GOLD":2,"BAS":2,"BAYN":3,"BRKB":22,"BHP":2,"BBVA":1,
    "BIOX":1,"BIIB":13,"KEEL":0.2,"BB":3,"BKNG":700,"BP":5,
    "LND":1,"BAK":2,"BRFS":0.333333,"BMY":3,"AVGO":39,"BNG":5,"BBDC3":1,
    # ── C ──────────────────────────────────────────────────────────────────────
    "CAJ":2,"CAH":3,"CCL":3,"CAT":20,"CX":1,"EBR":0.25,"SCHW":13,
    "CVX":16,"LFCHY":2,"SNPTY":3,"CSCO":5,"C":3,"KOFM":2,"CDE":1,
    "COIN":27,"CL":3,"CBD":1,"SBS":0.5,"ELP":0.333333,
    "GLW":4,"CAAP":0.25,"COST":48,"CS":1,"CVS":15,
    # ── D ──────────────────────────────────────────────────────────────────────
    "DHR":54,"BSN":20,"DE":40,"DAL":8,"DESP":1,"DTEA":3,"DEO":6,
    "DOCU":22,"DOW":6,"DD":5,
    # ── E ──────────────────────────────────────────────────────────────────────
    "EOAN":6,"EBAY":2,"EA":14,"LLY":56,"ERJ":1,"XLE":2,"E":4,
    "EFX":16,"EQNR":6,"GLD":50,"ETSY":16,"XOM":10,
    # ── F ──────────────────────────────────────────────────────────────────────
    "FNMA":1,"FDX":10,"RACE":83,"XLF":2,"FSLR":18,"FMX":6,"F":1,
    "FMCC":1,"FCX":3,
    # ── G ──────────────────────────────────────────────────────────────────────
    "GE":8,"GM":6,"GPRK":1,"GGB":0.25,"GILD":4,"GLNT":6,"GFI":1,
    "GT":2,"PAC":16,"ASR":20,"TV":3,"GSK":4,"GRMN":3,
    # ── H ──────────────────────────────────────────────────────────────────────
    "HAL":2,"HOG":3,"HMY":1,"HDB":2,"HL":1,"HHPD":2,
    "HMC":1,"HON":8,"HWM":1,"HPQ":1,"HSBC":2,"HUT":5,   # HUT split 25x (ratio 0.2→5) junio-2026
    # ── I ──────────────────────────────────────────────────────────────────────
    "IBN":1,"INFY":1,"ING":3,"INTC":5,"IBM":15,"IFF":12,"IP":4,
    "ISRG":90,"QQQ":20,"IBIT":10,"FXI":5,"IEUR":11,"ETHA":5,
    "EWZ":2,"EEM":5,"IBB":27,"IVW":20,"IVE":40,"IWM":10,"ITUB":1,
    # ── J ──────────────────────────────────────────────────────────────────────
    "JPM":15,"JD":4,"JNJ":15,"JCI":2,"YY":5,
    # ── K ──────────────────────────────────────────────────────────────────────
    "KB":2,"KMB":6,"KGC":1,"PHG":5,"KEP":1,
    # ── L ──────────────────────────────────────────────────────────────────────
    "LRCX":56,"LVS":2,"LAC":1,"LAR":1,"LYG":2,"ERIC":2,"LMT":20,
    # ── M ──────────────────────────────────────────────────────────────────────
    "MMC":16,"MRVL":14,"MA":33,"MCD":24,"MUX":2,"MDT":4,
    # MELI/META/MSFT corregidos: los valores >5000 eran erróneos (parseo con
    # decimales mal interpretados). Ratios reales BYMA junio-2026.
    "MELI":10,"MBG":4,"MRK":5,"META":30,"MU":5,"MSFT":25,"MSTR":20,
    "MUFG":1,"MFG":1,"MBT":2,"MRNA":19,"MDLZ":15,"MSI":20,
    # ── N ──────────────────────────────────────────────────────────────────────
    "NGG":2,"NEC1":0.333333,"NTES":14,"NFLX":48,"NEM":3,"NXE":1,
    "NKE":12,"NIO":4,"NSAN":1,"NOKA":1,"NMR":1,"NG":0.25,"NVS":4,
    # NVDA corregido (post-split 10:1 jun-2024, ratio real BYMA ~15)
    "NLM":2,"NU":2,"NUE":16,"NVDA":15,
    # ── O ──────────────────────────────────────────────────────────────────────
    "OXY":5,"ORCL":3,"ORANY":1,"ORLY":222,
    # ── P ──────────────────────────────────────────────────────────────────────
    "PCAR":3,"PAGS":3,"PLTR":3,"PANW":50,"PAAS":3,"PCRF":2,"PYPL":8,
    "PSO":1,"PEP":18,"PRIO3":2,"PBR":1,"PTRCY":4,"PFE":4,"PM":18,
    "PSX":6,"PINS":7,"PBI":1,"OGZD":2,"LKOD":4,"ATAD":4,"PKS":3,
    "PG":15,"SH":8,
    # ── Q ──────────────────────────────────────────────────────────────────────
    "QCOM":11,
    # ── R ──────────────────────────────────────────────────────────────────────
    "RTX":5,"RIO":8,"RIOT":3,"RBLX":2,"ROKU":13,"ROST":4,"SHEL":2,
    # ── S ──────────────────────────────────────────────────────────────────────
    "SPGI":45,"CRM":18,"SMSN":14,"SAP":6,"SATL":1,"SLB":3,"SE":32,
    "SHPWQ":0.5,"SHOP":107,"SIEGY":3,"SI":10,"SWKS":21,"SNAP":1,
    "SNA":6,"SNOW":30,"SONY":8,"SCCO":2,"DIA":20,"SPY":60,"SPOT":28,  # SPY split 3x (ratio 20→60) junio-2026
    "SDA":2,"SBUX":12,"STLA":5,"STNE":3,"SUZ":1,"SYY":8,"SID":0.125,
    # ── T ──────────────────────────────────────────────────────────────────────
    "TSM":9,"TGT":24,"TTM":1,"TIIAY":1,"TEFO":8,"TEN":1,"TSU":1,
    # KO corregido: ratio real ~5 (era 36577 por parseo erróneo)
    "TXR":4,"TSLA":15,"TXN":5,"BK":2,"BA":24,"KO":5,"XLC":19,
    "XLY":43,"XLP":16,"GS":13,"XLV":29,"HSY":21,"HD":32,"XLI":28,
    "XLB":18,"MOS":5,"XLRE":9,"XLK":46,"TRV":6,"DISN":12,"TMO":22,
    "TJX":22,"TMUS":33,"TTE":3,"TM":15,"TCOM":2,"TRIP":2,"TWLO":36,
    # ── U ──────────────────────────────────────────────────────────────────────
    "USB":5,"UBER":2,"UGP":1,"UL":3,"UNP":20,"UAL":5,"X":3,"UNH":33,
    "UPST":5,"URBN":2,
    # ── V ──────────────────────────────────────────────────────────────────────
    # VALE corregido: ratio real BYMA ~2 (era 31902 por parseo erróneo)
    "VALE":2,"VEA":10,"VRSN":6,"VZ":4,"SPCE":0.5,"V":18,"VIST":3,
    "VOD":1,"VIV":1,
    # ── W / X / Y / Z ──────────────────────────────────────────────────────────
    "WBA":3,"WMT":18,"WBO":6,"WFC":5,
    "XRX":1,"XROX":1,"XP":4,"AUY":1,"YZCA":2,"YELP":2,"ZM":47,
    "XYZ":20,
    # ── ETFs nuevos — Tablas Caja de Valores BYMA 17-04-2026 ───────────────────
    "URA":5,"SMH":50,"SPXL":25,"XLU":15,"CIBR":10,"TQQQ":25,
    "VXX":5,"ITA":50,"ICLN":5,"EWY":50,"XME":30,"RSP":30,
    # ── Acciones brasileñas código B3 (BYMA) — Tablas Caja de Valores ──────────
    "VALE3":1,"PETR3":1,"BBAS3":2,"RENT3":2,
    "MGLU3":1,"ITUB3":1,"LREN3":1,"HAPV3":1,"SUZB3":1,
    "ABEV3":1,"CSNA3":1,"BPA11":1,"NATU3":1,"WEGE3":1,
    "SBSP3":1,"VIVT3":1,"TIMS3":1,
    # ── Nuevos CEDEARs BYMA (2026) ───────────────────────────────────────────────
    "ANET":29,"CCJ":23,"COP":25,"CRWD":79,"FISV":11,
    "GLNG":10,"HIMS":4,"MP":10,"NBIS":27,"NEE":19,
    "O":13,"ONDS":2,"SNDK":170,
}

# ─── TICKERS EXCLUIDOS DEL UNIVERSO ARS ──────────────────────────────────────
# Acciones de EE.UU. que NO tienen CEDEAR en BYMA y solo se operan en USD
# desde brokers internacionales. No deben aparecer en carteras ARS ni en el
# optimizador local. Se mantienen en registros históricos pero se filtran al
# construir el universo de inversión.
TICKERS_NO_CEDEAR_BYMA: frozenset[str] = frozenset({
    "ADM",    # Archer-Daniels-Midland — NYSE, solo USD
    "GIS",    # General Mills — NYSE, solo USD
    "CMCSA",  # Comcast — NASDAQ, solo USD
})

# ─── CEDEAR_INFO — Enriquecido: exchange, currency, yf_ticker ─────────────────
# Uso: CEDEAR_INFO["AAPL"]["yf_ticker"] → "AAPL"
# RATIOS_CEDEAR sigue siendo el dict flat (ticker→float) para todo el código existente.
# Este dict es adicional y no rompe ningún consumidor existente.
CEDEAR_INFO = {
    # ── Equities USD — NYSE / NASDAQ ──────────────────────────────────────────
    "AAL":   {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AAL"},
    "AAP":   {"ratio":14,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AAP"},
    "AAPL":  {"ratio":20,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AAPL"},
    "AABA":  {"ratio":3,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"AABA"},
    "ABBV":  {"ratio":10,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ABBV"},
    "ABEV":  {"ratio":0.3333, "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ABEV"},
    "ABNB":  {"ratio":15,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ABNB"},
    "ABT":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ABT"},
    "ACHHY": {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"ACHHY"},
    "ACN":   {"ratio":75,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ACN"},
    "ADBE":  {"ratio":44,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ADBE"},
    "ADGO":  {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ADGO"},
    "ADI":   {"ratio":15,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ADI"},
    "ADP":   {"ratio":6,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ADP"},
    "AEG":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AEG"},
    "AEM":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AEM"},
    "AIG":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AIG"},
    "AMAT":  {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AMAT"},
    "AMD":   {"ratio":10,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AMD"},
    "AMGN":  {"ratio":30,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AMGN"},
    "AMX":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AMX"},
    "AMZN":  {"ratio":144,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AMZN"},
    "ANF":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ANF"},
    "ARCO":  {"ratio":0.5,    "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ARCO"},
    "ARM":   {"ratio":27,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ARM"},
    "ASR":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ASR"},
    "AUY":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AUY"},
    "AVGO":  {"ratio":39,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AVGO"},
    "AVY":   {"ratio":18,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AVY"},
    "AXP":   {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AXP"},
    "AZN":   {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"AZN"},
    "BA":    {"ratio":24,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BA"},
    "BABA":  {"ratio":9,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BABA"},
    "BAC":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BAC"},
    "BAK":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BAK"},
    "BB":    {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BB"},
    "BBD":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BBD"},
    "BBVA":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BBVA"},
    "BCS":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BCS"},
    "BHP":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BHP"},
    "BIDU":  {"ratio":11,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"BIDU"},
    "BIIB":  {"ratio":13,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"BIIB"},
    "BIOX":  {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"BIOX"},
    "BK":    {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BK"},
    "BKNG":  {"ratio":700,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"BKNG"},
    "BKR":   {"ratio":7,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"BKR"},
    "BMY":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BMY"},
    "BP":    {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BP"},
    "BRFS":  {"ratio":0.3333, "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BRFS"},
    "BRKB":  {"ratio":22,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BRK-B"},
    "BSBR":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"BSBR"},
    "C":     {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"C"},
    "CAAP":  {"ratio":0.25,   "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CAAP"},
    "CAH":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CAH"},
    "CAJ":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CAJ"},
    "CAR":   {"ratio":26,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"CAR"},
    "CAT":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CAT"},
    "CBD":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CBD"},
    "CCL":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CCL"},
    "CDE":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CDE"},
    "CL":    {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CL"},
    "COIN":  {"ratio":27,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"COIN"},
    "COST":  {"ratio":48,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"COST"},
    "CRM":   {"ratio":18,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CRM"},
    "CS":    {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CS"},
    "CSCO":  {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"CSCO"},
    "CVS":   {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CVS"},
    "CVX":   {"ratio":16,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CVX"},
    "CX":    {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"CX"},
    "DAL":   {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DAL"},
    "DD":    {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DD"},
    "DE":    {"ratio":40,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DE"},
    "DEO":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DEO"},
    "DESP":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DESP"},
    "DHR":   {"ratio":54,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DHR"},
    "DISN":  {"ratio":12,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DIS"},
    "DOCU":  {"ratio":22,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"DOCU"},
    "DOW":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"DOW"},
    "DTEA":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"DTEA"},
    "E":     {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"E"},
    "EA":    {"ratio":14,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"EA"},
    "EBAY":  {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"EBAY"},
    "EBR":   {"ratio":0.25,   "exchange":"NYSE",     "currency":"USD", "yf_ticker":"EBR"},
    "EFX":   {"ratio":16,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"EFX"},
    "ELP":   {"ratio":0.3333, "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ELP"},
    "EQNR":  {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"EQNR"},
    "ERIC":  {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ERIC"},
    "ERJ":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ERJ"},
    "ETSY":  {"ratio":16,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ETSY"},
    "FCX":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"FCX"},
    "FDX":   {"ratio":10,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"FDX"},
    "FMCC":  {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"FMCC"},
    "FMX":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"FMX"},
    "FNMA":  {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"FNMA"},
    "FSLR":  {"ratio":18,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"FSLR"},
    "F":     {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"F"},
    "GE":    {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GE"},
    "GFI":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GFI"},
    "GGB":   {"ratio":0.25,   "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GGB"},
    "GILD":  {"ratio":4,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"GILD"},
    "GLNT":  {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GLOB"},
    "GLW":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GLW"},
    "GM":    {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GM"},
    "GOLD":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GOLD"},
    "GOOGL": {"ratio":58,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"GOOGL"},
    "GPRK":  {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"GPRK"},
    "GRMN":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"GRMN"},
    "GS":    {"ratio":13,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GS"},
    "GSK":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"GSK"},
    "GT":    {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"GT"},
    "HAL":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HAL"},
    "HD":    {"ratio":32,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HD"},
    "HDB":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HDB"},
    "HL":    {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HL"},
    "HMC":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HMC"},
    "HMY":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HMY"},
    "HOG":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HOG"},
    "HON":   {"ratio":8,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"HON"},
    "HPQ":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HPQ"},
    "HSBC":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HSBC"},
    "HSY":   {"ratio":21,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HSY"},
    "HWM":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"HWM"},
    "IBN":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"IBN"},
    "IFF":   {"ratio":12,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"IFF"},
    "INFY":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"INFY"},
    "ING":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ING"},
    "INTC":  {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"INTC"},
    "IP":    {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"IP"},
    "ISRG":  {"ratio":90,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ISRG"},
    "ITUB":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ITUB"},
    "IBM":   {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"IBM"},
    "JCI":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"JCI"},
    "JD":    {"ratio":4,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"JD"},
    "JMIA":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"JMIA"},
    "JNJ":   {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"JNJ"},
    "JPM":   {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"JPM"},
    "KB":    {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KB"},
    "KEEL":  {"ratio":0.2,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"KEEL"},
    "KEP":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KEP"},
    "KGC":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KGC"},
    "KMB":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KMB"},
    "KO":    {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KO"},
    "KOFM":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"KOF"},
    "LAC":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"LAC"},
    "LAR":   {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"LRE"},
    "LFCHY": {"ratio":2,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"LFCHY"},
    "LKOD":  {"ratio":4,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"LUKOY"},
    "LLY":   {"ratio":56,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"LLY"},
    "LMT":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"LMT"},
    "LND":   {"ratio":1,      "exchange":"NYSE_AMEX","currency":"USD", "yf_ticker":"LND"},
    "LRCX":  {"ratio":56,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"LRCX"},
    "LVS":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"LVS"},
    "LYG":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"LYG"},
    "MA":    {"ratio":33,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MA"},
    "MBT":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MBT"},
    "MCD":   {"ratio":24,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MCD"},
    "MDLZ":  {"ratio":15,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MDLZ"},
    "MDT":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MDT"},
    "MELI":  {"ratio":120,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MELI"},
    "META":  {"ratio":24,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"META"},
    "MFG":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MFG"},
    "MMC":   {"ratio":16,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MMC"},
    "MMM":   {"ratio":10,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MMM"},
    "MO":    {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MO"},
    "MOS":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MOS"},
    "MRK":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MRK"},
    "MRNA":  {"ratio":19,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MRNA"},
    "MRVL":  {"ratio":14,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MRVL"},
    "MSFT":  {"ratio":30,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MSFT"},
    "MSI":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MSI"},
    "MSTR":  {"ratio":20,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MSTR"},
    "MU":    {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"MU"},
    "MUFG":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MUFG"},
    "MUX":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"MUX"},
    "NEM":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NEM"},
    "NFLX":  {"ratio":48,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"NFLX"},
    "NG":    {"ratio":0.25,   "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NG"},
    "NGG":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NGG"},
    "NIO":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NIO"},
    "NKE":   {"ratio":12,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NKE"},
    "NLM":   {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NLM"},
    "NMR":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NMR"},
    "NOKA":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NOK"},
    "NSAN":  {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"NSANY"},
    "NTES":  {"ratio":14,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"NTES"},
    "NU":    {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NU"},
    "NUE":   {"ratio":16,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NUE"},
    "NVDA":  {"ratio":24,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"NVDA"},
    "NVS":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NVS"},
    "NXE":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"NXE"},
    "ORANY": {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"ORANY"},
    "ORCL":  {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"ORCL"},
    "ORLY":  {"ratio":222,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ORLY"},
    "OXY":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"OXY"},
    "PAAS":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"PAAS"},
    "PAC":   {"ratio":16,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PAC"},
    "PANW":  {"ratio":50,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"PANW"},
    "PAGS":  {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PAGS"},
    "PBI":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PBI"},
    "PBR":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PBR"},
    "PCAR":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"PCAR"},
    "PCRF":  {"ratio":2,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"PCRFY"},
    "PEP":   {"ratio":18,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"PEP"},
    "PFE":   {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PFE"},
    "PG":    {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PG"},
    "PHG":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PHG"},
    "PINS":  {"ratio":7,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PINS"},
    "PKS":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PKS"},
    "PLTR":  {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PLTR"},
    "PM":    {"ratio":18,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PM"},
    "PSO":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PSO"},
    "PSX":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"PSX"},
    "PTRCY": {"ratio":4,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"PTRCY"},
    "PYPL":  {"ratio":8,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"PYPL"},
    "QCOM":  {"ratio":11,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"QCOM"},
    "RACE":  {"ratio":83,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"RACE"},
    "RBLX":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"RBLX"},
    "RIO":   {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"RIO"},
    "RIOT":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"RIOT"},
    "ROKU":  {"ratio":13,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ROKU"},
    "ROST":  {"ratio":4,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ROST"},
    "RTX":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"RTX"},
    "SAP":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SAP"},
    "SAN":   {"ratio":0.25,   "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SAN"},
    "SATL":  {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"SATL"},
    "SBS":   {"ratio":0.5,    "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SBS"},
    "SBUX":  {"ratio":12,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"SBUX"},
    "SCCO":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SCCO"},
    "SCHW":  {"ratio":13,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SCHW"},
    "SE":    {"ratio":32,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SE"},
    "SHEL":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SHEL"},
    "SHOP":  {"ratio":107,    "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SHOP"},
    "SHPWQ": {"ratio":0.5,    "exchange":"OTC",      "currency":"USD", "yf_ticker":"SHPWQ"},
    "SI":    {"ratio":10,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SI"},
    "SID":   {"ratio":0.125,  "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SID"},
    "SIEGY": {"ratio":3,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"SIEGY"},
    "SLB":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SLB"},
    "SNA":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SNA"},
    "SNAP":  {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SNAP"},
    "SNOW":  {"ratio":30,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SNOW"},
    "SNPTY": {"ratio":3,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"SNPTY"},
    "SONY":  {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SONY"},
    "SPCE":  {"ratio":0.5,    "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SPCE"},
    "SPGI":  {"ratio":45,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SPGI"},
    "SPOT":  {"ratio":28,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SPOT"},
    "STLA":  {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"STLA"},
    "STNE":  {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"STNE"},
    "SUZ":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SUZ"},
    "SWKS":  {"ratio":21,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"SWKS"},
    "SYY":   {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"SYY"},
    "T":     {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"T"},
    "TCOM":  {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TCOM"},
    "TEN":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TEN"},
    "TGT":   {"ratio":24,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TGT"},
    "TIIAY": {"ratio":1,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"TIIAY"},
    "TJX":   {"ratio":22,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TJX"},
    "TM":    {"ratio":15,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TM"},
    "TMO":   {"ratio":22,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TMO"},
    "TMUS":  {"ratio":33,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TMUS"},
    "TRIP":  {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TRIP"},
    "TRV":   {"ratio":6,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TRV"},
    "TSM":   {"ratio":9,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TSM"},
    "TSU":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TSU"},
    "TSLA":  {"ratio":15,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TSLA"},
    "TTE":   {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TTE"},
    "TV":    {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TV"},
    "TWLO":  {"ratio":36,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TWLO"},
    "TXN":   {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TXN"},
    "UAL":   {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"UAL"},
    "UBER":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"UBER"},
    "UGP":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"UGP"},
    "UL":    {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"UL"},
    "UNH":   {"ratio":33,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"UNH"},
    "UNP":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"UNP"},
    "UPST":  {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"UPST"},
    "URBN":  {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"URBN"},
    "USB":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"USB"},
    "V":     {"ratio":18,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"V"},
    "VALE":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"VALE"},
    "VIST":  {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"VIST"},
    "VIV":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"VIV"},
    "VOD":   {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"VOD"},
    "VRSN":  {"ratio":6,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"VRSN"},
    "VZ":    {"ratio":4,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"VZ"},
    "WBA":   {"ratio":3,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"WBA"},
    "WFC":   {"ratio":5,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"WFC"},
    "WMT":   {"ratio":18,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"WMT"},
    "X":     {"ratio":3,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"X"},
    "XOM":   {"ratio":10,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"XOM"},
    "XP":    {"ratio":4,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"XP"},
    "XRX":   {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"XRX"},
    "XYZ":   {"ratio":20,     "exchange":"NYSE",     "currency":"USD", "yf_ticker":"XYZ"},
    "YELP":  {"ratio":2,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"YELP"},
    "YY":    {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"YY"},
    "ZM":    {"ratio":47,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ZM"},
    # ── Equities EUR — XETRA ──────────────────────────────────────────────────
    "ADS":   {"ratio":22,     "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"ADS.DE"},
    "AKO.B": {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"AKO-B"},
    "BAS":   {"ratio":2,      "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"BAS.DE"},
    "BAYN":  {"ratio":3,      "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"BAYN.DE"},
    "BNG":   {"ratio":5,      "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"BNG.DE"},
    "EOAN":  {"ratio":6,      "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"EOAN.DE"},
    "MBG":   {"ratio":4,      "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"MBG.DE"},
    "NEC1":  {"ratio":0.3333, "exchange":"XETRA",    "currency":"EUR", "yf_ticker":"EN1.DE"},
    # ── Equities GBP — LSE ────────────────────────────────────────────────────
    "ATAD":  {"ratio":4,      "exchange":"LSE",      "currency":"USD", "yf_ticker":"ATAD.L"},
    "HHPD":  {"ratio":2,      "exchange":"LSE",      "currency":"USD", "yf_ticker":"HHPD.L"},
    "OGZD":  {"ratio":2,      "exchange":"LSE",      "currency":"USD", "yf_ticker":"OGZD.L"},
    "SMSN":  {"ratio":14,     "exchange":"LSE",      "currency":"USD", "yf_ticker":"SMSN.L"},
    "TXR":   {"ratio":4,      "exchange":"LSE",      "currency":"USD", "yf_ticker":"TXR.L"},
    "WBO":   {"ratio":6,      "exchange":"LSE",      "currency":"USD", "yf_ticker":"WBO.L"},
    # ── Euronext ──────────────────────────────────────────────────────────────
    "BSN":   {"ratio":20,     "exchange":"EURONEXT", "currency":"EUR", "yf_ticker":"CS.PA"},
    # ── OTC / Pink Sheets ─────────────────────────────────────────────────────
    "HUT":   {"ratio":0.2,    "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"HUT"},
    "TEFO":  {"ratio":8,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TEF"},
    "TTM":   {"ratio":1,      "exchange":"NYSE",     "currency":"USD", "yf_ticker":"TTM"},
    "XROX":  {"ratio":1,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"XRX"},
    "YZCA":  {"ratio":2,      "exchange":"OTC",      "currency":"USD", "yf_ticker":"YZCAY"},
    "SDA":   {"ratio":2,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"SDA"},
    # ── ETFs (NYSE Arca) ──────────────────────────────────────────────────────
    "ARKK":  {"ratio":10,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"ARKK"},
    "CIBR":  {"ratio":10,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"CIBR"},
    "DIA":   {"ratio":20,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"DIA"},
    "EEM":   {"ratio":5,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"EEM"},
    "ETHA":  {"ratio":5,      "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"ETHA"},
    "EWY":   {"ratio":50,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"EWY"},
    "EWZ":   {"ratio":2,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"EWZ"},
    "FXI":   {"ratio":5,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"FXI"},
    "GLD":   {"ratio":50,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"GLD"},
    "IBIT":  {"ratio":10,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"IBIT"},
    "IBB":   {"ratio":27,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"IBB"},
    "ICLN":  {"ratio":5,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"ICLN"},
    "IEUR":  {"ratio":11,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"IEUR"},
    "ITA":   {"ratio":50,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"ITA"},
    "IVE":   {"ratio":40,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"IVE"},
    "IVW":   {"ratio":20,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"IVW"},
    "IWM":   {"ratio":10,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"IWM"},
    "QQQ":   {"ratio":20,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"QQQ"},
    "RSP":   {"ratio":30,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"RSP"},
    "SH":    {"ratio":8,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"SH"},
    "SMH":   {"ratio":50,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"SMH"},
    "SPXL":  {"ratio":25,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"SPXL"},
    "SPY":   {"ratio":20,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"SPY"},
    "TQQQ":  {"ratio":25,     "exchange":"NASDAQ",   "currency":"USD", "yf_ticker":"TQQQ"},
    "URA":   {"ratio":5,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"URA"},
    "VEA":   {"ratio":10,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"VEA"},
    "VXX":   {"ratio":5,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"VXX"},
    "XLB":   {"ratio":18,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLB"},
    "XLC":   {"ratio":19,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLC"},
    "XLE":   {"ratio":2,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLE"},
    "XLF":   {"ratio":2,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLF"},
    "XLI":   {"ratio":28,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLI"},
    "XLK":   {"ratio":46,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLK"},
    "XLP":   {"ratio":16,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLP"},
    "XLRE":  {"ratio":9,      "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLRE"},
    "XLU":   {"ratio":15,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLU"},
    "XLV":   {"ratio":29,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLV"},
    "XLY":   {"ratio":43,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XLY"},
    "XME":   {"ratio":30,     "exchange":"NYSE_ARCA","currency":"USD", "yf_ticker":"XME"},
    # ── Acciones brasileñas — código B3 (BYMA) ────────────────────────────────
    "ABEV3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"ABEV3.SA"},
    "BBAS3": {"ratio":2,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"BBAS3.SA"},
    "BBDC3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"BBDC3.SA"},
    "BPA11": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"BPA11.SA"},
    "CSNA3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"CSNA3.SA"},
    "HAPV3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"HAPV3.SA"},
    "ITUB3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"ITUB3.SA"},
    "LREN3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"LREN3.SA"},
    "MGLU3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"MGLU3.SA"},
    "NATU3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"NATU3.SA"},
    "PETR3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"PETR3.SA"},
    "PRIO3": {"ratio":2,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"PRIO3.SA"},
    "RENT3": {"ratio":2,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"RENT3.SA"},
    "SBSP3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"SBSP3.SA"},
    "SUZB3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"SUZB3.SA"},
    "TIMS3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"TIMS3.SA"},
    "VALE3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"VALE3.SA"},
    "VIVT3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"VIVT3.SA"},
    "WEGE3": {"ratio":1,      "exchange":"B3",       "currency":"BRL", "yf_ticker":"WEGE3.SA"},
}

# ─── ACCIONES ARGENTINAS (Panel Líder y General — BYMA) ──────────────────────
ACCIONES_ARGENTINAS = {
    # Con ADR activo — arbitraje ARS/USD posible
    "BBAR":  {"nombre":"Banco BBVA Argentina",         "panel":"Lider", "ratio_adr":3,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"BBAR"},
    "BMA":   {"nombre":"Banco Macro",                  "panel":"Lider", "ratio_adr":10, "exchange":"NYSE",   "currency":"USD", "yf_ticker":"BMA"},
    "CEPU":  {"nombre":"Central Puerto",               "panel":"Lider", "ratio_adr":10, "exchange":"NYSE",   "currency":"USD", "yf_ticker":"CEPU"},
    "CRES":  {"nombre":"Cresud",                       "panel":"Lider", "ratio_adr":10, "exchange":"NASDAQ", "currency":"USD", "yf_ticker":"CRES"},
    "EDN":   {"nombre":"Edenor",                       "panel":"Lider", "ratio_adr":20, "exchange":"NYSE",   "currency":"USD", "yf_ticker":"EDN"},
    "GGAL":  {"nombre":"Grupo Financiero Galicia",     "panel":"Lider", "ratio_adr":10, "exchange":"NASDAQ", "currency":"USD", "yf_ticker":"GGAL"},
    "LOMA":  {"nombre":"Loma Negra",                   "panel":"Lider", "ratio_adr":5,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"LOMA"},
    "PAMP":  {"nombre":"Pampa Energía",                "panel":"Lider", "ratio_adr":25, "exchange":"NYSE",   "currency":"USD", "yf_ticker":"PAM"},
    "SUPV":  {"nombre":"Grupo Supervielle",            "panel":"Lider", "ratio_adr":5,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"SUPV"},
    "TECO2": {"nombre":"Telecom Argentina",            "panel":"Lider", "ratio_adr":5,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"TEO"},
    "TGSU2": {"nombre":"Transportadora de Gas del Sur","panel":"Lider", "ratio_adr":5,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"TGS"},
    "VIST":  {"nombre":"Vista Energy",                 "panel":"Lider", "ratio_adr":1,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"VIST"},
    "YPFD":  {"nombre":"YPF S.A.",                     "panel":"Lider", "ratio_adr":1,  "exchange":"NYSE",   "currency":"USD", "yf_ticker":"YPF"},
    # Sin ADR — cotización pura local BYMA
    "ALUA":  {"nombre":"Aluar Aluminio Argentino",     "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"ALUA.BA"},
    "BYMA":  {"nombre":"Bolsas y Mercados Argentinos", "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"BYMA.BA"},
    "COME":  {"nombre":"Soc. Comercial del Plata",     "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"COME.BA"},
    "METR":  {"nombre":"Metrogas",                     "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"METR.BA"},
    "MIRG":  {"nombre":"Mirgor",                       "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"MIRG.BA"},
    "TGNO4": {"nombre":"Transp. de Gas del Norte",     "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"TGNO4.BA"},
    "TRAN":  {"nombre":"Transener",                    "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"TRAN.BA"},
    "TXAR":  {"nombre":"Ternium Argentina",            "panel":"Lider",   "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"TXAR.BA"},
    "AGRO":  {"nombre":"Agrometal",                    "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"AGRO.BA"},
    "AUSO":  {"nombre":"Autopistas del Sol",           "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"AUSO.BA"},
    "BHIP":  {"nombre":"Banco Hipotecario",            "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"BHIP.BA"},
    "BOLT":  {"nombre":"Boldt",                        "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"BOLT.BA"},
    "BPAT":  {"nombre":"Banco Patagonia",              "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"BPAT.BA"},
    "CADO":  {"nombre":"Carlos Casado",                "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CADO.BA"},
    "CAPX":  {"nombre":"Capex",                        "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CAPX.BA"},
    "CARC":  {"nombre":"Carboclor",                    "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CARC.BA"},
    "CELU":  {"nombre":"Celulosa Argentina",           "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CELU.BA"},
    "CGPA2": {"nombre":"Camuzzi Gas Pampeana",         "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CGPA2.BA"},
    "CTIO":  {"nombre":"Consultatio",                  "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CTIO.BA"},
    "CVH":   {"nombre":"Cablevisión Holding",          "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"CVH.BA"},
    "DGCU2": {"nombre":"Distribuidora de Gas Cuyana",  "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"DGCU2.BA"},
    "FERR":  {"nombre":"Ferrum",                       "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"FERR.BA"},
    "FIPL":  {"nombre":"Fiplasto",                     "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"FIPL.BA"},
    "GCDI":  {"nombre":"GCDI S.A. (ex TGLT)",          "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"GCDI.BA"},
    "GRIM":  {"nombre":"Grimoldi",                     "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"GRIM.BA"},
    "HARG":  {"nombre":"Holcim Argentina",             "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"HARG.BA"},
    "INTR":  {"nombre":"Indupa",                       "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"INTR.BA"},
    "INVJ":  {"nombre":"Inversora Juramento",          "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"INVJ.BA"},
    "IRSA":  {"nombre":"IRSA Inv. y Representaciones", "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"IRSA.BA"},
    "LEDE":  {"nombre":"Ledesma",                      "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"LEDE.BA"},
    "LONG":  {"nombre":"Longvie",                      "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"LONG.BA"},
    "MOLA":  {"nombre":"Molinos Agro",                 "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"MOLA.BA"},
    "MOLI":  {"nombre":"Molinos Río de la Plata",      "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"MOLI.BA"},
    "MORI":  {"nombre":"Morixe Hermanos",              "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"MORI.BA"},
    "OEST":  {"nombre":"Autopistas del Oeste",         "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"OEST.BA"},
    "PATA":  {"nombre":"Importadora de la Patagonia",  "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"PATA.BA"},
    "RIGO":  {"nombre":"Rigolleau",                    "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"RIGO.BA"},
    "SAMI":  {"nombre":"San Miguel",                   "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"SAMI.BA"},
    "SEMI":  {"nombre":"Molinos Juan Semino",          "panel":"General", "ratio_adr":None, "exchange":"BYMA","currency":"ARS","yf_ticker":"SEMI.BA"},
}

# ─── OBLIGACIONES NEGOCIABLES (Renta fija corporativa — MAE/BYMA) ─────────────
# Convenciones: "30/360" | "ACT/365" | "ACT/ACT"
# Esquemas:     "BULLET" | "AMORTIZING"
# vn_residual:  fracción del VN original pendiente de amortizar (1.0 = sin amortizar capital)
# meses_cupon:  meses del año en que paga cupón (alineado al día del vencimiento)
OBLIGACIONES_NEGOCIABLES = {
    # ── YPF S.A. (Energía) ───────────────────────────────────────────────────
    "YMCQO": {
        "emisor": "YPF S.A.", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0700, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2033-09-30", "meses_cupon": [3, 9],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-09-30", "2027-03-30"],
    },
    "YMCHO": {
        "emisor": "YPF S.A.", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0900, "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING", "convencion_dias": "30/360",
        "fecha_vencimiento": "2029-06-30", "meses_cupon": [6, 12],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-06-30", "2026-12-30"],
    },
    "YMCIO": {
        "emisor": "YPF S.A.", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0700, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2026-07-28", "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-07-28"],
    },
    # ── Pampa Energía S.A. (Energía) ─────────────────────────────────────────
    "MGCCO": {
        "emisor": "Pampa Energía", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0795, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2029-12-08", "meses_cupon": [6, 12],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-06-08", "2026-12-08"],
    },
    "MCDCO": {
        "emisor": "Pampa Energía", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0650, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2027-04-14", "meses_cupon": [4, 10],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-10-14", "2027-04-14"],
    },
    # ── Pan American Energy (PAE) ─────────────────────────────────────────────
    "PNDCO": {
        "emisor": "Pan American Energy", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0850, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2027-04-30", "meses_cupon": [4, 10],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-10-30", "2027-04-30"],
    },
    "PNXOO": {
        "emisor": "Pan American Energy", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0500, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2026-11-26", "meses_cupon": [5, 11],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-11-26"],
    },
    # ── Telecom Argentina S.A. (Telecomunicaciones) ───────────────────────────
    "TLC5O": {
        "emisor": "Telecom Argentina", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0800, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2026-07-18", "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-07-18"],
    },
    "TLCMO": {
        "emisor": "Telecom Argentina", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0780, "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING", "convencion_dias": "30/360",
        "fecha_vencimiento": "2031-12-15", "meses_cupon": [6, 12],
        "vn_residual": 0.85,
        "proximos_cupones_estimados": ["2026-06-15", "2026-12-15"],
    },
    # ── IRSA Inversiones y Representaciones S.A. (Real Estate) ───────────────
    "IRCFO": {
        "emisor": "IRSA", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0800, "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2028-06-22", "meses_cupon": [6, 12],
        "vn_residual": 0.70,
        "proximos_cupones_estimados": ["2026-06-22", "2026-12-22"],
    },
    # ── Cresud S.A.C.I.F. y A. (Agro / Real Estate) — vencido 2026-03-04 ────
    "CSGJO": {
        "emisor": "Cresud", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0800, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2026-03-04", "meses_cupon": [3, 9],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": [],   # ya vencido — se conserva para historial
    },
    # ── Compañía General de Combustibles S.A. — CGC (AA.ar) ──────────────────
    "CPYOO": {
        "emisor": "CGC S.A.", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0650, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2027-02-17", "meses_cupon": [2, 8],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-08-17", "2027-02-17"],
    },
    "CPXOO": {
        "emisor": "CGC S.A.", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0550, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2026-03-09", "meses_cupon": [3, 9],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": [],   # ya vencido (vto 2026-03-09) — historial
    },
    # ── Vista Energy Argentina S.A. (AAA.ar) ─────────────────────────────────
    "VCSXO": {
        "emisor": "Vista Energy", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0350, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2026-08-10", "meses_cupon": [2, 8],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-08-10"],
        # Nota: TNA baja (3.5%) → AAA.ar; paridad esperada > 100; TIR un dígito bajo.
        # Precio > 100 no es anomalía en este instrumento.
    },
    # ── MSU Energy S.A. (A-.ar) ───────────────────────────────────────────────
    "MUNXO": {
        "emisor": "MSU Energy", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0687, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2027-05-14", "meses_cupon": [5, 11],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-11-14", "2027-05-14"],
    },
    # ── Transportadora de Gas del Sur S.A. — TGS (AAA.ar) ────────────────────
    "TSC2O": {
        "emisor": "TGS S.A.", "moneda_emision": "USD", "ley": "Nueva York",
        "tasa_nominal_anual": 0.0675, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "30/360",
        "fecha_vencimiento": "2029-05-02", "meses_cupon": [5, 11],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-11-02", "2027-05-02"],
    },
    # ── Generación Mediterránea / Albanesi (A-.ar) ────────────────────────────
    "MRCEO": {
        "emisor": "Albanesi", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0950, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2027-07-14", "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-07-14", "2027-01-14"],
    },
    # ── Central Puerto S.A. (AA+.ar) ─────────────────────────────────────────
    "BPCUO": {
        "emisor": "Central Puerto", "moneda_emision": "USD", "ley": "Local",
        "tasa_nominal_anual": 0.0625, "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET", "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2026-12-15", "meses_cupon": [6, 12],
        "vn_residual": 1.0,
        "proximos_cupones_estimados": ["2026-06-15", "2026-12-15"],
    },
}

# ─── SECTORES (para clasificación) ────────────────────────────────────────────
# Fuente: ratios cedears.txt columna "Area" (2026-05)
SECTORES = {
    # Tecnología
    "AAPL":"Tecnología","MSFT":"Tecnología","GOOGL":"Tecnología","NVDA":"Tecnología",
    "AMD":"Tecnología","ADBE":"Tecnología","ACN":"Tecnología","ADS":"Tecnología",
    "AMAT":"Tecnología","ARM":"Tecnología","AVGO":"Tecnología","BB":"Tecnología",
    "CSCO":"Tecnología","DOCU":"Tecnología","EA":"Tecnología","GLOB":"Tecnología",
    "HPQ":"Tecnología","IBM":"Tecnología","INFY":"Tecnología","INTC":"Tecnología",
    "LRCX":"Tecnología","MRVL":"Tecnología","NTES":"Tecnología",
    "ORCL":"Tecnología","PLTR":"Tecnología","QCOM":"Tecnología",
    "SAP":"Tecnología","SMSN":"Tecnología","SNOW":"Tecnología","SWKS":"Tecnología",
    "TXN":"Tecnología","TWLO":"Tecnología","XROX":"Tecnología","ZM":"Tecnología",
    "NEC1":"Tecnología","SONY":"Tecnología","TSM":"Tecnología","SIEGY":"Tecnología",
    "SDA":"Tecnología","PBI":"Tecnología","ADI":"Tecnología","ADP":"Tecnología",
    "MU":"Tecnología","MSTR":"Tecnología","PANW":"Tecnología","RBLX":"Tecnología",
    "SATL":"Tecnología","KEEL":"Tecnología","HUT":"Tecnología","HHPD":"Tecnología",
    "CAJ":"Tecnología","PCRF":"Tecnología","ARKK":"ETF",
    # Comunicaciones
    "AMZN":"Comunicaciones","META":"Comunicaciones","NFLX":"Comunicaciones",
    "BABA":"Comunicaciones","BIDU":"Comunicaciones","DESP":"Comunicaciones",
    "EBAY":"Comunicaciones","ERIC":"Comunicaciones","ETSY":"Comunicaciones",
    "GLW":"Comunicaciones","JD":"Comunicaciones","MELI":"Comunicaciones",
    "MSI":"Comunicaciones","SNAP":"Comunicaciones",
    "SPOT":"Comunicaciones","T":"Comunicaciones","TCOM":"Comunicaciones",
    "TIIAY":"Comunicaciones","TMUS":"Comunicaciones","TRIP":"Comunicaciones",
    "TV":"Comunicaciones","VIV":"Comunicaciones","VOD":"Comunicaciones",
    "WBO":"Comunicaciones","PINS":"Comunicaciones","ROKU":"Comunicaciones",
    "TEFO":"Comunicaciones","ORAN":"Comunicaciones","DTEA":"Comunicaciones",
    "AMX":"Comunicaciones","YY":"Comunicaciones","NGG":"Comunicaciones",
    "SE":"Comunicaciones","SHPW":"Comunicaciones","TWTR":"Comunicaciones",
    "TIMB":"Comunicaciones",
    # Consumo Defensivo
    "ABBV":"Consumo Def.","ABT":"Consumo Def.","AMGN":"Consumo Def.",
    "AVY":"Consumo Def.","BIIB":"Consumo Def.","BIOX":"Consumo Def.",
    "BMY":"Consumo Def.","BNG":"Consumo Def.","BRFS":"Consumo Def.",
    "CAH":"Consumo Def.","CL":"Consumo Def.","CVS":"Consumo Def.",
    "DEO":"Consumo Def.","GSK":"Consumo Def.","ISRG":"Consumo Def.",
    "JNJ":"Consumo Def.","KOFM":"Consumo Def.","KMB":"Consumo Def.",
    "KO":"Consumo Def.","LLY":"Consumo Def.","LND":"Consumo Def.",
    "MDLZ":"Consumo Def.","MDT":"Consumo Def.","MO":"Consumo Def.",
    "MRNA":"Consumo Def.","MRK":"Consumo Def.","NVS":"Consumo Def.",
    "PEP":"Consumo Def.","PFE":"Consumo Def.","PG":"Consumo Def.",
    "PHG":"Consumo Def.","PM":"Consumo Def.","SBS":"Consumo Def.",
    "SBUX":"Consumo Def.","SPGI":"Consumo Def.","SYY":"Consumo Def.",
    "TMO":"Consumo Def.","UL":"Consumo Def.","UNH":"Consumo Def.",
    "VRSN":"Consumo Def.","WBA":"Consumo Def.","WMT":"Consumo Def.",
    "AKO.B":"Consumo Def.","ELP":"Consumo Def.","PSO":"Consumo Def.",
    "GILD":"Consumo Def.","AAP":"Consumo Def.","URBN":"Consumo Def.",
    "BSN":"Consumo Def.","NTCO":"Consumo Def.","HAPV3":"Salud",
    # Consumo Cíclico
    "ANF":"Consumo Ciclico","ARCO":"Consumo Ciclico","ABNB":"Consumo Ciclico",
    "AAL":"Consumo Ciclico","BKNG":"Consumo Ciclico","CAR":"Consumo Ciclico",
    "CCL":"Consumo Ciclico","COST":"Consumo Ciclico","DAL":"Consumo Ciclico",
    "DISN":"Consumo Ciclico","GM":"Consumo Ciclico","GT":"Consumo Ciclico",
    "HD":"Consumo Ciclico","HMC":"Consumo Ciclico","HOG":"Consumo Ciclico",
    "LVS":"Consumo Ciclico","MBG":"Consumo Ciclico","MCD":"Consumo Ciclico",
    "NIO":"Consumo Ciclico","NKE":"Consumo Ciclico","NSAN":"Consumo Ciclico",
    "ORLY":"Consumo Ciclico","PCAR":"Consumo Ciclico","RACE":"Consumo Ciclico",
    "ROST":"Consumo Ciclico","SONY":"Consumo Ciclico",
    "STLA":"Consumo Ciclico","TGT":"Consumo Ciclico","TJX":"Consumo Ciclico",
    "TM":"Consumo Ciclico","TSLA":"Consumo Ciclico",
    "SPCE":"Consumo Ciclico","SQ":"Consumo Ciclico",
    "UAL":"Consumo Ciclico","UBER":"Consumo Ciclico","F":"Consumo Ciclico",
    "TTM":"Consumo Ciclico","LREN3":"Consumo Ciclico","MGLU3":"Consumo Ciclico",
    "RENT3":"Consumo Ciclico","JMIA":"Consumo Ciclico","CBRB":"Consumo Ciclico",
    # Financiero
    "AXP":"Financiero","BAC":"Financiero","BBD":"Financiero","BBV":"Financiero",
    "BCS":"Financiero","BK":"Financiero","BRKB":"Financiero",
    "BSBR":"Financiero","C":"Financiero","COIN":"Financiero",
    "FNMA":"Financiero","GS":"Financiero","HDB":"Financiero",
    "HSBC":"Financiero","IBN":"Financiero","ING":"Financiero","ITUB":"Financiero",
    "JPM":"Financiero","KB":"Financiero","LYG":"Financiero","MA":"Financiero",
    "MFG":"Financiero","MMC":"Financiero","MUFG":"Financiero",
    "NMR":"Financiero","NU":"Financiero","PAGS":"Financiero","PKS":"Financiero",
    "SAN":"Financiero","SCHW":"Financiero","STNE":"Financiero","TRVV":"Financiero",
    "USB":"Financiero","V":"Financiero","WFC":"Financiero","XP":"Financiero",
    "AEG":"Financiero","LFC":"Financiero","BBAS3":"Financiero","SI":"Financiero",
    # Energía
    "BKR":"Energía","BP":"Energía","CVX":"Energía","E":"Energía",
    "EOAN":"Energía","EQNR":"Energía","FSLR":"Energía","GPRK":"Energía",
    "HAL":"Energía","OGZD":"Energía","PSX":"Energía","SLB":"Energía",
    "SHEL":"Energía","TTE":"Energía","UGP":"Energía",
    "VIST":"Energía","XOM":"Energía","YZCA":"Energía","ATAD":"Energía",
    "LKOD":"Energía","PBR":"Energía","OXY":"Energía","PRIO3":"Energía",
    "SNP":"Energía","PTR":"Energía","HNPIY":"Energía",
    # Industria
    "BA":"Industria","CAT":"Industria","CX":"Industria",
    "DE":"Industria","DESP":"Industria","ERJ":"Industria",
    "FDX":"Industria","GE":"Industria","HON":"Industria",
    "HWM":"Industria","JCI":"Industria","LMT":"Defensa",
    "MMM":"Industria","PAC":"Industria","RTX":"Industria","SNA":"Industria",
    "TEN":"Industria","UNP":"Industria","ASR":"Industria",
    # Materiales
    "AEM":"Materiales","BAK":"Materiales","BAS":"Materiales","BAYN":"Materiales",
    "BHP":"Materiales","CDE":"Materiales","DD":"Materiales","DOW":"Materiales",
    "GFI":"Materiales","GGB":"Materiales","GOLD":"Materiales",
    "HL":"Materiales","HMY":"Materiales","IFF":"Materiales","IP":"Materiales",
    "KGC":"Materiales","LAAC":"Materiales","MUX":"Materiales",
    "NEM":"Materiales","NG":"Materiales","NLM":"Materiales","NUE":"Materiales",
    "NXE":"Materiales","PAAS":"Materiales","RIO":"Materiales","SCCO":"Materiales",
    "SID":"Materiales","SUZ":"Materiales","TXR":"Materiales","VALE":"Materiales",
    "X":"Materiales","MOS":"Materiales","AUY":"Materiales","AOCA":"Materiales",
    # ETFs
    "GLD":"Cobertura","SPY":"ETF","QQQ":"ETF","DIA":"ETF","IWM":"ETF",
    "FXI":"ETF","IBIT":"ETF","SH":"ETF","IEUR":"ETF","ETHA":"ETF",
    "EWZ":"ETF","EEM":"ETF","IBB":"ETF","IVW":"ETF","IVE":"ETF","VEA":"ETF",
    "XLE":"ETF","XLF":"ETF","XLC":"ETF","XLY":"ETF","XLP":"ETF",
    "XLV":"ETF","XLI":"ETF","XLB":"ETF","XLRE":"ETF","XLK":"ETF","XLU":"ETF",
    "URA":"ETF","SMH":"ETF","SPXL":"ETF","CIBR":"ETF","TQQQ":"ETF",
    "VXX":"ETF","ITA":"ETF","ICLN":"ETF","EWY":"ETF","XME":"ETF","RSP":"ETF",
    # Acciones brasileñas B3
    "VALE3":"Materiales","PETR3":"Energía","BBDC3":"Financiero",
    "BBAS3":"Financiero","PRIO3":"Energía","RENT3":"Consumo Ciclico",
    "MGLU3":"Consumo Ciclico","ITUB3":"Financiero","LREN3":"Consumo Ciclico",
    "HAPV3":"Salud","SUZB3":"Materiales","ABEV3":"Consumo Def.",
    "CSNA3":"Materiales","BPA11":"Financiero","NATU3":"Consumo Def.",
    "WEGE3":"Industria","SBSP3":"Consumo Def.","VIVT3":"Comunicaciones",
    "TIMS3":"Comunicaciones",
    # Nuevos CEDEARs 2026
    "ANET":"Tecnología","CRWD":"Tecnología","NBIS":"Tecnología",
    "SNDK":"Tecnología","FISV":"Financiero","ONDS":"Tecnología",
    "HIMS":"Salud","CCJ":"Materiales","MP":"Materiales",
    "NEE":"Energía","COP":"Energía","GLNG":"Energía","O":"Real Estate",
    # Acciones locales
    "YPFD":"Energía Local","CEPU":"Energía Local","TGNO4":"Energía Local",
    "PAMP":"Energía Local","GGAL":"Financiero","BMA":"Financiero",
    "SUPV":"Financiero","LOMA":"Materiales","TXAR":"Materiales",
    "AGRO":"Consumo Def.","IRSA":"Real Estate","MOLI":"Consumo Def.",
    "ALUA":"Materiales","BYMA":"Financiero","CRES":"Consumo Def.",
    "MIRG":"Industria","BOLT":"Industria","COME":"Industria",
}

# ─── UNIVERSOS CANÓNICOS PARA SCORING Y ANÁLISIS FUNDAMENTAL ─────────────────
#
# FUENTE ÚNICA DE VERDAD para qué tickers se analizan.
#
# Regla de inclusión CEDEAR:
#   ticker ∈ RATIOS_CEDEAR   → tiene ratio BYMA, se puede operar en ARS
#   ticker ∈ SECTORES        → tiene sector, el motor de scoring lo puede clasificar
#   ticker ∉ TICKERS_NO_CEDEAR_BYMA  → no es una acción extranjera directa
#
# Para agregar un nuevo CEDEAR al scoring:
#   1. Agregar a RATIOS_CEDEAR con su ratio (encima, en la sección correspondiente).
#   2. Agregar a SECTORES con su sector.
#   → Aparece automáticamente en UNIVERSO_CEDEARS_SCORING.
#
# Los ETFs (GLD, SPY, QQQ, etc.) están incluidos porque son negociados en ARS
# como CEDEAR y tienen scoring técnico válido (momentum, SMA). El scoring
# fundamental los omite internamente (P/E, ROE = N/A).
#
UNIVERSO_CEDEARS_SCORING: list[str] = sorted(
    t for t in RATIOS_CEDEAR
    if t in SECTORES and t not in TICKERS_NO_CEDEAR_BYMA
)

# Acciones del panel Merval/local (no son CEDEARs, cotizan en .BA)
# Mantenidos aquí para que scoring_engine y otros módulos compartan la misma lista.
UNIVERSO_MERVAL_SCORING: list[str] = [
    "YPFD", "CEPU", "TGNO4", "TGSU2", "PAMP",
    "GGAL", "BMA",  "SUPV",  "BBAR",
    "ALUA", "BYMA", "CRES",  "IRSA", "MIRG",
    "LOMA", "TXAR", "AGRO",  "MOLI", "VALO",
]

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

# ─── PERFILES DE RIESGO — Restricciones por perfil ───────────────────────────
# Cotas usadas por el optimizador para armar carteras según perfil del cliente.
# max_renta_variable / min_renta_fija : límites de asset class (suma de pesos)
# max_por_ticker_rv / rf              : concentración máxima por instrumento
# max_exposicion_local_rv             : techo de acciones argentinas en la parte RV
# volatilidad_max_anual               : vol. anualizada máxima tolerada (σ portafolio)
# sectores_excluidos                  : lista de strings que deben quedar fuera
RESTRICCIONES_POR_PERFIL = {
    # ── CONSERVADOR ────────────────────────────────────────────────────────────
    # Preservación de capital en USD.  Mínimo 55 % RF, baja tolerancia a duration.
    "CONSERVADOR": {
        "max_renta_variable":        0.45,
        "min_renta_fija":            0.55,
        "max_por_ticker_rv":         0.08,
        "max_por_ticker_rf":         0.15,
        "max_exposicion_local_rv":   0.05,
        "volatilidad_max_anual":     0.12,
        # Riesgo de tasa: duration modificada promedio ponderado del tramo RF
        "max_duration_modificada":   3.5,   # años — ONs cortas o hasta 2028
        # Riesgo de mercado: beta promedio ponderado del tramo RV
        "max_beta_ponderado_rv":     0.80,  # portafolio defensivo vs benchmark
        "sectores_excluidos": ["Tecnología de Alta Volatilidad", "Criptoassets"],
    },
    # ── MODERADO ───────────────────────────────────────────────────────────────
    # Balance retorno/riesgo.  50/50 RV-RF con duration media.
    "MODERADO": {
        "max_renta_variable":        0.50,
        "min_renta_fija":            0.50,
        "max_por_ticker_rv":         0.07,
        "max_por_ticker_rf":         0.10,
        "max_exposicion_local_rv":   0.15,
        "volatilidad_max_anual":     0.22,
        "max_duration_modificada":   5.0,   # años — ONs hasta 2030
        "max_beta_ponderado_rv":     1.00,  # beta neutro vs S&P500
        "sectores_excluidos": [],
    },
    # ── AGRESIVO ────────────────────────────────────────────────────────────────
    # Crecimiento en USD.  Hasta 70 % RV, duration más larga tolerada.
    "AGRESIVO": {
        "max_renta_variable":        0.70,
        "min_renta_fija":            0.30,
        "max_por_ticker_rv":         0.15,
        "max_por_ticker_rf":         0.05,
        "max_exposicion_local_rv":   0.25,
        "volatilidad_max_anual":     0.38,
        "max_duration_modificada":   7.0,   # años — ONs largas (YPF 2033, etc.)
        "max_beta_ponderado_rv":     1.30,  # búsqueda activa de alfa
        "sectores_excluidos": [],
    },
    # ── MUY AGRESIVO ────────────────────────────────────────────────────────────
    # Maximización de retorno.  Hasta 85 % RV, sin restricción de sector.
    "MUY AGRESIVO": {
        "max_renta_variable":        0.85,
        "min_renta_fija":            0.15,
        "max_por_ticker_rv":         0.15,
        "max_por_ticker_rf":         0.05,
        "max_exposicion_local_rv":   0.25,
        "volatilidad_max_anual":     0.38,
        "max_duration_modificada":  10.0,   # sin restricción práctica de duration
        "max_beta_ponderado_rv":     1.60,  # portafolio high-beta
        "sectores_excluidos": [],
    },
}

# ─── EXCLUSIONES ÉTICAS — Mapeo categoría → tickers ─────────────────────────
# Permite que PERFIL_INVERSOR_CODIFICADO.restricciones_eticas use nombres
# legibles ("Tabaco") y el filtro los resuelva a tickers concretos.
# Actualizar si se incorporan nuevos activos al universo.
EXCLUSIONES_ETICAS = {
    "Tabaco":      ["MO", "PM"],                     # Altria, Philip Morris
    "Armamento":   ["LMT", "RTX", "BA"],             # Lockheed, Raytheon, Boeing
    "Juego":       ["LVS"],                          # Las Vegas Sands
    "Criptoassets":["IBIT", "ETHA", "MSTR"],         # ETFs y proxies crypto
    "Alcohol":     [],                               # ninguno en universo actual
    "Cannabis":    [],
}

# ─── PERFIL DEL INVERSOR CODIFICADO ──────────────────────────────────────────
# Simulación de salida de base de datos — un registro por cliente / arquetipo.
# En producción estos datos vienen de DB; aquí sirven de defaults y tests.
#
# horizonte_inversion_anios  : afecta selección de Duration máxima en ONs
# necesidad_liquidez_pct     : fracción de cartera en activos ADV alto (< 30 días)
# objetivo_retorno_usd_anual : target μ para optimización media-varianza
# tolerancia_drawdown_max    : umbral implícito de drawdown mensual tolerable
# moneda_objetivo            : "USD" = Hard Dollar / "ARS_Real" = tasa real local
# restricciones_eticas       : lista de keys de EXCLUSIONES_ETICAS
# excluir_criptoassets       : atajo rápido para excluir tipo "alternativo" en ETF_INFO
PERFIL_INVERSOR_CODIFICADO = {
    "CLIENTE_DEFAULT_MODERADO": {
        "horizonte_inversion_anios":  3,
        "necesidad_liquidez_pct":     0.10,    # 10 % en activos con ADV alto
        "objetivo_retorno_usd_anual": 0.085,   # target 8.5 % anual USD
        "tolerancia_drawdown_max":   -0.15,    # máximo -15 % mensual tolerable
        "moneda_objetivo":            "USD",
        "restricciones_eticas":       [],
        "excluir_criptoassets":       False,
    },
    "CLIENTE_RETIRO_CONSERVADOR": {
        "horizonte_inversion_anios":  7,
        "necesidad_liquidez_pct":     0.20,    # 20 % líquido (retiro parcial anual)
        "objetivo_retorno_usd_anual": 0.055,
        "tolerancia_drawdown_max":   -0.07,
        "moneda_objetivo":            "USD",
        "restricciones_eticas":       ["Tabaco", "Armamento"],
        "excluir_criptoassets":       True,
    },
    "CLIENTE_JOVEN_AGRESIVO": {
        "horizonte_inversion_anios": 10,
        "necesidad_liquidez_pct":     0.00,
        "objetivo_retorno_usd_anual": 0.140,
        "tolerancia_drawdown_max":   -0.30,
        "moneda_objetivo":            "ARS_Real",  # maximizar tasa real vs IPC
        "restricciones_eticas":       [],
        "excluir_criptoassets":       False,
    },
}

# ─── LIQUIDEZ OPERATIVA BYMA — ADV en millones ARS ───────────────────────────
# Volumen diario promedio operado en BYMA (últimos 30 días, millones ARS).
# Usado por restriccion_liquidez() para escalar posición máxima a fracción del ADV.
# Instrumentos no listados aquí usan el default de 50 M ARS.
VOLUMEN_PROMEDIO_BYMA = {
    # CEDEARs más líquidos
    "AAPL":  4800.0,
    "AMZN":  4200.0,
    "NVDA":  5500.0,
    "MSFT":  3900.0,
    "MELI":  4600.0,
    "META":  3100.0,
    "TSLA":  3800.0,
    "KO":    2900.0,
    "XOM":   2100.0,
    "VALE":  1800.0,
    # Acciones locales
    "GGAL":  6200.0,
    "YPFD":  4900.0,
    "PAMP":  3800.0,
    "BMA":   3200.0,
    "ALUA":  2500.0,
    "TXAR":  2400.0,
    "CEPU":  1900.0,
    "CRES":  1500.0,
    "TGSU2": 1400.0,
    "EDN":   1100.0,
    # ONs corporativas
    "YMCQO": 1200.0,
    "YMCHO":  950.0,
    "MGCCO":  850.0,
    "TLC5O":  700.0,
    "TLCMO":  650.0,
    "IRCFO":  500.0,
    "PNDCO":  450.0,
    "CSGJO":  400.0,
    # Bonos soberanos USD (Bonares y Globales — los mas liquidos de BYMA)
    "AL30":  18500.0,   # muy liquido — referencia de mercado
    "GD30":  16200.0,   # Global 2030 Ley NY — alta liquidez
    "AL35":  12800.0,
    "GD35":  11500.0,
    "AE38":   8900.0,
    "GD41":   7200.0,
    # BOPREAL — liquidez intermedia
    "BPA27":  3200.0,
    "BPJ27":  2800.0,
    # Bonos CER (liquidez moderada)
    "TX26":   5400.0,   # muy liquido por vencimiento proximo
    "TX28":   4100.0,
    "TZXD7":  3600.0,
    "DICP":   2200.0,
    # Cauciones: liquidez instantanea (no tienen ADV como bono pero se modelan alta)
    "CAUCION_ARS_1D":  99000.0,  # liquido al dia siguiente
    "CAUCION_ARS_7D":  75000.0,
    "CAUCION_ARS_30D": 45000.0,
    "CAUCION_USD_30D": 12000.0,
}
# Valor por defecto para instrumentos sin registro de ADV
VOLUMEN_PROMEDIO_BYMA_DEFAULT = 50.0  # millones ARS
# Umbral de liquidez inmediata: activo considerado "líquido" si ADV ≥ este valor
ADV_LIQUIDEZ_MINIMA = 1500.0          # millones ARS (~30 días de ruedas)

# ─── DATOS FUNDAMENTALES — Filtros de valor por ticker ───────────────────────
# Métricas de valuación y riesgo de mercado para análisis fundamental.
# pe            : Price/Earnings (TTM)
# ev_ebitda     : EV/EBITDA (None si no aplica — bancos, holdings)
# dividend_yield: rendimiento por dividendo (decimal, ej. 0.031 = 3.1%)
# beta          : beta vs S&P500 (52 semanas)
# Fuente: Bloomberg / Yahoo Finance — actualizar trimestralmente
DATOS_FUNDAMENTALES = {
    "AAPL": {"pe": 31.5, "ev_ebitda": 22.1, "dividend_yield": 0.0055, "beta": 1.12},
    "MSFT": {"pe": 35.2, "ev_ebitda": 24.5, "dividend_yield": 0.0072, "beta": 1.08},
    "NVDA": {"pe": 68.4, "ev_ebitda": 45.2, "dividend_yield": 0.0002, "beta": 1.68},
    "KO":   {"pe": 24.1, "ev_ebitda": 18.2, "dividend_yield": 0.0310, "beta": 0.58},
    "XOM":  {"pe": 12.8, "ev_ebitda":  7.8, "dividend_yield": 0.0345, "beta": 0.75},
    "MELI": {"pe": 48.2, "ev_ebitda": 28.4, "dividend_yield": 0.0000, "beta": 1.42},
    "VALE": {"pe":  7.5, "ev_ebitda":  4.8, "dividend_yield": 0.0620, "beta": 0.95},
    "GGAL": {"pe":  6.2, "ev_ebitda": None, "dividend_yield": 0.0250, "beta": 1.45},
    "YPFD": {"pe":  8.1, "ev_ebitda":  4.2, "dividend_yield": 0.0000, "beta": 1.38},
    "PAMP": {"pe":  9.4, "ev_ebitda":  5.1, "dividend_yield": 0.0000, "beta": 1.15},
    "ALUA": {"pe": 11.2, "ev_ebitda":  7.4, "dividend_yield": 0.0410, "beta": 0.82},
    "TXAR": {"pe": 10.5, "ev_ebitda":  6.9, "dividend_yield": 0.0480, "beta": 0.85},
}

# ─── ETF_INFO — Parámetros estructurales de fondos cotizados ─────────────────
# Los ETFs NO se evalúan con métricas de empresa (P/E, ROE, rev_growth).
# Sus criterios de selección son: costo de administración (TER) y masa crítica (AUM).
#
# indice      : índice subyacente que replica el ETF
# ter         : Total Expense Ratio anual (decimal — 0.0009 = 0.09 %)
# aum_bn_usd  : Activos bajo gestión en miles de millones USD
# tipo        : "renta_variable" | "cobertura" | "alternativo"
# subcategoria: descripción del universo de inversión
#
# Uso clave: mu_neto = mu_bruto - TER  (penalidad de retorno anualizada)
#            si tipo=="alternativo" → verificar excluir_criptoassets del perfil
ETF_INFO = {
    # Broad Market
    "SPY":  {"indice": "S&P 500 Index",          "ter": 0.0009, "aum_bn_usd": 530.5, "tipo": "renta_variable", "subcategoria": "Large Cap Blend"},
    "QQQ":  {"indice": "NASDAQ-100 Index",        "ter": 0.0020, "aum_bn_usd": 230.2, "tipo": "renta_variable", "subcategoria": "Tecnologia Growth"},
    "DIA":  {"indice": "Dow Jones Industrial",    "ter": 0.0016, "aum_bn_usd":  32.4, "tipo": "renta_variable", "subcategoria": "Value Blue Chips"},
    "IWM":  {"indice": "Russell 2000 Index",      "ter": 0.0019, "aum_bn_usd":  65.1, "tipo": "renta_variable", "subcategoria": "Small Caps"},
    # Cobertura y alternativos
    "GLD":  {"indice": "Gold Spot Price",         "ter": 0.0040, "aum_bn_usd":  70.8, "tipo": "cobertura",      "subcategoria": "Commodities"},
    "IBIT": {"indice": "Bitcoin Spot",            "ter": 0.0025, "aum_bn_usd":  41.2, "tipo": "alternativo",    "subcategoria": "Criptoassets"},
    # Emergentes y Latam
    "EEM":  {"indice": "MSCI Emerging Markets",   "ter": 0.0070, "aum_bn_usd":  18.5, "tipo": "renta_variable", "subcategoria": "Emergentes"},
    "EWZ":  {"indice": "MSCI Brazil Index",       "ter": 0.0058, "aum_bn_usd":   5.2, "tipo": "renta_variable", "subcategoria": "Latam Brasil"},
    # Sectoriales SPDR (TER bajo — competitivos)
    "XLU":  {"indice": "Utilities Sector SPDR",   "ter": 0.0009, "aum_bn_usd":  18.1, "tipo": "renta_variable", "subcategoria": "Defensivo Sectorial"},
    "XLK":  {"indice": "Technology Sector SPDR",  "ter": 0.0009, "aum_bn_usd":  68.4, "tipo": "renta_variable", "subcategoria": "Tecnologia Sectorial"},
    "XLF":  {"indice": "Financial Sector SPDR",   "ter": 0.0009, "aum_bn_usd":  42.3, "tipo": "renta_variable", "subcategoria": "Financiero Sectorial"},
    "XLE":  {"indice": "Energy Sector SPDR",      "ter": 0.0009, "aum_bn_usd":  38.7, "tipo": "renta_variable", "subcategoria": "Energia Sectorial"},
    # Temáticos
    "SMH":  {"indice": "VanEck Semiconductor",    "ter": 0.0035, "aum_bn_usd":  25.6, "tipo": "renta_variable", "subcategoria": "Semiconductores"},
    "URA":  {"indice": "Global X Uranium",        "ter": 0.0069, "aum_bn_usd":   3.8, "tipo": "renta_variable", "subcategoria": "Uranium Nuclear"},
    "CIBR": {"indice": "First Trust Cybersecurity","ter":0.0060, "aum_bn_usd":   6.4, "tipo": "renta_variable", "subcategoria": "Ciberseguridad"},
    "ICLN": {"indice": "iShares Global Clean Energy","ter":0.0040,"aum_bn_usd":  3.2, "tipo": "renta_variable", "subcategoria": "Energia Limpia"},
    "ITA":  {"indice": "iShares Aerospace Defense","ter":0.0040, "aum_bn_usd":   7.1, "tipo": "renta_variable", "subcategoria": "Aeroespacial Defensa"},
    # Apalancados / Inversos (alta volatilidad — sólo perfiles Agresivo+)
    "SPXL": {"indice": "S&P 500 3x Bull",         "ter": 0.0091, "aum_bn_usd":   2.8, "tipo": "apalancado",     "subcategoria": "3x Long SP500"},
    "TQQQ": {"indice": "NASDAQ-100 3x Bull",      "ter": 0.0086, "aum_bn_usd":  22.4, "tipo": "apalancado",     "subcategoria": "3x Long NASDAQ"},
}

# ─── DATOS FUNDAMENTALES EXTENDIDOS — Scoring multifactorial ─────────────────
# 25 activos: 18 CEDEARs líderes + 7 acciones Panel Merval
# Campos:
#   pe              : Price/Earnings TTM
#   pb              : Price/Book
#   roe             : Return on Equity (decimal — 1.60 = 160 %)
#   div_yield       : Dividend Yield (decimal — 0.031 = 3.1 %)
#   deuda_patrimonio: Deuda Neta / Patrimonio (None para bancos — ratio no estándar)
#   rev_growth_yoy  : Crecimiento de ingresos YoY (decimal — 0.16 = 16 %)
# Fuente: Yahoo Finance / Bloomberg — actualizar trimestralmente
# Nota: acciones argentinas usan balances ajustados por inflación (UVA / IPC)
DATOS_FUNDAMENTALES_EXTENDIDOS = {
    # ── CEDEARs — Tecnología ────────────────────────────────────────────────────
    "AAPL":  {"pe": 29.5, "pb": 45.2, "roe": 1.600, "div_yield": 0.0052, "deuda_patrimonio": 1.8, "rev_growth_yoy":  0.08},
    "MSFT":  {"pe": 35.1, "pb": 12.4, "roe": 0.350, "div_yield": 0.0075, "deuda_patrimonio": 0.3, "rev_growth_yoy":  0.16},
    "NVDA":  {"pe": 66.2, "pb": 38.1, "roe": 1.150, "div_yield": 0.0002, "deuda_patrimonio": 0.2, "rev_growth_yoy":  1.25},
    "GOOGL": {"pe": 23.4, "pb":  6.8, "roe": 0.290, "div_yield": 0.0050, "deuda_patrimonio": 0.1, "rev_growth_yoy":  0.14},
    "AMZN":  {"pe": 40.5, "pb":  8.2, "roe": 0.210, "div_yield": 0.0000, "deuda_patrimonio": 0.6, "rev_growth_yoy":  0.11},
    "META":  {"pe": 26.1, "pb":  7.9, "roe": 0.320, "div_yield": 0.0045, "deuda_patrimonio": 0.1, "rev_growth_yoy":  0.19},
    # ── CEDEARs — Consumo Defensivo ─────────────────────────────────────────────
    "KO":    {"pe": 24.3, "pb": 10.1, "roe": 0.420, "div_yield": 0.0310, "deuda_patrimonio": 1.4, "rev_growth_yoy":  0.04},
    "PEP":   {"pe": 25.8, "pb": 14.2, "roe": 0.540, "div_yield": 0.0295, "deuda_patrimonio": 2.1, "rev_growth_yoy":  0.05},
    # ── CEDEARs — Energía ───────────────────────────────────────────────────────
    "XOM":   {"pe": 12.4, "pb":  2.1, "roe": 0.160, "div_yield": 0.0345, "deuda_patrimonio": 0.2, "rev_growth_yoy": -0.02},
    "CVX":   {"pe": 13.1, "pb":  1.8, "roe": 0.130, "div_yield": 0.0410, "deuda_patrimonio": 0.1, "rev_growth_yoy": -0.04},
    # ── CEDEARs — Latam ─────────────────────────────────────────────────────────
    "MELI":  {"pe": 45.2, "pb": 22.4, "roe": 0.480, "div_yield": 0.0000, "deuda_patrimonio": 0.9, "rev_growth_yoy":  0.38},
    "VALE":  {"pe":  7.2, "pb":  1.4, "roe": 0.190, "div_yield": 0.0650, "deuda_patrimonio": 0.5, "rev_growth_yoy":  0.02},
    "PBR":   {"pe":  4.8, "pb":  1.2, "roe": 0.240, "div_yield": 0.1250, "deuda_patrimonio": 1.1, "rev_growth_yoy":  0.01},
    # ── CEDEARs — Diversificados ────────────────────────────────────────────────
    "JPM":   {"pe": 11.5, "pb":  1.6, "roe": 0.140, "div_yield": 0.0240, "deuda_patrimonio": None, "rev_growth_yoy": 0.07},  # banco: deuda/patrim N/A
    "WMT":   {"pe": 28.2, "pb":  7.1, "roe": 0.230, "div_yield": 0.0135, "deuda_patrimonio": 0.7, "rev_growth_yoy":  0.06},
    "V":     {"pe": 32.4, "pb": 31.2, "roe": 0.960, "div_yield": 0.0070, "deuda_patrimonio": 0.4, "rev_growth_yoy":  0.09},
    "JNJ":   {"pe": 15.4, "pb":  4.2, "roe": 0.260, "div_yield": 0.0320, "deuda_patrimonio": 0.5, "rev_growth_yoy":  0.04},
    "LLY":   {"pe": 75.1, "pb": 42.5, "roe": 0.580, "div_yield": 0.0040, "deuda_patrimonio": 1.2, "rev_growth_yoy":  0.28},
    # ── Acciones argentinas (balances ajustados por IPC) ────────────────────────
    "YPFD":  {"pe":  7.8, "pb":  0.9, "roe": 0.110, "div_yield": 0.0000, "deuda_patrimonio": 0.8, "rev_growth_yoy":  0.12},
    "GGAL":  {"pe":  5.9, "pb":  1.5, "roe": 0.250, "div_yield": 0.0310, "deuda_patrimonio": None, "rev_growth_yoy": 0.08},  # banco: deuda/patrim N/A
    "PAMP":  {"pe":  8.4, "pb":  1.1, "roe": 0.140, "div_yield": 0.0000, "deuda_patrimonio": 0.9, "rev_growth_yoy":  0.15},
    "ALUA":  {"pe": 10.8, "pb":  2.1, "roe": 0.180, "div_yield": 0.0450, "deuda_patrimonio": 0.2, "rev_growth_yoy":  0.05},
    "TXAR":  {"pe":  9.9, "pb":  1.8, "roe": 0.160, "div_yield": 0.0510, "deuda_patrimonio": 0.1, "rev_growth_yoy":  0.03},
    "CEPU":  {"pe":  7.2, "pb":  0.8, "roe": 0.120, "div_yield": 0.0280, "deuda_patrimonio": 0.4, "rev_growth_yoy":  0.09},
    "BMA":   {"pe":  6.4, "pb":  1.2, "roe": 0.200, "div_yield": 0.0420, "deuda_patrimonio": None, "rev_growth_yoy": 0.06},  # banco: deuda/patrim N/A
}

# ─── PESOS DEL SCORING MULTIFACTORIAL ────────────────────────────────────────
# Ajustables sin tocar la función de scoring.
# Distribución: 30 % Value | 40 % Quality | 30 % Growth + Income
# Suma de pesos = 1.0
PESOS_SCORING_FUNDAMENTAL = {
    "score_pe":     0.15,   # Value
    "score_pb":     0.15,   # Value
    "score_roe":    0.25,   # Quality — eficiencia sobre el patrimonio
    "score_deuda":  0.15,   # Quality — solidez financiera (menor = mejor)
    "score_growth": 0.20,   # Growth  — expansión de ingresos YoY
    "score_yield":  0.10,   # Income  — retorno de dividendos
}

# Mix técnico/fundamental para Alpha Screen (configurable)
ALPHA_SCREEN_MIX = {
    "fundamental": 0.60,   # peso del scoring factorial
    "tecnico":     0.40,   # peso de señales técnicas (RSI + SMA)
}

# ─── PARÁMETROS DE SIMULACIÓN HISTÓRICA ──────────────────────────────────────
# Controlan la descarga y preprocesamiento en core/historico_retornos.py
# ventana_dias     : ruedas bursátiles para la Matriz de Covarianza (Σ)
# ventana_corta    : ruedas para betas dinámicos (un trimestre comercial)
# min_obs_validos  : mínimo de ruedas con datos reales; activos por debajo se descartan
# frecuencia       : compresión OHLC ('1d' = velas diarias)
# benchmark_global : S&P 500 — benchmark para betas de CEDEARs e internacionales
# benchmark_local  : Merval   — benchmark para betas de acciones argentinas
# fill_method      : imputación de huecos por feriados locales/internacionales
PARAMETROS_HISTORICO = {
    "ventana_dias":      252,       # 1 año de ruedas bursátiles (Σ)
    "ventana_corta":      63,       # 3 meses — betas dinámicos
    "min_obs_validos":   120,       # mínimo de observaciones reales para no descartar
    "frecuencia":        "1d",      # velas diarias
    "benchmark_global":  "^GSPC",  # S&P 500
    "benchmark_local":   "^MERV",  # Índice Merval
    "fill_method":       "ffill",   # Forward Fill para feriados cruzados
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

# ─── VARIABLES MACROECONÓMICAS Y DE REFERENCIA DE MERCADO ────────────────────
# INPUTS DINÁMICOS — actualizar diariamente antes de ejecutar el optimizador.
#
# Campos:
#   ccl_promedio          : CCL promedio financiero (ARS por USD) — fuente: MAE / Rava
#   mep_promedio          : Dólar MEP (ARS por USD)              — fuente: BYMA
#   spread_ccl_mep        : (ccl / mep) - 1  — desvío típico ~1-2 %
#   embi_arg_bps          : Riesgo País Argentina en puntos básicos — fuente: JP Morgan
#   risk_free_rate_us     : Rendimiento T10Y EE.UU.               — fuente: FRED / Bloomberg
#   inflacion_mensual_ipc : Último IPC mensual publicado (INDEC)  — decimal
#   tna_plazo_fijo_30d    : TNA promedio sistema bancario, 30 días — fuente: BCRA
#   tasa_politica_monetaria: Tasa de referencia BCRA (LELIQ/Pases) — fuente: BCRA
#   prima_riesgo_global   : ERP global implícito (Damodaran, enero de cada año)
#   fecha_actualizacion   : ISO-8601 — auditoría del último update
#   fuente_datos          : organismos de referencia
MACRO_AR = {
    # Tipos de cambio financieros
    "ccl_promedio": 1493.1,   # ARS/USD — CCL para arbitraje CEDEAR
    "mep_promedio": 1470.7,   # ARS/USD — MEP para descalces locales
    "spread_ccl_mep": 0.0152,   # (CCL/MEP) - 1  ≈ 1.63 %

    # Riesgo soberano y tasa libre de riesgo
    "embi_arg_bps":             580,     # puntos básicos (580 bps = 5.80 %)
    "risk_free_rate_us":       0.0435,   # T10Y EE.UU.
    "prima_riesgo_global":     0.0550,   # ERP Damodaran — se actualiza en enero

    # Inflación y tasas nominales locales
    "inflacion_mensual_ipc": 0.0341,   # 3.0 % mensual — último IPC INDEC
    "tna_plazo_fijo_30d":      0.3840,   # TNA 38.4 % → TEM 3.2 %
    "tasa_politica_monetaria": 0.3480,   # BCRA — TNA 34.8 % → TEM 2.9 %

    # Auditoría
    "fecha_actualizacion": "2026-05-20",
    "fuente_datos":            "BCRA / MAE / BYMA / JP Morgan / INDEC",
}

# ─── BONOS SOBERANOS — Deuda soberana argentina USD ──────────────────────────
# Comparten estructura con OBLIGACIONES_NEGOCIABLES + campos adicionales:
#   tipo             : "BONO_USD" | "BOPREAL"
#   rating           : calificación crediticia (CCC = soberano 2026)
#   tir_mercado_ref  : TIR de mercado de referencia (descuento para duration)
#   duration_ref_anos: Duration Modificada pre-calculada (fallback rápido)
#   paridad_ref_pct  : precio actual como % del VN (para CCL implícito)
#   tasa_nominal_anual: cupón vigente (step-up ya resuelto a la tasa final del tramo actual)
#
# Notas de estructura:
#   AL30 / GD30 : step-up completado → cupón 3.875 % anual desde 2026
#   AL35 / GD35 : step-up completado → cupón 4.875 % anual desde 2026
#   Amortizaciones: aproximadas — validar contra prospecto ISIN oficial
#   BOPREAL BPA27 / BPJ27: bullet simple, emisor BCRA, colateral importadores
#
# Fuente paridad / TIR referencia: Bloomberg / MAE / Rava (2026-05)
BONOS_SOBERANOS = {
    # ── Bonares USD Ley Local ────────────────────────────────────────────────
    "AL30": {
        "nombre": "Bonar 2030",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Local",
        "rating": "CCC",
        "tasa_nominal_anual": 0.03875,   # step-up vigente (tasa final)
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2030-07-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,              # sin amortizacion de capital al 2026-05
        "tir_mercado_ref": 0.0923,
        "duration_ref_anos": 3.2,
        "paridad_ref_pct": 63.5,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09",
            "2028-07-09", "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09",
        ],
    },
    "AL35": {
        "nombre": "Bonar 2035",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Local",
        "rating": "CCC",
        "tasa_nominal_anual": 0.04875,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2035-07-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.0950,
        "duration_ref_anos": 6.0,
        "paridad_ref_pct": 73.8,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09", "2028-07-09",
            "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09", "2031-01-09",
            "2031-07-09", "2032-01-09", "2032-07-09", "2033-01-09", "2033-07-09",
            "2034-01-09", "2034-07-09", "2035-01-09", "2035-07-09",
        ],
    },
    "AE38": {
        "nombre": "Bonar 2038",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Local",
        "rating": "CCC",
        "tasa_nominal_anual": 0.04750,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2038-01-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.1071,
        "duration_ref_anos": 6.8,
        "paridad_ref_pct": 78.0,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09", "2028-07-09",
            "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09", "2031-01-09",
            "2031-07-09", "2032-01-09", "2032-07-09", "2033-01-09", "2033-07-09",
            "2034-01-09", "2034-07-09", "2035-01-09", "2035-07-09",
            "2036-01-09", "2036-07-09", "2037-01-09", "2037-07-09", "2038-01-09",
        ],
    },
    # ── Globales USD Ley Nueva York ──────────────────────────────────────────
    "GD30": {
        "nombre": "Global 2030",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Nueva York",
        "rating": "CCC",
        "tasa_nominal_anual": 0.03875,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "30/360",
        "fecha_vencimiento": "2030-07-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.0880,
        "duration_ref_anos": 3.0,
        "paridad_ref_pct": 66.0,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09",
            "2028-07-09", "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09",
        ],
    },
    "GD35": {
        "nombre": "Global 2035",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Nueva York",
        "rating": "CCC",
        "tasa_nominal_anual": 0.04875,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "30/360",
        "fecha_vencimiento": "2035-07-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.0910,
        "duration_ref_anos": 6.5,
        "paridad_ref_pct": 75.2,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09", "2028-07-09",
            "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09", "2031-01-09",
            "2031-07-09", "2032-01-09", "2032-07-09", "2033-01-09", "2033-07-09",
            "2034-01-09", "2034-07-09", "2035-01-09", "2035-07-09",
        ],
    },
    "GD41": {
        "nombre": "Global 2041",
        "emisor": "Republica Argentina",
        "tipo": "BONO_USD",
        "moneda_emision": "USD",
        "ley": "Nueva York",
        "rating": "CCC",
        "tasa_nominal_anual": 0.04875,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "convencion_dias": "30/360",
        "fecha_vencimiento": "2041-07-09",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.1010,
        "duration_ref_anos": 9.5,
        "paridad_ref_pct": 70.5,
        "proximos_cupones_estimados": [
            "2026-07-09", "2027-01-09", "2027-07-09", "2028-01-09", "2028-07-09",
            "2029-01-09", "2029-07-09", "2030-01-09", "2030-07-09", "2031-01-09",
            "2031-07-09", "2032-01-09", "2032-07-09", "2033-01-09", "2033-07-09",
        ],  # truncado — flujos posteriores via cashflow_ilustrativo
    },
    # ── BOPREAL — Bono para la Reconstruccion de una Argentina Libre ─────────
    # Emisor: BCRA. Respaldo: divisas diferidas de importadores (2023-2024).
    # Bullet simple: sin step-up. Liquidez intermedia en BYMA (menor que soberanos).
    "BPA27": {
        "nombre": "BOPREAL Serie 1-A 2027",
        "emisor": "BCRA",
        "tipo": "BOPREAL",
        "moneda_emision": "USD",
        "ley": "Local",
        "rating": "CCC",
        "tasa_nominal_anual": 0.0500,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET",
        "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2027-01-31",
        "meses_cupon": [1, 7],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.058,
        "duration_ref_anos": 0.65,
        "paridad_ref_pct": 98.5,
        "proximos_cupones_estimados": ["2026-07-31", "2027-01-31"],
    },
    "BPJ27": {
        "nombre": "BOPREAL Serie 3 2027",
        "emisor": "BCRA",
        "tipo": "BOPREAL",
        "moneda_emision": "USD",
        "ley": "Local",
        "rating": "CCC",
        "tasa_nominal_anual": 0.0300,
        "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET",
        "convencion_dias": "ACT/365",
        "fecha_vencimiento": "2027-05-31",
        "meses_cupon": [5, 11],
        "vn_residual": 1.0,
        "tir_mercado_ref": 0.072,
        "duration_ref_anos": 0.95,
        "paridad_ref_pct": 96.2,
        "proximos_cupones_estimados": ["2026-11-30", "2027-05-31"],
    },
}

# ─── BONOS CER — Instrumentos ajustados por inflacion (CER/UVA) ───────────────
# moneda_emision: "ARS_CER" — ARS ajustados por el CER (Coeficiente de
#   Estabilizacion de Referencia) publicado diariamente por BCRA.
#
# Modelo de retorno para el optimizador:
#   retorno_nominal_ars  = inflacion_anual + spread_real_anual
#   retorno_real_ars     = spread_real_anual
#   retorno_usd_implicito = (1 + retorno_nominal_ars) / (1 + devaluacion_esperada) - 1
#
# duration_real_anos: Duration Modificada calculada en terminos REALES
#   (descontando con tasa real = spread_real, no con tasa nominal)
#   Es la metrica correcta de sensibilidad al movimiento de tasas reales.
#
# inflacion_breakeven_pct: inflacion acumulada anual que iguala el retorno
#   de este bono CER con el de un bono USD de duration similar.
#
# Fuente paridades: MAE / BYMA (2026-05) | CER base: BCRA diario
BONOS_CER = {
    "TX26": {
        "nombre": "Boncer Jun 2026",
        "emisor": "Tesoro Nacional",
        "tipo": "BONCER",
        "moneda_emision": "ARS_CER",
        "ley": "Local",
        "spread_real_anual": 0.0000,     # CER + 0% — referencia de mercado
        "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET",
        "fecha_vencimiento": "2026-06-30",
        "meses_cupon": [6, 12],
        "vn_residual": 1.0,
        "duration_real_anos": 0.12,      # ~1.5 meses residuales
        "paridad_ref_pct": 99.5,
        "tir_real_mercado": 0.0000,
        "inflacion_breakeven_pct": None,
    },
    "TX28": {
        "nombre": "Boncer Nov 2028",
        "emisor": "Tesoro Nacional",
        "tipo": "BONCER",
        "moneda_emision": "ARS_CER",
        "ley": "Local",
        "spread_real_anual": 0.0025,     # CER + 0.25%
        "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET",
        "fecha_vencimiento": "2028-11-30",
        "meses_cupon": [5, 11],
        "vn_residual": 1.0,
        "duration_real_anos": 2.40,
        "paridad_ref_pct": 98.8,
        "tir_real_mercado": 0.0025,
        "inflacion_breakeven_pct": 42.5, # vs Bonar similar duration
    },
    "TZXD7": {
        "nombre": "Boncer Dic 2027",
        "emisor": "Tesoro Nacional",
        "tipo": "BONCER",
        "moneda_emision": "ARS_CER",
        "ley": "Local",
        "spread_real_anual": 0.0050,     # CER + 0.5%
        "frecuencia_pago": 2,
        "esquema_amortizacion": "BULLET",
        "fecha_vencimiento": "2027-12-31",
        "meses_cupon": [6, 12],
        "vn_residual": 1.0,
        "duration_real_anos": 1.55,
        "paridad_ref_pct": 97.5,
        "tir_real_mercado": 0.005,
        "inflacion_breakeven_pct": 40.0,
    },
    "DICP": {
        "nombre": "Discount Peso 2033",
        "emisor": "Republica Argentina",
        "tipo": "BONCER",
        "moneda_emision": "ARS_CER",
        "ley": "Local",
        "spread_real_anual": 0.0800,     # CER + 8% (legacy Discount reestructurado)
        "frecuencia_pago": 2,
        "esquema_amortizacion": "AMORTIZING",
        "fecha_vencimiento": "2033-12-31",
        "meses_cupon": [6, 12],
        "vn_residual": 0.667,            # amortizacion progresiva de capital
        "duration_real_anos": 3.80,
        "paridad_ref_pct": 95.2,
        "tir_real_mercado": 0.080,
        "inflacion_breakeven_pct": 35.0,
    },
}

# ─── CAUCIONES BYMA — Repos colateralizados de corto plazo ───────────────────
# Las cauciones bursatiles NO son bonos; son prestamos colateralizados entre
# agentes de bolsa, garantizados por BYMA, con activos soberanos o ON como
# colateral. Se negocian via SENEBI (Sistema de Negociacion Bilateral).
#
# Rol en el portafolio:
#   CAPA DE LIQUIDEZ INMEDIATA — sustituyen al efectivo o plazo fijo bancario.
#   Se acumula en ellas la porcion "necesidad_liquidez_pct" del perfil cuando
#   no hay suficientes bonos cortos.
#
# Identificadores virtuales (no existen como tickers BYMA de instrumento):
#   CAUCION_ARS_1D / 7D / 30D: plazos estandar en ARS
#   CAUCION_USD_30D           : caución en dolares (mas escasa, spread reducido)
#
# tna_referencia: TNA promedio de rueda BYMA — ACTUALIZAR DIARIAMENTE.
# retorno_esperado_anual_ars/_usd: TEA implicita para el plazo dado.
# Fuente tasa: BYMA rueda cauciones / Rava / MAE (2026-05)
CAUCIONES_BYMA = {
    "CAUCION_ARS_1D": {
        "nombre": "Caucion ARS 1 dia",
        "tipo": "CAUCION",
        "moneda_emision": "ARS",
        "plazo_dias": 1,
        "tna_referencia": 0.330,
        "colateral": "BYMA_SENEBI",
        "duration_ref_anos": round(1 / 365, 4),      # 0.0027
        "retorno_esperado_anual_ars": 0.330,
        "riesgo_contraparte": "muy_bajo",
    },
    "CAUCION_ARS_7D": {
        "nombre": "Caucion ARS 7 dias",
        "tipo": "CAUCION",
        "moneda_emision": "ARS",
        "plazo_dias": 7,
        "tna_referencia": 0.340,
        "colateral": "BYMA_SENEBI",
        "duration_ref_anos": round(7 / 365, 4),      # 0.0192
        "retorno_esperado_anual_ars": round((1 + 0.340 * 7 / 365) ** (365 / 7) - 1, 4),
        "riesgo_contraparte": "muy_bajo",
    },
    "CAUCION_ARS_30D": {
        "nombre": "Caucion ARS 30 dias",
        "tipo": "CAUCION",
        "moneda_emision": "ARS",
        "plazo_dias": 30,
        "tna_referencia": 0.355,
        "colateral": "BYMA_SENEBI",
        "duration_ref_anos": round(30 / 365, 4),     # 0.0822
        "retorno_esperado_anual_ars": round((1 + 0.355 * 30 / 365) ** (365 / 30) - 1, 4),
        "riesgo_contraparte": "muy_bajo",
    },
    "CAUCION_USD_30D": {
        "nombre": "Caucion USD 30 dias",
        "tipo": "CAUCION",
        "moneda_emision": "USD",
        "plazo_dias": 30,
        "tna_referencia": 0.030,
        "colateral": "BYMA_SENEBI",
        "duration_ref_anos": round(30 / 365, 4),
        "retorno_esperado_anual_usd": round((1 + 0.030 * 30 / 365) ** (365 / 30) - 1, 4),
        "riesgo_contraparte": "muy_bajo",
    },
}

# ─── PATHS DE DATOS DINÁMICOS ────────────────────────────────────────────────
# Rutas para archivos de cache generados por scripts nocturnos.
# Usar pathlib para independencia de OS.
import pathlib as _pathlib
_BASE_DIR = _pathlib.Path(__file__).parent

# Cache JSON de fundamentales (actualizado por scripts/cron_update_fundamentales.py)
FUNDAMENTALES_CACHE_PATH = str(
    _BASE_DIR / "0_Data_Maestra" / "fundamentales_cache.json"
)
# Máxima antigüedad del cache antes de considerarlo vencido (horas)
FUNDAMENTALES_CACHE_MAX_EDAD_H = 26  # un poco más de un día de rueda

# ─── OBSERVABILIDAD ───────────────────────────────────────────────────────────
# LOG_LEVEL: DEBUG en dev, INFO en producción
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ENVIRONMENT: distingue dev local de producción Railway
ENVIRONMENT = os.environ.get("RAILWAY_ENVIRONMENT",
              os.environ.get("ENVIRONMENT", "development"))

