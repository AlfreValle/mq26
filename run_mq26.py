"""
run_mq26.py — MQ26 Terminal de Inversiones
Master Quant 26 | Optimizador Institucional de Carteras BYMA
6 Tabs: Cartera & Libro Mayor | Universo & Señales | Optimización | Riesgo | Ejecución | Reporte

Lanzar con:
    streamlit run run_mq26.py --server.port 8502
    (o mq26_main.py → redirige aquí; Docker/Railway usan run_mq26.py)
"""
import html
import io
import os
import sys

# ── SENTRY: monitoreo de errores en producción (Sprint 6) ─────────────────────
# Se activa solo si SENTRY_DSN está definida. En desarrollo es un no-op.
_SENTRY_DSN = os.environ.get("SENTRY_DSN", "").strip()
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.environ.get("RAILWAY_ENVIRONMENT", "development"),
        )
    except ImportError:
        pass  # sentry-sdk no instalado — silencioso, no rompe la app
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# ─── DEPLOY MARKER (para confirmar versión en Railway) ────────────────────────
_DEPLOY_MARKER = os.environ.get("MQ26_DEPLOY_MARKER", "").strip()
_GIT_SHA = (
    os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    or os.environ.get("GIT_COMMIT_SHA")
    or os.environ.get("GITHUB_SHA")
    or ""
).strip()

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).resolve().parent
MOTOR_DIR = BASE_DIR / "1_Scripts_Motor"
CORE_DIR  = BASE_DIR / "core"
SVC_DIR   = BASE_DIR / "services"

for d in [str(SVC_DIR), str(CORE_DIR), str(MOTOR_DIR)]:
    if d not in sys.path:
        sys.path.append(d)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from core.logging_config import get_logger

_log = get_logger(__name__)


import importlib.util as _ilu

_cfg_spec = _ilu.spec_from_file_location("config_root", str(BASE_DIR / "config.py"))
_cfg_mod  = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg_mod)
APP_PASSWORD     = _cfg_mod.APP_PASSWORD
MQ26_VIEWER_PASSWORD = getattr(_cfg_mod, "MQ26_VIEWER_PASSWORD", "") or ""
MQ26_INVESTOR_PASSWORD = getattr(_cfg_mod, "MQ26_INVESTOR_PASSWORD", "") or ""
MQ26_ADVISOR_PASSWORD = getattr(_cfg_mod, "MQ26_ADVISOR_PASSWORD", "") or ""
MQ26_USER_ADMIN = getattr(_cfg_mod, "MQ26_USER_ADMIN", "admin") or "admin"
MQ26_USER_ESTUDIO = getattr(_cfg_mod, "MQ26_USER_ESTUDIO", "estudio") or "estudio"
MQ26_USER_INVERSOR = getattr(_cfg_mod, "MQ26_USER_INVERSOR", "inversor") or "inversor"
MQ26_USER_ASESOR = getattr(_cfg_mod, "MQ26_USER_ASESOR", "asesor") or "asesor"
N_SIM_DEFAULT    = _cfg_mod.N_SIM_DEFAULT
RISK_FREE_RATE   = _cfg_mod.RISK_FREE_RATE
PESO_MAX_CARTERA = _cfg_mod.PESO_MAX_CARTERA
RUTA_ANALISIS    = _cfg_mod.RUTA_ANALISIS
RUTA_UNIVERSO    = _cfg_mod.RUTA_UNIVERSO
DEMO_MODE        = getattr(_cfg_mod, "DEMO_MODE", False)
DEMO_DB_PATH     = getattr(_cfg_mod, "DEMO_DB_PATH", "/tmp/mq26_demo.db")
_MQ26_TRY_DB_USERS = os.environ.get("MQ26_TRY_DB_USERS", "true").strip().lower() in ("1", "true", "yes")
_MQ26_DB_TENANT_ID = (os.environ.get("MQ26_DB_TENANT_ID", "default").strip() or "default")

# ─── MODO DEMO: activar antes de cualquier st. call ───────────────────────────
# Monkey-patchea el engine de db_manager para usar la BD demo si DEMO_MODE=true.
# Debe ejecutarse antes de st.set_page_config para no causar StreamlitAPIException.
if DEMO_MODE:
    try:
        from pathlib import Path as _DemoPath
        _demo_db  = _DemoPath(DEMO_DB_PATH)
        _demo_csv = _demo_db.with_suffix(".csv")
        # Regenerar si falta la BD o si falta el CSV (migración de versión anterior)
        if not _demo_db.exists() or not _demo_csv.exists():
            try:
                _scripts_dir = str(BASE_DIR / "scripts")
                if _scripts_dir not in sys.path:
                    sys.path.insert(0, _scripts_dir)
                from generate_demo_data import run as _run_demo
                _run_demo(str(_demo_db))
            except Exception as _e_gen:
                _log.warning("No se pudo generar la BD demo: %s", _e_gen)
        if _demo_db.exists():
            from sqlalchemy import create_engine as _demo_ce
            from sqlalchemy.orm import sessionmaker as _demo_sm
            import core.db_manager as _dbm
            # Parchear engine, SessionLocal Y SQLITE_PATH para que init_db() use la BD demo
            _demo_engine = _demo_ce(
                f"sqlite:///{_demo_db}",
                connect_args={"check_same_thread": False},
            )
            _dbm.engine = _demo_engine
            _dbm.DB_BACKEND = "sqlite"
            _dbm.SQLITE_PATH = _demo_db
            _dbm.SessionLocal = _demo_sm(
                bind=_demo_engine, autocommit=False, autoflush=False
            )
            _dbm.Base.metadata.create_all(_demo_engine)
            _log.info("DEMO MODE: BD patcheada -> %s", _demo_db)
            # Parchear RUTA_TRANSAC en config Y en data_engine (ambos importan por copia)
            _demo_csv = _demo_db.with_suffix(".csv")
            if _demo_csv.exists():
                import config as _cfg_patch
                _cfg_patch.RUTA_TRANSAC = _demo_csv
                # data_engine importa RUTA_TRANSAC como variable local al módulo.
                # Si ya fue importado, parchear directamente la variable del módulo.
                if "data_engine" in sys.modules:
                    sys.modules["data_engine"].RUTA_TRANSAC = _demo_csv
                _log.info("DEMO MODE: CSV patcheado -> %s", _demo_csv)
    except Exception as _e_demo:
        try:
            _log.warning("Error activando modo demo: %s", _e_demo)
        except Exception:
            pass

