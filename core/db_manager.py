"""
db_manager.py — Capa ORM MQ26
Motor: SQLAlchemy con fallback automático SQLite si PostgreSQL no está disponible.
FIX CRÍTICO: reemplaza la conexión directa a Supabase que crasheaba la app.
"""
import datetime as dt
import logging
import os
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    or_,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

logger = logging.getLogger(__name__)

# ─── CONFIGURACIÓN DE CONEXIÓN CON FALLBACK AUTOMÁTICO ────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
# Ruta única de BD: debe coincidir con config.py → RUTA_DB
SQLITE_PATH = BASE_DIR / "0_Data_Maestra" / "master_quant.db"

def _build_engine():
    """
    FIX CRÍTICO BUG #1: Intenta PostgreSQL primero, cae a SQLite si falla.
    Nunca crashea la app en el arranque.
    """
    pg_url = os.environ.get("DATABASE_URL", os.environ.get("DB_URL", ""))

    if pg_url and "postgresql" in pg_url.lower():
        try:
            eng = create_engine(
                pg_url,
                pool_pre_ping=True,        # detecta conexiones muertas
                connect_args={"connect_timeout": 5},
                pool_timeout=8,
            )
            # Test real de conectividad
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("DB: Conectado a PostgreSQL")
            return eng, "postgresql"
        except Exception as e:
            logger.warning("PostgreSQL no disponible (%s). Usando SQLite local.", e)

    # Fallback: SQLite (siempre funciona, sin red)
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(
        f"sqlite:///{SQLITE_PATH}",
        connect_args={"check_same_thread": False},
    )
    logger.info("DB: Usando SQLite local -> %s", SQLITE_PATH)
    return eng, "sqlite"


engine, DB_BACKEND = _build_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_engine():
    """Retorna el engine SQLAlchemy activo. Usado por servicios que necesitan acceso directo."""
    return engine


# ─── MODELOS ORM ──────────────────────────────────────────────────────────────
class Cliente(Base):
    __tablename__ = "clientes"
    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(200), nullable=False)
    perfil_riesgo   = Column(String(50), default="Moderado")
    horizonte_label = Column(String(30), default="1 año")   # "1 mes" | "3 meses" | "6 meses" | "1 año" | "3 años" | "+5 años"
    capital_usd     = Column(Float, default=0.0)
    tipo_cliente    = Column(String(50), default="Persona")
    activo          = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=dt.datetime.utcnow)
    tenant_id       = Column(String(200), nullable=False, default="default", index=True)
    transacciones   = relationship("Transaccion", back_populates="cliente")
    objetivos       = relationship("ObjetivosInversion", back_populates="cliente")


class Activo(Base):
    __tablename__ = "activos"
    id            = Column(Integer, primary_key=True, index=True)
    tipo          = Column(String(20), default="CEDEAR")   # CEDEAR | ACCION | ETF | ON
    ticker_local  = Column(String(20), nullable=False, unique=True)
    ticker_yf     = Column(String(20), nullable=False)
    nombre        = Column(String(200))
    ratio         = Column(Float, default=1.0)
    sector        = Column(String(100))
    pais          = Column(String(100), default="Estados Unidos")
    activo        = Column(Boolean, default=True)
    # C06: se incrementa en cada actualización de metadatos del universo (ratio, mapping, etc.)
    universo_version = Column(Integer, nullable=False, default=1)
    cupon_anual = Column(Float, nullable=True)
    vencimiento = Column(Date, nullable=True)
    valor_nominal = Column(Float, nullable=True)
    moneda = Column(String(5), default="USD")
    calificacion = Column(String(10), nullable=True)
    ley = Column(String(20), nullable=True)
    transacciones = relationship("Transaccion", back_populates="activo")


class Transaccion(Base):
    __tablename__ = "transacciones"
    id                 = Column(Integer, primary_key=True, index=True)
    cliente_id         = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    activo_id          = Column(Integer, ForeignKey("activos.id"), nullable=False)
    fecha              = Column(Date, nullable=False)
    tipo_op            = Column(String(10), nullable=False)   # COMPRA | VENTA
    nominales          = Column(Integer, nullable=False)
    precio_bruto_ars   = Column(Float, nullable=False)
    comision_broker    = Column(Float, default=0.0)
    derechos_mercado   = Column(Float, default=0.0)
    iva                = Column(Float, default=0.0)
    total_neto_ars     = Column(Float, nullable=False)
    notas              = Column(Text, default="")
    cliente            = relationship("Cliente", back_populates="transacciones")
    activo             = relationship("Activo", back_populates="transacciones")
    __table_args__     = (
        Index("ix_trans_cliente_fecha", "cliente_id", "fecha"),
    )


class ObjetivosInversion(Base):
    """Objetivos de inversión persistidos por cliente.
    Permite trackear: 'Invertí $3M en AAPL por 1 mes para retiro parcial'.
    """
    __tablename__ = "objetivos_inversion"
    id                = Column(Integer, primary_key=True, index=True)
    cliente_id        = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    ticker            = Column(String(20), default="")       # activo principal (puede estar vacío si es liquidez)
    monto_ars         = Column(Float, default=0.0)
    plazo_label       = Column(String(30), default="1 año")  # "1 mes" | "3 meses" | etc.
    plazo_dias        = Column(Integer, default=365)
    motivo            = Column(Text, default="")             # texto libre del cliente
    fecha_creacion    = Column(Date, default=dt.date.today)
    fecha_vencimiento = Column(Date, nullable=True)
    target_pct        = Column(Float, nullable=True)         # override del perfil (None = usa perfil)
    stop_pct          = Column(Float, nullable=True)
    estado            = Column(String(20), default="ACTIVO") # ACTIVO | VENCIDO | COMPLETADO
    created_at        = Column(DateTime, default=dt.datetime.utcnow)
    tenant_id         = Column(String(200), nullable=False, default="default", index=True)
    cliente           = relationship("Cliente", back_populates="objetivos")


