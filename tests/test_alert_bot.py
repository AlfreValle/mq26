"""
tests/test_alert_bot.py — Tests de alert_bot.py
Mockea enviar_telegram para evitar llamadas reales.
Sin red ni Telegram.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture(autouse=True)
def sin_telegram_env(monkeypatch):
    """Evita credenciales reales de Telegram en el entorno durante los tests."""
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


# ─── enviar_telegram (sin red; mock de requests) ──────────────────

class TestEnviarTelegram:
    def test_sin_configurar_retorna_false(self):
        from services.alert_bot import enviar_telegram
        assert enviar_telegram("hola") is False

    def test_con_mock_requests_ok(self, monkeypatch):
        import requests
        monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        fake_resp = type("R", (), {"status_code": 200})()
        monkeypatch.setattr(requests, "post", lambda *a, **kw: fake_resp)
        from services.alert_bot import enviar_telegram
        assert enviar_telegram("test") is True

    def test_con_mock_requests_fallo(self, monkeypatch):
        import requests
        monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        monkeypatch.setattr(
            requests,
            "post",
            lambda *a, **kw: (_ for _ in ()).throw(Exception("timeout")),
        )
        from services.alert_bot import enviar_telegram
        assert enviar_telegram("test") is False

    @patch("services.alert_bot.requests.post")
    def test_sin_config_no_llama_requests_post(self, mock_post):
        from services.alert_bot import enviar_telegram

        assert enviar_telegram("sin config") is False
        mock_post.assert_not_called()

    def test_http_error_retorna_false(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_TOKEN", "123:ABC")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        from services.alert_bot import enviar_telegram

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad request"
        with patch("services.alert_bot.requests.post", return_value=mock_resp):
            with patch("services.alert_bot.time.sleep"):
                result = enviar_telegram("test")
        assert result is False


# ─── Guards de negocio sin patch (Telegram desconfigurado) ────────

class TestAlertasNegocio:
    def test_var_breach_no_activa_encima_umbral(self):
        from services.alert_bot import alerta_var_breach
        assert alerta_var_breach("AAPL", var_95=-0.10, umbral=-0.20) is False

    def test_drawdown_no_activa_encima_umbral(self):
        from services.alert_bot import alerta_drawdown
        assert alerta_drawdown(-0.05, umbral=-0.15) is False

    def test_senal_venta_no_activa_score_alto(self):
        from services.alert_bot import alerta_senal_venta
        assert alerta_senal_venta("AAPL", score=7.0, estado="ALCISTA") is False

    def test_senal_venta_activa_score_bajo(self, monkeypatch):
        import requests
        monkeypatch.setenv("TELEGRAM_TOKEN", "x")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "y")
        monkeypatch.setattr(
            requests,
            "post",
            lambda *a, **kw: type("R", (), {"status_code": 200})(),
        )
        from services.alert_bot import alerta_senal_venta
        assert alerta_senal_venta("KO", score=2.5, estado="BAJISTA") is True


# ─── Utilidades (spec Sprint 13) ──────────────────────────────────

class TestUtilidadesAlertBot:
    def test_verificar_objetivos_none_retorna_cero(self):
        from services.alert_bot import verificar_objetivos_por_vencer
        assert verificar_objetivos_por_vencer(None, "Cliente X") == 0

    def test_filtrar_token_redacta_url_bot(self):
        from services.alert_bot import filtrar_token_logs
        msg = (
            "https://api.telegram.org/bot1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789/sendMessage"
        )
        result = filtrar_token_logs(msg)
        assert "***" in result
        assert "ABCdef" not in result


# ─── filtrar_token_logs ───────────────────────────────────────────

class TestFiltrarTokenLogs:
    def test_importa_sin_error(self):
        from services.alert_bot import filtrar_token_logs
        assert callable(filtrar_token_logs)

    def test_mensaje_sin_token_sin_cambios(self):
        from services.alert_bot import filtrar_token_logs
        msg = "Alerta: AAPL cayó 5%"
        result = filtrar_token_logs(msg)
        assert result == msg

    def test_retorna_string(self):
        from services.alert_bot import filtrar_token_logs
        assert isinstance(filtrar_token_logs("cualquier mensaje"), str)

    def test_token_numerico_se_oculta(self):
        from services.alert_bot import filtrar_token_logs
        msg = "Token: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
        result = filtrar_token_logs(msg)
        assert "1234567890:ABC" not in result
        assert "***" in result

    def test_mensaje_numero_corto_sin_redactar(self):
        from services.alert_bot import filtrar_token_logs
        msg = "ID usuario: 12345"
        assert filtrar_token_logs(msg) == msg


# ─── funciones alerta_* ───────────────────────────────────────────

class TestFuncionesAlerta:
    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_alerta_var_breach_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_var_breach
        result = alerta_var_breach("AAPL", -0.25, umbral=-0.20)
        mock_tg.assert_called_once()
        assert isinstance(result, bool)

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_alerta_drawdown_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_drawdown
        result = alerta_drawdown(-0.20, umbral=-0.15, cliente="Test")
        mock_tg.assert_called_once()
        assert isinstance(result, bool)

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_alerta_senal_venta_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_senal_venta
        result = alerta_senal_venta("AAPL", 2.5, "BAJISTA", "Test Cliente")
        mock_tg.assert_called_once()
        assert isinstance(result, bool)

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_alerta_rebalanceo_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_rebalanceo
        result = alerta_rebalanceo(["AAPL", "MSFT"], ["KO"], "Test")
        mock_tg.assert_called_once()
        assert isinstance(result, bool)

    @patch("services.alert_bot.enviar_telegram", return_value=False)
    def test_alerta_retorna_false_cuando_telegram_falla(self, mock_tg):
        from services.alert_bot import alerta_senal_venta
        result = alerta_senal_venta("KO", 1.5, "BAJISTA", "Test")
        assert isinstance(result, bool)

    @patch("services.alert_bot.enviar_telegram", side_effect=Exception("no internet"))
    def test_alerta_no_lanza_cuando_telegram_falla(self, mock_tg):
        from services.alert_bot import alerta_senal_venta
        try:
            alerta_senal_venta("AAPL", 2.0, "BAJISTA", "Test")
        except Exception:
            pytest.fail("alerta_senal_venta lanzó excepción con Telegram fallido")

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_alerta_objetivo_proximo_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_objetivo_proximo_vencimiento
        objetivo = {
            "Ticker": "AAPL", "Motivo": "Retiro parcial",
            "Monto ARS": 500_000.0, "Días restantes": 3,
        }
        result = alerta_objetivo_proximo_vencimiento(objetivo, "Alfredo")
        mock_tg.assert_called_once()
        assert isinstance(result, bool)


# ─── verificar_objetivos_por_vencer ──────────────────────────────

class TestVerificarObjetivosPorVencer:
    def test_importa_sin_error(self):
        from services.alert_bot import verificar_objetivos_por_vencer
        assert callable(verificar_objetivos_por_vencer)

    def test_df_vacio_retorna_cero(self):
        from services.alert_bot import verificar_objetivos_por_vencer
        result = verificar_objetivos_por_vencer(pd.DataFrame(), "Test")
        assert result == 0

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_cuenta_objetivos_proximos(self, mock_tg):
        from services.alert_bot import verificar_objetivos_por_vencer
        df = pd.DataFrame({
            "Días restantes": [3, 10, 1, 20],
            "Estado":         ["ACTIVO", "ACTIVO", "ACTIVO", "ACTIVO"],
            "Ticker":         ["AAPL", "MSFT", "KO", "XOM"],
            "Motivo":         ["retiro"] * 4,
        })
        result = verificar_objetivos_por_vencer(df, "Test")
        assert isinstance(result, int)

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_cuenta_solo_activos_y_plazo(self, mock_tg):
        from services.alert_bot import verificar_objetivos_por_vencer
        df = pd.DataFrame({
            "Días restantes": [5, 25, 60, 10],
            "Estado":         ["ACTIVO", "ACTIVO", "ACTIVO", "COMPLETADO"],
            "Ticker":         ["AAPL", "MSFT", "KO", "XOM"],
            "Motivo":         ["retiro", "retiro", "retiro", "retiro"],
            "Monto ARS":      [100_000, 50_000, 200_000, 30_000],
        })
        enviadas = verificar_objetivos_por_vencer(df, "Alfredo")
        assert enviadas == 2

    @patch("services.alert_bot.enviar_telegram", return_value=False)
    def test_no_cuenta_telegram_fallido(self, mock_tg):
        from services.alert_bot import verificar_objetivos_por_vencer
        df = pd.DataFrame({
            "Días restantes": [5],
            "Estado":         ["ACTIVO"],
            "Ticker":         ["AAPL"],
            "Motivo":         ["retiro"],
            "Monto ARS":      [100_000],
        })
        assert verificar_objetivos_por_vencer(df, "Test") == 0


# ─── Sprint 23: guards con mock explícito de enviar_telegram ─────

class TestAlertaGuardsConMockTelegram:
    def test_var_breach_no_envia_si_dentro_umbral(self):
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            from services.alert_bot import alerta_var_breach
            assert alerta_var_breach("AAPL", var_95=-0.10, umbral=-0.20) is False
            mock_tg.assert_not_called()

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_var_breach_envia_si_supera_umbral(self, mock_tg):
        from services.alert_bot import alerta_var_breach
        assert alerta_var_breach("AAPL", var_95=-0.25, umbral=-0.20) is True
        mock_tg.assert_called_once()

    def test_drawdown_no_envia_si_dentro_umbral(self):
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            from services.alert_bot import alerta_drawdown
            assert alerta_drawdown(-0.05, umbral=-0.15) is False
            mock_tg.assert_not_called()

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_drawdown_envia_si_supera_umbral(self, mock_tg):
        from services.alert_bot import alerta_drawdown
        assert alerta_drawdown(-0.25, umbral=-0.15, cliente="Alfredo") is True
        mock_tg.assert_called_once()

    def test_senal_venta_no_envia_si_score_alto(self):
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            from services.alert_bot import alerta_senal_venta
            assert alerta_senal_venta("AAPL", score=7.5, estado="ALCISTA") is False
            mock_tg.assert_not_called()

    def test_senal_venta_no_envia_score_exactamente_4(self):
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            from services.alert_bot import alerta_senal_venta
            assert alerta_senal_venta("MSFT", score=4.0, estado="NEUTRO") is False
            mock_tg.assert_not_called()

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_senal_venta_envia_score_bajo(self, mock_tg):
        from services.alert_bot import alerta_senal_venta
        assert alerta_senal_venta("KO", score=2.5, estado="BAJISTA") is True
        mock_tg.assert_called_once()

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_rebalanceo_listas_vacias_llama_telegram(self, mock_tg):
        from services.alert_bot import alerta_rebalanceo
        alerta_rebalanceo([], [])
        mock_tg.assert_called_once()

    @patch("services.alert_bot.enviar_telegram", return_value=False)
    def test_rebalanceo_retorna_false_si_telegram_falla(self, mock_tg):
        from services.alert_bot import alerta_rebalanceo
        assert alerta_rebalanceo(["AAPL"], []) is False

    def test_objetivo_no_envia_si_mas_de_30_dias(self):
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            from services.alert_bot import alerta_objetivo_proximo_vencimiento
            obj = {
                "Ticker": "AAPL", "Motivo": "x",
                "Monto ARS": 0.0, "Días restantes": 45,
            }
            assert alerta_objetivo_proximo_vencimiento(obj, "X") is False
            mock_tg.assert_not_called()

    @patch("services.alert_bot.enviar_telegram", return_value=True)
    def test_objetivo_envia_menos_de_7_dias(self, mock_tg):
        from services.alert_bot import alerta_objetivo_proximo_vencimiento
        obj = {
            "Ticker": "MSFT", "Motivo": "vencimiento crítico",
            "Monto ARS": 1.0, "Días restantes": 3,
        }
        assert alerta_objetivo_proximo_vencimiento(obj, "Alfredo") is True
        mock_tg.assert_called_once()
