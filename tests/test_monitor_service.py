"""
tests/test_monitor_service.py — Tests de monitor_service.py (Sprint 9)
Sin red, sin Telegram real, sin yfinance. Mocks para todo externo.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def df_pos_ok():
    return pd.DataFrame({
        "TICKER":    ["AAPL", "MSFT"],
        "VALOR_ARS": [100_000.0, 80_000.0],
        "PESO_PCT":  [20.0, 15.0],
        "PNL_PCT":   [0.10, 0.05],
    })


@pytest.fixture
def df_pos_concentrado():
    return pd.DataFrame({
        "TICKER":    ["AAPL"],
        "VALOR_ARS": [500_000.0],
        "PESO_PCT":  [85.0],
        "PNL_PCT":   [0.05],
    })


@pytest.fixture
def df_analisis_vacio():
    return pd.DataFrame()


# ─── revisar_cartera_completa ──────────────────────────────────────────────────

class TestRevisarCarteraCompleta:
    def test_importa_sin_error(self):
        from services.monitor_service import revisar_cartera_completa
        assert callable(revisar_cartera_completa)

    def test_df_vacio_retorna_todo_cero(self, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        result = revisar_cartera_completa(
            pd.DataFrame(), df_analisis_vacio,
            {}, None, "Test", enviar_telegram=False
        )
        assert result["total"] == 0
        for k in ("mod23", "concentracion", "drawdown", "vencimientos"):
            assert result[k] == 0

    def test_concentracion_alta_se_detecta(self, df_pos_concentrado, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        with patch("services.alert_bot.enviar_telegram", return_value=True):
            result = revisar_cartera_completa(
                df_pos_concentrado, df_analisis_vacio,
                {}, None, "Test", enviar_telegram=True
            )
        assert result["concentracion"] >= 1

    def test_concentracion_normal_no_dispara(self, df_pos_ok, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        result = revisar_cartera_completa(
            df_pos_ok, df_analisis_vacio,
            {}, None, "Test", enviar_telegram=False
        )
        assert result["concentracion"] == 0

    def test_no_lanza_con_telegram_fallando(self, df_pos_concentrado, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        with patch("services.alert_bot.enviar_telegram", side_effect=Exception("no internet")):
            result = revisar_cartera_completa(
                df_pos_concentrado, df_analisis_vacio,
                {}, None, "Test", enviar_telegram=True
            )
        assert isinstance(result, dict)

    def test_retorna_claves_requeridas(self, df_pos_ok, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        result = revisar_cartera_completa(
            df_pos_ok, df_analisis_vacio,
            {}, None, "Test", enviar_telegram=False
        )
        for k in ("mod23", "concentracion", "drawdown", "vencimientos", "total"):
            assert k in result

    def test_total_es_suma_de_categorias(self, df_pos_ok, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        result = revisar_cartera_completa(
            df_pos_ok, df_analisis_vacio,
            {}, None, "Test", enviar_telegram=False
        )
        esperado = result["mod23"] + result["concentracion"] + \
                   result["drawdown"] + result["vencimientos"]
        assert result["total"] == esperado

    def test_drawdown_alto_se_detecta(self, df_pos_ok, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        with patch("services.alert_bot.alerta_drawdown", return_value=True):
            result = revisar_cartera_completa(
                df_pos_ok, df_analisis_vacio,
                {"pnl_pct": -0.25},
                None, "Test", enviar_telegram=True
            )
        assert result["drawdown"] >= 1

    def test_drawdown_normal_no_dispara(self, df_pos_ok, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        result = revisar_cartera_completa(
            df_pos_ok, df_analisis_vacio,
            {"pnl_pct": 0.10},
            None, "Test", enviar_telegram=False
        )
        assert result["drawdown"] == 0

    def test_sin_telegram_no_llama_alert_bot(self, df_pos_concentrado, df_analisis_vacio):
        from services.monitor_service import revisar_cartera_completa
        with patch("services.alert_bot.enviar_telegram") as mock_tg:
            revisar_cartera_completa(
                df_pos_concentrado, df_analisis_vacio,
                {}, None, "Test", enviar_telegram=False
            )
            mock_tg.assert_not_called()


# ─── contar_vencimientos_proximos ─────────────────────────────────────────────

class TestContarVencimientosProximos:
    def test_cliente_none_retorna_cero(self):
        from services.monitor_service import contar_vencimientos_proximos
        assert contar_vencimientos_proximos(None) == 0

    def test_retorna_entero(self):
        from services.monitor_service import contar_vencimientos_proximos
        result = contar_vencimientos_proximos(None, dias=7)
        assert isinstance(result, int)
        assert result >= 0

    def test_no_lanza_con_bd_no_disponible(self):
        from services.monitor_service import contar_vencimientos_proximos
        with patch("core.db_manager.obtener_objetivos_cliente",
                   side_effect=Exception("BD no disponible")):
            result = contar_vencimientos_proximos(1, dias=7)
        assert result == 0

    def test_df_vacio_retorna_cero(self):
        from services.monitor_service import contar_vencimientos_proximos
        with patch("core.db_manager.obtener_objetivos_cliente",
                   return_value=pd.DataFrame()):
            result = contar_vencimientos_proximos(1, dias=7)
        assert result == 0

    def test_cuenta_vencimientos_correctamente(self):
        from services.monitor_service import contar_vencimientos_proximos
        df_mock = pd.DataFrame({
            "Días restantes": [3, 10, 1, 0],
            "Estado":         ["ACTIVO", "ACTIVO", "ACTIVO", "VENCIDO"],
        })
        with patch("core.db_manager.obtener_objetivos_cliente",
                   return_value=df_mock):
            result = contar_vencimientos_proximos(1, dias=7)
        # Dias <= 7 y ACTIVO: 3 (ok), 1 (ok), 0 es VENCIDO → 2
        assert result == 2


# ─── enviar_reporte_mensual_email ─────────────────────────────────────────────

class TestEnviarReporteMensualEmail:
    def test_importa_sin_error(self):
        from services.monitor_service import enviar_reporte_mensual_email
        assert callable(enviar_reporte_mensual_email)

    def test_retorna_true_con_mocks(self):
        from services.monitor_service import enviar_reporte_mensual_email
        with patch("services.reporte_mensual.generar_reporte_mensual_html",
                   return_value="<html>test</html>"):
            with patch("services.email_sender.enviar_email_gmail", return_value=True):
                result = enviar_reporte_mensual_email(
                    "Test Cliente", pd.DataFrame(),
                    {}, 1465.0, pd.DataFrame(), "test@example.com"
                )
        assert result is True

    def test_retorna_false_cuando_falla(self):
        from services.monitor_service import enviar_reporte_mensual_email
        with patch("services.reporte_mensual.generar_reporte_mensual_html",
                   side_effect=Exception("error de generacion")):
            result = enviar_reporte_mensual_email(
                "X", pd.DataFrame(), {}, 1465.0, pd.DataFrame(), "a@b.com"
            )
        assert result is False

    def test_retorna_bool_siempre(self):
        from services.monitor_service import enviar_reporte_mensual_email
        with patch("services.reporte_mensual.generar_reporte_mensual_html",
                   return_value="<html/>"):
            with patch("services.email_sender.enviar_email_gmail", return_value=False):
                result = enviar_reporte_mensual_email(
                    "X", pd.DataFrame(), {}, 1465.0, pd.DataFrame(), "x@y.com"
                )
        assert isinstance(result, bool)


# ─── FlowManager paso 5 con vencimientos ──────────────────────────────────────

class TestFlowManagerPaso5Vencimientos:
    def test_paso5_pendiente_sin_vencimientos(self):
        from core.flow_manager import FlowManager, StepState
        fm = FlowManager()
        assert fm.get_step_state(5, {
            "ultimo_reporte_generado": False,
            "n_vencimientos_proximos": 0,
        }) == StepState.PENDIENTE

    def test_paso5_alerta_con_vencimientos(self):
        from core.flow_manager import FlowManager, StepState
        fm = FlowManager()
        assert fm.get_step_state(5, {
            "ultimo_reporte_generado": False,
            "n_vencimientos_proximos": 2,
        }) == StepState.ALERTA

    def test_paso5_completo_con_reporte(self):
        from core.flow_manager import FlowManager, StepState
        fm = FlowManager()
        assert fm.get_step_state(5, {
            "ultimo_reporte_generado": True,
            "n_vencimientos_proximos": 0,
        }) == StepState.COMPLETO

    def test_paso5_completo_aunque_haya_vencimientos(self):
        """Si el reporte ya fue generado, es COMPLETO sin importar vencimientos."""
        from core.flow_manager import FlowManager, StepState
        fm = FlowManager()
        assert fm.get_step_state(5, {
            "ultimo_reporte_generado": True,
            "n_vencimientos_proximos": 5,
        }) == StepState.COMPLETO

    def test_paso5_sin_clave_vencimientos_compatible(self):
        """Sin n_vencimientos_proximos, comportamiento anterior se preserva."""
        from core.flow_manager import FlowManager, StepState
        fm = FlowManager()
        assert fm.get_step_state(5, {
            "ultimo_reporte_generado": False,
        }) == StepState.PENDIENTE

    def test_resumen_paso5_alerta_con_vencimiento(self):
        from core.flow_manager import FlowManager
        fm = FlowManager()
        r = fm.resumen({
            "price_coverage_pct":    100.0,
            "ultimo_reporte_generado": False,
            "n_vencimientos_proximos": 1,
        })
        assert r[5]["state"] == "alerta"