class AlertaLog(Base):
    __tablename__ = "alertas_log"
    id          = Column(Integer, primary_key=True, index=True)
    cliente_id  = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    tipo_alerta = Column(String(50))   # VAR_BREACH | DRAWDOWN | SELL_SIGNAL | AUDITORIA
    ticker      = Column(String(20))
    mensaje     = Column(Text)
    enviada     = Column(Boolean, default=False)
    usuario     = Column(String(100), default="")
    created_at  = Column(DateTime, default=dt.datetime.utcnow)


class PreciosFallback(Base):
    """
    Precios fallback persistidos en BD (A5).
    Sobreviven reinicios de la app, evitando P&L = -100%.
    """
    __tablename__ = "precios_fallback"
    id                = Column(Integer, primary_key=True, index=True)
    ticker            = Column(String(20), nullable=False, unique=True)
    precio_ars        = Column(Float, nullable=False)
    fecha_actualizacion = Column(Date, default=dt.date.today)
    fuente            = Column(String(50), default="manual")


class Configuracion(Base):
    """
    Tabla clave-valor genérica para persistir configuraciones (B12, A5).
    Permite guardar: contexto macro, fallback CCL, etc.
    """
    __tablename__ = "configuracion"
    clave    = Column(String(100), primary_key=True)
    valor    = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class GlobalParamAudit(Base):
    """
    G02: auditoría append-only de cambios a parámetros globales críticos.
    Solo INSERT desde la app; no actualizar ni borrar filas en uso normal.
    """
    __tablename__ = "global_param_audit"
    id = Column(Integer, primary_key=True, autoincrement=True)
    param_key = Column(String(100), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    changed_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    changed_by = Column(String(200), default="")


# Claves cuyo cambio vía guardar_config() genera fila de auditoría (G02).
GLOBAL_PARAM_AUDIT_KEYS = frozenset({
    "RISK_FREE_RATE",
    "PESO_MAX_OPT",
    "PESO_MAX_CARTERA",
    "PESO_MAX",
})

# ─── INICIALIZACIÓN ───────────────────────────────────────────────────────────
def init_db():
    """Crea tablas si no existen y aplica migraciones de columnas nuevas."""
    Base.metadata.create_all(bind=engine)
    _migrar_columnas_nuevas()
    _seed_activos_desde_excel()


class Usuario(Base):
    """T-2.1: Usuarios del sistema con tier de acceso."""
    __tablename__ = "usuarios"
    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(200), unique=True, nullable=False, index=True)
    tier            = Column(String(20), default="inversor")
    tenant_id       = Column(String(200), nullable=False, default="default", index=True)
    hashed_password = Column(String(200))
    activo          = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=dt.datetime.utcnow)


class ScoreHistorico(Base):
    """T-2.1: Historial diario de scores MOD-23 por ticker."""
    __tablename__ = "scores_historicos"
    id                = Column(Integer, primary_key=True, index=True)
    ticker            = Column(String(20), nullable=False, index=True)
    fecha             = Column(Date, nullable=False)
    score_tecnico     = Column(Float)
    score_fundamental = Column(Float)
    score_total       = Column(Float)


# ─── Usuarios de aplicación (login MQ26 desde BD + alcance de clientes) ──────
_ROLES_APP_USER = frozenset({"super_admin", "asesor", "estudio", "inversor"})
_RAMAS_APP_USER = frozenset({"profesional", "retail"})


class AppUsuario(Base):
    """
    Usuario operativo MQ26: login por usuario/clave persistido (SHA-256 hex en password_hash).
    rol: super_admin | asesor | estudio | inversor
    rama: profesional (estudio/asesor/admin operativo) | retail (inversor típico)
    """
    __tablename__ = "app_usuarios"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_app_usuario_tenant_username"),
        Index("ix_app_usuarios_tenant", "tenant_id"),
    )
    id                   = Column(Integer, primary_key=True, index=True)
    tenant_id            = Column(String(200), nullable=False, default="default")
    username             = Column(String(100), nullable=False)
    password_hash        = Column(String(64), nullable=False)
    rol                  = Column(String(30), nullable=False, default="inversor")
    rama                 = Column(String(20), nullable=False, default="retail")
    cliente_default_id   = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    activo               = Column(Boolean, default=True)
    created_at           = Column(DateTime, default=dt.datetime.utcnow)


class AppUsuarioCliente(Base):
    """N:M qué clientes (carteras) puede ver / operar un usuario (además de cliente_default_id)."""
    __tablename__ = "app_usuario_cliente"
    __table_args__ = (
        UniqueConstraint("usuario_id", "cliente_id", name="uq_app_usuario_cliente"),
        Index("ix_app_usuario_cliente_usuario", "usuario_id"),
    )
    id         = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("app_usuarios.id", ondelete="CASCADE"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)


def ensure_schema():
    """
    Compatibilidad retroactiva:
    algunos entrypoints llaman ensure_schema() en cada run para aplicar migraciones.
    """
    Base.metadata.create_all(bind=engine)
    _migrar_columnas_nuevas()


