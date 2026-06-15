"""
tests/test_logging_config.py — Tests de core/logging_config.py (Sprint 26)
Sin red. Verifica el filtro de datos sensibles y la inicialización del logger.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


class TestGetLogger:
    def test_retorna_logger(self):
        from core.logging_config import get_logger

        logger = get_logger("test_modulo_sprint26")
        assert isinstance(logger, logging.Logger)

    def test_mismo_nombre_retorna_misma_instancia(self):
        from core.logging_config import get_logger

        l1 = get_logger("mismo_nombre_s26")
        l2 = get_logger("mismo_nombre_s26")
        assert l1 is l2

    def test_distintos_nombres_distintas_instancias(self):
        from core.logging_config import get_logger

        l1 = get_logger("modulo_a_s26")
        l2 = get_logger("modulo_b_s26")
        assert l1 is not l2

    def test_logger_tiene_nombre_correcto(self):
        from core.logging_config import get_logger

        logger = get_logger("mi_modulo_test")
        assert logger.name == "mi_modulo_test"

    def test_raiz_configurada_tras_primer_get_logger(self):
        from core.logging_config import get_logger

        get_logger("cualquier_modulo")
        import core.logging_config as lc

        assert lc._configurado is True

    def test_idempotente_multiples_llamadas(self):
        """Llamar get_logger muchas veces no duplica handlers."""
        from core.logging_config import get_logger

        for _ in range(5):
            get_logger("test_idempotente")
        root = logging.getLogger()
        tipos = [type(h) for h in root.handlers]
        stream_handlers = [t for t in tipos if t == logging.StreamHandler]
        assert len(stream_handlers) <= 3


class TestSensitiveDataFilter:
    def _make_record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )

    def test_filtra_token_telegram(self):
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        token = "1234567890:ABCdefGHIjklMNOpqrSTUvwxyz1234567"
        record = self._make_record(f"Token recibido: {token}")
        f.filter(record)
        assert token not in record.msg
        assert "REDACTED" in record.msg

    def test_filtra_password_env(self):
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        record = self._make_record("MQ26_PASSWORD=mi_pass_super_secreta")
        f.filter(record)
        assert "mi_pass_super_secreta" not in record.msg
        assert "REDACTED" in record.msg

    def test_filtra_password_key(self):
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        record = self._make_record("password: abc123def")
        f.filter(record)
        assert "abc123def" not in record.msg

    def test_mensaje_normal_sin_cambios(self):
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        msg = "Cartera cargada: 5 posiciones, valor USD 12.340"
        record = self._make_record(msg)
        f.filter(record)
        assert record.msg == msg

    def test_siempre_retorna_true(self):
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        for msg in ["normal", "password: secreto", "MQ26_PASSWORD=abc"]:
            record = self._make_record(msg)
            assert f.filter(record) is True

    def test_args_se_vacia_tras_filtrar(self):
        """record.args queda vacío después del filtro."""
        from core.logging_config import _SensitiveDataFilter

        f = _SensitiveDataFilter()
        record = self._make_record("valor=%s")
        record.args = ("dato_sensible",)
        f.filter(record)
        assert record.args == ()
