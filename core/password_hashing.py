"""
Hashing de contraseñas para usuarios de app (Fase 3).

Soporta:
- bcrypt (nuevo estándar)
- sha256 legacy (solo verificación/migración)
"""
from __future__ import annotations

import hashlib
import hmac

import bcrypt


def hash_password_bcrypt(plain: str) -> str:
    pwd = (plain or "").encode("utf-8")
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")


def hash_password_sha256_legacy(plain: str) -> str:
    return hashlib.sha256((plain or "").encode("utf-8")).hexdigest()


def verify_password(plain: str, stored_hash: str) -> tuple[bool, bool]:
    """
    Retorna (ok, needs_upgrade_to_bcrypt).
    """
    sh = str(stored_hash or "")
    pwd = (plain or "").encode("utf-8")
    if sh.startswith("$2a$") or sh.startswith("$2b$") or sh.startswith("$2y$"):
        try:
            return bool(bcrypt.checkpw(pwd, sh.encode("utf-8"))), False
        except Exception:
            return False, False
    # Legacy SHA-256 hex
    legacy = hash_password_sha256_legacy(plain)
    ok = hmac.compare_digest(sh, legacy)
    return ok, ok