def _migrar_columnas_nuevas():
    """Agrega columnas nuevas a tablas existentes (SQLite no soporta ALTER TABLE automático).
    Cada migración individual se ejecuta de forma aislada para evitar que un fallo
    bloquee el resto. Se crea un inspector FRESCO dentro de la conexión para evitar
    cache de schema stale.
    """
    with engine.connect() as conn:
        # Inspector fresco dentro de la conexión activa (evita cache de schema antiguo)
        fresh_inspector = inspect(conn)

        # ── Columna horizonte_label en clientes ────────────────────────────
        try:
            cols_clientes = [c["name"] for c in fresh_inspector.get_columns("clientes")]
            if "horizonte_label" not in cols_clientes:
                # Usar ASCII en el DEFAULT para evitar problemas de encoding en Windows
                conn.execute(text(
                    "ALTER TABLE clientes ADD COLUMN horizonte_label VARCHAR(30) DEFAULT '1 anio'"
                ))
                conn.commit()
        except Exception as _e:
            logger.warning("Migración horizonte_label: %s", _e)

        # ── tenant_id en clientes (multi-tenant SaaS) ──────────────────────
        try:
            insp = inspect(conn)
            if "clientes" in insp.get_table_names():
                cols_c = [c["name"] for c in insp.get_columns("clientes")]
                if "tenant_id" not in cols_c:
                    conn.execute(text(
                        "ALTER TABLE clientes ADD COLUMN tenant_id VARCHAR(200) "
                        "NOT NULL DEFAULT 'default'"
                    ))
                    conn.commit()
                    try:
                        conn.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_clientes_tenant_id "
                            "ON clientes (tenant_id)"
                        ))
                        conn.commit()
                    except Exception as _ix:
                        logger.warning("Índice clientes.tenant_id: %s", _ix)
        except Exception as _e:
            logger.warning("Migración clientes.tenant_id: %s", _e)

        # ── tenant_id en objetivos_inversion ───────────────────────────────
        try:
            insp = inspect(conn)
            if "objetivos_inversion" in insp.get_table_names():
                cols_o = [c["name"] for c in insp.get_columns("objetivos_inversion")]
                if "tenant_id" not in cols_o:
                    conn.execute(text(
                        "ALTER TABLE objetivos_inversion ADD COLUMN tenant_id VARCHAR(200) "
                        "NOT NULL DEFAULT 'default'"
                    ))
                    conn.commit()
                    try:
                        conn.execute(text(
                            "CREATE INDEX IF NOT EXISTS ix_objetivos_tenant_id "
                            "ON objetivos_inversion (tenant_id)"
                        ))
                        conn.commit()
                    except Exception as _ix:
                        logger.warning("Índice objetivos_inversion.tenant_id: %s", _ix)
        except Exception as _e:
            logger.warning("Migración objetivos_inversion.tenant_id: %s", _e)

        # ── Columna usuario en alertas_log (E3 auditoría) ─────────────────
        try:
            tablas = fresh_inspector.get_table_names()
            if "alertas_log" in tablas:
                cols_alerta = [c["name"] for c in fresh_inspector.get_columns("alertas_log")]
                if "usuario" not in cols_alerta:
                    conn.execute(text(
                        "ALTER TABLE alertas_log ADD COLUMN usuario VARCHAR(100) DEFAULT ''"
                    ))
                    conn.commit()
        except Exception as _e:
            logger.warning("Migración alertas_log.usuario: %s", _e)

        # ── activos.universo_version (C06) ─────────────────────────────────
        try:
            if "activos" in fresh_inspector.get_table_names():
                cols_a = [c["name"] for c in fresh_inspector.get_columns("activos")]
                if "universo_version" not in cols_a:
                    conn.execute(text(
                        "ALTER TABLE activos ADD COLUMN universo_version INTEGER NOT NULL DEFAULT 1"
                    ))
                    conn.commit()
        except Exception as _e:
            logger.warning("Migración activos.universo_version: %s", _e)

        # ── activos: metadatos renta fija (S5) ─────────────────────────────
        try:
            if "activos" in fresh_inspector.get_table_names():
                cols_a = [c["name"] for c in fresh_inspector.get_columns("activos")]
                for col_name, col_sql in [
                    ("cupon_anual", "FLOAT"),
                    ("vencimiento", "DATE"),
                    ("valor_nominal", "FLOAT"),
                    ("moneda", "VARCHAR(5) DEFAULT 'USD'"),
                    ("calificacion", "VARCHAR(10)"),
                    ("ley", "VARCHAR(20)"),
                ]:
                    if col_name not in cols_a:
                        conn.execute(text(f"ALTER TABLE activos ADD COLUMN {col_name} {col_sql}"))
                        conn.commit()
                        cols_a.append(col_name)
        except Exception as _e:
            logger.warning("Migración activos RF: %s", _e)

        # ── Tablas faltantes ───────────────────────────────────────────────
        try:
            tablas = fresh_inspector.get_table_names()
            if "objetivos_inversion" not in tablas:
                Base.metadata.tables["objetivos_inversion"].create(bind=engine)
            if "precios_fallback" not in tablas:
                Base.metadata.tables["precios_fallback"].create(bind=engine)
            if "configuracion" not in tablas:
                Base.metadata.tables["configuracion"].create(bind=engine)
            if "global_param_audit" not in tablas:
                Base.metadata.tables["global_param_audit"].create(bind=engine)
            if "app_usuarios" not in tablas:
                Base.metadata.tables["app_usuarios"].create(bind=engine)
            if "app_usuario_cliente" not in tablas:
                Base.metadata.tables["app_usuario_cliente"].create(bind=engine)
        except Exception as _e:
            logger.warning("Migración tablas nuevas: %s", _e)


