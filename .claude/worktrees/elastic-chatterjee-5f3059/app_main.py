"""
app_main.py — Master Quant · Cartera Inteligente MQ v10 (entrypoint principal)
Versión consolidada — única fuente de verdad (reemplaza V7, V8, V9).

Producto: 4 perfiles de riesgo (Conservador / Moderado / Arriesgado / Muy arriesgado).
Navegación por rol via ui/navigation.py — única fuente de verdad para tabs:
  - inversor   → 1 tab "Mi Cartera" (tab_inversor) con selector de perfil + RF·RV
  - admin      → 7 tabs (institucionales + Admin)
  - estudio    → 6 tabs institucionales (Cartera | Mercado | Señales | Optimización | Riesgo | Ejecución | Informe)
  - viewer     → 6 tabs institucionales

Variables de entorno (Railway / local):
  MQ26_TRY_DB_USERS=true      → login desde BD de usuarios
  MQ26_DB_TENANT_ID=nombre    → filtrado multi-tenant
  MQ26_INVESTOR_PASSWORD      → contraseña rol inversor
  MQ26_USER_INVERSOR          → usuario rol inversor
  DEMO_MODE=true              → datos de ejemplo sin credenciales

CONTRATO PÚBLICO:
  - navigation.py es SSOT de tabs por rol (no hardcodear st.tabs aquí)
  - perfil_allocation.py es SSOT de targets RF/RV por perfil
  - byma_market_data.py provee precios en vivo de ONs (RF) desde BYMA Open Data
  - tab_inversor.py contiene toda la UI del inversor (no duplicar lógica aquí)

Para arrancar: streamlit run app_main.py
"""
import io
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
MOTOR_DIR = BASE_DIR / "1_Scripts_Motor"
CORE_DIR  = BASE_DIR / "core"
SVC_DIR   = BASE_DIR / "services"

# BASE_DIR al frente: el config.py raíz tiene prioridad sobre el de 1_Scripts_Motor
for d in [str(SVC_DIR), str(CORE_DIR), str(MOTOR_DIR)]:
    if d not in sys.path:
        sys.path.append(d)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Logging centralizado (inicializa handlers antes que cualquier otro módulo)
from core.logging_config import get_logger

_log = get_logger(__name__)


def _log_degradacion(evento: str, exc: Exception | None = None, **ctx) -> None:
    """Logging estructurado para degradaciones no fatales."""
    payload = {"evento": evento, **ctx}
    if exc is not None:
        _log.warning("degradacion_app_main: %s | error=%s", payload, exc, exc_info=True)
    else:
        _log.warning("degradacion_app_main: %s", payload)


def _app_scope_clientes_df(df: pd.DataFrame) -> pd.DataFrame:
    """Misma regla que run_mq26: BD + rol inversor = un solo cliente visible."""
    from core.cliente_scope_ui import scope_clientes_df_por_sesion

    return scope_clientes_df_por_sesion(df, app_id="app")


# Importar config desde la raíz explícitamente (evita conflicto con 1_Scripts_Motor/config.py)
import importlib.util as _ilu

_cfg_spec = _ilu.spec_from_file_location("config_root", str(BASE_DIR / "config.py"))
_cfg_mod  = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg_mod)
APP_PASSWORD     = _cfg_mod.APP_PASSWORD
MQ26_VIEWER_PASSWORD = getattr(_cfg_mod, "MQ26_VIEWER_PASSWORD", "") or ""
MQ26_INVESTOR_PASSWORD = getattr(_cfg_mod, "MQ26_INVESTOR_PASSWORD", "") or ""
MQ26_USER_ADMIN = getattr(_cfg_mod, "MQ26_USER_ADMIN", "admin") or "admin"
MQ26_USER_ESTUDIO = getattr(_cfg_mod, "MQ26_USER_ESTUDIO", "estudio") or "estudio"
MQ26_USER_INVERSOR = getattr(_cfg_mod, "MQ26_USER_INVERSOR", "inversor") or "inversor"
_MQ26_TRY_DB_USERS = os.environ.get("MQ26_TRY_DB_USERS", "true").strip().lower() in ("1", "true", "yes")
_MQ26_DB_TENANT_ID = (os.environ.get("MQ26_DB_TENANT_ID", "default").strip() or "default")
N_SIM_DEFAULT    = _cfg_mod.N_SIM_DEFAULT
RISK_FREE_RATE   = _cfg_mod.RISK_FREE_RATE
PESO_MAX_CARTERA = _cfg_mod.PESO_MAX_CARTERA
RUTA_ANALISIS    = _cfg_mod.RUTA_ANALISIS
RUTA_UNIVERSO    = _cfg_mod.RUTA_UNIVERSO
from core.cartera_scope import filtrar_transaccional_por_rol
from data_engine import DataEngine, asignar_sector, obtener_ccl
from risk_engine import RiskEngine

import broker_importer as bi
import core.db_manager as dbm
import gmail_reader as gr
import libro_mayor as lm
import services.alert_bot as ab
import services.backtester as bt

