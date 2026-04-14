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
    # override=True: si en PowerShell quedó MQ26_PASSWORD=otra (p. ej. tests), el .env debe ganar en local.
    load_dotenv(BASE_DIR / ".env", override=True)
except ImportError:
    pass

from core.logging_config import get_logger
from core.structured_logging import log_degradacion

_log = get_logger(__name__)


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
    page_icon="📈",
    initial_sidebar_state="expanded",
)


def _mq26_logged_in() -> bool:
    return bool(
        st.session_state.get("mq26_auth")
        or (st.session_state.get("authentication_status") is True)
    )


def _inject_css_markdown(_extra_css: str, _light_css: str) -> None:
    st.markdown(
        f"<style>{_extra_css}{_light_css}</style>",
        unsafe_allow_html=True,
    )


def _build_theme_css(*, use_light: bool) -> tuple[str, str]:
    """Devuelve (extra_css, light_css) para un solo bloque <style>."""
    from ui.mq26_theme import build_theme_css_bundle

    return build_theme_css_bundle(BASE_DIR, use_light=use_light)


def _inject_css_pre_login():
    # Pantalla de login: sin sesión aún o credencial no validada en esta corrida.
    # Siempre tema claro retail aquí: contraste legible (texto/placeholders) como el resto de la app.
    if _mq26_logged_in():
        return
    _extra, _light = _build_theme_css(use_light=True)
    _inject_css_markdown(_extra, _light)


def _sync_mq_light_session_post_auth() -> None:
    """Default claro para inversor; no pisar si el usuario ya eligió oscuro (toggle)."""
    from core.auth import get_user_role as _role

    if _role("mq26") != "inversor":
        return
    if "mq_light_mode" not in st.session_state:
        st.session_state["mq_light_mode"] = True
    if st.session_state.get("inv_mostrar_sugerencia"):
        st.session_state["mq_light_mode"] = True


def _inject_css_after_auth():
    # MQ-S9: Meta tags de seguridad removidas — no funcionan inyectadas via Streamlit.
    # Tema sólo después de auth: mq_light_mode y rol están alineados (evita default False del toggle).
    if not _mq26_logged_in():
        return
    _sync_mq_light_session_post_auth()
    try:
        from core.auth import get_user_role as _get_user_role_css

        if "mq_light_mode" not in st.session_state:
            st.session_state["mq_light_mode"] = bool(
                _get_user_role_css("mq26") == "inversor"
            )
        _use_light = bool(st.session_state["mq_light_mode"])
    except Exception:
        _use_light = True
    _extra, _light = _build_theme_css(use_light=_use_light)
    _inject_css_markdown(_extra, _light)


_inject_css_pre_login()

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
    # Modo SaaS: login individual por usuario
    st.caption(LOGIN_LEGAL_DISCLAIMER_ES)
    st.markdown(
        '<p class="mq-auth-login-subtitle" style="text-align:center;margin:0.25rem 0 0.75rem 0;">'
        "Tu cartera de inversiones, ordenada.</p>",
        unsafe_allow_html=True,
    )
    _name, _auth_ok, _username = login_saas(_auth)
    if not _auth_ok:
        if _auth_ok is False:
            st.error('Usuario o contraseña incorrectos.')
        st.stop()
    TENANT_ID = get_tenant_id(_auth)
    _inv_saas = {x.strip().lower() for x in os.environ.get("MQ26_INVESTORS", "").split(",") if x.strip()}
    _vw = {x.strip().lower() for x in os.environ.get("MQ26_VIEWERS", "").split(",") if x.strip()}
    _un = (_username or "").strip().lower()
    if _un in _inv_saas:
        st.session_state["mq26_user_role"] = "inversor"
    elif _un in _vw:
        st.session_state["mq26_user_role"] = "viewer"
    else:
        st.session_state["mq26_user_role"] = "admin"
else:
    # Modo local: auth legacy con contraseña única (sin cambios)
    if not check_password(
        'mq26', 'MQ26 — Terminal de Inversiones',
        subtitle='Tu cartera de inversiones, ordenada.',
        icon='📈',
        password_env=APP_PASSWORD,
        viewer_password_env=MQ26_VIEWER_PASSWORD,
        investor_password_env=MQ26_INVESTOR_PASSWORD,
        user_admin=MQ26_USER_ADMIN,
        user_estudio=MQ26_USER_ESTUDIO,
        user_inversor=MQ26_USER_INVERSOR,
        username_login=True,
        try_database_users=_MQ26_TRY_DB_USERS,
        db_tenant_id=_MQ26_DB_TENANT_ID if _MQ26_TRY_DB_USERS else None,
    ):  # usuario + contraseña; opcional login desde tablas app_usuarios
        st.stop()
    TENANT_ID = 'default'