def _seed_activos_desde_excel():
    """Importa el Universo_120_CEDEARs.xlsx y Maestra_Inversiones.xlsx si la tabla activos está vacía."""
    with SessionLocal() as session:
        if session.query(Activo).count() > 0:
            return  # Ya hay datos, no reimportar

    # Cargar universo 120
    universo_path = BASE_DIR / "0_Data_Maestra" / "Universo_120_CEDEARs.xlsx"
    if universo_path.exists():
        try:
            df = pd.read_excel(universo_path)
            df["Ticker"] = df["Ticker"].astype(str).str.strip().str.upper()
            with SessionLocal() as session:
                for _, row in df.iterrows():
                    ticker = str(row.get("Ticker", "")).strip()
                    if not ticker or ticker == "NAN":
                        continue
                    # Ticker Yahoo Finance
                    traducciones = {"BRKB": "BRK-B", "YPFD": "YPF", "PAMP": "PAM"}
                    tipo = str(row.get("Tipo", "CEDEAR")).strip()
                    if tipo in ("Acción", "Acciones"):
                        ticker_yf = f"{ticker}.BA"
                    else:
                        ticker_yf = traducciones.get(ticker, ticker)

                    existing = session.query(Activo).filter(Activo.ticker_local == ticker).first()
                    if not existing:
                        activo = Activo(
                            tipo=tipo if tipo else "CEDEAR",
                            ticker_local=ticker,
                            ticker_yf=ticker_yf,
                            nombre=str(row.get("Nombre", ticker)),
                            ratio=float(row.get("Ratio", 1.0)) if pd.notna(row.get("Ratio")) else 1.0,
                            sector=str(row.get("SECTOR", "")),
                            pais=str(row.get("Pais", "Estados Unidos")),
                        )
                        session.add(activo)
                session.commit()
            logger.info("Universo importado: %d activos", len(df))
        except Exception as e:
            logger.warning("Error importando universo: %s", e)

    # Importar clientes desde Maestra_Inversiones.xlsx
    maestra_path = BASE_DIR / "0_Data_Maestra" / "Maestra_Inversiones.xlsx"
    if maestra_path.exists():
        try:
            df_m = pd.read_excel(maestra_path, sheet_name="Hoja1")
            with SessionLocal() as session:
                for prop in df_m["Propietario"].dropna().unique():
                    nombre = str(prop).strip()
                    if not nombre:
                        continue
                    existing = session.query(Cliente).filter(Cliente.nombre == nombre).first()
                    if not existing:
                        c = Cliente(nombre=nombre, perfil_riesgo="Moderado", capital_usd=0.0)
                        session.add(c)
                session.commit()
            logger.info("Clientes importados desde Maestra_Inversiones")
        except Exception as e:
            logger.warning("Error importando clientes: %s", e)


# ─── CONTEXT MANAGER ──────────────────────────────────────────────────────────
@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Mapeo horizonte legible → días
HORIZONTE_DIAS = {
    "1 mes":   30,
    "3 meses": 90,
    "6 meses": 180,
    "1 año":   365,
    "3 años":  1095,
    "+5 años": 1825,
}


# ─── CLIENTES ─────────────────────────────────────────────────────────────────
def registrar_cliente(nombre, perfil_riesgo="Moderado", capital_usd=0.0,
                      tipo_cliente="Persona", horizonte_label="1 año",
                      tenant_id: str = "default"):
    """Registra un cliente nuevo para el tenant dado. Retorna id existente si ya existe para ese tenant."""
    with get_session() as s:
        existing = s.query(Cliente).filter(
            Cliente.nombre == nombre,
            Cliente.tenant_id == tenant_id
        ).first()
        if existing:
            return existing.id
        c = Cliente(nombre=nombre, perfil_riesgo=perfil_riesgo,
                    capital_usd=capital_usd, tipo_cliente=tipo_cliente,
                    horizonte_label=horizonte_label,
                    tenant_id=tenant_id)
        s.add(c)
        s.flush()
        return c.id


def obtener_clientes_df(tenant_id: str = "default") -> pd.DataFrame:
    """Retorna DataFrame de clientes activos del tenant dado. Aislamiento garantizado."""
    try:
        with get_session() as s:
            tid = (tenant_id or "default").strip() or "default"
            if tid == "default":
                tenant_match = or_(
                    Cliente.tenant_id == "default",
                    Cliente.tenant_id.is_(None),
                    Cliente.tenant_id == "",
                )
            else:
                tenant_match = Cliente.tenant_id == tid
            rows = (s.query(Cliente)
                    .filter(Cliente.activo == True, tenant_match)
                    .order_by(Cliente.id).all())
            if not rows:
                return pd.DataFrame(columns=["ID", "Nombre", "Perfil", "Horizonte", "Capital_USD", "Tipo"])
            return pd.DataFrame([{
                "ID": r.id, "Nombre": r.nombre, "Perfil": r.perfil_riesgo,
                "Horizonte": getattr(r, "horizonte_label", None) or "1 año",
                "Capital_USD": r.capital_usd, "Tipo": r.tipo_cliente,
            } for r in rows])
    except Exception as _qe:
        # Si falta columna horizonte_label (base de datos antigua), ejecutar migración y reintentar
        if "horizonte_label" in str(_qe):
            logger.warning("DB sin horizonte_label, ejecutando migración de emergencia...")
            _migrar_columnas_nuevas()
            # Reintentar con query de texto puro para no depender del ORM
            with engine.connect() as _conn:
                _res = _conn.execute(text(
                    "SELECT id, nombre, perfil_riesgo, capital_usd, tipo_cliente FROM clientes WHERE activo=1 ORDER BY id"
                ))
                _rows = _res.fetchall()
            if not _rows:
                return pd.DataFrame(columns=["ID", "Nombre", "Perfil", "Horizonte", "Capital_USD", "Tipo"])
            return pd.DataFrame([{
                "ID": r[0], "Nombre": r[1], "Perfil": r[2],
                "Horizonte": "1 año",
                "Capital_USD": r[3], "Tipo": r[4],
            } for r in _rows])
        raise


def actualizar_capital_cliente(id_cliente: int, nuevo_capital: float):
    with get_session() as s:
        c = s.query(Cliente).filter(Cliente.id == id_cliente).first()
        if c:
            c.capital_usd = nuevo_capital