# Servicios de dominio (nuevos)
import services.cartera_service as cs
import services.ejecucion_service as ejsvc
import services.market_connector as mc
import services.mod23_service as m23svc
import services.report_service as rpt


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def _df_to_excel(df: pd.DataFrame) -> bytes:
    """Serializa un DataFrame a bytes Excel (.xlsx) sin dependencias extras."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=True, sheet_name="Datos")
    return buf.getvalue()

def _boton_exportar(df: pd.DataFrame, nombre: str, label: str = "📥 Exportar Excel"):
    """Muestra un botón de descarga inline para el DataFrame dado."""
    if df is None or df.empty:
        return
    try:
        data = _df_to_excel(df)
        ext  = "xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception as exc:
        _log_degradacion("export_excel_fallback_csv", exc, nombre=nombre, filas=int(len(df)))
        data = df.to_csv(index=True).encode("utf-8")
        ext  = "csv"
        mime = "text/csv"
    st.download_button(label, data=data, file_name=f"{nombre}.{ext}", mime=mime)


# ─── CONFIG STREAMLIT ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MQ26 | Terminal Cuantitativa",
    layout="wide",
    page_icon="",
    initial_sidebar_state="expanded",
)

if not (APP_PASSWORD or "").strip():
    st.error(
        "Falta la variable de entorno **`MQ26_PASSWORD`** (Railway → Variables, o `.env` en local)."
    )
    st.stop()

# CSS: mismo bundle que run_mq26 (oscuro + retail light) para login y app legibles
def _inject_css():
    from ui.mq26_theme import build_theme_css_bundle

    _logged = bool(
        st.session_state.get("app_auth")
        or st.session_state.get("authentication_status") is True
    )
    _use_light = bool(st.session_state.get("mq_light_mode", False)) if _logged else True
    _extra, _light = build_theme_css_bundle(BASE_DIR, use_light=_use_light)
    st.markdown(f"<style>{_extra}{_light}</style>", unsafe_allow_html=True)
    st.markdown(
        """
    <style>
        .main-header { font-size: 1.8rem; font-weight: 700; color: var(--c-accent); margin-bottom: 0; }
        .sub-header  { font-size: 0.95rem; color: var(--c-text-2); margin-bottom: 1rem; }
        .badge-green { background: var(--c-green); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
        .badge-red   { background: var(--c-red); color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
        .badge-gold  { background: var(--c-yellow); color: #0f172a; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; }
    </style>
    """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="mq26-watermark">MQ26 Institucional</div>',
        unsafe_allow_html=True,
    )

_inject_css()


# ─── AUTENTICACIÓN SEGURA (core/auth.py — rate limiting, SHA-256, token de sesión) ──
from core.auth import check_password, get_user_role

if not check_password(
    "app",
    "MQ26 Terminal",
    password_env=APP_PASSWORD,
    viewer_password_env=MQ26_VIEWER_PASSWORD,
    investor_password_env=MQ26_INVESTOR_PASSWORD,
    user_admin=MQ26_USER_ADMIN,
    user_estudio=MQ26_USER_ESTUDIO,
    user_inversor=MQ26_USER_INVERSOR,
    username_login=True,
    try_database_users=_MQ26_TRY_DB_USERS,
    db_tenant_id=_MQ26_DB_TENANT_ID if _MQ26_TRY_DB_USERS else None,
):
    st.stop()

# Migraciones en cada run: init_db() detrás de @st.cache_resource no se re-ejecuta si el caché sigue vivo
dbm.ensure_schema()

# ─── INICIALIZACIÓN BD ────────────────────────────────────────────────────────
@st.cache_resource
def init_sistema():
    dbm.init_db()
    return DataEngine()

engine_data = init_sistema()


# ─── PANTALLA DE INGRESO ───────────────────────────────────────────────────────
def _pantalla_ingreso():
    """Bloquea la app hasta que se seleccione o cree un cliente (inversor: alcance acotado, sin alta)."""
    _ing = get_user_role("app")
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem 0;">
        <span style="font-size:3rem"></span>
        <h1 style="color:var(--c-accent, #2E86AB); margin:0.3rem 0">MQ26 Terminal</h1>
        <p style="color:var(--c-text-2, #64748b); font-size:1rem">Seleccioná un cliente para comenzar el análisis</p>
    </div>
    """, unsafe_allow_html=True)

    if _ing == "inversor":
        col_sel = st.container()
        col_nuevo = None
    else:
        col_sel, col_nuevo = st.columns([1, 1], gap="large")

    with col_sel:
        st.markdown("### Seleccionar cliente existente")
        df_cli = _app_scope_clientes_df(dbm.obtener_clientes_df())
        if df_cli.empty:
            if _ing == "inversor":
                st.warning(
                    "No hay un perfil de cliente asignado a tu usuario. "
                    "Un administrador debe vincular tu cuenta en la base o definir **MQ26_INVESTOR_CLIENTE_IDS** en el entorno."
                )
            else:
                st.info("No hay clientes registrados aún. Creá el primero al lado.")
        else:
            opciones_cli = ["— Elegir cliente —"] + df_cli["Nombre"].tolist()
            _idx_sel = 0
            if _ing == "inversor" and len(df_cli) == 1:
                _idx_sel = 1
            sel = st.selectbox("Cliente:", opciones_cli, index=_idx_sel, key="ing_sel_cliente")
            if sel != "— Elegir cliente —":
                row = df_cli[df_cli["Nombre"] == sel].iloc[0]
                st.markdown(f"""
                | | |
                |---|---|
                | **Perfil** | {row['Perfil']} |
                | **Horizonte** | {row.get('Horizonte','1 año')} |
                | **Capital** | USD {row['Capital_USD']:,.0f} |
                """)
                if st.button("✅ Ingresar con este cliente", type="primary", use_container_width=True, key="btn_ingresar"):
                    st.session_state["cliente_id"]      = int(row["ID"])
                    st.session_state["cliente_nombre"]  = sel
                    st.session_state["cliente_perfil"]  = row["Perfil"]
                    st.session_state["cliente_horizonte_label"] = row.get("Horizonte", "1 año")
                    st.rerun()

    if col_nuevo is not None:
        with col_nuevo:
            st.markdown("### Nuevo cliente")
            with st.form("form_nuevo_cliente_ingreso", clear_on_submit=True):
                nc_nombre  = st.text_input("Nombre completo *")
                nc_tipo    = st.selectbox("Tipo de cliente", ["Persona", "Empresa"])
                nc_perfil  = st.selectbox("Perfil de riesgo", ["Conservador", "Moderado", "Agresivo"],
                                           help="Conservador: preserva capital. Moderado: balance riesgo/retorno. Agresivo: maximiza retorno.")
                nc_horiz   = st.selectbox("Horizonte de inversión",
                                           ["1 mes","3 meses","6 meses","1 año","3 años","+5 años"],
                                           index=3,
                                           help="¿En cuánto tiempo podría necesitar este capital?")
                nc_capital = st.number_input("Capital inicial estimado (USD)", min_value=0.0,
                                              value=10_000.0, step=1_000.0)
                submitted = st.form_submit_button("💾 Crear cliente e ingresar", type="primary", use_container_width=True)
                if submitted:
                    if not nc_nombre.strip():
                        st.error("El nombre es obligatorio.")
                    else:
                        nuevo_id = dbm.registrar_cliente(
                            nc_nombre.strip(), nc_perfil, nc_capital, nc_tipo, nc_horiz
                        )
                        st.session_state["cliente_id"]      = nuevo_id
                        st.session_state["cliente_nombre"]  = nc_nombre.strip()
                        st.session_state["cliente_perfil"]  = nc_perfil
                        st.session_state["cliente_horizonte_label"] = nc_horiz
                        st.success(f"✅ Cliente '{nc_nombre.strip()}' creado.")
                        st.rerun()

    st.stop()


# Bloquear app hasta que haya un cliente seleccionado
if "cliente_id" not in st.session_state:
    _pantalla_ingreso()


# ─── CACHE DE DATOS ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def cached_ccl():
    return obtener_ccl()

@st.cache_data(ttl=3600)
def cached_historico(tickers: tuple, period: str = "1y"):
    return engine_data.descargar_historico(list(tickers), period)

@st.cache_data(ttl=300)
def cached_precios_actuales(tickers: tuple, ccl: float):
    return engine_data.obtener_precios_cartera(list(tickers), ccl)

@st.cache_data(ttl=3600)
def cached_ratios_fundamentales(tickers: tuple):
    return mc.obtener_ratios_fundamentales(list(tickers))

@st.cache_data(ttl=60)
def cached_metricas_resumen(df_serialized: str, ccl: float, cartera_key: str) -> dict:
    """F6: metricas_resumen cacheada con TTL=60s para evitar recalcular en cada render."""
    import io as _io_f6

    import services.cartera_service as _cs_f6
    try:
        _df_f6 = pd.read_json(_io_f6.StringIO(df_serialized))
        if _df_f6.empty:
            return {}
        return _cs_f6.metricas_resumen(_df_f6)
    except Exception as exc:
        _log_degradacion("cached_metricas_resumen_error", exc, cartera=cartera_key, ccl=round(float(ccl or 0.0), 2))
        return {}


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("## MQ26 Terminal")
st.sidebar.markdown("---")

# Info BD
info_bd = dbm.info_backend()
backend_label = "🟢 PostgreSQL" if info_bd["backend"] == "postgresql" else "🟡 SQLite Local"
st.sidebar.caption(f"BD: {backend_label}")

# CCL en tiempo real
ccl = cached_ccl()
st.sidebar.metric("💵 Dólar CCL/MEP", f"${ccl:,.0f}")
st.sidebar.markdown("---")

# ── Cliente activo (viene de la pantalla de ingreso) ──────────────────────────
_cliente_id     = st.session_state.get("cliente_id")
_cliente_nombre = st.session_state.get("cliente_nombre", "")
_cliente_perfil = st.session_state.get("cliente_perfil", "Moderado")
_horiz_label    = st.session_state.get("cliente_horizonte_label", "1 año")

df_clientes = _app_scope_clientes_df(dbm.obtener_clientes_df())

st.sidebar.markdown(f"**👤 {_cliente_nombre}**")
st.sidebar.caption(f"Perfil: {_cliente_perfil}  |  Horizonte: {_horiz_label}")
_app_role_sidebar = get_user_role("app")
from ui.rbac import can_action as _can_action_rbac
_can_sensitive_utils = _can_action_rbac({"user_role": _app_role_sidebar}, "sensitive_utils")
# Inversor con un solo cliente en alcance: no ofrecer cambiar (misma lógica que run_mq26).
if _app_role_sidebar != "inversor" or len(df_clientes) > 1:
    if st.sidebar.button("🔄 Cambiar cliente", key="btn_cambiar_cliente", use_container_width=True):
        for k in ["cliente_id", "cliente_nombre", "cliente_perfil", "cliente_horizonte_label"]:
            st.session_state.pop(k, None)
        st.rerun()
st.sidebar.markdown("---")

# Horizonte en días derivado del cliente (no hay slider)
horizonte_dias = dbm.HORIZONTE_DIAS.get(_horiz_label, 365)

# Simulaciones MC (único parámetro técnico que queda)
n_escenarios = st.sidebar.selectbox("Simulaciones MC:", [1000, 3000, 5000, 10000], index=2)
capital_nuevo = 0.0   # queda en 0; se gestiona desde Mesa de Ejecución
st.sidebar.markdown("---")

# Selección de cartera del cliente (inversor: un cliente activo a la vez; lista de clientes ya acotada arriba)
trans = engine_data.cargar_transaccional()
_app_role = get_user_role("app")
trans = filtrar_transaccional_por_rol(trans, _app_role, _cliente_nombre, df_clientes)

if _app_role == "inversor":
    from core.cartera_scope import normalizar_transacciones_inversor_una_cartera

    trans, _ = normalizar_transacciones_inversor_una_cartera(trans, _cliente_nombre)

carteras_csv: list[str] = []
if not trans.empty and "CARTERA" in trans.columns:
    carteras_csv = sorted(trans["CARTERA"].dropna().unique().tolist())

if _app_role == "inversor":
    if carteras_csv:
        carteras_opciones = [carteras_csv[0]]
    elif _cliente_nombre.strip():
        carteras_opciones = [f"{_cliente_nombre.strip()} | (sin datos)"]
    else:
        carteras_opciones = []
else:
    carteras_opciones = ["-- Todas las carteras --"] + list(carteras_csv)
    if not df_clientes.empty:
        propietarios_csv = {c.split("|")[0].strip() for c in carteras_csv}
        for _nombre_cli in sorted(df_clientes["Nombre"].dropna().tolist()):
            if _nombre_cli.strip() not in propietarios_csv:
                carteras_opciones.append(f"{_nombre_cli.strip()} | (sin datos)")

_default_cartera_idx = 0
if _app_role != "inversor":
    for _i, _opt in enumerate(carteras_opciones):
        if _opt in ("-- Todas las carteras --",) or _opt.endswith("| (sin datos)"):
            continue
        if "|" in _opt:
            _pref = _opt.split("|")[0].strip()
            if _cliente_nombre and _pref == _cliente_nombre.strip():
                _default_cartera_idx = _i
                break

if carteras_opciones:
    _default_cartera_idx = min(_default_cartera_idx, max(0, len(carteras_opciones) - 1))
else:
    _default_cartera_idx = 0

if not carteras_opciones:
    cartera_activa = ""
elif _app_role == "inversor":
    cartera_activa = carteras_opciones[0]
else:
    cartera_activa = st.sidebar.selectbox(
        "📁 Cartera activa:", carteras_opciones, index=_default_cartera_idx
    )
    st.sidebar.caption(
        "Vista **Cartera → Posición actual** usa la misma tabla resumen que el inversor y, debajo, "
        "targets / progreso / Kelly para trabajo profesional."
    )
# B11: Toggle FIFO vs Promedio ponderado para cálculo de PPC
st.sidebar.checkbox(
    "Usar FIFO para PPC",
    key="modo_ppc_fifo",
    value=False,
    help="B11: FIFO = primeras compras son las primeras ventas (estándar impositivo ARG). Default: promedio ponderado.",
)
st.sidebar.markdown("---")

# ── Mantenimiento de datos ────────────────────────────────────────────────────
with st.sidebar.expander("🔄 Sincronización de datos"):
    st.caption("Regenera las posiciones netas leyendo el Excel completo.")
    _can_manage_data = _can_sensitive_utils
    if not _can_manage_data:
        st.info("Solo administradores pueden ejecutar acciones de mantenimiento.")
    _ruta_transac_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
    _ruta_maestra_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
    _ruta_sqlite_sb  = BASE_DIR / "0_Data_Maestra" / "master_quant.db"
    if _ruta_maestra_sb.exists():
        st.caption(f"Excel: {_ruta_maestra_sb.stat().st_size // 1024} KB")
    if _ruta_transac_sb.exists():
        _mtime = datetime.fromtimestamp(_ruta_transac_sb.stat().st_mtime).strftime("%d/%m %H:%M")
        st.caption(f"CSV actual: {_mtime}")
    else:
        st.warning("CSV no generado aún.")
    if st.button("🔄 Regenerar posiciones desde Excel", key="btn_regen_csv", disabled=not _can_manage_data):
        if _ruta_transac_sb.exists():
            _ruta_transac_sb.unlink()
        st.cache_data.clear()
        st.success("✅ CSV eliminado. Recargando...")
        st.rerun()
    st.markdown("---")
    st.caption("⚠️ **Reset total**: borra carteras, clientes y caché. Punto cero.")
    if "confirmar_reset" not in st.session_state:
        st.session_state["confirmar_reset"] = False
    if not st.session_state["confirmar_reset"]:
        if st.button("🗑️ Resetear todo (punto cero)", key="btn_reset_confirm", disabled=not _can_manage_data):
            st.session_state["confirmar_reset"] = True
            st.rerun()
    else:
        st.warning("¿Estás seguro? Se borrarán **clientes, carteras y operaciones**.")
        col_si, col_no = st.columns(2)
        with col_si:
            if st.button("✅ Sí, borrar", key="btn_reset_si", type="primary", disabled=not _can_manage_data):
                for _ruta in [_ruta_transac_sb, _ruta_sqlite_sb]:
                    if _ruta.exists():
                        _ruta.unlink()
                st.cache_data.clear()
                st.session_state.clear()
                st.rerun()
        with col_no:
            if st.button("❌ Cancelar", key="btn_reset_no"):
                st.session_state["confirmar_reset"] = False
                st.rerun()

# ── Panel de precios fallback ─────────────────────────────────────────────────
with st.sidebar.expander("💰 Precios fallback (sin red)"):
    st.caption("Precios ARS por CEDEAR usados cuando yfinance no responde.")
    if not _can_sensitive_utils:
        st.info("Utilidad sensible: solo administradores pueden editar precios fallback.")
    _fb = cs.PRECIOS_FALLBACK_ARS.copy()
    _df_fb = pd.DataFrame(
        [{"Ticker": t, "Precio ARS": p} for t, p in sorted(_fb.items())]
    )
    _df_fb_edit = st.data_editor(
        _df_fb.reset_index(drop=True), num_rows="dynamic", use_container_width=True,
        column_config={
            "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
            "Precio ARS": st.column_config.NumberColumn("Precio ARS", min_value=0, format="$%d"),
        },
        key="editor_fallback_sb", hide_index=True,
    )
    if st.button("💾 Aplicar precios", key="btn_aplicar_fb", disabled=not _can_sensitive_utils):
        _nuevos = dict(zip(_df_fb_edit["Ticker"], _df_fb_edit["Precio ARS"]))
        _nuevos = {t: float(p) for t, p in _nuevos.items() if t and p and float(p) > 0}
        cs.actualizar_fallback(_nuevos)
        st.cache_data.clear()
        st.success(f"✅ {len(_nuevos)} precios actualizados.")
        st.rerun()

# ── Widget de noticias macro (H11) ─────────────────────────────────────────────
with st.sidebar.expander("📰 Noticias Macro Argentina"):
    try:
        import feedparser as _fp
        _feeds = [
            ("Infobae Economía", "https://www.infobae.com/feeds/rss/economia/"),
            ("Bloomberg en Español", "https://feeds.bloomberg.com/economics/news.rss"),
        ]
        _noticias = []
        for _fuente, _url in _feeds:
            try:
                _feed = _fp.parse(_url)
                for _entry in _feed.entries[:3]:
                    _noticias.append((_fuente, _entry.get("title",""), _entry.get("link","")))
            except Exception as exc:
                _log_degradacion("noticias_feed_parse_error", exc, fuente=_fuente, url=_url)
        if _noticias:
            for _fuente, _titulo, _link in _noticias[:6]:
                st.markdown(f"📌 **[{_titulo[:60]}...]({_link})**")
                st.caption(_fuente)
        else:
            st.caption("Sin noticias disponibles ahora.")
    except ImportError as exc:
        _log_degradacion("noticias_feedparser_no_disponible", exc)
        st.caption("Instalar `feedparser` para ver noticias.")

# ── Salud del sistema (C7) ────────────────────────────────────────────────────
with st.sidebar.expander("⚙️ Salud del sistema"):
    import datetime as _dt_sys
    _now = _dt_sys.datetime.now().strftime("%H:%M:%S")
    st.markdown(f"**Última sync:** {_now}")
    st.markdown(f"**BD:** {dbm.info_backend()['backend'].upper()}")
    _trans_loaded = not trans.empty if "trans" in dir() else False
    st.markdown(f"**CSV cargado:** {'✅' if _trans_loaded else '❌'}")
    st.markdown(f"**CCL:** ${ccl:,.0f}" if "ccl" in dir() else "**CCL:** —")
    _cb = len(getattr(__import__("services.market_connector", fromlist=["_circuit_breaker"]),
                       "_circuit_breaker", set()))
    if _cb > 0:
        st.warning(f"⚡ {_cb} ticker(s) en circuit breaker")
    else:
        st.success("✅ Sin errores de mercado")

# Config Telegram
with st.sidebar.expander("📱 Alertas Telegram"):
    if not _can_sensitive_utils:
        st.info("Utilidad sensible: solo administradores pueden configurar Telegram.")
    tg_token   = st.text_input("Bot Token", type="password",
                                value=os.environ.get("TELEGRAM_TOKEN",""))
    tg_chat    = st.text_input("Chat ID",
                                value=os.environ.get("TELEGRAM_CHAT_ID",""))
    if st.button("🔔 Probar conexión", disabled=not _can_sensitive_utils):
        if tg_token and tg_chat:
            os.environ["TELEGRAM_TOKEN"]   = tg_token
            os.environ["TELEGRAM_CHAT_ID"] = tg_chat
            ok = ab.test_conexion()
            st.success("✅ Telegram OK") if ok else st.error("❌ Sin respuesta")
        else:
            st.warning("Completá token y chat ID")


# ─── HEADER PRINCIPAL ─────────────────────────────────────────────────────────
st.markdown('<p class="main-header">MQ26 Terminal Institucional</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Master Quant 26 x Advisory Suite x DSS ALFREDO — Sistema Cuantitativo Unificado</p>', unsafe_allow_html=True)

# ─── CARGA DE DATOS DE CARTERA ACTIVA ─────────────────────────────────────────
df_analisis = engine_data.cargar_analisis()

df_ag = pd.DataFrame()
tickers_cartera = []
precios_dict = {}
prop_nombre = ""
price_coverage_pct = 100.0
tickers_sin_precio: list[str] = []
valoracion_audit: dict = {}
precio_records: dict = {}

_cartera_sin_datos = cartera_activa.endswith("| (sin datos)")
if cartera_activa != "-- Todas las carteras --" and not _cartera_sin_datos and not trans.empty:
    # F3: Cache de df_ag en session_state — no recalcular en cada render
    _trans_hash    = hash(str(len(trans)) + str(cartera_activa) + str(trans.get("CANTIDAD", pd.Series()).sum() if "CANTIDAD" in trans.columns else 0))
    _cache_key_ag  = f"_df_ag_cache_{cartera_activa}"
    _cache_key_h   = f"_df_ag_hash_{cartera_activa}"
    _modo_ppc      = st.session_state.get("modo_ppc_fifo", False)
    _cache_key_fifo = f"_df_ag_fifo_{cartera_activa}"

    if (st.session_state.get(_cache_key_h) != _trans_hash or
            st.session_state.get(_cache_key_fifo) != _modo_ppc):
        if _modo_ppc:
            df_ag = engine_data.agregar_cartera_fifo(trans, cartera_activa)
        else:
            df_ag = engine_data.agregar_cartera(trans, cartera_activa)
        st.session_state[_cache_key_ag]   = df_ag
        st.session_state[_cache_key_h]    = _trans_hash
        st.session_state[_cache_key_fifo] = _modo_ppc
    else:
        df_ag = st.session_state.get(_cache_key_ag, pd.DataFrame())

    if not df_ag.empty:
        tickers_cartera = df_ag["TICKER"].str.upper().tolist()
        precios_dict_live = cached_precios_actuales(tuple(tickers_cartera), ccl)
        try:
            from core.price_engine import PriceEngine, records_tras_rellenar_ppc
            from services.valoracion_audit import auditar_inferido_live_vs_resto, auditar_valoracion_por_tipo

            _pe = PriceEngine(universo_df=engine_data.universo_df)
            _records = _pe.get_portfolio(tickers_cartera, ccl, precios_live_override=precios_dict_live)
            price_coverage_pct = _pe.cobertura_pct(_records)
            tickers_sin_precio = _pe.tickers_sin_precio(_records)
            precios_dict = _pe.to_precios_ars(_records)
            _precios_pre_ppc = dict(precios_dict)
            if tickers_sin_precio:
                precios_dict = cs.rellenar_precios_desde_ultimo_ppc(
                    trans, cartera_activa, tickers_cartera, precios_dict, float(ccl or 0)
                )
                _records = records_tras_rellenar_ppc(
                    _records, _precios_pre_ppc, precios_dict, float(ccl or 0)
                )
                tickers_sin_precio = [
                    t for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) <= 0
                ]
                price_coverage_pct = (
                    round(100.0 * (len(tickers_cartera) - len(tickers_sin_precio)) / len(tickers_cartera), 1)
                    if tickers_cartera else 100.0
                )
            precio_records = _records
        except Exception as exc:
            _log_degradacion("app_main_price_engine_fallo", exc)
            # Fallback controlado
            precios_dict = cs.resolver_precios(
                tickers_cartera, precios_dict_live, ccl, universo_df=engine_data.universo_df
            )
            tickers_sin_precio = [
                t for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) <= 0
            ]
            price_coverage_pct = (
                round(100.0 * (len(tickers_cartera) - len(tickers_sin_precio)) / len(tickers_cartera), 1)
                if tickers_cartera else 100.0
            )
        prop_nombre = cartera_activa.split("|")[0].strip() if "|" in cartera_activa else cartera_activa
        _log.info("Cartera activa cargada: %s (%d posiciones)", cartera_activa, len(df_ag))

