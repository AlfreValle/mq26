"""
tests/test_auth_saas.py — Tests de core/auth_saas.py (Sprint 29)
Sin streamlit real: se inyecta un mock en sys.modules['streamlit'] donde haga falta.
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


def _swap_streamlit(mock_st: MagicMock):
    """Invariante: restaura el módulo streamlit previo tras el bloque (finally)."""
    orig = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    return orig


def _restore_streamlit(orig):
    if orig is not None:
        sys.modules["streamlit"] = orig
    else:
        sys.modules.pop("streamlit", None)


# ─── get_authenticator ────────────────────────────────────────────


class TestGetAuthenticator:
    def test_sin_auth_config_retorna_none(self, monkeypatch):
        monkeypatch.delenv("AUTH_CONFIG", raising=False)
        from core.auth_saas import get_authenticator

        assert get_authenticator() is None

    def test_auth_config_vacia_retorna_none(self, monkeypatch):
        monkeypatch.setenv("AUTH_CONFIG", "")
        from core.auth_saas import get_authenticator

        assert get_authenticator() is None

    def test_auth_config_sin_modulo_stauth_retorna_none(self, monkeypatch):
        """AUTH_CONFIG definida pero import de streamlit_authenticator falla → None."""
        monkeypatch.setenv("AUTH_CONFIG", "placeholder: true")
        orig = sys.modules.get("streamlit_authenticator")
        sys.modules["streamlit_authenticator"] = None
        try:
            from core.auth_saas import get_authenticator

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = get_authenticator()
            assert result is None
        finally:
            if orig is not None:
                sys.modules["streamlit_authenticator"] = orig
            else:
                sys.modules.pop("streamlit_authenticator", None)

    def test_nunca_lanza_excepcion(self, monkeypatch):
        monkeypatch.setenv("AUTH_CONFIG", "yaml_invalido: {{{ roto")
        from core.auth_saas import get_authenticator

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                get_authenticator()
            except Exception as e:  # pragma: no cover
                pytest.fail(f"get_authenticator lanzó: {e}")


# ─── get_tenant_id ────────────────────────────────────────────────


class TestGetTenantId:
    def test_authenticator_none_retorna_default(self):
        from core.auth_saas import get_tenant_id

        assert get_tenant_id(None) == "default"

    def test_nunca_retorna_string_vacio(self):
        from core.auth_saas import get_tenant_id

        result = get_tenant_id(None)
        assert isinstance(result, str) and len(result) > 0

    def test_con_auth_sin_username_retorna_default(self):
        from core.auth_saas import get_tenant_id

        mock_st = MagicMock()
        mock_st.session_state = {}
        orig = _swap_streamlit(mock_st)
        try:
            result = get_tenant_id(MagicMock())
        finally:
            _restore_streamlit(orig)
        assert result == "default"

    def test_con_username_retorna_email(self):
        from core.auth_saas import get_tenant_id

        mock_auth = MagicMock()
        mock_auth._credentials = {
            "usernames": {
                "alfredo": {"email": "alfredo@mail.com", "name": "Alfredo"},
            },
        }
        mock_st = MagicMock()
        mock_st.session_state = {"username": "alfredo"}
        orig = _swap_streamlit(mock_st)
        try:
            result = get_tenant_id(mock_auth)
        finally:
            _restore_streamlit(orig)
        assert result == "alfredo@mail.com"

    def test_con_username_sin_email_retorna_username(self):
        from core.auth_saas import get_tenant_id

        mock_auth = MagicMock()
        mock_auth._credentials = {"usernames": {"alfredo": {"name": "Alfredo"}}}
        mock_st = MagicMock()
        mock_st.session_state = {"username": "alfredo"}
        orig = _swap_streamlit(mock_st)
        try:
            result = get_tenant_id(mock_auth)
        finally:
            _restore_streamlit(orig)
        assert result == "alfredo"

    def test_excepcion_interna_retorna_default(self):
        """Invariante: fallo al leer credenciales → 'default' sin propagar."""
        from core.auth_saas import get_tenant_id

        class AuthCredentialsCrash:
            @property
            def _credentials(self):
                raise RuntimeError("crash")

        mock_st = MagicMock()
        mock_st.session_state = {"username": "alfredo"}
        orig = _swap_streamlit(mock_st)
        try:
            result = get_tenant_id(AuthCredentialsCrash())
        finally:
            _restore_streamlit(orig)
        assert result == "default"


# ─── login_saas ───────────────────────────────────────────────────


class TestLoginSaas:
    def test_llama_login_y_retorna_tuple(self):
        from core.auth_saas import login_saas

        mock_auth = MagicMock()
        mock_auth.login.return_value = ("Alfredo", True, "alfredo")
        name, status, user = login_saas(mock_auth)
        assert name == "Alfredo"
        assert status is True
        assert user == "alfredo"

    def test_excepcion_retorna_none_triple(self):
        from core.auth_saas import login_saas

        mock_auth = MagicMock()
        mock_auth.login.side_effect = Exception("fallo total")
        result = login_saas(mock_auth)
        assert result == (None, None, None)

    def test_nunca_lanza_excepcion(self):
        from core.auth_saas import login_saas

        mock_auth = MagicMock()
        mock_auth.login.side_effect = RuntimeError("error grave")
        try:
            login_saas(mock_auth)
        except Exception as e:  # pragma: no cover
            pytest.fail(f"login_saas lanzó: {e}")

    def test_retorna_tupla_de_tres(self):
        from core.auth_saas import login_saas

        mock_auth = MagicMock()
        mock_auth.login.return_value = ("X", False, "y")
        result = login_saas(mock_auth)
        assert isinstance(result, tuple) and len(result) == 3

    def test_typeerror_cae_a_login_con_location(self):
        """Invariante: si login(posicional) falla con TypeError, se intenta location=."""
        from core.auth_saas import login_saas

        mock_auth = MagicMock()
        mock_auth.login.side_effect = [TypeError("bad sig"), ("N", True, "u")]
        result = login_saas(mock_auth)
        assert result == ("N", True, "u")
        assert mock_auth.login.call_count == 2