# ─── CONFIG STREAMLIT (primero: obligatorio para Streamlit + healthcheck Railway) ─
# Ningún st.session_state / st.markdown / etc. antes de esta línea.
st.set_page_config(
    page_title="MQ26 | Terminal de inversiones",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

if _DEPLOY_MARKER or _GIT_SHA:
    _sha_short = _GIT_SHA[:7] if _GIT_SHA else ""
    st.sidebar.caption(
        f"Deploy: `{_DEPLOY_MARKER or '—'}`"
        + (f" · `{_sha_short}`" if _sha_short else "")
    )

if DEMO_MODE:
    st.sidebar.warning("**Modo demo** — datos sintéticos de ejemplo")

from data_engine import DataEngine, asignar_sector, obtener_ccl
from risk_engine import RiskEngine

# ── DEMO: parchear RUTA_TRANSAC en data_engine DESPUÉS de importarlo ──────────
# data_engine importa RUTA_TRANSAC de config al cargarse (línea 18 de data_engine.py).
# Esa copia local NO se ve afectada por el patch previo a config. Hay que parchearla aquí.
if DEMO_MODE:
    try:
        import data_engine as _de_mod
        _demo_csv_post = Path(DEMO_DB_PATH).with_suffix(".csv")
        if _demo_csv_post.exists():
            _de_mod.RUTA_TRANSAC = _demo_csv_post
            _log.info("DEMO MODE: data_engine.RUTA_TRANSAC -> %s", _demo_csv_post)
    except Exception as _e_de:
        try:
            _log.warning("DEMO: no se pudo parchear data_engine: %s", _e_de)
        except Exception:
            pass
import broker_importer as bi
import core.db_manager as dbm
import gmail_reader as gr
import libro_mayor as lm
import services.alert_bot as ab
import services.backtester as bt
import services.cartera_service as cs
import services.ejecucion_service as ejsvc
import services.market_connector as mc
import services.mod23_service as m23svc
import services.report_service as rpt
from core.cartera_scope import filtrar_transaccional_por_rol
from core.flow_manager import FlowManager
from core.price_engine import PriceEngine, records_tras_rellenar_ppc
from services.valoracion_audit import auditar_inferido_live_vs_resto, auditar_valoracion_por_tipo


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def _df_to_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=True, sheet_name="Datos")
    return buf.getvalue()

def _boton_exportar(df: pd.DataFrame, nombre: str, label: str = "📥 Exportar Excel"):
    if df is None or df.empty:
        return
    try:
        data = _df_to_excel(df)
        ext  = "xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except Exception:
        data = df.to_csv(index=True).encode("utf-8")
        ext  = "csv"
        mime = "text/csv"
    st.download_button(label, data=data, file_name=f"{nombre}.{ext}", mime=mime)


def _inject_css():
    # MQ-S9: Meta tags de seguridad removidas — no funcionan inyectadas via Streamlit.
    # Configurar en el reverse proxy (nginx/Railway) para producción.

    _css_path = BASE_DIR / "assets" / "style.css"
    _extra_css = _css_path.read_text(encoding="utf-8") if _css_path.exists() else ""
    # Consolidar en UNA sola llamada para evitar conflictos de reconciliación React.
    # El watermark se maneja exclusivamente via CSS (.stApp::after) en style.css.
    st.markdown(f"<style>{_extra_css}</style>", unsafe_allow_html=True)

_inject_css()


# ─── AUTENTICACIÓN ────────────────────────────────────────────────────────────
# ─── AUTENTICACIÓN SEGURA (core/auth.py — rate limiting, SHA-256, token de sesión) ──
from core.auth import check_password, get_user_role
from core.auth_saas import get_authenticator, get_tenant_id, login_saas
from core.mq26_disclaimers import LOGIN_LEGAL_DISCLAIMER_ES

_auth = get_authenticator()

if _auth is None and not (APP_PASSWORD or "").strip():
    st.error(
        "Falta la variable de entorno **`MQ26_PASSWORD`** (Railway → Variables, o `.env` en local). "
        "Sin ella no podés iniciar sesión en modo legacy."
    )
    st.info("Si usás modo SaaS, definí **`AUTH_CONFIG`** con credenciales YAML en su lugar.")
    st.stop()

if _auth is not None:
    # Modo SaaS: login individual por asesor
    st.caption(LOGIN_LEGAL_DISCLAIMER_ES)
    _name, _auth_ok, _username = login_saas(_auth)
    if not _auth_ok:
        if _auth_ok is False:
            st.error('Usuario o contraseña incorrectos.')
        st.stop()
    TENANT_ID = get_tenant_id(_auth)
    _inv_saas = {x.strip().lower() for x in os.environ.get("MQ26_INVESTORS", "").split(",") if x.strip()}
    _adv_saas = {x.strip().lower() for x in os.environ.get("MQ26_ADVISORS", "").split(",") if x.strip()}
    _vw = {x.strip().lower() for x in os.environ.get("MQ26_VIEWERS", "").split(",") if x.strip()}
    _un = (_username or "").strip().lower()
    if _un in _inv_saas:
        st.session_state["mq26_user_role"] = "inversor"
    elif _un in _adv_saas:
        st.session_state["mq26_user_role"] = "asesor"
    elif _un in _vw:
        st.session_state["mq26_user_role"] = "viewer"
    else:
        st.session_state["mq26_user_role"] = "admin"
else:
    # Modo local: auth legacy con contraseña única (sin cambios)
    if not check_password(
        'mq26', 'MQ26 — Terminal de Inversiones',
        subtitle='Optimizador Institucional BYMA',
        icon='📈',
        password_env=APP_PASSWORD,
        viewer_password_env=MQ26_VIEWER_PASSWORD,
        investor_password_env=MQ26_INVESTOR_PASSWORD,
        advisor_password_env=MQ26_ADVISOR_PASSWORD,
        user_admin=MQ26_USER_ADMIN,
        user_estudio=MQ26_USER_ESTUDIO,
        user_inversor=MQ26_USER_INVERSOR,
        user_asesor=MQ26_USER_ASESOR,
        username_login=True,
        try_database_users=_MQ26_TRY_DB_USERS,
        db_tenant_id=_MQ26_DB_TENANT_ID if _MQ26_TRY_DB_USERS else None,
    ):  # usuario + contraseña; opcional login desde tablas app_usuarios
        st.stop()
    TENANT_ID = 'default'


# ─── INICIALIZACIÓN ───────────────────────────────────────────────────────────
@st.cache_resource
def init_sistema():
    dbm.init_db()
    engine = DataEngine()
    # MQ2-A3: registrar universo en servicio centralizado
    try:
        from services.universo_service import set_universo_df
        set_universo_df(engine.universo_df)
    except Exception:
        pass
    # MQ2-S2: limpiar tokens de reporte expirados (> 24h)
    try:
        from datetime import datetime as _dt
        _ahora = _dt.now()
        _claves = dbm.obtener_clientes_df(tenant_id=TENANT_ID)  # disparador para init
        with dbm.get_session() as _sess:
            from sqlalchemy import text as _text
            _sess.execute(_text(
                "DELETE FROM configuracion WHERE clave LIKE 'token_reporte_%' "
                "AND CAST(strftime('%s','now') AS INTEGER) - "
                "CAST(strftime('%s', created_at) AS INTEGER) > 86400"
            ))
            _sess.commit()
    except Exception:
        pass
    return engine

# MQ2-A7: error handler global — muestra mensaje amigable si el motor falla
try:
    engine_data = init_sistema()
except Exception as _init_err:
    import logging as _logging
    _logging.error("init_sistema falló: %s", _init_err)
    st.error(
        f"**Error al iniciar MQ26**\n\n"
        f"No se pudo conectar a la base de datos o cargar el motor de datos.\n\n"
        f"`{type(_init_err).__name__}: {_init_err}`"
    )
    st.stop()