# Banner informativo para clientes sin datos en el CSV todavía
if _cartera_sin_datos:
    _nombre_nuevo = cartera_activa.replace("| (sin datos)", "").strip()
    prop_nombre = _nombre_nuevo
    st.info(
        f"**{_nombre_nuevo}** está registrado en el CRM pero todavía no tiene posiciones cargadas. "
        "Para cargar su cartera: ir al **Tab 2 (Ledger)** → importar comprobante de broker, "
        "o cargá operaciones manualmente desde el formulario de este mismo Tab 1."
    )

# Valor default de metricas (se sobreescribe si hay cartera activa)
metricas = {}

# Verificar objetivos próximos a vencer y enviar alertas Telegram (H9)
# Solo se ejecuta una vez por sesión
if _cliente_id and not st.session_state.get("_objetivos_alertas_verificados"):
    try:
        _df_obj_alerta = dbm.obtener_objetivos_cliente(_cliente_id)
        if not _df_obj_alerta.empty:
            _n_alertas = ab.verificar_objetivos_por_vencer(_df_obj_alerta, _cliente_nombre)
            if _n_alertas > 0:
                st.toast(f"⏰ {_n_alertas} objetivo(s) próximos a vencer — alertas Telegram enviadas", icon="⏰")
    except Exception as exc:
        _log_degradacion("objetivos_alerta_verificacion_error", exc, cliente_id=int(_cliente_id))
    st.session_state["_objetivos_alertas_verificados"] = True