_inject_css_after_auth()

# Header cartera / métricas (se usa antes del bloque de imports de tabs).
from ui.mq26_ux import metric_card_html, topline_html

# ─── INICIALIZACIÓN ───────────────────────────────────────────────────────────
@st.cache_resource
def init_sistema():
    dbm.init_db()
    engine = DataEngine()
    # MQ2-A3: registrar universo en servicio centralizado
    try:
        from services.universo_service import set_universo_df
        set_universo_df(engine.universo_df)
    except Exception as _e_univ:
        log_degradacion("run_mq26", "universo_service_set_fallo", _e_univ)
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
    except Exception as _e_tokens:
        log_degradacion("run_mq26", "limpieza_tokens_reporte_fallo", _e_tokens)
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
    except Exception as _e_cli:
        log_degradacion(
            "run_mq26",
            "cached_clientes_df_fallo",
            _e_cli,
            tenant_id=str(tenant_id)[:64],
        )
        return pd.DataFrame()


def _scope_clientes_df(df: pd.DataFrame) -> pd.DataFrame:
    """Delega en core.cliente_scope_ui (misma regla que app_main con app_id='app')."""
    from core.cliente_scope_ui import scope_clientes_df_por_sesion

    return scope_clientes_df_por_sesion(df, app_id="mq26")


def _df_clientes_scoped(tenant_id: str) -> pd.DataFrame:
    """Lista de clientes del tenant con RBAC de sesión aplicado."""
    return _scope_clientes_df(cached_clientes_df(tenant_id))


# Alias explícito: si algún deploy antiguo aún llama _cached_clientes_ingreso(), existe en globals.
_cached_clientes_ingreso = cached_clientes_df