def obtener_cliente(id_cliente: int) -> dict:
    """Devuelve dict con datos del cliente o {} si no existe."""
    try:
        with get_session() as s:
            c = s.query(Cliente).filter(Cliente.id == id_cliente).first()
            if not c:
                return {}
            return {
                "id": c.id, "nombre": c.nombre, "perfil_riesgo": c.perfil_riesgo,
                "horizonte_label": getattr(c, "horizonte_label", None) or "1 año",
                "capital_usd": c.capital_usd, "tipo_cliente": c.tipo_cliente,
            }
    except Exception as _qe:
        if "horizonte_label" in str(_qe):
            _migrar_columnas_nuevas()
            with engine.connect() as _conn:
                _res = _conn.execute(text(
                    "SELECT id, nombre, perfil_riesgo, capital_usd, tipo_cliente FROM clientes WHERE id=:cid"
                ), {"cid": id_cliente})
                _row = _res.fetchone()
            if not _row:
                return {}
            return {
                "id": _row[0], "nombre": _row[1], "perfil_riesgo": _row[2],
                "horizonte_label": "1 año",
                "capital_usd": _row[3], "tipo_cliente": _row[4],
            }
        raise


def actualizar_cliente(id_cliente: int, nombre: str, perfil: str,
                       capital_usd: float, tipo: str, horizonte_label: str = "1 año"):
    """Actualiza nombre, perfil, horizonte, capital y tipo de un cliente existente."""
    with get_session() as s:
        c = s.query(Cliente).filter(Cliente.id == id_cliente).first()
        if c:
            c.nombre          = nombre.strip()
            c.perfil_riesgo   = perfil
            c.capital_usd     = float(capital_usd)
            c.tipo_cliente    = tipo
            c.horizonte_label = horizonte_label


# ─── ACTIVOS ──────────────────────────────────────────────────────────────────
def get_activos_df(only_active=True) -> pd.DataFrame:
    with get_session() as s:
        q = s.query(Activo)
        if only_active:
            q = q.filter(Activo.activo == True)
        rows = q.order_by(Activo.ticker_local).all()
        if not rows:
            return pd.DataFrame(columns=[
                "id", "tipo", "ticker_local", "ticker_yf", "nombre", "ratio", "sector", "pais",
                "universo_version",
            ])
        return pd.DataFrame([{
            "id": r.id, "tipo": r.tipo, "ticker_local": r.ticker_local,
            "ticker_yf": r.ticker_yf, "nombre": r.nombre,
            "ratio": r.ratio, "sector": r.sector, "pais": r.pais,
            "universo_version": int(getattr(r, "universo_version", 1) or 1),
        } for r in rows])


def get_activo_by_ticker(ticker: str):
    """Devuelve el id del activo o None. No devuelve el objeto ORM para evitar DetachedInstanceError."""
    with get_session() as s:
        a = s.query(Activo).filter(Activo.ticker_local == ticker.upper()).first()
        return a.id if a is not None else None


def registrar_activo(tipo, ticker_local, ticker_yf, nombre="", ratio=1.0, sector="", pais=""):
    with get_session() as s:
        existing = s.query(Activo).filter(Activo.ticker_local == ticker_local.upper()).first()
        if existing:
            return existing.id
        a = Activo(tipo=tipo, ticker_local=ticker_local.upper(), ticker_yf=ticker_yf,
                   nombre=nombre, ratio=ratio, sector=sector, pais=pais)
        s.add(a)
        s.flush()
        return a.id


def actualizar_activo_universo(ticker: str, **campos) -> int | None:
    """
    C06: actualiza campos permitidos del activo e incrementa universo_version.
    Retorna el nuevo version_id o None si no existe el ticker.
    """
    permitidos = {"ticker_yf", "nombre", "ratio", "sector", "pais", "tipo", "activo"}
    with get_session() as s:
        a = s.query(Activo).filter(Activo.ticker_local == str(ticker).upper().strip()).first()
        if a is None:
            return None
        for k, v in campos.items():
            if k in permitidos and hasattr(a, k):
                setattr(a, k, v)
        v0 = int(getattr(a, "universo_version", 1) or 1)
        a.universo_version = v0 + 1
        return int(a.universo_version)


# ─── TRANSACCIONES ────────────────────────────────────────────────────────────
def registrar_transaccion(
    cliente_id, ticker, tipo_op, nominales, precio_ars,
    fecha=None, notas="",
    comision_broker: float = 0.0,
    derechos_mercado: float = 0.0,
    iva: float = 0.0,
):
    """
    Registra una transacción con costos reales desglosados.
    total_neto_ars = precio_bruto * nominales + comision + derechos + iva
    """
    aid = get_activo_by_ticker(ticker)  # devuelve id o None
    if aid is None:
        aid = registrar_activo("CEDEAR", ticker, ticker, ticker)

    fecha_dt = dt.date.today() if fecha is None else (
        dt.datetime.strptime(str(fecha), "%Y-%m-%d").date() if isinstance(fecha, str) else fecha
    )
    valor_bruto = float(precio_ars) * int(nominales)
    total_neto  = valor_bruto + float(comision_broker) + float(derechos_mercado) + float(iva)

    with get_session() as s:
        tx = Transaccion(
            cliente_id=int(cliente_id),
            activo_id=int(aid),
            fecha=fecha_dt,
            tipo_op=tipo_op.upper(),
            nominales=int(nominales),
            precio_bruto_ars=float(precio_ars),
            comision_broker=float(comision_broker),
            derechos_mercado=float(derechos_mercado),
            iva=float(iva),
            total_neto_ars=round(total_neto, 2),
            notas=notas,
        )
        s.add(tx)


def obtener_portafolio_cliente(id_cliente: int) -> pd.DataFrame:
    """Deriva el portafolio actual del trade log (compras - ventas)."""
    sql = """
        SELECT a.ticker_local AS ticker, t.tipo_op, t.nominales, t.precio_bruto_ars AS precio
        FROM transacciones t
        JOIN activos a ON a.id = t.activo_id
        WHERE t.cliente_id = :cid
        ORDER BY t.fecha ASC, t.id ASC
    """
    df = pd.read_sql_query(text(sql), engine, params={"cid": id_cliente})
    if df.empty:
        return pd.DataFrame(columns=["ticker","nominales","precio_promedio_compra"])

    rows = []
    for ticker, g in df.groupby("ticker"):
        neto = g.apply(lambda r: r["nominales"] if r["tipo_op"] == "COMPRA" else -r["nominales"], axis=1).sum()
        if neto <= 0:
            continue
        compras = g[g["tipo_op"] == "COMPRA"]
        ppc = (compras["nominales"] * compras["precio"]).sum() / compras["nominales"].sum() if not compras.empty else 0.0
        rows.append({"ticker": ticker, "nominales": int(neto), "precio_promedio_compra": round(ppc, 2)})

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ticker","nominales","precio_promedio_compra"])


