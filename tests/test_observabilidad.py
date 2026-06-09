"""
tests/test_observabilidad.py — Tests del sistema de observabilidad (Sprint 16)
Cubre: metrics_service, logging_config (JSON/dev formatters, set_log_context),
constantes en config.py, regresión P1-OBS-01 (fuente) y P1-OBS-02 (mocks de fallo).
Sin red. Sin yfinance real.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── metrics_service ─────────────────────────────────────────────────────────

class TestMetricsService:
    def setup_method(self):
        """Resetear contadores antes de cada test."""
        from services.metrics_service import resetear
        resetear()

    def test_incrementar_contador(self):
        from services.metrics_service import incrementar, obtener_resumen
        incrementar("cache_hit", 3)
        r = obtener_resumen()
        assert r["contadores"].get("cache_hit", 0) == 3

    def test_incrementar_acumula(self):
        from services.metrics_service import incrementar, obtener_resumen
        incrementar("evento", 2)
        incrementar("evento", 3)
        r = obtener_resumen()
        assert r["contadores"]["evento"] == 5

    def test_registrar_tiempo(self):
        from services.metrics_service import obtener_resumen, registrar_tiempo
        registrar_tiempo("operacion_test", 0.123)
        r = obtener_resumen()
        assert "operacion_test" in r["tiempos_promedio"]
        assert abs(r["tiempos_promedio"]["operacion_test"] - 0.123) < 0.001

    def test_promedio_de_tiempos(self):
        from services.metrics_service import obtener_resumen, registrar_tiempo
        registrar_tiempo("op", 0.1)
        registrar_tiempo("op", 0.3)
        r = obtener_resumen()
        assert abs(r["tiempos_promedio"]["op"] - 0.2) < 0.01

    def test_registrar_error(self):
        from services.metrics_service import obtener_resumen, registrar_error
        registrar_error("price_engine", "timeout", {"ticker": "AAPL"})
        r = obtener_resumen()
        assert r["n_errores_total"] >= 1

    def test_ring_buffer_max_100_errores(self):
        from services.metrics_service import obtener_resumen, registrar_error
        for i in range(110):
            registrar_error("modulo", f"error {i}")
        r = obtener_resumen()
        assert r["n_errores_total"] <= 100

    def test_obtener_resumen_retorna_dict(self):
        from services.metrics_service import obtener_resumen
        r = obtener_resumen()
        assert isinstance(r, dict)
        for k in ("contadores", "tiempos_promedio", "ultimos_errores", "n_errores_total"):
            assert k in r

    def test_resetear_limpia_todo(self):
        from services.metrics_service import incrementar, obtener_resumen, resetear
        incrementar("algo", 5)
        resetear()
        r = obtener_resumen()
        assert r["contadores"].get("algo", 0) == 0

    def test_funciones_no_lanzan_con_inputs_invalidos(self):
        from services.metrics_service import (
            incrementar,
            obtener_resumen,
            registrar_error,
            registrar_tiempo,
        )
        try:
            incrementar(None)
            registrar_tiempo("", -1.0)
            registrar_error("", None, None)
            obtener_resumen()
        except Exception as e:
            pytest.fail(f"metrics_service lanzó con input inválido: {e}")


# ─── logging_config ───────────────────────────────────────────────────────────

class TestLoggingConfig:
    def teardown_method(self):
        """Limpiar contexto de log tras cada test."""
        try:
            from core.logging_config import clear_log_context
            clear_log_context()
        except Exception:
            pass

    def test_get_logger_retorna_logger(self):
        from core.logging_config import get_logger
        logger = get_logger("test_modulo_s16")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_mismo_nombre_misma_instancia(self):
        from core.logging_config import get_logger
        l1 = get_logger("mismo_nombre_s16")
        l2 = get_logger("mismo_nombre_s16")
        assert l1 is l2

    def test_set_log_context_no_lanza(self):
        from core.logging_config import set_log_context
        try:
            set_log_context(tenant_id="test@mail.com", cartera="Retiro")
        except Exception as e:
            pytest.fail(f"set_log_context lanzó: {e}")

    def test_clear_log_context_no_lanza(self):
        from core.logging_config import clear_log_context, set_log_context
        set_log_context(x="1")
        try:
            clear_log_context()
        except Exception as e:
            pytest.fail(f"clear_log_context lanzó: {e}")

    def test_json_formatter_produce_json_valido(self):
        from core.logging_config import _JsonFormatter
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0,
            msg="mensaje de prueba", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "ts" in parsed
        assert "level" in parsed
        assert "msg" in parsed
        assert parsed["msg"] == "mensaje de prueba"

    def test_dev_formatter_produce_string_legible(self):
        from core.logging_config import _DevFormatter
        formatter = _DevFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname="", lineno=0,
            msg="advertencia de prueba", args=(), exc_info=None,
        )
        output = formatter.format(record)
        assert isinstance(output, str)
        assert "WARNING" in output or "advertencia" in output

    def test_logger_tiene_handler(self):
        from core.logging_config import get_logger
        logger = get_logger("test_handler_check_s16")
        # El handler puede estar en el root logger o en este logger
        root_handlers = logging.getLogger().handlers
        own_handlers   = logger.handlers
        assert len(root_handlers) > 0 or len(own_handlers) > 0

    def test_logger_nivel_correcto(self):
        from core.logging_config import get_logger
        logger = get_logger("test_nivel_s16")
        # El nivel efectivo debe ser INFO o más detallado (DEBUG)
        assert logger.getEffectiveLevel() <= logging.INFO


# ─── config.py — nuevas constantes ───────────────────────────────────────────

class TestConfigObservabilidad:
    def test_log_level_es_string_valido(self):
        from config import LOG_LEVEL
        assert isinstance(LOG_LEVEL, str)
        assert LOG_LEVEL in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def test_environment_es_string_no_vacio(self):
        from config import ENVIRONMENT
        assert isinstance(ENVIRONMENT, str)
        assert len(ENVIRONMENT) > 0

    def test_environment_por_defecto_es_development(self, monkeypatch):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        import importlib

        import config as cfg
        importlib.reload(cfg)
        assert cfg.ENVIRONMENT == "development"


# ─── P1-OBS-01: `log_degradacion` en tabs calientes + run_mq26 (regresión fuente) ─

def _read_repo_file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def test_log_degradacion_no_lanza():
    from core.structured_logging import log_degradacion

    log_degradacion("tests.observabilidad", "evento_sintetico", ValueError("probe"), k=1)
    log_degradacion("tests.observabilidad", "evento_sin_exc", ok=True)


def test_p1_obs01_archivos_tienen_eventos_log_degradacion():
    """Evita regresión a `except: pass` en puntos acordados (P1-OBS-01)."""
    opt = _read_repo_file("ui/tab_optimizacion.py")
    assert "from core.structured_logging import log_degradacion" in opt
    assert "listar_snapshots_lab" in opt
    assert "lab_quant_modelo_fallo" in opt
    assert "lab_quant_multiobjetivo_fallo" in opt
    assert "lab_quant_black_litterman_fallo" in opt

    rsk = _read_repo_file("ui/tab_riesgo.py")
    assert "from core.structured_logging import log_degradacion" in rsk
    assert "ccl_proxy_series_fallo" in rsk
    assert "exposicion_factorial_beta_fallo" in rsk

    uni = _read_repo_file("ui/tab_universo.py")
    assert "from core.structured_logging import log_degradacion" in uni
    assert "sp500_sector_panel_fallo" in uni
    assert "monitor_on_usd_fallo" in uni
    assert "historial_alertas_mod23_fallo" in uni
    assert "cafci_fci_scanner_fallo" in uni

    rm = _read_repo_file("run_mq26.py")
    assert "from core.structured_logging import log_degradacion" in rm
    assert "price_engine_portfolio_fallo" in rm
    assert "alertas_sidebar_monitor_fallo" in rm
    assert "cached_clientes_df_fallo" in rm
    assert "registrar_alerta_precio_manual_fallo" in rm


# ─── P1-OBS-02: mocks de fallo — asegura que degradaciones no queden silenciadas ─


class TestP1Obs02LogDegradacionMocks:
    def test_log_degradacion_con_excepcion_usa_exc_info_en_warning(self, monkeypatch):
        mock_logger = MagicMock()
        monkeypatch.setattr(
            "core.structured_logging.get_logger",
            lambda _name: mock_logger,
        )
        from core.structured_logging import log_degradacion

        exc = OSError("fallo simulado")
        log_degradacion("tests.p1_obs02", "evento_mock", exc, ticker="GGAL")

        mock_logger.warning.assert_called_once()
        _args, kwargs = mock_logger.warning.call_args
        assert kwargs.get("exc_info") is True
        assert "evento_mock" in str(_args[1])
        assert exc in _args

    def test_log_degradacion_sin_excepcion_no_pasa_exc_info(self, monkeypatch):
        mock_logger = MagicMock()
        monkeypatch.setattr(
            "core.structured_logging.get_logger",
            lambda _name: mock_logger,
        )
        from core.structured_logging import log_degradacion

        log_degradacion("tests.p1_obs02", "solo_contexto", nivel="warn")

        mock_logger.warning.assert_called_once()
        _args, kwargs = mock_logger.warning.call_args
        assert kwargs.get("exc_info") in (None, False)
        payload = _args[1]
        assert payload["evento"] == "solo_contexto"
        assert payload["nivel"] == "warn"


class TestP1Obs02BuildCclSeriesMock:
    def test_build_ccl_series_llama_log_degradacion_si_callback_lanza(self, monkeypatch):
        mock_ld = MagicMock()
        monkeypatch.setattr("ui.tab_riesgo.log_degradacion", mock_ld)
        from ui.tab_riesgo import _build_ccl_series

        def _falla(_tickers, _period):
            raise ConnectionError("red caída (mock)")

        assert _build_ccl_series(_falla, "2y") is None
        mock_ld.assert_called_once()
        args, kwargs = mock_ld.call_args
        assert args[0] == "ui.tab_riesgo"
        assert args[1] == "ccl_proxy_series_fallo"
        assert isinstance(args[2], ConnectionError)
        assert kwargs.get("period") == "2y"

    def test_build_ccl_series_no_log_si_dataframe_vacio_sin_excepcion(self, monkeypatch):
        mock_ld = MagicMock()
        monkeypatch.setattr("ui.tab_riesgo.log_degradacion", mock_ld)
        from ui.tab_riesgo import _build_ccl_series

        assert _build_ccl_series(lambda _t, _p: pd.DataFrame(), "1y") is None
        mock_ld.assert_not_called()

    def test_build_ccl_series_no_log_si_faltan_columnas_ggal(self, monkeypatch):
        mock_ld = MagicMock()
        monkeypatch.setattr("ui.tab_riesgo.log_degradacion", mock_ld)
        from ui.tab_riesgo import _build_ccl_series

        assert _build_ccl_series(
            lambda _t, _p: pd.DataFrame({"OTRO": [1.0, 2.0]}),
            "6mo",
        ) is None
        mock_ld.assert_not_called()
