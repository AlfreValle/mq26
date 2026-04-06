"""
tests/test_core_finales.py — Cobertura final de módulos core.
Sprint 34: pruebas puras y/o con mocks sin red real.
"""
from __future__ import annotations

import logging
import re
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestConstants:
    def test_tipos_instrumento_contiene_cedear(self):
        from core.constants import TIPOS_INSTRUMENTO

        assert "CEDEAR" in TIPOS_INSTRUMENTO

    def test_horizonte_a_dias_ordenado(self):
        from core.constants import HORIZONTE_A_DIAS

        vals = list(HORIZONTE_A_DIAS.values())
        assert vals == sorted(vals)

    def test_1_anio_es_365_dias(self):
        from core.constants import HORIZONTE_A_DIAS

        assert HORIZONTE_A_DIAS["1 año"] == 365

    def test_colores_son_hex(self):
        from core.constants import COLORES

        patron = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for _, value in COLORES.items():
            assert patron.match(value)

    def test_mensajes_son_strings(self):
        from core.constants import MENSAJES

        for _, value in MENSAJES.items():
            assert isinstance(value, str)


class TestAppContext:
    def test_defaults_correctos(self):
        from core.app_context import AppContext

        ctx = AppContext()
        assert ctx.ccl == 1500.0
        assert ctx.tenant_id == "default"
        assert ctx.cliente_id is None
        assert ctx.cliente_perfil == "Moderado"

    def test_acceso_dict_style(self):
        from core.app_context import AppContext

        ctx = AppContext(ccl=1465.0)
        assert ctx["ccl"] == 1465.0

    def test_contains_funciona(self):
        from core.app_context import AppContext

        ctx = AppContext()
        assert "ccl" in ctx
        assert "campo_inexistente_xyz" not in ctx

    def test_get_con_default(self):
        from core.app_context import AppContext

        ctx = AppContext()
        assert ctx.get("campo_raro", "fallback") == "fallback"

    def test_to_dict_retorna_dict(self):
        from core.app_context import AppContext

        ctx = AppContext(ccl=1300.0)
        dct = ctx.to_dict()
        assert isinstance(dct, dict)
        assert dct.get("ccl") == 1300.0


class TestLoggingConfig:
    def test_get_logger_retorna_logger(self):
        from core.logging_config import get_logger

        assert isinstance(get_logger("test_s34"), logging.Logger)

    def test_mismo_nombre_misma_instancia(self):
        from core.logging_config import get_logger

        assert get_logger("test_s34_x") is get_logger("test_s34_x")

    def test_filtro_redacta_token_telegram(self):
        from core.logging_config import _SensitiveDataFilter

        filtro = _SensitiveDataFilter()
        token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxyz1234567"
        record = logging.LogRecord("t", logging.INFO, "", 0, f"token={token}", (), None)
        filtro.filter(record)
        assert token not in record.msg
        assert "REDACTED" in record.msg

    def test_filtro_redacta_mq26_password(self):
        from core.logging_config import _SensitiveDataFilter

        filtro = _SensitiveDataFilter()
        record = logging.LogRecord("t", logging.INFO, "", 0, "MQ26_PASSWORD=secreto_real", (), None)
        filtro.filter(record)
        assert "secreto_real" not in record.msg

    def test_filtro_siempre_retorna_true(self):
        from core.logging_config import _SensitiveDataFilter

        filtro = _SensitiveDataFilter()
        for msg in ("normal", "MQ26_PASSWORD=x", "token=abc"):
            record = logging.LogRecord("t", logging.INFO, "", 0, msg, (), None)
            assert filtro.filter(record) is True