def obtener_trade_log(id_cliente: int) -> pd.DataFrame:
    sql = """
        SELECT t.id AS id_trade, t.fecha, a.ticker_local AS ticker,
               t.tipo_op, t.nominales, t.precio_bruto_ars AS precio_ars, t.notas
        FROM transacciones t
        JOIN activos a ON a.id = t.activo_id
        WHERE t.cliente_id = :cid
        ORDER BY t.fecha DESC, t.id DESC
    """
    return pd.read_sql_query(text(sql), engine, params={"cid": id_cliente})


def obtener_todos_los_trades(tenant_id: str = "default") -> pd.DataFrame:
    """
    Trades consolidados solo para el tenant indicado (nunca cruza tenants).

    El default \"default\" mantiene compatibilidad con despliegues de un solo estudio;
    en SaaS multi-tenant pasar siempre el tenant activo.
    """
    tid = (tenant_id or "default").strip() or "default"
    sql = """
        SELECT c.nombre AS cliente, t.fecha, a.ticker_local AS ticker,
               t.tipo_op, t.nominales, t.precio_bruto_ars AS precio_ars
        FROM transacciones t
        JOIN activos a ON a.id = t.activo_id
        JOIN clientes c ON c.id = t.cliente_id
        WHERE c.tenant_id = :tid
        ORDER BY t.fecha DESC, t.id DESC
    """
    return pd.read_sql_query(text(sql), engine, params={"tid": tid})


# ─── ALERTAS ──────────────────────────────────────────────────────────────────
def registrar_alerta(tipo_alerta, mensaje, ticker="", cliente_id=None):
    with get_session() as s:
        a = AlertaLog(tipo_alerta=tipo_alerta, mensaje=mensaje,
                      ticker=ticker, cliente_id=cliente_id)
        s.add(a)


def obtener_alertas_recientes(limite=20) -> pd.DataFrame:
    sql = """
        SELECT al.created_at, al.tipo_alerta, al.ticker, al.mensaje, al.enviada
        FROM alertas_log al
        ORDER BY al.created_at DESC
        LIMIT :lim
    """
    return pd.read_sql_query(text(sql), engine, params={"lim": limite})


# ─── OBJETIVOS DE INVERSIÓN ───────────────────────────────────────────────────
def registrar_objetivo(
    cliente_id: int,
    monto_ars: float,
    plazo_label: str,
    motivo: str = "",
    ticker: str = "",
    target_pct: float = None,
    stop_pct: float = None,
    tenant_id: str = "default",
) -> int:
    """Registra un objetivo de inversión nuevo y devuelve su id."""
    plazo_dias   = HORIZONTE_DIAS.get(plazo_label, 365)
    fecha_hoy    = dt.date.today()
    fecha_venc   = fecha_hoy + dt.timedelta(days=plazo_dias)
    with get_session() as s:
        obj = ObjetivosInversion(
            cliente_id=cliente_id,
            ticker=ticker,
            monto_ars=monto_ars,
            plazo_label=plazo_label,
            plazo_dias=plazo_dias,
            motivo=motivo,
            fecha_creacion=fecha_hoy,
            fecha_vencimiento=fecha_venc,
            target_pct=target_pct,
            stop_pct=stop_pct,
            estado="ACTIVO",
            tenant_id=tenant_id,
        )
        s.add(obj)
        s.flush()
        return obj.id


def obtener_objetivos_cliente(cliente_id: int) -> pd.DataFrame:
    """Devuelve todos los objetivos de un cliente con estado actualizado."""
    with get_session() as s:
        rows = (s.query(ObjetivosInversion)
                .filter(ObjetivosInversion.cliente_id == cliente_id)
                .order_by(ObjetivosInversion.fecha_creacion.desc())
                .all())
        if not rows:
            return pd.DataFrame()
        hoy = dt.date.today()
        data = []
        for r in rows:
            # Auto-actualizar estado VENCIDO si pasó la fecha
            estado = r.estado
            if estado == "ACTIVO" and r.fecha_vencimiento and r.fecha_vencimiento < hoy:
                r.estado = "VENCIDO"
                estado = "VENCIDO"
            dias_restantes = (r.fecha_vencimiento - hoy).days if r.fecha_vencimiento else 0
            data.append({
                "ID":               r.id,
                "Ticker":           r.ticker or "—",
                "Monto ARS":        r.monto_ars,
                "Horizonte":        r.plazo_label,
                "Motivo":           r.motivo,
                "Fecha creación":   r.fecha_creacion,
                "Vencimiento":      r.fecha_vencimiento,
                "Días restantes":   max(dias_restantes, 0),
                "Target %":         r.target_pct,
                "Stop %":           r.stop_pct,
                "Estado":           estado,
            })
        try:
            s.commit()
        except Exception:
            pass
        return pd.DataFrame(data)


