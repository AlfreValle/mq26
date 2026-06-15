"""
tests/test_cache_manager.py — Tests de core/cache_manager.py (Sprint 18)
cache_manager.py importa streamlit en nivel de módulo con @st.cache_data decorators.
limpiar_cache_sesion usa st.session_state → se parchea 'core.cache_manager.st'.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── TTLs configurables ───────────────────────────────────────────────────────

class TestTtlsConfigurables:
    def test_ttl_ccl_es_entero_positivo(self):
        from core import cache_manager as cm
        assert isinstance(cm._TTL_CCL, int) and cm._TTL_CCL > 0

    def test_ttl_historico_es_entero_positivo(self):
        from core import cache_manager as cm
        assert isinstance(cm._TTL_HISTORICO, int) and cm._TTL_HISTORICO > 0

    def test_ttl_precios_es_entero_positivo(self):
        from core import cache_manager as cm
        assert isinstance(cm._TTL_PRECIOS, int) and cm._TTL_PRECIOS > 0

    def test_ttl_metricas_es_entero_positivo(self):
        from core import cache_manager as cm
        assert isinstance(cm._TTL_METRICAS, int) and cm._TTL_METRICAS > 0

    def test_ttl_historico_mayor_o_igual_precios(self):
        from core import cache_manager as cm
        assert cm._TTL_HISTORICO >= cm._TTL_PRECIOS

    def test_ttl_metricas_menor_o_igual_precios(self):
        from core import cache_manager as cm
        assert cm._TTL_METRICAS <= cm._TTL_PRECIOS

    def test_todos_los_ttls_son_enteros_positivos(self):
        from core import cache_manager as cm
        for attr in (
            "_TTL_CCL",
            "_TTL_HISTORICO",
            "_TTL_PRECIOS",
            "_TTL_RATIOS",
            "_TTL_METRICAS",
            "_TTL_DASHBOARD",
        ):
            val = getattr(cm, attr)
            assert isinstance(val, int) and val > 0, f"{attr}={val}"

    def test_ttl_desde_env(self, monkeypatch):
        """TTL_CCL se puede configurar vía variable de entorno."""
        monkeypatch.setenv("CACHE_TTL_CCL", "999")
        from core import cache_manager as cm
        importlib.reload(cm)
        assert cm._TTL_CCL == 999

    def test_ttl_default_cuando_env_no_definida(self, monkeypatch):
        """Sin variable de entorno, TTL_CCL vuelve al default 300."""
        monkeypatch.delenv("CACHE_TTL_CCL", raising=False)
        from core import cache_manager as cm
        importlib.reload(cm)
        assert cm._TTL_CCL == 300

    def test_ttl_metricas_desde_env(self, monkeypatch):
        import core.cache_manager as cm
        monkeypatch.setenv("CACHE_TTL_METRICAS", "999")
        importlib.reload(cm)
        try:
            assert cm._TTL_METRICAS == 999
        finally:
            monkeypatch.delenv("CACHE_TTL_METRICAS", raising=False)
            importlib.reload(cm)
            assert cm._TTL_METRICAS == 60


# ─── limpiar_cache_sesion ─────────────────────────────────────────────────────

class TestLimpiarCacheSesion:
    def test_no_lanza_con_session_state_vacio(self):
        """Si las claves no existen, no debe lanzar excepción."""
        from core import cache_manager as cm
        mock_st = MagicMock()
        mock_st.session_state = {}
        with patch.object(cm, "st", mock_st):
            try:
                cm.limpiar_cache_sesion("Retiro")
            except Exception as e:
                pytest.fail(f"limpiar_cache_sesion lanzó: {e}")

    def test_elimina_claves_de_la_cartera_activa(self):
        """Las tres claves de la cartera se eliminan; las de otras carteras quedan."""
        from core import cache_manager as cm
        mock_st = MagicMock()
        mock_st.session_state = {
            "_df_ag_cache_Retiro": "datos",
            "_df_ag_hash_Retiro":  "hash",
            "_df_ag_fifo_Retiro":  False,
            "_df_ag_cache_Otras":  "otros",
        }
        with patch.object(cm, "st", mock_st):
            cm.limpiar_cache_sesion("Retiro")
        assert "_df_ag_cache_Retiro" not in mock_st.session_state
        assert "_df_ag_hash_Retiro"  not in mock_st.session_state
        assert "_df_ag_fifo_Retiro"  not in mock_st.session_state
        assert "_df_ag_cache_Otras"  in mock_st.session_state

    def test_no_elimina_claves_de_otras_carteras(self):
        """Limpiar 'Retiro' no toca las claves de 'Agresivo'."""
        from core import cache_manager as cm
        mock_st = MagicMock()
        mock_st.session_state = {
            "_df_ag_cache_Retiro":  "datos_retiro",
            "_df_ag_cache_Agresivo": "datos_agresivo",
        }
        with patch.object(cm, "st", mock_st):
            cm.limpiar_cache_sesion("Retiro")
        assert "_df_ag_cache_Agresivo" in mock_st.session_state


# ─── cache_metricas_resumen (lógica interna) ─────────────────────────────────

class TestCacheMetricasResumen:
    def test_metricas_resumen_con_df_valido_retorna_dict(self):
        """La función interna metricas_resumen (que alimenta el cache) retorna dict."""
        import pandas as pd

        import services.cartera_service as cs

        df = pd.DataFrame({
            "VALOR_ARS":      [100_000.0],
            "INV_ARS":        [ 80_000.0],
            "PNL_ARS":        [ 20_000.0],
            "PNL_PCT":        [0.25],
            "PPC_ARS":        [ 8_000.0],
            "CANTIDAD_TOTAL": [10],
        })
        result = cs.metricas_resumen(df)
        assert isinstance(result, dict)
        assert result.get("total_valor", 0) == pytest.approx(100_000.0)

    def test_cache_metricas_resumen_con_json_valido(self):
        """cache_metricas_resumen puede procesar JSON de un DataFrame."""
        import io

        import pandas as pd


        df = pd.DataFrame({
            "VALOR_ARS": [150_000.0, 50_000.0],
            "INV_ARS":   [120_000.0, 40_000.0],
            "PNL_ARS":   [ 30_000.0, 10_000.0],
            "PNL_PCT":   [0.25, 0.25],
            "PPC_ARS":   [12_000.0, 4_000.0],
            "CANTIDAD_TOTAL": [10, 20],
        })
        df_json = df.to_json()

        # Llamar directamente a la función (sin cache de Streamlit)
        import services.cartera_service as cs
        df_parsed = pd.read_json(io.StringIO(df_json))
        result = cs.metricas_resumen(df_parsed)
        assert isinstance(result, dict)
        assert result.get("n_posiciones") == 2