# ─── PANTALLA DE INGRESO (v9 Quant Dark — tenant + RBAC) ─────────────────────
def _pantalla_ingreso():
    from datetime import datetime as _dt_footer

    _ing_role = get_user_role("mq26")
    _puede_alta_cliente = _ing_role in ("super_admin", "admin")
    _lbl_nuevo = "Mi perfil de inversión" if _ing_role == "inversor" else "Nuevo cliente"
    _PERFIL_AYUDA = {
        "Conservador": "Priorizás no perder. Preferís seguridad sobre rendimiento.",
        "Moderado": "Buscás equilibrio. Aceptás algo de volatilidad por mejor retorno.",
        "Arriesgado": "Priorizás rendimiento. Tolerás que el valor fluctúe bastante.",
        "Muy arriesgado": "Buscás máximo potencial. Tu cartera puede variar mucho.",
    }

    st.markdown(
        """
    <div class="mq-motion-page-fade mq-login-hero">
        <div class="mq-login-hero-icon" aria-hidden="true">📈</div>
        <h1>Master Quant</h1>
        <p>¿Con qué cartera trabajamos hoy?</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    col_sel, col_sep, col_nuevo = st.columns([5, 1, 5])

    with col_sel:
        st.markdown(
            '<p class="mq-login-col-label">Cliente existente</p>',
            unsafe_allow_html=True,
        )
        try:
            # Línea canónica exigida por Dockerfile (build Railway): cache por tenant explícito.
            df_cli = cached_clientes_df(TENANT_ID)
            df_cli = _scope_clientes_df(df_cli)
        except Exception as _e:
            _log.exception("MQ26 pantalla ingreso: carga de clientes")
            st.error("No se pudo cargar la lista de clientes.")
            st.exception(_e)
            st.stop()
        if df_cli.empty:
            if _puede_alta_cliente:
                st.markdown(
                    """
                <div class="mq-login-empty">
                    <p>Sin clientes aún.<br>Creá el primero a la derecha →</p>
                </div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.warning(
                    "No hay clientes en la base. Iniciá sesión con usuario **admin** "
                    "y la contraseña correspondiente, y creá al menos un cliente."
                )
        else:
            # Inversor: si hay un solo cliente en alcance, entra directo; si hay varios, selector como el resto de roles.
            if _ing_role == "inversor" and len(df_cli) == 1:
                sel = str(df_cli.iloc[0]["Nombre"])
            else:
                opciones_cli = ["Elegí tu cartera..."] + df_cli["Nombre"].tolist()
                sel = st.selectbox(
                    "Cliente",
                    opciones_cli,
                    key="ing_sel_cliente",
                    label_visibility="collapsed",
                )
            if sel == "Elegí tu cartera...":
                pass
            elif sel:
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
                <div class="mq-login-client-card">
                    <div class="mq-login-client-head">
                        <div>
                            <div class="mq-login-client-title">{sel_esc}</div>
                        </div>
                        <span class="mq-login-badge-perfil"
                            style="background:rgba({rgb},0.15);color:{perfil_color};">{perfil_esc}</span>
                    </div>
                    <div class="mq-login-grid-2">
                        <div>
                            <div class="mq-inv-kpi-label">Horizonte</div>
                            <div class="mq-login-kpi-val">{horiz_esc}</div>
                        </div>
                        <div>
                            <div class="mq-inv-kpi-label">Capital inicial</div>
                            <div class="mq-login-kpi-val-mono">USD {cap_usd:,.0f}</div>
                        </div>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )
                if _ing_role == "inversor" and len(df_cli) > 1:
                    st.caption(
                        "Elegí con qué perfil ingresar. Podés cambiar después con **Cambiar cliente** en el menú lateral."
                    )
                st.markdown('<div class="mq-login-spacer-md"></div>', unsafe_allow_html=True)
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
        <div class="mq-login-vsep">
            <div class="mq-login-vsep-line"></div>
            <span class="mq-login-vsep-mid">o</span>
            <div class="mq-login-vsep-line"></div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col_nuevo:
        st.markdown(
            f'<p class="mq-login-col-label">{html.escape(_lbl_nuevo)}</p>',
            unsafe_allow_html=True,
        )
        if not _puede_alta_cliente:
            if _ing_role == "estudio":
                st.info(
                    "El rol **estudio** (contraseña de visor / solo lectura) no puede registrar "
                    "clientes nuevos en la base de datos."
                )
            else:
                st.info("Tu rol actual no puede registrar clientes nuevos.")
        elif _ing_role == "inversor":
            try:
                _df_chk = _scope_clientes_df(cached_clientes_df(TENANT_ID))
            except Exception:
                _df_chk = pd.DataFrame()
            if not _df_chk.empty:
                st.info(
                    "Tu cuenta ya tiene **al menos un perfil** vinculado: ingresá desde la columna izquierda. "
                    "Más perfiles los asocia el estudio o el administrador a tu usuario."
                )
            else:
                with st.form("form_nuevo_cliente_ingreso_inv", clear_on_submit=True):
                    nc_nombre = st.text_input(
                        "Nombre completo",
                        placeholder="Ej: María Fernández",
                        key="nc_nombre_ingreso_inv",
                    )
                    col_a, col_b = st.columns(2)
                    with col_a:
                        nc_perfil = st.selectbox(
                            "Perfil de riesgo",
                            ["Conservador", "Moderado", "Arriesgado", "Muy arriesgado"],
                            help="Conservador: preserva capital. Moderado: balance. "
                            "Arriesgado/Muy arriesgado: maximiza retorno.",
                            key="nc_perfil_ing_inv",
                        )
                    with col_b:
                        nc_horiz = st.selectbox(
                            "Horizonte",
                            ["1 mes", "3 meses", "6 meses", "1 año", "3 años", "+5 años"],
                            index=3,
                            key="nc_horiz_ing_inv",
                        )
                    st.caption(_PERFIL_AYUDA.get(nc_perfil, ""))
                    nc_tipo = "Persona"
                    nc_capital = 0.0
                    submitted = st.form_submit_button(
                        "Crear mi perfil",
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
                st.caption(_PERFIL_AYUDA.get(nc_perfil, ""))
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

    st.caption(
        "📌 Master Quant es una herramienta de análisis. "
        "No brinda asesoramiento personalizado de inversión. "
        "Verificá siempre en tu broker antes de operar."
    )
    _yfooter = _dt_footer.now().year
    st.markdown(
        f"""
    <div class="mq-login-footer">
        <span>Master Quant · {_yfooter}</span>
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
# Modo claro: default y CSS se sincronizan tras auth (_inject_css_after_auth) antes de este widget.
st.sidebar.toggle("☀️ Modo claro", key="mq_light_mode")

_mq26_role = get_user_role("mq26")
_login_u = st.session_state.get("mq26_login_user", "")
if _login_u and str(_mq26_role).lower() != "inversor":
    st.sidebar.caption(f"Sesión: **{_login_u}** · rol {_mq26_role}")
_mq26_viewer = _mq26_role in ("estudio", "inversor")
from ui.rbac import can_action as _can_action_rbac
_mq26_can_sensitive_utils = _can_action_rbac({"user_role": _mq26_role}, "sensitive_utils")
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
except Exception as _e_cb:
    log_degradacion("run_mq26", "circuit_breaker_sidebar_estado_fallo", _e_cb)

# MQ2-S7: botón de cierre de sesión explícito
if st.sidebar.button("🔒 Cerrar sesión", key="btn_cerrar_sesion_mq", use_container_width=True):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

info_bd = dbm.info_backend()
backend_label = "🟢 PostgreSQL" if info_bd["backend"] == "postgresql" else "🟡 SQLite Local"
st.sidebar.caption(f"BD: {backend_label}")

ccl = cached_ccl()
st.sidebar.markdown(
    f"""
<div style="padding:0.5rem 0;">
    <div style="font-size:0.65rem;color:var(--c-text-3, #94a3b8);text-transform:uppercase;
                letter-spacing:0.06em;">Dólar hoy (CCL)</div>
    <div style="font-family:'DM Mono',monospace;font-size:1.2rem;font-weight:600;
                color:var(--c-text, #f1f5f9);">${ccl:,.0f}</div>
</div>
""",
    unsafe_allow_html=True,
)

_cliente_id     = st.session_state.get("cliente_id")
_cliente_nombre = st.session_state.get("cliente_nombre", "")
_cliente_perfil = st.session_state.get("cliente_perfil", "Moderado")
_horiz_label    = st.session_state.get("cliente_horizonte_label", "1 año")

df_clientes = _df_clientes_scoped(TENANT_ID)

if _mq26_role == "estudio":
    _n_rojos_sb = int(st.session_state.get("dashboard_n_rojos", 0) or 0)
    if _n_rojos_sb > 0:
        st.sidebar.error(f"🔴 {_n_rojos_sb} cliente(s) necesitan atención")
    st.sidebar.divider()

_nombre_corto_sb = _cliente_nombre.split("|")[0].strip() if _cliente_nombre else ""
st.sidebar.markdown(
    f"""
<div style="padding:0.25rem 0 0.5rem 0;">
    <div style="font-size:0.875rem;font-weight:600;color:var(--c-text, #f1f5f9);">
        👤 {html.escape(_nombre_corto_sb or "—")}
    </div>
    <div style="font-size:0.72rem;color:var(--c-text-3, #94a3b8);margin-top:2px;">
        {html.escape(str(_cliente_perfil))} · {html.escape(str(_horiz_label))}
    </div>
</div>
""",
    unsafe_allow_html=True,
)
# Inversor: un solo cliente en alcance → no ofrecer cambio (evita lista de "personas").
if _mq26_role != "inversor" or len(df_clientes) > 1:
    if st.sidebar.button("🔄 Cambiar cliente", key="btn_cambiar_cliente", use_container_width=True):
        for k in ["cliente_id", "cliente_nombre", "cliente_perfil", "cliente_horizonte_label"]:
            st.session_state.pop(k, None)
        st.session_state.pop("mq_cartera_activa_sidebar", None)
        st.session_state.pop("_mq_cartera_sync_key", None)
        st.rerun()

st.sidebar.divider()

horizonte_dias = dbm.HORIZONTE_DIAS.get(_horiz_label, 365)
_ruta_transac_main = BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
_mtime_transac_main = _ruta_transac_main.stat().st_mtime if _ruta_transac_main.exists() else 0.0
trans = cached_transaccional(_mtime_transac_main)
trans = filtrar_transaccional_por_rol(trans, _mq26_role, _cliente_nombre, df_clientes)

if _mq26_role == "inversor":
    from core.cartera_scope import normalizar_transacciones_inversor_una_cartera

    trans, _ = normalizar_transacciones_inversor_una_cartera(trans, _cliente_nombre)

carteras_csv: list[str] = []
if not trans.empty and "CARTERA" in trans.columns:
    carteras_csv = sorted(trans["CARTERA"].dropna().unique().tolist())

if _mq26_role == "inversor":
    # Una sola cartera lógica; sin "-- Todas --" ni selector de múltiples libros.
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
if _mq26_role == "inversor":
    _default_cartera_idx = 0
else:
    _cnorm = (_cliente_nombre or "").strip()
    if _cnorm:
        _hit_datos: int | None = None
        _hit_sin: int | None = None
        for _i, _opt in enumerate(carteras_opciones):
            if _opt == "-- Todas las carteras --" or "|" not in _opt:
                continue
            _pref = _opt.split("|")[0].strip()
            if _pref != _cnorm:
                continue
            if _opt.endswith("| (sin datos)"):
                _hit_sin = _i
            else:
                _hit_datos = _i
                break
        if _hit_datos is not None:
            _default_cartera_idx = _hit_datos
        elif _hit_sin is not None:
            _default_cartera_idx = _hit_sin

if carteras_opciones:
    _default_cartera_idx = min(_default_cartera_idx, max(0, len(carteras_opciones) - 1))
else:
    _default_cartera_idx = 0

if not carteras_opciones:
    cartera_activa = ""
elif _mq26_role == "inversor":
    cartera_activa = carteras_opciones[_default_cartera_idx]
else:
    _cab_sync = (TENANT_ID, _cnorm, tuple(carteras_opciones))
    if st.session_state.get("_mq_cartera_sync_key") != _cab_sync:
        st.session_state["_mq_cartera_sync_key"] = _cab_sync
        st.session_state["mq_cartera_activa_sidebar"] = carteras_opciones[_default_cartera_idx]
    elif st.session_state.get("mq_cartera_activa_sidebar") not in carteras_opciones:
        st.session_state["mq_cartera_activa_sidebar"] = carteras_opciones[_default_cartera_idx]
    cartera_activa = st.sidebar.selectbox(
        "📁 Cartera activa (misma lógica que el inversor, con más libros):",
        carteras_opciones,
        key="mq_cartera_activa_sidebar",
    )
    st.sidebar.caption(
        "Elegí el **libro** del cliente para ver posiciones. "
        "«-- Todas--» solo sirve para vistas agregadas; en **Posición actual** necesitás una cartera concreta."
    )

_mc_niveles = [1000, 3000, 5000, 10000]
st.session_state.setdefault("mc_n_escenarios_select", 3000)
if _mq26_role != "inversor":
    _mc_cur = st.session_state.get("mc_n_escenarios_select", 3000)
    if _mc_cur not in _mc_niveles:
        _mc_cur = 3000
    _mc_idx = _mc_niveles.index(_mc_cur)
    n_escenarios = st.sidebar.selectbox(
        "Simulaciones MC:", _mc_niveles, index=_mc_idx, key="mc_n_escenarios_select"
    )
else:
    n_escenarios = int(st.session_state.get("mc_n_escenarios_select", 3000) or 3000)

capital_nuevo = float(st.session_state.get("capital_inyectado_mq26", 0.0))
st.sidebar.divider()

try:
    from core.logging_config import set_log_context

    _cshort = ""
    if cartera_activa:
        _cshort = (
            cartera_activa.split("|")[-1].strip()[:20]
            if "|" in cartera_activa
            else cartera_activa[:20]
        )
    set_log_context(
        tenant=TENANT_ID,
        cartera=_cshort,
        env=os.environ.get("RAILWAY_ENVIRONMENT", "dev"),
    )
except Exception as _e_logctx:
    log_degradacion("run_mq26", "set_log_context_fallo", _e_logctx)

if _mq26_role == "inversor":
    st.session_state["modo_ppc_fifo"] = False
    if cartera_activa:
        st.sidebar.caption(
            f"📁 **Tu cartera:** {html.escape(cartera_activa.split('|')[-1].strip() or '—')} "
            "(un solo libro por usuario inversor)"
        )
else:
    st.session_state.setdefault("modo_ppc_fifo", False)

if _mq26_role != "inversor":
    st.sidebar.divider()

    with st.sidebar.expander("🔄 Sincronización de datos"):
        if not _mq26_can_sensitive_utils:
            st.info("Utilidad sensible: solo administradores pueden regenerar datos.")
        _ruta_transac_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Transaccional.csv"
        _ruta_maestra_sb = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
        _ruta_sqlite_sb = BASE_DIR / "0_Data_Maestra" / "master_quant.db"
        if _ruta_transac_sb.exists():
            _mtime = datetime.fromtimestamp(_ruta_transac_sb.stat().st_mtime).strftime("%d/%m %H:%M")
            st.caption(f"CSV: {_mtime}")

        import time as _time_rl

        _sync_times = st.session_state.get("_sync_timestamps", [])
        _ahora_rl = _time_rl.monotonic()
        _sync_times = [t for t in _sync_times if _ahora_rl - t < 60]
        _bloqueado = len(_sync_times) >= 3
        _espera_rl = max(0, int(60 - (_ahora_rl - _sync_times[0]))) if _bloqueado else 0

        if _bloqueado:
            st.warning(f"⏳ Rate limit — esperá {_espera_rl}s antes de sincronizar de nuevo.")
        else:
            if st.button(
                "🔄 Regenerar desde Excel",
                key="btn_regen_csv",
                disabled=_bloqueado or (not _mq26_can_sensitive_utils),
            ):
                _sync_times.append(_ahora_rl)
                st.session_state["_sync_timestamps"] = _sync_times
                if _ruta_transac_sb.exists():
                    _ruta_transac_sb.unlink()
                st.cache_data.clear()
                st.rerun()
        st.session_state["_sync_timestamps"] = _sync_times


    with st.sidebar.expander("💰 Precios fallback"):
        if not _mq26_can_sensitive_utils:
            st.info("Utilidad sensible: solo administradores pueden editar precios fallback.")
        _fb = cs.PRECIOS_FALLBACK_ARS.copy()
        _df_fb = pd.DataFrame([{"Ticker": t, "Precio ARS": p} for t, p in sorted(_fb.items())])
        _df_fb_edit = st.data_editor(
            _df_fb.reset_index(drop=True), num_rows="dynamic", use_container_width=True,
            column_config={
                "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
                "Precio ARS": st.column_config.NumberColumn("Precio ARS", min_value=0, format="$%d"),
            },
            key="editor_fallback_sb", hide_index=True, disabled=not _mq26_can_sensitive_utils,
        )
        if st.button("💾 Aplicar precios", key="btn_aplicar_fb", disabled=not _mq26_can_sensitive_utils):
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
                    except Exception as _e_alerta:
                        log_degradacion(
                            "run_mq26",
                            "registrar_alerta_precio_manual_fallo",
                            _e_alerta,
                            ticker=str(_t_fb)[:32],
                        )
            cs.actualizar_fallback(_nuevos)
            try:
                dbm.registrar_admin_audit_event(
                    "precios_fallback.rf_rv_manual",
                    actor=str(st.session_state.get("mq26_login_user") or "")[:200],
                    tenant_id=str(st.session_state.get("tenant_id") or "default"),
                    detail={
                        "n_tickers": len(_nuevos),
                        "tickers_muestra": sorted([str(x) for x in _nuevos.keys()])[:40],
                        "nota": "Precios manuales RF/RV (tabla fallback sidebar); afectan valoración y motor.",
                    },
                )
            except Exception:
                pass
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
        if not _mq26_can_sensitive_utils:
            st.info("Utilidad sensible: solo administradores pueden editar capital global.")
        # MQ2-D6: capital_disponible configurable desde sidebar
        _cap_default = float(dbm.obtener_config("capital_disponible_mq", "500000") or 500000)
        _capital_disp = st.number_input(
            "Capital disponible (ARS):",
            min_value=0.0, value=_cap_default, step=10_000.0, format="%.0f",
            key="capital_disponible_input", help="Capital para calcular órdenes de compra",
            disabled=not _mq26_can_sensitive_utils,
        )
        if st.button("💾 Guardar capital", key="btn_guardar_cap", disabled=not _mq26_can_sensitive_utils):
            dbm.guardar_config("capital_disponible_mq", str(_capital_disp))
            st.success("✅ Capital guardado")
        # Hacer disponible para el Motor de Salida
        st.session_state["capital_disponible_mq"] = _capital_disp

    with st.sidebar.expander("⚙️ Salud del sistema"):
        import datetime as _dt_sys
        st.markdown(f"**Última sync:** {_dt_sys.datetime.now().strftime('%H:%M:%S')}")
        st.markdown(f"**BD:** {dbm.info_backend()['backend'].upper()}")
        st.markdown(f"**CCL:** ${ccl:,.0f}")
        st.checkbox(
            "Usar FIFO para PPC (detalle contable)",
            key="modo_ppc_fifo",
            help="Afecta cómo se calcula el precio promedio de compra con múltiples operaciones.",
        )

    with st.sidebar.expander("📱 Alertas Telegram"):
        if not _mq26_can_sensitive_utils:
            st.info("Utilidad sensible: solo administradores pueden configurar Telegram.")
        # MQ-S1: Las credenciales Telegram se persisten en la BD, NO en os.environ
        _tg_token_bd = dbm.obtener_config("telegram_token", "")
        _tg_chat_bd  = dbm.obtener_config("telegram_chat_id", "")
        tg_token = st.text_input(
            "Bot Token", type="password",
            value=_tg_token_bd or os.environ.get("TELEGRAM_TOKEN", ""),
            disabled=not _mq26_can_sensitive_utils,
        )
        tg_chat = st.text_input(
            "Chat ID",
            value=_tg_chat_bd or os.environ.get("TELEGRAM_CHAT_ID", ""),
            disabled=not _mq26_can_sensitive_utils,
        )
        if st.button("💾 Guardar credenciales", key="btn_tg_guardar", disabled=not _mq26_can_sensitive_utils):
            if tg_token:
                dbm.guardar_config("telegram_token", tg_token)
            if tg_chat:
                dbm.guardar_config("telegram_chat_id", tg_chat)
            st.success("✅ Guardadas en BD")
        if st.button("🔔 Probar conexión", key="btn_tg_probar", disabled=not _mq26_can_sensitive_utils):
            if tg_token and tg_chat:
                # Solo poner en env para la prueba (en-memoria, no persiste entre procesos)
                os.environ["TELEGRAM_TOKEN"]   = tg_token
                os.environ["TELEGRAM_CHAT_ID"] = tg_chat
                ok = ab.test_conexion()
                st.success("✅ Telegram OK") if ok else st.error("❌ Sin respuesta")

else:
    st.session_state.setdefault(
        "capital_disponible_mq",
        float(dbm.obtener_config("capital_disponible_mq", "500000") or 500000),
    )

_HEADER_POR_ROL = {
    "inversor": "Master Quant · Tu cartera",
    "estudio": "Master Quant · Mis clientes",
    "super_admin": "Master Quant · Control total",
}
_nombre_corto_hdr = _cliente_nombre.split("|")[0].strip() if _cliente_nombre else ""
if _mq26_role == "inversor":
    _sub_txt = (
        f"Hola, {html.escape(_nombre_corto_hdr)} · CCL ${ccl:,.0f}"
        if _nombre_corto_hdr
        else f"CCL ${ccl:,.0f}"
    )
elif _mq26_role == "estudio":
    _sub_txt = f"Estudio · {len(df_clientes)} clientes activos · CCL ${ccl:,.0f}"
elif _mq26_role == "super_admin":
    _sub_txt = (
        f"Admin · {html.escape(_nombre_corto_hdr)}"
        if _nombre_corto_hdr
        else "Admin"
    )
else:
    _sub_txt = f"CCL ${ccl:,.0f}"

# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown(
    f'<p class="main-header">{html.escape(_HEADER_POR_ROL.get(_mq26_role, "Master Quant"))}</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<p class="sub-header">{_sub_txt}</p>',
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

_cartera_sin_datos = cartera_activa.endswith("| (sin datos)") if cartera_activa else False
_trans_tiene_filas_cartera = (
    not trans.empty
    and "CARTERA" in trans.columns
    and bool(cartera_activa)
    and (trans["CARTERA"].astype(str).str.strip() == str(cartera_activa).strip()).any()
)
# Placeholder «(sin datos)»: no armar posiciones solo si aún no hay filas en el transaccional.
_cartera_placeholder_vacia = _cartera_sin_datos and not _trans_tiene_filas_cartera
if (
    cartera_activa
    and cartera_activa != "-- Todas las carteras --"
    and not _cartera_placeholder_vacia
    and not trans.empty
):
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
            log_degradacion(
                "run_mq26",
                "price_engine_portfolio_fallo",
                _e_pe,
                n_tickers=len(tickers_cartera),
                cartera=str(cartera_activa)[:80],
            )
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

if _cartera_placeholder_vacia:
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

    # Semáforos sidebar — oculto al inversor (resume en topline principal)
    if _mq26_role != "inversor":
        st.sidebar.divider()
        st.sidebar.markdown("### Resumen cartera")
        st.sidebar.metric("Valor", f"${total_valor/1e6:.2f}M ARS" if total_valor > 1e6 else f"${total_valor:,.0f} ARS")
        st.sidebar.metric("P&L", f"${total_pnl:,.0f} ARS", f"{pnl_pct_total:.1%}")
        _sem_txt = "Cartera en verde" if pnl_pct_total >= 0 else "Cartera en rojo"
        st.sidebar.caption(f"{_sem_txt} · {pnl_pct_total:+.1%}")
    _va = st.session_state.get("valoracion_audit") or {}
    if _mq26_role != "inversor" and _va.get("total_valor_ars", 0) > 0:
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

    # ── Monitor de alertas proactivas (S13-01) — firma real revisar_cartera_completa ──
    if not df_ag.empty and tickers_cartera:
        try:
            from services.monitor_service import revisar_cartera_completa
            _met_mon = dict(metricas)
            _met_mon.setdefault("pnl_pct", float(metricas.get("pnl_pct_total", 0) or 0))
            _alertas_m = revisar_cartera_completa(
                df_ag,
                df_analisis,
                _met_mon,
                _cliente_id,
                prop_nombre or _cliente_nombre,
                ccl=float(ccl or 0),
                enviar_telegram=False,
            )
            _n_al = int(_alertas_m.get("total", 0) or 0)
            if _n_al > 0 and _mq26_role != "inversor":
                st.sidebar.divider()
                _ico = "🔴" if int(_alertas_m.get("mod23", 0) or 0) > 0 else "🟡"
                st.sidebar.warning(
                    f"{_ico} **{_n_al} alerta(s) activa(s)**  \n"
                    f"MOD-23: {_alertas_m.get('mod23', 0)} · "
                    f"Venc.: {_alertas_m.get('vencimientos', 0)}"
                )
        except Exception as _e_side_al:
            log_degradacion("run_mq26", "alertas_sidebar_monitor_fallo", _e_side_al)

    # ── CCL/MEP — últimos 30 días (S14-04); no inversor ───────────────────────
    if _mq26_role != "inversor":
        with st.sidebar.expander("📈 Dólar — últimos 30 días", expanded=False):
            try:
                import yfinance as yf
                import plotly.graph_objects as go

                ggal_ba = yf.Ticker("GGAL.BA").history(period="30d")["Close"].dropna()
                ggal_us = yf.Ticker("GGAL").history(period="30d")["Close"].dropna()
                if not ggal_ba.empty and not ggal_us.empty:
                    ccl_hist = (ggal_ba / ggal_us).dropna()
                    ccl_hist = ccl_hist[ccl_hist > 0]
                    if not ccl_hist.empty:
                        fig_ccl = go.Figure(go.Scatter(
                            x=ccl_hist.index,
                            y=ccl_hist.values,
                            mode="lines",
                            line=dict(color="#3b82f6", width=1.5),
                            fill="tozeroy",
                            fillcolor="rgba(59,130,246,0.06)",
                        ))
                        fig_ccl.update_layout(
                            height=110,
                            margin=dict(t=4, b=4, l=4, r=4),
                            showlegend=False,
                            xaxis=dict(showgrid=False, showticklabels=False),
                            yaxis=dict(
                                showgrid=True,
                                gridcolor="rgba(148,163,184,0.06)",
                                tickformat=",.0f",
                            ),
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                        )
                        st.plotly_chart(fig_ccl, use_container_width=True, key="sidebar_ccl_hist")
                        ccl_min = float(ccl_hist.min())
                        ccl_max = float(ccl_hist.max())
                        st.caption(
                            f"mín ${ccl_min:,.0f} · máx ${ccl_max:,.0f} · "
                            f"hoy ${float(ccl_hist.iloc[-1]):,.0f}"
                        )
            except Exception as _e_ccl_hist:
                log_degradacion("run_mq26", "sidebar_ccl_hist_30d_fallo", _e_ccl_hist)
                st.caption("Sin datos históricos disponibles.")

# Alerta objetivos
if _cliente_id and not st.session_state.get("_objetivos_alertas_verificados"):
    try:
        _df_obj = dbm.obtener_objetivos_cliente(_cliente_id)
        if not _df_obj.empty:
            _n = ab.verificar_objetivos_por_vencer(_df_obj, _cliente_nombre)
            if _n > 0:
                st.toast(f"⏰ {_n} objetivo(s) próximos a vencer", icon="⏰")
    except Exception as _e_obj:
        log_degradacion(
            "run_mq26",
            "objetivos_por_vencer_toast_fallo",
            _e_obj,
            cliente_id=_cliente_id,
        )
    st.session_state["_objetivos_alertas_verificados"] = True


def _n_alertas_concentracion(df_ag: pd.DataFrame) -> int:
    """Cuenta tickers con peso > 30% (alerta de concentración)."""
    if df_ag is None or df_ag.empty or "PESO_PCT" not in df_ag.columns:
        return 0
    return int((df_ag["PESO_PCT"] > 30.0).sum())

# ─── IMPORTS TABS (render por pestaña vía ui/navigation.py — P1-NAV-01 SSOT) ──
from ui.carga_activos import render_carga_activos
from ui.navigation import render_main_tabs
from ui.workflow_header import render_workflow_header

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
    "login_user":       st.session_state.get("mq26_login_user", ""),
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
    "valoracion_audit": st.session_state.get("valoracion_audit") or {},
    "precio_records": (st.session_state.get("_mq26_audit_ctx") or {}).get("records") or {},
    "session_correlation_id": st.session_state.get("mq26_auth_token", ""),
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
except Exception as _e_venc:
    log_degradacion("run_mq26", "contar_vencimientos_flow_ctx_fallo", _e_venc)
try:
    if not df_analisis.empty and tickers_cartera:
        _n_mod23_alertas = len(m23svc.detectar_alertas_venta(df_analisis, tickers_cartera))
except Exception as _e_m23_flow:
    log_degradacion("run_mq26", "mod23_alertas_flow_ctx_fallo", _e_m23_flow)

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

# ─── TABS por rol (SSOT: ui/navigation.get_main_tabs + render_main_tabs) ─────
render_main_tabs(ctx, app_kind="mq26", role=_mq26_role)

# Motor de Salida
if _mq26_role != "inversor" and st.sidebar.button(
    "🚪 Motor de Salida", use_container_width=True, key="btn_motor_salida"
):
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
st.caption(
    f"Master Quant · {datetime.now().year} · BD: {info_bd['backend'].upper()} · "
    f"CCL: ${ccl:,.0f}"
)