def actualizar_objetivo(
    id_objetivo: int,
    monto_ars: float = None,
    plazo_label: str = None,
    motivo: str = None,
    target_pct: float = None,
    stop_pct: float = None,
    estado: str = None,
):
    """Actualiza campos de un objetivo existente."""
    with get_session() as s:
        obj = s.query(ObjetivosInversion).filter(ObjetivosInversion.id == id_objetivo).first()
        if not obj:
            return
        if monto_ars is not None:
            obj.monto_ars = monto_ars
        if plazo_label is not None:
            obj.plazo_label = plazo_label
            obj.plazo_dias  = HORIZONTE_DIAS.get(plazo_label, 365)
            obj.fecha_vencimiento = obj.fecha_creacion + dt.timedelta(days=obj.plazo_dias)
        if motivo is not None:
            obj.motivo = motivo
        if target_pct is not None:
            obj.target_pct = target_pct
        if stop_pct is not None:
            obj.stop_pct = stop_pct
        if estado is not None:
            obj.estado = estado


def marcar_objetivo_completado(id_objetivo: int):
    actualizar_objetivo(id_objetivo, estado="COMPLETADO")


# ─── PRECIOS FALLBACK PERSISTIDOS (D1) ────────────────────────────────────────
def guardar_precio_fallback(ticker: str, precio_ars: float, fuente: str = "manual") -> None:
    """Persiste un precio fallback en BD para sobrevivir reinicios."""
    with get_session() as s:
        existing = s.query(PreciosFallback).filter(
            PreciosFallback.ticker == ticker.upper()
        ).first()
        if existing:
            existing.precio_ars = precio_ars
            existing.fecha_actualizacion = dt.date.today()
            existing.fuente = fuente
        else:
            s.add(PreciosFallback(
                ticker=ticker.upper(),
                precio_ars=precio_ars,
                fecha_actualizacion=dt.date.today(),
                fuente=fuente,
            ))


def obtener_precios_fallback() -> dict:
    """Retorna todos los precios fallback persistidos como {ticker: precio_ars}."""
    with get_session() as s:
        rows = s.query(PreciosFallback).all()
        return {r.ticker: r.precio_ars for r in rows}


def guardar_precios_fallback_bulk(precios: dict, fuente: str = "yfinance") -> None:
    """Guarda/actualiza múltiples precios fallback de una vez."""
    for ticker, precio in precios.items():
        if precio and float(precio) > 0:
            guardar_precio_fallback(ticker, float(precio), fuente)


# ─── AUDITORÍA (E3) ──────────────────────────────────────────────────────────
def registrar_auditoria(
    accion: str,
    detalle: str,
    usuario: str = "asesor",
    cliente_id: int = None,
    ticker: str = "",
) -> None:
    """Registra toda operación de escritura en AlertaLog con tipo AUDITORIA."""
    with get_session() as s:
        s.add(AlertaLog(
            cliente_id  = cliente_id,
            tipo_alerta = "AUDITORIA",
            ticker      = ticker,
            mensaje     = f"[{accion}] {detalle}",
            usuario     = usuario,
            enviada     = True,
            created_at  = dt.datetime.utcnow(),
        ))


def registrar_optimization_audit(
    *,
    cliente_id: int | None = None,
    usuario: str = "",
    accion: str = "",
    modelo: str = "",
    ccl: float | None = None,
    tickers: list[str] | None = None,
    pesos: dict[str, float] | None = None,
    run_id: str = "",
    version_app: str = "",
    extra: dict | None = None,
    ticker_resumen: str = "",
) -> None:
    """
    Ledger mínimo de optimización / ejecución: JSON en alertas_log (tipo OPTIMIZATION_AUDIT).
    Sin Streamlit; seguro para llamar desde UI con try/except externo si se desea.
    """
    import json as _json

    ts = dt.datetime.utcnow()
    payload: dict = {
        "fecha": ts.isoformat() + "Z",
        "cliente_id": cliente_id,
        "accion": accion,
        "modelo": modelo,
        "ccl": ccl,
        "tickers": list(tickers) if tickers is not None else None,
        "run_id": run_id or None,
        "version_app": version_app or None,
    }
    if pesos is not None:
        payload["pesos"] = {str(k): round(float(v), 6) for k, v in pesos.items()}
    if extra:
        payload["extra"] = extra
    try:
        msg = _json.dumps(payload, ensure_ascii=False, default=str)
    except Exception as e:
        logger.warning("registrar_optimization_audit: serialización JSON: %s", e)
        msg = _json.dumps(
            {"fecha": payload["fecha"], "accion": accion, "error": str(e)},
            ensure_ascii=False,
            default=str,
        )
    tkr = (ticker_resumen or "").strip()[:20]
    if not tkr and tickers:
        tkr = str(tickers[0])[:20]
    if not tkr:
        tkr = "PORTFOLIO"
    with get_session() as s:
        s.add(AlertaLog(
            cliente_id=cliente_id,
            tipo_alerta="OPTIMIZATION_AUDIT",
            ticker=tkr,
            mensaje=msg,
            usuario=(usuario or "")[:100],
            enviada=True,
            created_at=ts,
        ))


# ─── CONFIGURACIÓN CLAVE/VALOR (A5, B12) ──────────────────────────────────────
import json as _json_mod


def guardar_config(clave: str, valor, *, audit_user: str = "") -> None:
    """Persiste una configuración clave/valor en BD (JSON para valores complejos)."""
    valor_str = _json_mod.dumps(valor) if not isinstance(valor, str) else valor
    try:
        with get_session() as s:
            existing = s.query(Configuracion).filter(Configuracion.clave == clave).first()
            old_val = existing.valor if existing else None
            if existing:
                existing.valor = valor_str
                existing.updated_at = dt.datetime.utcnow()
            else:
                s.add(Configuracion(clave=clave, valor=valor_str,
                                    updated_at=dt.datetime.utcnow()))
            if clave in GLOBAL_PARAM_AUDIT_KEYS and (old_val or "") != valor_str:
                s.add(GlobalParamAudit(
                    param_key=clave,
                    old_value=old_val,
                    new_value=valor_str,
                    changed_by=audit_user or "",
                ))
    except Exception as _e:
        logger.warning("guardar_config(%s): %s", clave, _e)


