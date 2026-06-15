"""
tests/test_notificaciones.py — Tests de core/notificaciones.py (Sprint 18)
notificaciones.py usa 'import streamlit as st' dentro de cada método (inline),
por lo que se parchea 'streamlit.X' directamente en el módulo streamlit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── NotificadorDSS ───────────────────────────────────────────────────────────

class TestNotificadorDSS:
    def test_importa_sin_error(self):
        from core.notificaciones import NotificadorDSS
        assert callable(NotificadorDSS)

    def test_instancia_sin_argumentos(self):
        from core.notificaciones import NotificadorDSS
        n = NotificadorDSS()
        assert n.cliente_id is None
        assert n.dbm is None

    def test_exito_llama_st_toast_cuando_toast_true(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.toast") as mock_toast:
            n = NotificadorDSS()
            n.exito("Operación exitosa", toast=True)
        mock_toast.assert_called_once()

    def test_exito_llama_st_success_cuando_toast_false(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.success") as mock_success:
            n = NotificadorDSS()
            n.exito("OK", toast=False)
        mock_success.assert_called_once()

    def test_error_llama_st_error(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.error") as mock_error:
            n = NotificadorDSS()
            n.error("Error grave")
        mock_error.assert_called_once()

    def test_error_toast_true_llama_st_toast(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.toast") as mock_toast:
            n = NotificadorDSS()
            n.error("Error con toast", toast=True)
        mock_toast.assert_called_once()

    def test_alerta_llama_st_warning(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.warning") as mock_warning:
            n = NotificadorDSS()
            n.alerta("Alerta de presupuesto")
        mock_warning.assert_called_once()

    def test_info_llama_st_info(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.info") as mock_info:
            n = NotificadorDSS()
            n.info("Información útil")
        mock_info.assert_called_once()

    def test_presupuesto_desvio_llama_st_markdown(self):
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.markdown") as mock_md:
            n = NotificadorDSS()
            n.presupuesto_desvio("Alimentos", 92.0, 9_200.0, 10_000.0)
        mock_md.assert_called_once()

    def test_no_lanza_con_bd_fallida(self):
        """Fallo en BD no debe propagar la excepción al llamador."""
        from core.notificaciones import NotificadorDSS
        mock_dbm = MagicMock()
        mock_dbm.registrar_alerta_log.side_effect = Exception("BD caída")
        with patch("streamlit.toast"), patch("streamlit.success"):
            n = NotificadorDSS(cliente_id=1, dbm=mock_dbm)
            try:
                n.exito("Test con BD caída")
            except Exception as e:
                pytest.fail(f"NotificadorDSS.exito lanzó con BD caída: {e}")

    def test_mensajes_incluyen_texto(self):
        """El mensaje del usuario aparece en los args de la llamada a st."""
        from core.notificaciones import NotificadorDSS
        with patch("streamlit.error") as mock_error:
            n = NotificadorDSS()
            n.error("ERROR_ESPECIFICO_XYZ")
        call_args = str(mock_error.call_args)
        assert "ERROR_ESPECIFICO_XYZ" in call_args


# ─── Funciones convenience ────────────────────────────────────────────────────

class TestNotificacionesConvenience:
    def test_notificar_exito_callable(self):
        from core.notificaciones import notificar_exito
        assert callable(notificar_exito)

    def test_notificar_error_callable(self):
        from core.notificaciones import notificar_error
        assert callable(notificar_error)

    def test_notificar_exito_no_lanza(self):
        from core.notificaciones import notificar_exito
        with patch("streamlit.toast"), patch("streamlit.success"):
            try:
                notificar_exito("Test éxito")
            except Exception as e:
                pytest.fail(f"notificar_exito lanzó: {e}")

    def test_notificar_error_no_lanza(self):
        from core.notificaciones import notificar_error
        with patch("streamlit.error"):
            try:
                notificar_error("Test error")
            except Exception as e:
                pytest.fail(f"notificar_error lanzó: {e}")