class TestAudit:
    def test_registrar_accion_no_lanza_sin_bd(self):
        from core.audit import registrar_accion

        with patch("core.db_manager.registrar_alerta_log", side_effect=Exception("BD")):
            registrar_accion("TEST_S34", "detalle")

    def test_registrar_login_exitoso(self):
        from core.audit import registrar_login

        with patch("core.db_manager.registrar_alerta_log") as mock_dbm:
            registrar_login("mq26", exito=True, usuario="alfredo")
        assert "LOGIN_EXITOSO" in str(mock_dbm.call_args)

    def test_registrar_login_fallido(self):
        from core.audit import registrar_login

        with patch("core.db_manager.registrar_alerta_log") as mock_dbm:
            registrar_login("mq26", exito=False)
        assert "LOGIN_FALLIDO" in str(mock_dbm.call_args)

    def test_registrar_backup_trunca_hash(self):
        from core.audit import registrar_backup

        hash_largo = "abc123def456ghi789jkl012mno345pqr678"
        with patch("core.db_manager.registrar_alerta_log") as mock_dbm:
            registrar_backup("/ruta/backup.db", hash_largo)
        msg = str(mock_dbm.call_args)
        assert hash_largo[:16] in msg


class TestNotificaciones:
    @pytest.fixture()
    def mock_streamlit_module(self):
        """Invariante: notificaciones usa streamlit mockeado en import local."""
        mock_st = MagicMock()
        with patch.dict(sys.modules, {"streamlit": mock_st}):
            yield mock_st

    def test_exito_llama_st_toast(self, mock_streamlit_module):
        from core.notificaciones import NotificadorDSS

        NotificadorDSS().exito("OK", toast=True)
        mock_streamlit_module.toast.assert_called_once()

    def test_error_llama_st_error(self, mock_streamlit_module):
        from core.notificaciones import NotificadorDSS

        NotificadorDSS().error("Error")
        mock_streamlit_module.error.assert_called_once()

    def test_no_lanza_con_bd_fallida(self, mock_streamlit_module):
        from core.notificaciones import NotificadorDSS

        mock_dbm = MagicMock()
        mock_dbm.registrar_alerta_log.side_effect = Exception("BD")
        NotificadorDSS(dbm=mock_dbm).exito("Test")


class TestCacheManager:
    def test_ttls_son_positivos(self):
        import core.cache_manager as cm

        for attr in ("_TTL_CCL", "_TTL_HISTORICO", "_TTL_PRECIOS", "_TTL_METRICAS", "_TTL_DASHBOARD"):
            assert getattr(cm, attr) > 0

    def test_limpiar_sesion_elimina_claves(self):
        import core.cache_manager as cm

        mock_st = MagicMock()
        mock_st.session_state = {
            "_df_ag_cache_Retiro": "datos",
            "_df_ag_hash_Retiro": "hash",
            "_df_ag_cache_Otros": "no tocar",
        }
        with patch.object(cm, "st", mock_st):
            cm.limpiar_cache_sesion("Retiro")
        assert "_df_ag_cache_Retiro" not in mock_st.session_state
        assert "_df_ag_cache_Otros" in mock_st.session_state


class TestDataBridge:
    def test_publicar_y_leer_ccl(self):
        from services.data_bridge import publicar_ccl

        with patch("core.db_manager.set_config") as mock_set:
            publicar_ccl(1465.0)
        mock_set.assert_called_with("ccl_actual", "1465.0")

    def test_leer_ccl_retorna_float(self):
        from services.data_bridge import leer_ccl

        with patch("core.db_manager.get_config", return_value="1465.50"):
            result = leer_ccl()
        assert result == pytest.approx(1465.50)

    def test_leer_ccl_fallback_sin_config(self, monkeypatch):
        from services.data_bridge import leer_ccl

        monkeypatch.delenv("CCL_FALLBACK_OVERRIDE", raising=False)
        with patch("core.db_manager.get_config", return_value=None):
            result = leer_ccl()
        assert result == pytest.approx(1500.0)

    def test_publicar_no_lanza_con_bd_fallida(self):
        from services.data_bridge import publicar_ccl

        with patch("core.db_manager.set_config", side_effect=Exception("BD")):
            publicar_ccl(1465.0)