def _app_password_hash(plain: str) -> str:
    import hashlib
    return hashlib.sha256(plain.encode()).hexdigest()


def list_app_usuarios(tenant_id: str = "default") -> list[dict]:
    """Listado para administración (sin contraseñas)."""
    tid = (tenant_id or "default").strip() or "default"
    try:
        with get_session() as s:
            rows = (
                s.query(AppUsuario)
                .filter(AppUsuario.tenant_id == tid)
                .order_by(AppUsuario.username)
                .all()
            )
            out: list[dict] = []
            for r in rows:
                links = (
                    s.query(AppUsuarioCliente.cliente_id)
                    .filter(AppUsuarioCliente.usuario_id == r.id)
                    .all()
                )
                cids = [x[0] for x in links]
                out.append({
                    "id": r.id,
                    "username": r.username,
                    "rol": r.rol,
                    "rama": r.rama,
                    "activo": r.activo,
                    "cliente_default_id": r.cliente_default_id,
                    "cliente_ids": cids,
                })
            return out
    except Exception as _e:
        logger.warning("list_app_usuarios: %s", _e)
        return []


def create_app_usuario(
    tenant_id: str,
    username: str,
    plain_password: str,
    rol: str,
    rama: str,
    cliente_default_id: int | None,
    cliente_ids: list[int] | None,
) -> int:
    """Crea usuario y vínculos N:M con clientes. Contraseña mínimo 8 caracteres."""
    if rol not in _ROLES_APP_USER:
        raise ValueError("rol inválido")
    if rama not in _RAMAS_APP_USER:
        raise ValueError("rama inválida")
    tid = (tenant_id or "default").strip() or "default"
    uname = (username or "").strip().lower()
    if not uname:
        raise ValueError("usuario vacío")
    if len(plain_password or "") < 8:
        raise ValueError("contraseña muy corta (mín. 8)")
    ph = _app_password_hash(plain_password)
    ids = {int(x) for x in (cliente_ids or []) if x is not None}
    if cliente_default_id is not None:
        ids.add(int(cliente_default_id))
    with get_session() as s:
        exists = (
            s.query(AppUsuario)
            .filter(AppUsuario.tenant_id == tid, AppUsuario.username == uname)
            .first()
        )
        if exists:
            raise ValueError("usuario ya existe en este tenant")
        u = AppUsuario(
            tenant_id=tid,
            username=uname,
            password_hash=ph,
            rol=rol,
            rama=rama,
            cliente_default_id=cliente_default_id,
            activo=True,
        )
        s.add(u)
        s.flush()
        uid = u.id
        for cid in ids:
            s.add(AppUsuarioCliente(usuario_id=uid, cliente_id=cid))
        s.commit()
        return uid


def set_app_usuario_clientes(usuario_id: int, cliente_ids: list[int], cliente_default_id: int | None = None) -> None:
    with get_session() as s:
        u = s.query(AppUsuario).filter(AppUsuario.id == usuario_id).first()
        if u:
            u.cliente_default_id = cliente_default_id
        s.query(AppUsuarioCliente).filter(AppUsuarioCliente.usuario_id == usuario_id).delete()
        base = {int(x) for x in (cliente_ids or [])}
        if cliente_default_id is not None:
            base.add(int(cliente_default_id))
        for cid in base:
            s.add(AppUsuarioCliente(usuario_id=usuario_id, cliente_id=cid))
        s.commit()


def delete_app_usuario(usuario_id: int) -> None:
    with get_session() as s:
        s.query(AppUsuarioCliente).filter(AppUsuarioCliente.usuario_id == usuario_id).delete()
        u = s.query(AppUsuario).filter(AppUsuario.id == usuario_id).first()
        if u:
            s.delete(u)
        s.commit()


def list_global_param_audit(
    param_key: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Historial de cambios (solo lectura)."""
    try:
        with get_session() as s:
            q = s.query(GlobalParamAudit).order_by(GlobalParamAudit.id.desc())
            if param_key:
                q = q.filter(GlobalParamAudit.param_key == param_key)
            rows = q.limit(limit).all()
            return [{
                "id": r.id,
                "param_key": r.param_key,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "changed_at": r.changed_at,
                "changed_by": r.changed_by or "",
            } for r in rows]
    except Exception as _e:
        logger.warning("list_global_param_audit: %s", _e)
        return []


def obtener_config(clave: str, default=None):
    """Recupera una configuración. Intenta deserializar JSON automáticamente."""
    try:
        with get_session() as s:
            row = s.query(Configuracion).filter(Configuracion.clave == clave).first()
            if row is None:
                return default
            try:
                return _json_mod.loads(row.valor)
            except Exception:
                return row.valor
    except Exception:
        return default



# ─── ALIASES CONFIG (compatibilidad) ─────────────────────────────────────────
def set_config(clave: str, valor_str: str) -> None:
    """Alias de guardar_config para escritura clave/valor."""
    guardar_config(clave, valor_str)


def get_config(clave: str, default: str = None) -> str | None:
    """Alias de obtener_config para lectura clave/valor."""
    v = obtener_config(clave, default)
    return str(v) if v is not None else default


# ─── INFO DE BACKEND ──────────────────────────────────────────────────────────
def info_backend() -> dict:
    return {
        "backend": DB_BACKEND,
        "url": str(SQLITE_PATH) if DB_BACKEND == "sqlite" else "PostgreSQL (Supabase)",
        "tablas": inspect(engine).get_table_names(),
    }


# ─── ALIAS DE COMPATIBILIDAD (core/audit.py, core/auth.py, core/notificaciones.py) ──
def registrar_alerta_log(tipo_alerta: str, mensaje: str, ticker: str = "",
                         enviada: bool = False, cliente_id=None) -> None:
    """Alias de registrar_alerta para compatibilidad con audit.py, auth.py y notificaciones.py."""
    registrar_alerta(tipo_alerta, mensaje, ticker, cliente_id)