@st.cache_data(ttl=30, show_spinner=False)
def cached_clientes_df(tenant_id: str) -> pd.DataFrame:
    """Lista de clientes del tenant (ingreso + sidebar). tenant_id en la firma = clave de caché por tenant."""
    try:
        return dbm.obtener_clientes_df(tenant_id=tenant_id)
    except Exception:
        return pd.DataFrame()


def _df_clientes_scoped(tenant_id: str) -> pd.DataFrame:
    """Filtra por mq26_allowed_cliente_ids si el login vino de BD (o deja todo si es None)."""
    df = cached_clientes_df(tenant_id)
    allowed = st.session_state.get("mq26_allowed_cliente_ids")
    if allowed is None:
        return df
    if not allowed:
        return df.iloc[0:0].copy()
    return df[df["ID"].isin(allowed)].copy()


# Alias explícito: si algún deploy antiguo aún llama _cached_clientes_ingreso(), existe en globals.
_cached_clientes_ingreso = cached_clientes_df

# ─── PANTALLA DE INGRESO (v9 Quant Dark — tenant + RBAC) ─────────────────────
def _pantalla_ingreso():
    _ing_role = get_user_role("mq26")
    _puede_alta_cliente = _ing_role in ("super_admin", "asesor")

    st.markdown(
        """
    <div style="text-align:center;padding:3rem 0 2rem 0;">
        <div style="display:inline-flex;align-items:center;justify-content:center;
            width:52px;height:52px;background:rgba(59,130,246,0.12);
            border:1px solid rgba(59,130,246,0.25);border-radius:14px;
            font-size:1.5rem;margin-bottom:1.25rem;">📈</div>
        <h1 style="font-family:'DM Sans',sans-serif;font-size:1.5rem;font-weight:600;
            letter-spacing:-0.03em;color:#f1f5f9;margin:0 0 0.4rem 0;">
            MQ26 Terminal</h1>
        <p style="font-size:0.8125rem;color:#4b5563;margin:0;letter-spacing:0.01em;">
            Seleccioná un cliente para comenzar el análisis</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col_sel, col_sep, col_nuevo = st.columns([5, 1, 5])

    with col_sel:
        st.markdown(
            """
        <p style="font-size:0.72rem;font-weight:600;color:#4b5563;
            text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.75rem;">
            Cliente existente</p>""",
            unsafe_allow_html=True,
        )
        try:
            df_cli = _df_clientes_scoped(TENANT_ID)
        except Exception as _e:
            _log.exception("MQ26 pantalla ingreso: carga de clientes")
            st.error("No se pudo cargar la lista de clientes.")
            st.exception(_e)
            st.stop()
        if df_cli.empty:
            if _puede_alta_cliente:
                st.markdown(
                    """
                <div style="background:#0f1117;border:1px dashed rgba(255,255,255,0.08);
                    border-radius:12px;padding:2rem;text-align:center;">
                    <p style="color:#4b5563;font-size:0.8125rem;margin:0;">
                        Sin clientes aún.<br>Creá el primero a la derecha →</p>
                </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.warning(
                    "No hay clientes en la base. Iniciá sesión con usuario **admin** o **asesor** "
                    "y la contraseña correspondiente, y creá al menos un cliente."
                )
        else:
            opciones_cli = ["— Elegir cliente —"] + df_cli["Nombre"].tolist()
            sel = st.selectbox(
                "Cliente",
                opciones_cli,
                key="ing_sel_cliente",
                label_visibility="collapsed",
            )
            if sel != "— Elegir cliente —":
                row = df_cli[df_cli["Nombre"] == sel].iloc[0]
                sel_esc = html.escape(sel)
                perfil_raw = str(row.get("Perfil", ""))
                perfil_esc = html.escape(perfil_raw)
                perfil_color = {
                    "Conservador": "#10b981",
                    "Moderado": "#f59e0b",
                    "Agresivo": "#ef4444",
                    "Arriesgado": "#ef4444",
                    "Muy arriesgado": "#dc2626",
                }.get(perfil_raw, "#3b82f6")
                rgb = ",".join(
                    str(int(perfil_color.lstrip("#")[i : i + 2], 16)) for i in (0, 2, 4)
                )
                horiz_esc = html.escape(str(row.get("Horizonte", "1 año")))
                cap_usd = float(row.get("Capital_USD", 0) or 0)
                st.markdown(
                    f"""
                <div style="background:#161b27;border:1px solid rgba(255,255,255,0.08);
                    border-radius:12px;padding:1.25rem 1.5rem;margin-top:0.75rem;">
                    <div style="display:flex;justify-content:space-between;
                        align-items:flex-start;margin-bottom:0.75rem;">
                        <div>
                            <div style="font-weight:600;font-size:0.9375rem;
                                color:#f1f5f9;letter-spacing:-0.01em;">{sel_esc}</div>
                        </div>
                        <span style="background:rgba({rgb},0.15);color:{perfil_color};
                            font-size:0.65rem;font-weight:600;padding:2px 8px;
                            border-radius:999px;text-transform:uppercase;
                            letter-spacing:0.05em;">{perfil_esc}</span>
                    </div>
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;">
                        <div>
                            <div style="font-size:0.65rem;color:#4b5563;
                                text-transform:uppercase;letter-spacing:0.06em;">Horizonte</div>
                            <div style="font-size:0.8125rem;color:#94a3b8;margin-top:2px;">
                                {horiz_esc}</div>
                        </div>
                        <div>
                            <div style="font-size:0.65rem;color:#4b5563;
                                text-transform:uppercase;letter-spacing:0.06em;">Capital inicial</div>
                            <div style="font-family:'DM Mono',monospace;font-size:0.8125rem;
                                color:#94a3b8;margin-top:2px;">USD {cap_usd:,.0f}</div>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
                if st.button(
                    "Ingresar →",
                    type="primary",
                    use_container_width=True,
                    key="btn_ingresar",
                ):
                    st.session_state["cliente_id"] = int(row["ID"])
                    st.session_state["cliente_nombre"] = sel
                    st.session_state["cliente_perfil"] = row["Perfil"]
                    st.session_state["cliente_horizonte_label"] = row.get("Horizonte", "1 año")
                    st.rerun()

    with col_sep:
        st.markdown(
            """
        <div style="display:flex;flex-direction:column;align-items:center;height:100%;
            padding-top:2rem;">
            <div style="flex:1;width:1px;background:rgba(255,255,255,0.06);"></div>
            <span style="font-size:0.65rem;color:#4b5563;padding:0.5rem 0;
                letter-spacing:0.05em;">o</span>
            <div style="flex:1;width:1px;background:rgba(255,255,255,0.06);"></div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_nuevo:
        st.markdown(
            """
        <p style="font-size:0.72rem;font-weight:600;color:#4b5563;
            text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.75rem;">
            Nuevo cliente</p>""",
            unsafe_allow_html=True,
        )
        if not _puede_alta_cliente:
            if _ing_role == "estudio":
                st.info(
                    "El rol **estudio** (contraseña de visor / solo lectura) no puede registrar "
                    "clientes nuevos en la base de datos."
                )
            elif _ing_role == "inversor":
                st.info(
                    "El rol **inversor** no puede registrar clientes nuevos; solo podés operar "
                    "sobre clientes que ya existan."
                )
            else:
                st.info("Tu rol actual no puede registrar clientes nuevos.")
        else:
            with st.form("form_nuevo_cliente_ingreso", clear_on_submit=True):
                nc_nombre = st.text_input(
                    "Nombre completo",
                    placeholder="Ej: María Fernández",
                    key="nc_nombre_ingreso",
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    nc_perfil = st.selectbox(
                        "Perfil de riesgo",
                        ["Conservador", "Moderado", "Arriesgado", "Muy arriesgado"],
                        help="Conservador: preserva capital. Moderado: balance. "
                        "Arriesgado/Muy arriesgado: maximiza retorno.",
                    )
                with col_b:
                    nc_horiz = st.selectbox(
                        "Horizonte",
                        ["1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años"],
                        index=3,
                    )
                col_c, col_d = st.columns(2)
                with col_c:
                    nc_tipo = st.selectbox("Tipo", ["Persona", "Empresa"])
                with col_d:
                    nc_capital = st.number_input(
                        "Capital inicial (USD)",
                        min_value=0.0,
                        value=10_000.0,
                        step=1_000.0,
                        format="%.0f",
                    )
                submitted = st.form_submit_button(
                    "Crear cliente",
                    type="primary",
                    use_container_width=True,
                )
                if submitted:
                    if not nc_nombre.strip():
                        st.error("El nombre es obligatorio.")
                    else:
                        nuevo_id = dbm.registrar_cliente(
                            nc_nombre.strip(),
                            nc_perfil,
                            nc_capital,
                            nc_tipo,
                            nc_horiz,
                            tenant_id=TENANT_ID,
                        )
                        st.session_state["cliente_id"] = nuevo_id
                        st.session_state["cliente_nombre"] = nc_nombre.strip()
                        st.session_state["cliente_perfil"] = nc_perfil
                        st.session_state["cliente_horizonte_label"] = nc_horiz
                        try:
                            cached_clientes_df.clear()
                        except Exception:
                            pass
                        st.success(f"✓ {nc_nombre.strip()} creado")
                        st.rerun()

    st.markdown(
        """
    <div style="text-align:center;padding-top:3rem;padding-bottom:1rem;">
        <span style="font-size:0.65rem;color:#1f2937;letter-spacing:0.08em;">
            MQ26 · V8 · BYMA/CEDEARs</span>
    </div>
    """,
        unsafe_allow_html=True,
    )
    st.stop()

if "cliente_id" not in st.session_state:
    _pantalla_ingreso()


# ─── CACHE ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def cached_ccl():
    return obtener_ccl()

@st.cache_data(ttl=120, show_spinner=False)
def cached_transaccional(_mtime_key: float) -> pd.DataFrame:
    """
    Cache corto del transaccional.
    Se invalida al cambiar el mtime del CSV (sincronización/regeneración).
    """
    _ = _mtime_key
    return engine_data.cargar_transaccional()

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
    import io as _io_f6

    import services.cartera_service as _cs_f6
    try:
        _df_f6 = pd.read_json(_io_f6.StringIO(df_serialized))
        return _cs_f6.metricas_resumen(_df_f6) if not _df_f6.empty else {}
    except Exception:
        return {}


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 📈 MQ26 — Inversiones")
_login_u = st.session_state.get("mq26_login_user", "")
if _login_u:
    st.sidebar.caption(f"Sesión: **{_login_u}** · rol {get_user_role('mq26')}")
_mq26_viewer = get_user_role("mq26") in ("estudio", "inversor")
if _mq26_viewer:
    st.sidebar.info(
        "👁️ **Solo lectura**: sincronización, credenciales y escrituras a BD están deshabilitadas."
    )

# MQ2-A9: badge de estado del circuit breaker de yfinance
try:
    from services.precio_cache_service import estado_circuit_breaker as _cb_estado
    _cb = _cb_estado()
    if _cb["degradado"]:
        st.sidebar.error(
            f"🔴 **Precios offline** — yfinance bloqueado por {_cb['segundos_restantes']}s. "
            "Usando precios fallback."
        )
except Exception:
    pass

# MQ2-S7: botón de cierre de sesión explícito
if st.sidebar.button("🔒 Cerrar sesión", key="btn_cerrar_sesion_mq", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.markdown("---")

info_bd = dbm.info_backend()
backend_label = "🟢 PostgreSQL" if info_bd["backend"] == "postgresql" else "🟡 SQLite Local"
st.sidebar.caption(f"BD: {backend_label}")

# MQ2-D3: toggle modo claro/oscuro (CSS puro — sin <script> que rompe React DOM)
_light_mode = st.sidebar.toggle("☀️ Modo claro", key="mq_light_mode", value=False)
if _light_mode:
    st.markdown("""
    <style>
        .stApp, [data-testid="stAppViewContainer"] {
            background-color: #FAFAFA !important;
            color: #1A1A2E !important;
        }
        .stSidebar, [data-testid="stSidebar"] > div {
            background-color: #F0F0F5 !important;
            color: #1A1A2E !important;
        }
        p, span, label, .stMarkdown, h1, h2, h3, h4 {
            color: #1A1A2E !important;
        }
    </style>
    """, unsafe_allow_html=True)

ccl = cached_ccl()
st.sidebar.metric("💵 Dólar CCL/MEP", f"${ccl:,.0f}")
st.sidebar.markdown("---")

_cliente_id     = st.session_state.get("cliente_id")
_cliente_nombre = st.session_state.get("cliente_nombre", "")
_cliente_perfil = st.session_state.get("cliente_perfil", "Moderado")
_horiz_label    = st.session_state.get("cliente_horizonte_label", "1 año")

st.sidebar.markdown(f"**👤 {_cliente_nombre}**")
st.sidebar.caption(f"Perfil: {_cliente_perfil}  |  Horizonte: {_horiz_label}")
if st.sidebar.button("🔄 Cambiar cliente", key="btn_cambiar_cliente", use_container_width=True):
    for k in ["cliente_id","cliente_nombre","cliente_perfil","cliente_horizonte_label"]:
        st.session_state.pop(k, None)
    st.rerun()
st.sidebar.markdown("---")

horizonte_dias = dbm.HORIZONTE_DIAS.get(_horiz_label, 365)
n_escenarios   = st.sidebar.selectbox("Simulaciones MC:", [1000, 3000, 5000, 10000], index=2)
capital_nuevo  = float(st.session_state.get("capital_inyectado_mq26", 0.0))
st.sidebar.markdown("---")

df_clientes = _df_clientes_scoped(TENANT_ID)
_ruta_transac_main = BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
_mtime_transac_main = _ruta_transac_main.stat().st_mtime if _ruta_transac_main.exists() else 0.0
trans = cached_transaccional(_mtime_transac_main)
_mq26_role = get_user_role("mq26")
trans = filtrar_transaccional_por_rol(trans, _mq26_role, _cliente_nombre, df_clientes)

carteras_csv: list[str] = []
if not trans.empty and "CARTERA" in trans.columns:
    carteras_csv = sorted(trans["CARTERA"].dropna().unique().tolist())

if _mq26_role == "inversor":
    if len(carteras_csv) <= 1:
        carteras_opciones = list(carteras_csv)
        if not carteras_opciones and _cliente_nombre.strip():
            carteras_opciones = [f"{_cliente_nombre.strip()} | (sin datos)"]
    else:
        carteras_opciones = ["-- Todas las carteras --"] + list(carteras_csv)
else:
    carteras_opciones = ["-- Todas las carteras --"] + list(carteras_csv)
    if not df_clientes.empty:
        propietarios_csv = {c.split("|")[0].strip() for c in carteras_csv}
        for _nombre_cli in sorted(df_clientes["Nombre"].dropna().tolist()):
            if _nombre_cli.strip() not in propietarios_csv:
                carteras_opciones.append(f"{_nombre_cli.strip()} | (sin datos)")

_default_cartera_idx = 0
if _mq26_role == "inversor":
    for _i, _opt in enumerate(carteras_opciones):
        if _opt.endswith("| (sin datos)"):
            _default_cartera_idx = _i
            break
        if "|" in _opt:
            _pref = _opt.split("|")[0].strip()
            if _cliente_nombre and _pref == _cliente_nombre.strip():
                _default_cartera_idx = _i
                break
else:
    for _i, _opt in enumerate(carteras_opciones):
        if _opt in ("-- Todas las carteras --",) or _opt.endswith("| (sin datos)"):
            continue
        if "|" in _opt:
            _pref = _opt.split("|")[0].strip()
            if _cliente_nombre and _pref == _cliente_nombre.strip():
                _default_cartera_idx = _i
                break

_default_cartera_idx = min(_default_cartera_idx, max(0, len(carteras_opciones) - 1))

cartera_activa = st.sidebar.selectbox("📁 Cartera activa:", carteras_opciones,
                                       index=_default_cartera_idx)

# Sprint 16: contexto de log estructurado para toda la sesión
try:
    from core.logging_config import set_log_context
    set_log_context(
        tenant=TENANT_ID,
        cartera=(cartera_activa.split("|")[-1].strip()[:20]
                 if "|" in cartera_activa else cartera_activa[:20]),
        env=os.environ.get("RAILWAY_ENVIRONMENT", "dev"),
    )
except Exception:
    pass

st.sidebar.checkbox("Usar FIFO para PPC", key="modo_ppc_fifo", value=False)
st.sidebar.markdown("---")

with st.sidebar.expander("🔄 Sincronización de datos"):
    _ruta_transac_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
    _ruta_maestra_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
    _ruta_sqlite_sb  = BASE_DIR / "0_Data_Maestra" / "master_quant.db"
    if _ruta_transac_sb.exists():
        _mtime = datetime.fromtimestamp(_ruta_transac_sb.stat().st_mtime).strftime("%d/%m %H:%M")
        st.caption(f"CSV: {_mtime}")

    # MQ2-S8: rate limiting — máx 3 sincronizaciones en 60 segundos
    import time as _time_rl
    _sync_times = st.session_state.get("_sync_timestamps", [])
    _ahora_rl   = _time_rl.monotonic()
    _sync_times = [t for t in _sync_times if _ahora_rl - t < 60]
    _bloqueado  = len(_sync_times) >= 3
    _espera_rl  = max(0, int(60 - (_ahora_rl - _sync_times[0]))) if _bloqueado else 0

    if _bloqueado:
        st.warning(f"⏳ Rate limit — esperá {_espera_rl}s antes de sincronizar de nuevo.")
    else:
        if st.button("🔄 Regenerar desde Excel", key="btn_regen_csv", disabled=_bloqueado or _mq26_viewer):
            _sync_times.append(_ahora_rl)
            st.session_state["_sync_timestamps"] = _sync_times
            if _ruta_transac_sb.exists():
                _ruta_transac_sb.unlink()
            st.cache_data.clear()
            st.rerun()
    st.session_state["_sync_timestamps"] = _sync_times

with st.sidebar.expander("💰 Precios fallback"):
    _fb = cs.PRECIOS_FALLBACK_ARS.copy()
    _df_fb = pd.DataFrame([{"Ticker": t, "Precio ARS": p} for t, p in sorted(_fb.items())])
    _df_fb_edit = st.data_editor(
        _df_fb.reset_index(drop=True), num_rows="dynamic", use_container_width=True,
        column_config={
            "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
            "Precio ARS": st.column_config.NumberColumn("Precio ARS", min_value=0, format="$%d"),
        },
        key="editor_fallback_sb", hide_index=True, disabled=_mq26_viewer,
    )
    if st.button("💾 Aplicar precios", key="btn_aplicar_fb", disabled=_mq26_viewer):
        _nuevos = {t: float(p) for t, p in zip(_df_fb_edit["Ticker"], _df_fb_edit["Precio ARS"])
                   if t and p and float(p) > 0}
        # MQ2-S3: validar rango — diff > 50% requiere confirmación
        _precios_sospechosos = []
        for _t_fb, _p_fb in _nuevos.items():
            _p_ant = _fb.get(_t_fb, _p_fb)
            if _p_ant > 0 and abs(_p_fb / _p_ant - 1) > 0.50:
                _precios_sospechosos.append(f"{_t_fb}: {_p_ant:,.0f} → {_p_fb:,.0f} ({(_p_fb/_p_ant-1):+.0%})")
        if _precios_sospechosos:
            st.warning(
                "⚠️ **Cambio > 50% detectado** en:\n" + "\n".join(_precios_sospechosos) +
                "\n\nPresioná nuevamente para confirmar."
            )
            if not st.session_state.get("_fb_confirm"):
                st.session_state["_fb_confirm"] = True
                st.stop()
        st.session_state.pop("_fb_confirm", None)
        # MQ2-S4: log de cambios en alertas_log
        for _t_fb, _p_fb in _nuevos.items():
            _p_ant = _fb.get(_t_fb, _p_fb)
            if _p_ant != _p_fb:
                try:
                    dbm.registrar_alerta(
                        tipo_alerta="PRECIO_MANUAL",
                        mensaje=f"Fallback {_t_fb}: {_p_ant:,.0f} → {_p_fb:,.0f}",
                        ticker=_t_fb
                    )
                except Exception:
                    pass
        cs.actualizar_fallback(_nuevos)
        st.cache_data.clear()
        st.rerun()

    # MQ2-S1: verificar integridad HMAC de backups
    st.divider()
    st.caption("🔒 Integridad de backups")
    _bak_files = sorted((BASE_DIR / "0_Data_Maestra").glob("*.bak_*.xlsx")) if (BASE_DIR / "0_Data_Maestra").exists() else []
    if _bak_files:
        st.caption(f"{len(_bak_files)} backups disponibles")
    else:
        st.caption("Sin backups locales")

with st.sidebar.expander("🚀 Motor de Salida — Config"):
    # MQ2-D6: capital_disponible configurable desde sidebar
    _cap_default = float(dbm.obtener_config("capital_disponible_mq", "500000") or 500000)
    _capital_disp = st.number_input(
        "Capital disponible (ARS):",
        min_value=0.0, value=_cap_default, step=10_000.0, format="%.0f",
        key="capital_disponible_input", help="Capital para calcular órdenes de compra",
        disabled=_mq26_viewer,
    )
    if st.button("💾 Guardar capital", key="btn_guardar_cap", disabled=_mq26_viewer):
        dbm.guardar_config("capital_disponible_mq", str(_capital_disp))
        st.success("✅ Capital guardado")
    # Hacer disponible para el Motor de Salida
    st.session_state["capital_disponible_mq"] = _capital_disp

with st.sidebar.expander("⚙️ Salud del sistema"):
    import datetime as _dt_sys
    st.markdown(f"**Última sync:** {_dt_sys.datetime.now().strftime('%H:%M:%S')}")
    st.markdown(f"**BD:** {dbm.info_backend()['backend'].upper()}")
    st.markdown(f"**CCL:** ${ccl:,.0f}")

with st.sidebar.expander("📱 Alertas Telegram"):
    # MQ-S1: Las credenciales Telegram se persisten en la BD, NO en os.environ
    _tg_token_bd = dbm.obtener_config("telegram_token", "")
    _tg_chat_bd  = dbm.obtener_config("telegram_chat_id", "")
    tg_token = st.text_input(
        "Bot Token", type="password",
        value=_tg_token_bd or os.environ.get("TELEGRAM_TOKEN", ""),
        disabled=_mq26_viewer,
    )
    tg_chat = st.text_input(
        "Chat ID",
        value=_tg_chat_bd or os.environ.get("TELEGRAM_CHAT_ID", ""),
        disabled=_mq26_viewer,
    )
    if st.button("💾 Guardar credenciales", key="btn_tg_guardar", disabled=_mq26_viewer):
        if tg_token:
            dbm.guardar_config("telegram_token", tg_token)
        if tg_chat:
            dbm.guardar_config("telegram_chat_id", tg_chat)
        st.success("✅ Guardadas en BD")
    if st.button("🔔 Probar conexión", key="btn_tg_probar", disabled=_mq26_viewer):
        if tg_token and tg_chat:
            # Solo poner en env para la prueba (en-memoria, no persiste entre procesos)
            os.environ["TELEGRAM_TOKEN"]   = tg_token
            os.environ["TELEGRAM_CHAT_ID"] = tg_chat
            ok = ab.test_conexion()
            st.success("✅ Telegram OK") if ok else st.error("❌ Sin respuesta")


# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown(
    '<p class="main-header">MQ26 · Terminal de inversiones</p>',
    unsafe_allow_html=True,
)
# MQ-S2: html.escape para prevenir XSS si el nombre del cliente contiene caracteres especiales
_nombre_safe = html.escape(_cliente_nombre)
st.markdown(
    f'<p class="sub-header">BYMA · Master Quant 26'
    f'{" · " + _nombre_safe if _nombre_safe else ""}</p>',
    unsafe_allow_html=True,
)

# MQ2-U9: chequeo SPY opcional para no bloquear carga inicial en redes lentas.
# Activar con MQ26_ENABLE_SPY_REGIMEN=1 en .env
if os.environ.get("MQ26_ENABLE_SPY_REGIMEN", "0").strip() == "1":
    try:
        @st.cache_data(ttl=3600)
        def _spy_regimen():
            import yfinance as _yf_spy
            _h = _yf_spy.Ticker("SPY").history(period="30d")["Close"].dropna()
            if len(_h) >= 20:
                _ret = _h.iloc[-1] / _h.iloc[-20] - 1
                return float(_ret)
            return 0.0
        _spy_ret = _spy_regimen()
        if _spy_ret < -0.10:
            st.error(
                f"⚠️ **Mercado en corrección** — SPY bajó **{_spy_ret:.1%}** en los últimos 20 días. "
                "El contexto macro se ajustó automáticamente a **ALTO riesgo**."
            )
            st.session_state["recesion_riesgo"] = "ALTO"
        elif _spy_ret < -0.05:
            st.warning(f"📉 SPY en zona de alerta: {_spy_ret:.1%} en 20 días.")
    except Exception:
        pass

# ─── CARGA DE DATOS ───────────────────────────────────────────────────────────
df_analisis = engine_data.cargar_analisis()
df_ag = pd.DataFrame()
tickers_cartera = []
precios_dict = {}
prop_nombre  = ""
price_coverage_pct = 100.0
tickers_sin_precio = []
valoracion_audit: dict = {}
st.session_state.pop("_mq26_audit_ctx", None)

_cartera_sin_datos = cartera_activa.endswith("| (sin datos)")
if cartera_activa != "-- Todas las carteras --" and not _cartera_sin_datos and not trans.empty:
    # MQ2-D5: hash robusto SHA-256 del DataFrame — detecta ediciones de precio/fecha
    import hashlib as _hl
    _df_hash_bytes = str(pd.util.hash_pandas_object(
        trans[trans["CARTERA"] == cartera_activa] if "CARTERA" in trans.columns else trans
    ).sum()).encode()
    _trans_hash = _hl.sha256(_df_hash_bytes + cartera_activa.encode()).hexdigest()
    _cache_key_ag = f"_df_ag_cache_{cartera_activa}"
    _cache_key_h  = f"_df_ag_hash_{cartera_activa}"
    _modo_ppc     = st.session_state.get("modo_ppc_fifo", False)
    _cache_key_fifo = f"_df_ag_fifo_{cartera_activa}"

    if (st.session_state.get(_cache_key_h) != _trans_hash or
            st.session_state.get(_cache_key_fifo) != _modo_ppc):
        df_ag = (engine_data.agregar_cartera_fifo(trans, cartera_activa) if _modo_ppc
                 else engine_data.agregar_cartera(trans, cartera_activa))
        st.session_state[_cache_key_ag]   = df_ag
        st.session_state[_cache_key_h]    = _trans_hash
        st.session_state[_cache_key_fifo] = _modo_ppc
    else:
        df_ag = st.session_state.get(_cache_key_ag, pd.DataFrame())

    if not df_ag.empty:
        tickers_cartera = df_ag["TICKER"].str.upper().tolist()
        precios_dict_live = cached_precios_actuales(tuple(tickers_cartera), ccl)
        cs.asegurar_precios_fallback_cargados()
        _n_live = sum(
            1 for t in tickers_cartera if float(precios_dict_live.get(str(t).upper(), 0) or 0) > 0
        )
        _univ_n = (
            int(len(engine_data.universo_df))
            if getattr(engine_data, "universo_df", None) is not None
            and not engine_data.universo_df.empty
            else 0
        )
        prop_nombre = cartera_activa.split("|")[0].strip() if "|" in cartera_activa else cartera_activa
        # S2: PriceEngine — solo `precios_dict_live` como override (live real); resto BYMA/yfinance/BD
        _records: dict = {}
        try:
            _pe = PriceEngine(universo_df=engine_data.universo_df)
            _records = _pe.get_portfolio(
                tickers_cartera, ccl, precios_live_override=precios_dict_live
            )
            price_coverage_pct = _pe.cobertura_pct(_records)
            tickers_sin_precio = _pe.tickers_sin_precio(_records)
            precios_dict = _pe.to_precios_ars(_records)
            _n_pe = sum(1 for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) > 0)
            _sources = {}
            for _tk, _rec in list(_records.items())[:12]:
                _sources[str(_tk)] = getattr(_rec.source, "value", str(_rec.source))
        except Exception as _e_pe:
            _log.debug("PriceEngine: %s", _e_pe)
            precios_dict = cs.resolver_precios(
                tickers_cartera, precios_dict_live, ccl,
                universo_df=engine_data.universo_df,
            )
            price_coverage_pct = 100.0 if precios_dict and len(precios_dict) >= len(tickers_cartera) else 0.0
            tickers_sin_precio = [
                t for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) <= 0
            ]

        _n_res = sum(
            1 for t in tickers_cartera if float(precios_dict.get(str(t).upper(), 0) or 0) > 0
        )

        _precios_pre_ppc = dict(precios_dict)
        if tickers_sin_precio:
            precios_dict = cs.rellenar_precios_desde_ultimo_ppc(
                trans, cartera_activa, tickers_cartera, precios_dict, float(ccl or 0)
            )
            if _records:
                _records = records_tras_rellenar_ppc(
                    _records, _precios_pre_ppc, precios_dict, float(ccl or 0)
                )
            tickers_sin_precio = [
                t
                for t in tickers_cartera
                if float(precios_dict.get(str(t).upper(), 0) or 0) <= 0
            ]
            price_coverage_pct = (
                round(
                    100.0 * (len(tickers_cartera) - len(tickers_sin_precio)) / len(tickers_cartera),
                    1,
                )
                if tickers_cartera
                else 100.0
            )

        st.session_state["_mq26_audit_ctx"] = {
            "records": _records,
            "precios_live": dict(precios_dict_live),
            "precios_final": dict(precios_dict),
        }

if _cartera_sin_datos:
    prop_nombre = cartera_activa.replace("| (sin datos)", "").strip()
    st.info(f"**{prop_nombre}** no tiene posiciones cargadas aún. "
            "Ir al **Tab Cartera & Libro Mayor** para cargarlas.")

metricas = {}
if not df_ag.empty and precios_dict:
    df_ag = cs.calcular_posicion_neta(
        df_ag, precios_dict, ccl, universo_df=engine_data.universo_df
    )
    _aud_ctx = st.session_state.get("_mq26_audit_ctx") or {}
    _aud_rec = _aud_ctx.get("records") or {}
    if _aud_rec:
        valoracion_audit = auditar_valoracion_por_tipo(df_ag, _aud_rec)
    else:
        valoracion_audit = auditar_inferido_live_vs_resto(
            df_ag,
            _aud_ctx.get("precios_live") or {},
            _aud_ctx.get("precios_final") or precios_dict,
        )
    st.session_state["valoracion_audit"] = valoracion_audit
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

    # MQ2-V9: actualizar favicon en session_state para próxima carga
    st.session_state["_pnl_total_favicon"] = total_pnl

    _cartera_corta = (
        cartera_activa.split("|")[1].strip() if "|" in cartera_activa else cartera_activa
    )
    _valor_txt = (
        f"${total_valor / 1e6:.2f}M ARS" if total_valor > 1e6 else f"${total_valor:,.0f} ARS"
    )
    st.markdown(
        topline_html(
            cartera=_cartera_corta or "Mi cartera",
            cliente=prop_nombre,
            perfil=_cliente_perfil or "Moderado",
            valor_txt=_valor_txt,
            pnl_pct=pnl_pct_total,
            ccl=ccl,
            n_pos=int(metricas.get("n_posiciones", 0) or 0) if metricas else 0,
        ),
        unsafe_allow_html=True,
    )

    _m_cols = st.columns(4)
    _pnl_sign = "+" if pnl_pct_total >= 0 else ""
    with _m_cols[0]:
        st.markdown(
            metric_card_html("Valor cartera", _valor_txt, icon="💰"),
            unsafe_allow_html=True,
        )
    with _m_cols[1]:
        st.markdown(
            metric_card_html(
                "P&L total",
                f"{_pnl_sign}{pnl_pct_total:.1%}",
                delta=f"${total_pnl:,.0f} ARS",
                delta_ok=pnl_pct_total >= 0,
                icon="📈" if pnl_pct_total >= 0 else "📉",
            ),
            unsafe_allow_html=True,
        )
    with _m_cols[2]:
        st.markdown(
            metric_card_html("CCL", f"${ccl:,.0f}", icon="💱"),
            unsafe_allow_html=True,
        )
    with _m_cols[3]:
        st.markdown(
            metric_card_html(
                "Posiciones",
                str(metricas.get("n_posiciones", 0)) if metricas else "—",
                icon="📊",
            ),
            unsafe_allow_html=True,
        )
    st.divider()

    # Semáforos sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Resumen cartera")
    st.sidebar.metric("Valor", f"${total_valor/1e6:.2f}M ARS" if total_valor > 1e6 else f"${total_valor:,.0f} ARS")
    st.sidebar.metric("P&L", f"${total_pnl:,.0f} ARS", f"{pnl_pct_total:.1%}")
    _sem_txt = "En ganancia" if pnl_pct_total >= 0 else "En pérdida"
    st.sidebar.caption(f"{_sem_txt} · {pnl_pct_total:+.1%}")
    _va = st.session_state.get("valoracion_audit") or {}
    if _va.get("total_valor_ars", 0) > 0:
        with st.sidebar.expander("Cobertura de precios (live vs fallback)", expanded=False):
            st.caption(
                f"Valor con cotización **live**: **{_va.get('pct_valor_live', 0):.1f}%** "
                f"— resto fallback / PPC / BD."
            )
            _por = _va.get("por_tipo") or {}
            for _tipo, _b in sorted(_por.items()):
                st.caption(
                    f"**{_tipo}** — {_b.get('pct_valor_live', 0):.1f}% del valor con precio live"
                )

# Alerta objetivos
if _cliente_id and not st.session_state.get("_objetivos_alertas_verificados"):
    try:
        _df_obj = dbm.obtener_objetivos_cliente(_cliente_id)
        if not _df_obj.empty:
            _n = ab.verificar_objetivos_por_vencer(_df_obj, _cliente_nombre)
            if _n > 0:
                st.toast(f"⏰ {_n} objetivo(s) próximos a vencer", icon="⏰")
    except Exception:
        pass
    st.session_state["_objetivos_alertas_verificados"] = True


def _n_alertas_concentracion(df_ag: pd.DataFrame) -> int:
    """Cuenta tickers con peso > 30% (alerta de concentración)."""
    if df_ag is None or df_ag.empty or "PESO_PCT" not in df_ag.columns:
        return 0
    return int((df_ag["PESO_PCT"] > 30.0).sum())

# ─── IMPORTS TABS ─────────────────────────────────────────────────────────────
from ui.tab_cartera import render_tab_cartera
from ui.tab_ejecucion import render_tab_ejecucion
from ui.tab_inversor import render_tab_inversor
from ui.carga_activos import render_carga_activos
from ui.tab_estudio import render_tab_estudio
from ui.tab_admin import render_tab_admin
from ui.tab_optimizacion import render_tab_optimizacion
from ui.tab_reporte import render_tab_reporte
from ui.tab_riesgo import render_tab_riesgo
from ui.tab_universo import render_tab_universo
from ui.workflow_header import render_workflow_header
from ui.mq26_ux import metric_card_html, topline_html

# ─── CONTEXTO ─────────────────────────────────────────────────────────────────
ctx = {
    "df_ag":            df_ag,
    "tickers_cartera":  tickers_cartera,
    "precios_dict":     precios_dict,
    "ccl":              ccl,
    "cartera_activa":   cartera_activa,
    "prop_nombre":      prop_nombre,
    "df_clientes":      df_clientes,
    "df_analisis":      df_analisis,
    "metricas":         metricas if not df_ag.empty and precios_dict else {},
    "tenant_id":        TENANT_ID,
    "cliente_id":       _cliente_id,
    "cliente_nombre":   _cliente_nombre,
    "cliente_perfil":   _cliente_perfil,
    "horizonte_label":  _horiz_label,
    "RISK_FREE_RATE":   RISK_FREE_RATE,
    "PESO_MAX_CARTERA": PESO_MAX_CARTERA,
    "N_SIM_DEFAULT":    N_SIM_DEFAULT,
    "RUTA_ANALISIS":    RUTA_ANALISIS,
    "horizonte_dias":   horizonte_dias,
    "capital_nuevo":    capital_nuevo,
    "BASE_DIR":         BASE_DIR,
    "df_trans":         trans,
    "engine_data":      engine_data,
    "universo_df":      getattr(engine_data, "universo_df", None),
    "RiskEngine":       RiskEngine,
    "cached_historico": cached_historico,
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
    "_boton_exportar": _boton_exportar,
    "asignar_sector":  asignar_sector,
    "render_carga_activos_fn": render_carga_activos,
    "user_role":       _mq26_role,
    "price_coverage_pct": price_coverage_pct,
    "tickers_sin_precio": tickers_sin_precio,
}

# S2: FlowManager — contexto de workflow y siguiente acción
# S7: MOD-23 alertas para FlowManager
_n_mod23_alertas = 0
_n_vencimientos  = 0
try:
    from services.monitor_service import contar_vencimientos_proximos
    _n_vencimientos = contar_vencimientos_proximos(
        ctx.get("cliente_id") if isinstance(ctx, dict) else None, dias=7
    )
except Exception:
    pass
try:
    if not df_analisis.empty and tickers_cartera:
        _n_mod23_alertas = len(m23svc.detectar_alertas_venta(df_analisis, tickers_cartera))
except Exception:
    pass

_flow_ctx = {
    "price_coverage_pct":     price_coverage_pct,
    "n_concentration_alerts": _n_alertas_concentracion(df_ag),
    "n_mod23_alertas":        _n_mod23_alertas,
    "n_vencimientos_proximos": _n_vencimientos,
    "max_drift_pct":          st.session_state.get("max_drift_pct", 0.0),
    "optimizacion_aprobada":  st.session_state.get("optimizacion_aprobada", False),
    "ordenes_aprobadas":      st.session_state.get("ordenes_aprobadas", False),
    "ordenes_pendientes":     st.session_state.get("n_ordenes_pendientes", 0),
    "ultimo_reporte_generado": st.session_state.get("ultimo_reporte_generado", False),
}
_fm = FlowManager()
_flow_resumen = _fm.resumen(_flow_ctx)
ctx["flow_resumen"] = _flow_resumen

# S4: Header de workflow — oculto para inversor (experiencia tipo producto retail)
if _mq26_role != "inversor":
    render_workflow_header(_flow_resumen, compact=False)

# ─── TABS por rol (tiers SA/ES/IN) ───────────────────────────────────────────
_role = _mq26_role
if _role == "inversor":
    (t1,) = st.tabs(["Mi cartera"])
    with t1:
        render_tab_inversor(ctx)
elif _role == "estudio":
    t1, t2, t3, t4 = st.tabs(["Clientes", "Cartera", "Reportes", "Universo"])
    with t1:
        render_tab_estudio(ctx)
    with t2:
        render_tab_cartera(ctx)
    with t3:
        render_tab_reporte(ctx)
    with t4:
        render_tab_universo(ctx)
elif _role == "asesor":
    t1, t2, t3, t4, t5, t6 = st.tabs([
        "Cartera y libro mayor",
        "Universo y señales",
        "Optimización",
        "Riesgo y simulación",
        "Mesa de ejecución",
        "Reporte",
    ])
    with t1:
        render_tab_cartera(ctx)
    with t2:
        render_tab_universo(ctx)
    with t3:
        render_tab_optimizacion(ctx)
    with t4:
        render_tab_riesgo(ctx)
    with t5:
        render_tab_ejecucion(ctx)
    with t6:
        render_tab_reporte(ctx)
else:
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "1. Cartera y libro mayor",
        "2. Universo y señales",
        "3. Optimización",
        "4. Riesgo y simulación",
        "5. Mesa de ejecución",
        "6. Reporte",
        "Admin",
    ])
    with t1:
        render_tab_cartera(ctx)
    with t2:
        render_tab_universo(ctx)
    with t3:
        render_tab_optimizacion(ctx)
    with t4:
        render_tab_riesgo(ctx)
    with t5:
        render_tab_ejecucion(ctx)
    with t6:
        render_tab_reporte(ctx)
    with t7:
        render_tab_admin(ctx)

