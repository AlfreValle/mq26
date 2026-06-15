"""
tests/test_email_sender.py — Tests de email_sender.py (Sprint 23)
Mockea smtplib.SMTP_SSL para no conectarse a Gmail real.
Sin red.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestEnviarEmailGmail:
    def test_sin_gmail_user_retorna_false(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import enviar_email_gmail
        ok, msg = enviar_email_gmail("dest@test.com", "Asunto", "<p>body</p>")
        assert ok is False
        assert "GMAIL_USER" in msg

    def test_sin_gmail_pwd_retorna_false(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import enviar_email_gmail
        ok, msg = enviar_email_gmail("dest@test.com", "Asunto", "<p>body</p>")
        assert ok is False
        assert "PASSWORD" in msg.upper() or "contraseña" in msg.lower()

    def test_sin_destinatario_retorna_false(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import enviar_email_gmail
        ok, msg = enviar_email_gmail("", "Asunto", "<p>body</p>")
        assert ok is False
        assert "destinatario" in msg.lower()

    def test_envio_exitoso_con_smtp_mock(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import enviar_email_gmail
        mock_server = MagicMock()
        mock_ctx_mgr = MagicMock()
        mock_ctx_mgr.__enter__ = MagicMock(return_value=mock_server)
        mock_ctx_mgr.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx_mgr):
            ok, msg = enviar_email_gmail(
                "dest@test.com", "Test Asunto", "<p>HTML</p>"
            )
        assert ok is True
        assert "enviado" in msg.lower() or "dest@test.com" in msg
        mock_server.login.assert_called_once()
        mock_server.sendmail.assert_called_once()

    def test_auth_error_retorna_false_con_instrucciones(self, monkeypatch):
        import smtplib
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "wrong_pwd")
        from services.email_sender import enviar_email_gmail
        mock_ctx = MagicMock()
        mock_ctx.__enter__.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            ok, msg = enviar_email_gmail("dest@test.com", "X", "<p/>")
        assert ok is False
        assert "autenticación" in msg.lower() or "Authentication" in msg

    def test_destinatario_rechazado_retorna_false(self, monkeypatch):
        import smtplib
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        mock_ctx = MagicMock()
        mock_ctx.__enter__.side_effect = smtplib.SMTPRecipientsRefused(
            {"bad@bad.bad": (550, b"no")}
        )
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            from services.email_sender import enviar_email_gmail
            ok, msg = enviar_email_gmail("bad@bad.bad", "X", "<p/>")
        assert ok is False
        assert "rechazado" in msg.lower() or "Recipient" in msg

    def test_excepcion_generica_retorna_false(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        with patch("smtplib.SMTP_SSL", side_effect=Exception("timeout")):
            from services.email_sender import enviar_email_gmail
            ok, msg = enviar_email_gmail("dest@test.com", "X", "<p/>")
        assert ok is False
        assert len(msg) > 0

    def test_retorna_tupla_bool_str(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        from services.email_sender import enviar_email_gmail
        result = enviar_email_gmail("dest@test.com", "X", "<p/>")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_credenciales_via_parametros_sin_env(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import enviar_email_gmail
        mock_server = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_server)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
            ok, msg = enviar_email_gmail(
                "dest@test.com", "Test", "<p/>",
                remitente="override@gmail.com",
                app_password="xxxx xxxx xxxx xxxx",
            )
        assert ok is True

    def test_adjunto_existente_no_rompe_envio(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import enviar_email_gmail

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tmp:
            tmp.write("adjunto test")
            tmp_path = tmp.name

        try:
            mock_server = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_server)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            with patch("smtplib.SMTP_SSL", return_value=mock_ctx):
                ok, _ = enviar_email_gmail(
                    "dest@test.com", "Adjunto", "<p/>", adjuntos=[tmp_path]
                )
            assert ok is True
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_error_adjuntando_retorna_false(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import enviar_email_gmail

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_bytes", side_effect=Exception("read error")):
                ok, msg = enviar_email_gmail(
                    "dest@test.com", "Adjunto", "<p/>", adjuntos=["archivo.txt"]
                )
        assert ok is False
        assert "adjuntando" in msg.lower()

    def test_smtp_exception_retorna_false(self, monkeypatch):
        import smtplib

        monkeypatch.setenv("GMAIL_USER", "test@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import enviar_email_gmail

        with patch("smtplib.SMTP_SSL", side_effect=smtplib.SMTPException("smtp down")):
            ok, msg = enviar_email_gmail("dest@test.com", "X", "<p/>")
        assert ok is False
        assert "smtp" in msg.lower()


class TestVerificarConfigEmail:
    def test_sin_config_retorna_false(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import verificar_config_email
        ok, user, msg = verificar_config_email()
        assert ok is False
        assert user == ""
        assert "❌" in msg or "no configurado" in msg.lower()

    def test_con_env_completo_retorna_true(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "alfredo@gmail.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
        from services.email_sender import verificar_config_email
        ok, user, msg = verificar_config_email()
        assert ok is True
        assert user == "alfredo@gmail.com"
        assert "✅" in msg

    def test_solo_user_sin_pwd_retorna_false(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "alfredo@gmail.com")
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import verificar_config_email
        ok, user, msg = verificar_config_email()
        assert ok is False
        assert user == "alfredo@gmail.com"
        assert "⚠️" in msg or "falta" in msg.lower()

    def test_dbm_tiene_prioridad_sobre_env(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        from services.email_sender import verificar_config_email
        mock_dbm = MagicMock()
        mock_dbm.obtener_config.side_effect = lambda k: (
            "bd@gmail.com" if k == "gmail_user" else "bd_pwd"
        )
        ok, user, msg = verificar_config_email(dbm=mock_dbm)
        assert ok is True
        assert user == "bd@gmail.com"

    def test_retorna_tupla_tres_elementos(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        from services.email_sender import verificar_config_email
        result = verificar_config_email()
        assert isinstance(result, tuple) and len(result) == 3