# Métricas header (usando cartera_service)
if not df_ag.empty and precios_dict:
    df_ag = cs.calcular_posicion_neta(
        df_ag, precios_dict, ccl, universo_df=engine_data.universo_df
    )
    if precio_records:
        try:
            from services.valoracion_audit import auditar_valoracion_por_tipo
            valoracion_audit = auditar_valoracion_por_tipo(df_ag, precio_records)
        except Exception as exc:
            _log_degradacion("app_main_valoracion_audit_records_fallo", exc)
    else:
        try:
            from services.valoracion_audit import auditar_inferido_live_vs_resto
            valoracion_audit = auditar_inferido_live_vs_resto(df_ag, precios_dict_live, precios_dict)
        except Exception as exc:
            _log_degradacion("app_main_valoracion_audit_inferido_fallo", exc)
    # F6: metricas_resumen cacheada con TTL=60s — evita recalcular en cada render
    try:
        _df_ag_json = df_ag.to_json(orient="records", date_format="iso")
        metricas = cached_metricas_resumen(_df_ag_json, round(ccl, 0), cartera_activa)
        if not metricas:
            metricas = cs.metricas_resumen(df_ag)
    except Exception:
        metricas = cs.metricas_resumen(df_ag)
    total_valor     = metricas["total_valor"]
    total_inversion = metricas["total_inversion"]
    total_pnl       = metricas["total_pnl"]
    pnl_pct_total   = metricas["pnl_pct_total"]

    # C2: Métricas con tooltips explicativos y delta colorizado
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(
        "💼 Cartera activa",
        cartera_activa.split("|")[0].strip()[:25] if "|" in cartera_activa else cartera_activa[:25],
        help="Nombre de la cartera o propietario actualmente seleccionado.",
    )
    m2.metric(
        "📊 Valor cartera",
        f"${total_valor/1e6:.2f}M ARS" if total_valor > 1e6 else f"${total_valor:,.0f} ARS",
        help="Valor de mercado total de las posiciones, a precios actuales en ARS.",
    )
    _delta_pnl_str = f"{pnl_pct_total:+.1%}"
    m3.metric(
        "💰 P&L Total",
        f"${total_pnl:,.0f} ARS",
        delta=_delta_pnl_str,
        delta_color="normal",
        help="Ganancia/Pérdida total en ARS. Incluye apreciación del CCL (dólar). "
             "Para ver el retorno puro en USD, revisar columna P&L % USD en la tabla.",
    )
    m4.metric(
        "💵 CCL/MEP",
        f"${ccl:,.0f}",
        help="Tipo de cambio Contado con Liquidación (GGAL.BA/GGAL x 10). "
             "Referencia para convertir USD ↔ ARS en activos CEDEARs.",
    )
    m5.metric(
        "🎯 Posiciones",
        metricas["n_posiciones"],
        help="Cantidad de activos con posición neta positiva en la cartera activa.",
    )
    st.divider()