# Motor de Salida
if st.sidebar.button("🚪 Motor de Salida", use_container_width=True, key="btn_motor_salida"):
    st.session_state["tab_activo"] = "motor_salida"

if st.session_state.get("tab_activo") == "motor_salida":
    precios_act = precios_dict if 'precios_dict' in dir() else {}
    scores_act  = {r.get("Ticker",""):r.get("Score_Total",50)
                   for r in st.session_state.get("df_scores", pd.DataFrame()).to_dict("records")} \
                   if not st.session_state.get("df_scores", pd.DataFrame()).empty else {}
    rsi_act = {r.get("Ticker",""):r.get("RSI",50)
               for r in st.session_state.get("df_scores", pd.DataFrame()).to_dict("records")} \
               if not st.session_state.get("df_scores", pd.DataFrame()).empty else {}

    from services.motor_salida import render_motor_salida
    render_motor_salida(
        df_posiciones=df_ag if not df_ag.empty else pd.DataFrame(),
        precios_actuales=precios_act,
        scores_actuales=scores_act,
        rsi_actuales=rsi_act,
        perfil=_cliente_perfil or "Moderado",
        ccl=ccl,
        capital_disponible=float(st.session_state.get("capital_disponible_mq", 500_000)),
    )

# ─── FOOTER ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"📈 MQ26 Terminal de Inversiones | BD: {info_bd['backend'].upper()} | "
           f"CCL: ${ccl:,.0f} | © Estrategia Capitales {datetime.now().year}")
