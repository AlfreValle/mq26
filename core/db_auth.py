"""
core/db_auth.py — Dominio: Autenticación & Usuarios Operativos
DB: 0_Data_Maestra/db_auth.db

Tablas:
  app_usuarios         — Usuarios de login (bcrypt, roles)
  app_usuario_cliente  — N:M usuario ↔ cliente (alcance de cartera)
  usuarios             — Tier legacy (mantener compatibilidad)

Aislado de otros dominios: cliente_id referenciado por valor, no FK.
"""
from __future__ import annotations

import datetime as dt
import hashlib

from sqlalchemy import (
    Boolean, Column, DateTime, Index, Integer,
    String, Text, UniqueConstraint,
)

from core.db_domains import AUTH

_B = AUTH.Base

_ROLES_VALIDOS  = frozenset({"super_admin", "asesor", "estudio", "inversor"})
_RAMAS_VALIDAS  = frozenset({"profesional", "retail"})


# ─── Modelos ──────────────────────────────────────────────────────────────────

class AppUsuario(_B):
    """Usuario operativo con hash bcrypt (preferred) o SHA-256 (legacy)."""
    __tablename__ = "app_usuarios"
    __table_args__ = (
        UniqueConstraint("tenant_id", "username", name="uq_appusr_tenant_username"),
        Index("ix_appusr_tenant", "tenant_id"),
    )

    id            = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id     = Column(String(200), nullable=False, default="default")
    username      = Column(String(100), nullable=False)
    password_hash = Column(String(300), nullable=False)
    rol           = Column(String(30), default="inversor")
    rama          = Column(String(30), default="retail")
    activo        = Column(Boolean, default=True)
    email         = Column(String(200), default="")
    notas         = Column(Text, default="")
    created_at    = Column(DateTime, default=dt.datetime.utcnow)
    last_login    = Column(DateTime, nullable=True)


class AppUsuarioCliente(_B):
    """Alcance N:M — qué clientes puede ver cada usuario."""
    __tablename__ = "app_usuario_cliente"
    __table_args__ = (
        UniqueConstraint("usuario_id", "cliente_id", name="uq_usr_cli"),
        Index("ix_usr_cli_usuario", "usuario_id"),
    )

    id         = Column(Integer, primary_key=True, autoincrement=True)
    usuario_id = Column(Integer, nullable=False)   # ref a app_usuarios.id (mismo dominio)
    cliente_id = Column(Integer, nullable=False)   # ref a db_clientes.clientes.id (cross-domain por valor)
    tenant_id  = Column(String(200), nullable=False, default="default")


class Usuario(_B):
    """Tier legacy (SaaS v1). Mantener para compatibilidad con auth_saas.py."""
    __tablename__ = "usuarios"
    __table_args__ = (Index("ix_usuarios_tenant", "tenant_id"),)

    id              = Column(Integer, primary_key=True, autoincrement=True)
    email           = Column(String(200), unique=True, nullable=False, index=True)
    tier            = Column(String(20), default="inversor")
    tenant_id       = Column(String(200), nullable=False, default="default")
    hashed_password = Column(String(200))
    activo          = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=dt.datetime.utcnow)


# ─── Inicializar ──────────────────────────────────────────────────────────────
AUTH.create_all()


# ─── API de dominio ───────────────────────────────────────────────────────────

def _hash_sha256(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def crear_usuario(
    username: str,
    password: str,
    rol: str = "inversor",
    rama: str = "retail",
    tenant_id: str = "default",
    email: str = "",
    notas: str = "",
    use_bcrypt: bool = True,
) -> int:
    """Crea un usuario y retorna su ID. Hash bcrypt preferido."""
    if rol not in _ROLES_VALIDOS:
        raise ValueError(f"Rol inválido: {rol!r}. Válidos: {_ROLES_VALIDOS}")
    if rama not in _RAMAS_VALIDAS:
        raise ValueError(f"Rama inválida: {rama!r}. Válidas: {_RAMAS_VALIDAS}")

    if use_bcrypt:
        try:
            import bcrypt
            pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        except ImportError:
            pwd_hash = _hash_sha256(password)
    else:
        pwd_hash = _hash_sha256(password)

    with AUTH.session() as s:
        u = AppUsuario(
            tenant_id=tenant_id,
            username=username.strip()[:100],
            password_hash=pwd_hash,
            rol=rol,
            rama=rama,
            email=email.strip()[:200],
            notas=notas,
        )
        s.add(u)
        s.flush()
        return u.id


def verificar_password(username: str, password: str, tenant_id: str = "default") -> "AppUsuario | None":
    """Verifica credenciales y retorna el usuario si son correctas."""
    with AUTH.session() as s:
        u = (
            s.query(AppUsuario)
            .filter(
                AppUsuario.tenant_id == tenant_id,
                AppUsuario.username == username.strip(),
                AppUsuario.activo == True,
            )
            .first()
        )
        if not u:
            return None
        # Intentar bcrypt
        try:
            import bcrypt
            ok = bcrypt.checkpw(password.encode(), u.password_hash.encode())
        except Exception:
            ok = (_hash_sha256(password) == u.password_hash)
        if not ok:
            return None
        u.last_login = dt.datetime.utcnow()
        return u


def obtener_usuarios_df(tenant_id: str = "default") -> "pd.DataFrame":
    import pandas as pd

    with AUTH.session() as s:
        rows = (
            s.query(AppUsuario)
            .filter(AppUsuario.tenant_id == tenant_id)
            .order_by(AppUsuario.username)
            .all()
        )
        if not rows:
            return pd.DataFrame(columns=["id", "username", "rol", "rama", "activo", "email"])
        return pd.DataFrame([{
            "id": r.id, "username": r.username, "rol": r.rol,
            "rama": r.rama, "activo": r.activo, "email": r.email,
            "created_at": r.created_at, "last_login": r.last_login,
        } for r in rows])


def vincular_usuario_cliente(usuario_id: int, cliente_id: int, tenant_id: str = "default") -> None:
    """Asocia un usuario a un cliente (alcance de cartera)."""
    with AUTH.session() as s:
        exists = (
            s.query(AppUsuarioCliente)
            .filter(
                AppUsuarioCliente.usuario_id == usuario_id,
                AppUsuarioCliente.cliente_id == cliente_id,
            )
            .first()
        )
        if not exists:
            s.add(AppUsuarioCliente(
                usuario_id=usuario_id,
                cliente_id=cliente_id,
                tenant_id=tenant_id,
            ))


def clientes_de_usuario(usuario_id: int) -> list[int]:
    """IDs de clientes que puede ver el usuario."""
    with AUTH.session() as s:
        rows = (
            s.query(AppUsuarioCliente.cliente_id)
            .filter(AppUsuarioCliente.usuario_id == usuario_id)
            .all()
        )
        return [r.cliente_id for r in rows]