# ─── MÉTRICAS Y SEMÁFOROS EN SIDEBAR (visibles en cualquier tab) ─────────────
if not df_ag.empty and precios_dict:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Resumen de cartera")
    _lbl_val = f"${total_valor/1e6:.2f}M ARS" if total_valor > 1e6 else f"${total_valor:,.0f} ARS"
    _delta_pnl = f"{pnl_pct_total:.1%}"
    st.sidebar.metric("💼 Valor total",   _lbl_val)
    st.sidebar.metric("📈 P&L total",     f"${total_pnl:,.0f} ARS", _delta_pnl)
    st.sidebar.metric("🎯 Posiciones",    metricas["n_posiciones"])

    # C4: Indicadores semáforo — estado cartera, mercado y alertas MOD-23
    _pnl_ok = pnl_pct_total >= 0
    _semaforo_cartera = "🟢 Cartera positiva" if _pnl_ok else "🔴 Cartera en pérdida"
    st.sidebar.markdown(f"**{_semaforo_cartera}** ({pnl_pct_total:+.1%})")

    # Semáforo CCL (estabilidad del tipo de cambio)
    from config import CCL_FALLBACK as _ccl_fb
    _ccl_delta_pct = abs(ccl - _ccl_fb) / _ccl_fb if _ccl_fb > 0 else 0
    if _ccl_delta_pct < 0.05:
        st.sidebar.markdown("🟢 **CCL estable** (±5%)")
    elif _ccl_delta_pct < 0.15:
        st.sidebar.markdown("🟡 **CCL volátil** (±15%)")
    else:
        st.sidebar.markdown(f"🔴 **CCL muy volátil** (>{_ccl_delta_pct:.0%})")

    # Semáforo alertas MOD-23 (desde session_state si ya escaneó)
    _n_alertas_mod23 = 0
    try:
        _df_scores_sb = st.session_state.get("df_scores", pd.DataFrame())
        if not _df_scores_sb.empty and "Senal" in _df_scores_sb.columns:
            _n_alertas_mod23 = int((_df_scores_sb["Senal"].str.contains("SALIR|REDUCIR", na=False)).sum())
    except Exception as exc:
        _log_degradacion("mod23_alertas_sidebar_error", exc)
    if _n_alertas_mod23 == 0:
        st.sidebar.markdown("🟢 **MOD-23:** Sin alertas")
    elif _n_alertas_mod23 <= 2:
        st.sidebar.markdown(f"🟡 **MOD-23:** {_n_alertas_mod23} alerta(s)")
    else:
        st.sidebar.markdown(f"🔴 **MOD-23:** {_n_alertas_mod23} alertas ACTIVAS")

    # Mini barra de distribución por activo
    if "PESO_PCT" in df_ag.columns:
        _top = (
            df_ag[["TICKER","PESO_PCT"]]
            .sort_values("PESO_PCT", ascending=False)
            .head(5)
        )
        _fig_mini = px.bar(
            _top, x="TICKER", y="PESO_PCT",
            color="PESO_PCT", color_continuous_scale="Blues",
            height=160,
        )
        _fig_mini.update_layout(
            margin=dict(l=0, r=0, t=4, b=0),
            showlegend=False,
            coloraxis_showscale=False,
            xaxis_title="", yaxis_title="",
            yaxis_tickformat=".0%",
        )
        st.sidebar.plotly_chart(_fig_mini, use_container_width=True)
    st.sidebar.caption(f"CCL: ${ccl:,.0f}  |  {cartera_activa.split('|')[-1].strip()}")


