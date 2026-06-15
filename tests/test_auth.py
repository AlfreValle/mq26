"""
tests/test_auth.py — Tests de core/auth.py (Sprint 18)
Las funciones puras (_hash_password, verificar_password) se testean directamente.
check_password, get_session_token y cerrar_sesion mockean st a nivel de módulo.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── _hash_password ───────────────────────────────────────────────────────────

class TestHashPassword:
    def test_retorna_string(self):
        from core.auth import _hash_password
        result = _hash_password("mi_contraseña")
        assert isinstance(result, str)

    def test_longitud_sha256(self):
        from core.auth import _hash_password
        result = _hash_password("test")
        assert len(result) == 64  # SHA-256 = 32 bytes = 64 hex chars

    def test_determinista(self):
        from core.auth import _hash_password
        assert _hash_password("abc") == _hash_password("abc")

    def test_distintas_entradas_distinto_hash(self):
        from core.auth import _hash_password
        assert _hash_password("abc") != _hash_password("ABC")
        assert _hash_password("abc") != _hash_password("abcd")

    def test_string_vacio(self):
        from core.auth import _hash_password
        result = _hash_password("")
        assert isinstance(result, str) and len(result) == 64


# ─── verificar_password ───────────────────────────────────────────────────────

class TestVerificarPassword:
    def test_password_correcto_retorna_true(self):
        from core.auth import verificar_password
        assert verificar_password("mi_pass_segura", "mi_pass_segura") is True

    def test_password_incorrecto_retorna_false(self):
        from core.auth import verificar_password
        assert verificar_password("wrong", "correcto") is False

    def test_password_env_vacio_retorna_false(self):
        from core.auth import verificar_password
        assert verificar_password("cualquier", "") is False

    def test_case_sensitive(self):
        from core.auth import verificar_password
        assert verificar_password("Password", "password") is False

    def test_espacios_importan(self):
        from core.auth import verificar_password
        assert verificar_password("pass ", "pass") is False

    def test_unicode_correcto(self):
        from core.auth import verificar_password
        pwd = "contraseña_con_ñ_2024"
        assert verificar_password(pwd, pwd) is True

    def test_resistente_a_timing_usa_hmac(self):
        """verificar_password usa hmac.compare_digest (no ==)."""
        import inspect

        from core.auth import verificar_password
        src = inspect.getsource(verificar_password)
        assert "compare_digest" in src


# ─── check_password (mockeando st a nivel de módulo) ─────────────────────────

class TestCheckPassword:
    def test_sesion_activa_retorna_true(self):
        """Si auth está en session_state con ts reciente → retorna True."""
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth":    True,
            "mq26_auth_ts": time.time(),
        }
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.check_password(app_id="mq26", password_env="test_pass")
        assert result is True

    def test_sin_sesion_retorna_false(self):
        """Sin sesión activa → muestra login form → retorna False."""
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.check_password(app_id="mq26", password_env="test_pass")
        assert result is False

    def test_sesion_expirada_retorna_false(self):
        """Sesión expirada (elapsed > timeout) → limpia y retorna False."""
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth":    True,
            "mq26_auth_ts": time.time() - 9_999,  # hace mucho tiempo
        }
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.check_password(
                app_id="mq26",
                password_env="test_pass",
                session_timeout=300,
            )
        assert result is False

    def test_sesion_expirada_limpia_keys_auth_ts_token_error(self):
        """Sesión expirada: elimina mq26_auth, ts, token y error del session_state."""
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth":       True,
            "mq26_auth_ts":    time.time() - 9_999,
            "mq26_auth_token": "tok",
            "mq26_auth_error": True,
        }
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.check_password(
                app_id="mq26",
                password_env="test_pass",
                session_timeout=300,
            )
        assert result is False
        assert "mq26_auth" not in mock_st.session_state
        assert "mq26_auth_ts" not in mock_st.session_state
        assert "mq26_auth_token" not in mock_st.session_state
        assert "mq26_auth_error" not in mock_st.session_state


# ─── _esta_bloqueado ─────────────────────────────────────────────────────────

class TestEstaBloqueado:
    """Invariante: (bloqueado, restante) coherente con fails/lock_ts y cooldown."""

    def test_sin_intentos_no_bloqueado(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(auth_mod, "st", mock_st):
            bloqueado, restante = auth_mod._esta_bloqueado("mq26_auth")
        assert bloqueado is False
        assert restante == 0

    def test_bloqueado_tras_max_intentos(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth_fails":   5,
            "mq26_auth_lock_ts": time.time(),
        }
        with patch.object(auth_mod, "st", mock_st):
            bloqueado, restante = auth_mod._esta_bloqueado("mq26_auth")
        assert bloqueado is True
        assert restante > 0

    def test_bloqueo_expirado_no_bloqueado(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth_fails":   5,
            "mq26_auth_lock_ts": time.time() - 400,
        }
        with patch.object(auth_mod, "st", mock_st):
            bloqueado, _ = auth_mod._esta_bloqueado("mq26_auth")
        assert bloqueado is False

    def test_pocos_intentos_no_bloqueado(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth_fails":   3,
            "mq26_auth_lock_ts": time.time(),
        }
        with patch.object(auth_mod, "st", mock_st):
            bloqueado, _ = auth_mod._esta_bloqueado("mq26_auth")
        assert bloqueado is False


# ─── get_session_token / cerrar_sesion ───────────────────────────────────────

class TestSesionUtils:
    def test_get_session_token_retorna_none_sin_sesion(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.get_session_token("mq26")
        assert result is None

    def test_get_session_token_retorna_token_si_existe(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {"mq26_auth_token": "abc123token"}
        with patch.object(auth_mod, "st", mock_st):
            result = auth_mod.get_session_token("mq26")
        assert result == "abc123token"

    def test_cerrar_sesion_limpia_session_state(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {
            "mq26_auth":       True,
            "mq26_auth_ts":    12345,
            "mq26_auth_token": "abc",
        }
        with patch.object(auth_mod, "st", mock_st):
            auth_mod.cerrar_sesion("mq26")
        assert "mq26_auth" not in mock_st.session_state

    def test_cerrar_sesion_idempotente_sin_estado(self):
        """Invariante: cerrar_sesion con session_state vacío no lanza."""
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(auth_mod, "st", mock_st):
            auth_mod.cerrar_sesion("mq26")
            auth_mod.cerrar_sesion("mq26")


# ─── get_user_role (G01) ──────────────────────────────────────────────────────


class TestGetUserRole:
    def test_default_admin(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(auth_mod, "st", mock_st):
            assert auth_mod.get_user_role("mq26") == "super_admin"

    def test_viewer_cuando_esta_en_sesion(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {"mq26_user_role": "viewer"}
        with patch.object(auth_mod, "st", mock_st):
            assert auth_mod.get_user_role("mq26") == "estudio"

    def test_inversor_cuando_esta_en_sesion(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {"mq26_user_role": "inversor"}
        with patch.object(auth_mod, "st", mock_st):
            assert auth_mod.get_user_role("mq26") == "inversor"

    def test_estudio_passthrough(self):
        from core import auth as auth_mod
        mock_st = MagicMock()
        mock_st.session_state = {"mq26_user_role": "estudio"}
        with patch.object(auth_mod, "st", mock_st):
            assert auth_mod.get_user_role("mq26") == "estudio"


class TestHasFeature:
    def test_super_admin_tiene_admin(self):
        from core.auth import has_feature

        assert has_feature("super_admin", "tab_admin") is True

    def test_inversor_no_tiene_tab_admin(self):
        from core.auth import has_feature

        assert has_feature("inversor", "tab_admin") is False

    def test_estudio_lab_quant_sin_tab_admin(self):
        from core.auth import has_feature

        assert has_feature("estudio", "lab_quant") is True
        assert has_feature("estudio", "tab_admin") is False
