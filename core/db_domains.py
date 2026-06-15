"""
core/db_domains.py — Arquitectura de bases de datos por dominio (MQ26 v11+)

Divide el monolítico master_quant.db en 6 dominios independientes:

  Dominio          Archivo              Responsabilidad
  ──────────────── ──────────────────── ──────────────────────────────────────
  clientes         db_clientes.db       Clientes + objetivos de inversión
  auth             db_auth.db           Usuarios operativos, roles, sesiones
  portfolio        db_portfolio.db      Activos, transacciones, ops CSV
  mercado          db_mercado.db        Precios fallback, scores históricos
  config           db_config.db         Parámetros globales, auditoría config
  auditoria        db_auditoria.db      Alertas, recomendaciones, órdenes

Reglas de diseño:
  - Sin FK entre dominios (aislamiento total).
  - IDs cruzados solo via application layer (int tenant-qualified).
  - Cada dominio tiene su propio engine / session / Base.
  - `db_manager.py` sigue siendo la fachada legacy; delega aquí.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ─── Rutas ────────────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "0_Data_Maestra"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Override via env (Railway / Docker)
def _db_path(nombre: str) -> str:
    env_key = f"MQ26_DB_{nombre.upper()}"
    custom = os.environ.get(env_key, "").strip()
    if custom:
        return custom
    return str(_DATA_DIR / f"{nombre}.db")


# ─── Dominios ─────────────────────────────────────────────────────────────────

class DomainDB:
    """
    Contenedor de engine + SessionLocal + Base para un dominio.

    Uso:
        with CLIENTES.session() as s:
            s.add(...)
            s.commit()
    """
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.path   = _db_path(nombre)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            connect_args={"check_same_thread": False},
        )
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.Base    = declarative_base()

    def create_all(self) -> None:
        """Crea todas las tablas registradas en este dominio."""
        self.Base.metadata.create_all(bind=self.engine)

    def session(self):
        """Context manager de sesión (commit/rollback automático)."""
        from contextlib import contextmanager

        @contextmanager
        def _mgr():
            s = self.Session()
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()

        return _mgr()

    def __repr__(self) -> str:
        return f"DomainDB({self.nombre!r}, path={self.path!r})"


# ─── Instancias globales ───────────────────────────────────────────────────────
CLIENTES  = DomainDB("db_clientes")
AUTH      = DomainDB("db_auth")
PORTFOLIO = DomainDB("db_portfolio")
MERCADO   = DomainDB("db_mercado")
CONFIG    = DomainDB("db_config")
AUDITORIA = DomainDB("db_auditoria")

ALL_DOMAINS: list[DomainDB] = [CLIENTES, AUTH, PORTFOLIO, MERCADO, CONFIG, AUDITORIA]


def init_all_domains() -> None:
    """
    Inicializa todos los dominios (crea tablas si no existen).
    Llamar al arrancar la app, después de importar todos los managers.
    """
    for d in ALL_DOMAINS:
        d.create_all()