# ─── IMPORTAR MÓDULOS DE TABS ─────────────────────────────────────────────────
from ui.tab_cartera import render_tab_cartera
from ui.tab_ejecucion import render_tab_ejecucion
from ui.tab_optimizacion import render_tab_optimizacion
from ui.tab_reporte import render_tab_reporte
from ui.tab_riesgo import render_tab_riesgo
from ui.tab_universo import render_tab_universo
from ui.carga_activos import render_carga_activos
from ui.navigation import render_main_tabs

# ─── CONTEXTO COMPARTIDO ──────────────────────────────────────────────────────
# Empaqueta todas las dependencias en un dict; cada render_tab extrae lo que necesita.
ctx = {
    # Estado de cartera
    "df_ag":            df_ag,
    "tickers_cartera":  tickers_cartera,
    "precios_dict":     precios_dict,
    "ccl":              ccl,
    "cartera_activa":   cartera_activa,
    "prop_nombre":      prop_nombre,
    "df_clientes":      df_clientes,
    "df_analisis":      df_analisis,
    "metricas":         metricas if not df_ag.empty and precios_dict else {},
    "price_coverage_pct": price_coverage_pct,
    "tickers_sin_precio": tickers_sin_precio,
    "valoracion_audit": valoracion_audit,
    "precio_records": precio_records,
    # Cliente activo
    "cliente_id":       _cliente_id,
    "cliente_nombre":   _cliente_nombre,
    "cliente_perfil":   _cliente_perfil,
    "horizonte_label":  _horiz_label,
    # Config
    "RISK_FREE_RATE":   RISK_FREE_RATE,
    "PESO_MAX_CARTERA": PESO_MAX_CARTERA,
    "N_SIM_DEFAULT":    N_SIM_DEFAULT,
    "RUTA_ANALISIS":    RUTA_ANALISIS,
    "horizonte_dias":   horizonte_dias,
    "capital_nuevo":    capital_nuevo,
    # Rutas
    "BASE_DIR":         BASE_DIR,
    # Datos transaccionales (para timeline, TWRR, etc.)
    "df_trans":         trans,
    # Motores / engines
    "engine_data":      engine_data,
    "RiskEngine":       RiskEngine,
    "cached_historico": cached_historico,
    # Servicios
    "dbm":     dbm,
    "cs":      cs,
    "m23svc":  m23svc,
    "ejsvc":   ejsvc,
    "rpt":     rpt,
    "bt":      bt,
    "ab":      ab,
    "lm":      lm,
    "bi":      bi,
    "gr":      gr,
    "mc":      mc,
    # Helpers
    "_boton_exportar": _boton_exportar,
    "asignar_sector":  asignar_sector,
    "render_carga_activos_fn": render_carga_activos,
    "user_role":       _app_role,
    "tenant_id":       _MQ26_DB_TENANT_ID,
    "login_user":      st.session_state.get("app_login_user", ""),
    "session_correlation_id": st.session_state.get("app_auth_token", ""),
}

