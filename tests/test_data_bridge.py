"""
tests/test_data_bridge.py — Tests de services/data_bridge.py (Sprint 19 + 23)
Cubre: publicar_ccl, leer_ccl, publicar_objetivo_completado.
Usa BD SQLite en memoria via db_en_memoria fixture y mocks de core.db_manager.
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

import services.data_bridge as db


class TestPublicarCcl:
    def test_publicar_y_leer_ccl(self, db_en_memoria):
        db.publicar_ccl(1465.0)
        valor = db.leer_ccl()
        assert isinstance(valor, float)
        assert valor == pytest.approx(1465.0)

    def test_publicar_actualiza_valor(self, db_en_memoria):
        db.publicar_ccl(1400.0)
        db.publicar_ccl(1550.0)
        valor = db.leer_ccl()
        assert valor == pytest.approx(1550.0)

    def test_no_lanza_excepcion(self, db_en_memoria):
        try:
            db.publicar_ccl(1500.0)
        except Exception as e:
            pytest.fail(f"publicar_ccl lanzó: {e}")


class TestLeerCcl:
    def test_retorna_float(self, db_en_memoria):
        result = db.leer_ccl()
        assert isinstance(result, float)

    def test_sin_valor_retorna_fallback(self, db_en_memoria):
        result = db.leer_ccl()
        assert result > 0

    def test_valor_invalido_retorna_fallback(self, db_en_memoria):
        import core.db_manager as dbm
        dbm.set_config("ccl_actual", "not_a_number")
        result = db.leer_ccl()
        assert isinstance(result, float)
        assert result == pytest.approx(1500.0)

    def test_valor_vacio_retorna_fallback(self, db_en_memoria):
        import core.db_manager as dbm
        dbm.set_config("ccl_actual", "")
        result = db.leer_ccl()
        assert isinstance(result, float)
        assert result > 0


class TestPublicarObjetivoCompletado:
    def test_no_lanza_excepcion(self, db_en_memoria):
        try:
            db.publicar_objetivo_completado(1, "AAPL", 100_000.0)
        except Exception as e:
            pytest.fail(f"publicar_objetivo_completado lanzó: {e}")

    def test_guarda_en_bd(self, db_en_memoria):
        import core.db_manager as dbm
        db.publicar_objetivo_completado(5, "MSFT", 250_000.0)
        key = "objetivo_completado_5_MSFT"
        valor = dbm.get_config(key)
        assert valor is not None
        assert "250000" in str(valor)

    def test_multiples_clientes(self, db_en_memoria):
        db.publicar_objetivo_completado(1, "KO", 50_000.0)
        db.publicar_objetivo_completado(2, "KO", 75_000.0)
        # No debe lanzar excepción con mismos tickers para distintos clientes


# ─── Mocks core.db_manager (sin BD real) — Sprint 23 ──────────────

class TestPublicarCclMocked:
    def test_llama_set_config_con_clave_correcta(self):
        with patch("core.db_manager.set_config") as mock_set:
            db.publicar_ccl(1465.0)
        mock_set.assert_called_once_with("ccl_actual", "1465.0")

    def test_redondea_a_dos_decimales(self):
        with patch("core.db_manager.set_config") as mock_set:
            db.publicar_ccl(1465.123456)
        assert mock_set.call_args[0][1] == "1465.12"

    def test_no_lanza_con_bd_fallida(self):
        with patch("core.db_manager.set_config", side_effect=Exception("BD caída")):
            try:
                db.publicar_ccl(1465.0)
            except Exception as e:
                pytest.fail(f"publicar_ccl lanzó: {e}")

    def test_no_lanza_con_ccl_cero(self):
        with patch("core.db_manager.set_config"):
            try:
                db.publicar_ccl(0.0)
            except Exception as e:
                pytest.fail(f"publicar_ccl(0.0) lanzó: {e}")


class TestLeerCclMocked:
    def test_retorna_valor_guardado(self):
        with patch("core.db_manager.get_config", return_value="1465.50"):
            result = db.leer_ccl()
        assert result == pytest.approx(1465.50)

    def test_fallback_cuando_no_existe(self, monkeypatch):
        monkeypatch.delenv("CCL_FALLBACK_OVERRIDE", raising=False)
        with patch("core.db_manager.get_config", return_value=None):
            result = db.leer_ccl()
        assert result == pytest.approx(1500.0)

    def test_fallback_desde_env(self, monkeypatch):
        monkeypatch.setenv("CCL_FALLBACK_OVERRIDE", "1800.0")
        with patch("core.db_manager.get_config", return_value=None):
            result = db.leer_ccl()
        assert result == pytest.approx(1800.0)

    def test_retorna_float_siempre(self):
        with patch("core.db_manager.get_config", return_value="1400"):
            result = db.leer_ccl()
        assert isinstance(result, float)

    def test_valor_invalido_retorna_fallback(self, monkeypatch):
        monkeypatch.delenv("CCL_FALLBACK_OVERRIDE", raising=False)
        with patch("core.db_manager.get_config", return_value="no_es_numero"):
            result = db.leer_ccl()
        assert isinstance(result, float)
        assert result > 0

    def test_no_lanza_con_bd_fallida(self):
        with patch("core.db_manager.get_config", side_effect=Exception("BD caída")):
            try:
                result = db.leer_ccl()
                assert isinstance(result, float)
                assert result > 0
            except Exception as e:
                pytest.fail(f"leer_ccl lanzó con BD caída: {e}")


class TestPublicarObjetivoCompletadoMocked:
    def test_llama_set_config_con_clave_compuesta(self):
        with patch("core.db_manager.set_config") as mock_set:
            db.publicar_objetivo_completado(5, "AAPL", 500_000.0)
        mock_set.assert_called_once()
        clave = mock_set.call_args[0][0]
        assert "5" in clave and "AAPL" in clave

    def test_valor_incluye_monto_y_fecha(self):
        with patch("core.db_manager.set_config") as mock_set:
            db.publicar_objetivo_completado(3, "MSFT", 250_000.0)
        valor = mock_set.call_args[0][1]
        assert "250000" in valor
        assert str(datetime.date.today().year) in valor

    def test_no_lanza_con_bd_fallida(self):
        with patch("core.db_manager.set_config", side_effect=Exception("BD caída")):
            try:
                db.publicar_objetivo_completado(1, "KO", 100_000.0)
            except Exception as e:
                pytest.fail(f"publicar_objetivo_completado lanzó: {e}")