# ─── TABS PRINCIPALES — navegación por rol ────────────────────────────────────
# navigation.py es la única fuente de verdad para tabs por rol:
#   inversor  → 1 tab "Mi Cartera" (tab_inversor)
#   estudio   → 6 tabs institucionales
#   admin     → 7 tabs (institucionales + Admin)
#   viewer/otros → 6 tabs institucionales
render_main_tabs(ctx, app_kind="app", role=_app_role)


# ── Motor de Salida — accesible desde sidebar ─────────────────────────────────
if st.sidebar.button("🚪 Motor de Salida", use_container_width=True, key="btn_motor_salida"):
    st.session_state["tab_activo"] = "motor_salida"

if st.session_state.get("tab_activo") == "motor_salida":
    if df_ag is None or df_ag.empty:
        st.warning("Seleccioná una cartera con posiciones para usar el Motor de Salida.")
        st.stop()

    # Construir datos para el motor de salida
    precios_act = precios_dict if 'precios_dict' in dir() else {}
    scores_act  = {r.get("Ticker",""):r.get("Score_Total",50)
                   for r in st.session_state.get("df_scores", pd.DataFrame()).to_dict("records")}                   if not st.session_state.get("df_scores", pd.DataFrame()).empty else {}
    rsi_act     = {r.get("Ticker",""):r.get("RSI",50)
                   for r in st.session_state.get("df_scores", pd.DataFrame()).to_dict("records")}                   if not st.session_state.get("df_scores", pd.DataFrame()).empty else {}

    perfil_act2 = _cliente_perfil or "Moderado"

    from services.motor_salida import render_motor_salida
    render_motor_salida(
        df_posiciones        = df_ag,
        precios_actuales     = precios_act,
        scores_actuales      = scores_act,
        rsi_actuales         = rsi_act,
        perfil               = perfil_act2,
        ccl                  = ccl,
        capital_disponible   = 500_000,
    )

# ─── FOOTER ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"MQ26 Terminal | BD: {info_bd['backend'].upper()} | CCL: ${ccl:,.0f} | "
           f"(c) Estrategia Capitales {datetime.now().year}")
