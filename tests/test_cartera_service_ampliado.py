"""
tests/test_cartera_service_ampliado.py — Tests ampliados de cartera_service (Sprint 17)
Cubre: calcular_progreso_objetivo, metricas_resumen, calcular_rendimiento_global_anual.
Funciones 100% puras — sin yfinance ni red.
"""
from __future__ import annotations

import pandas as pd
import pytest

# ─── calcular_progreso_objetivo ───────────────────────────────────────────────

class TestCalcularProgresoObjetivo:
    def test_importa_sin_error(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert callable(calcular_progreso_objetivo)

    def test_progreso_cero_en_ppc(self):
        """Precio igual al PPC → progreso = 0%."""
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 100.0, 35.0)
        assert result == pytest.approx(0.0)

    def test_progreso_cien_en_target(self):
        """Precio = PPC * (1 + target%) → progreso = 100%."""
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 135.0, 35.0)
        assert result == pytest.approx(100.0, abs=0.1)

    def test_progreso_mayor_a_100_cuando_supera_target(self):
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 200.0, 35.0)
        assert result > 100.0

    def test_progreso_negativo_en_perdida(self):
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 80.0, 35.0)
        assert result < 0.0

    def test_clipeado_a_200_maximo(self):
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 1000.0, 35.0)
        assert result <= 200.0

    def test_clipeado_a_menos_100_minimo(self):
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 1.0, 35.0)
        assert result >= -100.0

    def test_ppc_cero_retorna_cero(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(0.0, 150.0, 35.0) == 0.0

    def test_precio_actual_cero_retorna_cero(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(100.0, 0.0, 35.0) == 0.0

    def test_target_cero_retorna_cero(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(100.0, 120.0, 0.0) == 0.0

    def test_valores_negativos_retornan_cero(self):
        from services.cartera_service import calcular_progreso_objetivo
        assert calcular_progreso_objetivo(-50.0, 100.0, 35.0) == 0.0
        assert calcular_progreso_objetivo(100.0, -50.0, 35.0) == 0.0

    def test_proporcionalidad(self):
        """A mitad de camino al target → progreso ≈ 50%."""
        from services.cartera_service import calcular_progreso_objetivo
        result = calcular_progreso_objetivo(100.0, 117.5, 35.0)
        assert result == pytest.approx(50.0, abs=1.0)


# ─── metricas_resumen ─────────────────────────────────────────────────────────

class TestMetricasResumen:
    @pytest.fixture
    def df_pos_completo(self):
        return pd.DataFrame({
            "TICKER":         ["AAPL", "MSFT", "KO"],
            "VALOR_ARS":      [150_000.0, 100_000.0, 50_000.0],
            "INV_ARS":        [120_000.0,  90_000.0, 48_000.0],
            "PNL_ARS":        [ 30_000.0,  10_000.0,  2_000.0],
            "PNL_PCT":        [0.25, 0.111, 0.042],
            "PPC_ARS":        [12_000.0, 18_000.0, 2_400.0],
            "CANTIDAD_TOTAL": [10, 5, 20],
        })

    def test_retorna_dict(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        assert isinstance(result, dict)

    def test_claves_requeridas(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        for k in ("total_valor", "total_inversion", "total_pnl",
                  "pnl_pct_total", "n_posiciones"):
            assert k in result, f"Clave faltante: {k}"

    def test_total_valor_correcto(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        assert result["total_valor"] == pytest.approx(300_000.0)

    def test_total_inversion_correcto(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        assert result["total_inversion"] == pytest.approx(258_000.0)

    def test_total_pnl_correcto(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        assert result["total_pnl"] == pytest.approx(42_000.0)

    def test_pnl_pct_total_correcto(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        esperado = 42_000.0 / 258_000.0
        assert result["pnl_pct_total"] == pytest.approx(esperado, rel=0.01)

    def test_n_posiciones_correcto(self, df_pos_completo):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(df_pos_completo)
        assert result["n_posiciones"] == 3

    def test_df_vacio_retorna_ceros(self):
        from services.cartera_service import metricas_resumen
        result = metricas_resumen(pd.DataFrame())
        assert result["total_valor"] == 0.0
        assert result["total_pnl"] == 0.0
        assert result["n_posiciones"] == 0

    def test_pnl_negativo_posible(self):
        from services.cartera_service import metricas_resumen
        df = pd.DataFrame({
            "VALOR_ARS":      [80_000.0],
            "INV_ARS":        [100_000.0],
            "PNL_ARS":        [-20_000.0],
            "PNL_PCT":        [-0.20],
            "PPC_ARS":        [10_000.0],
            "CANTIDAD_TOTAL": [10],
        })
        result = metricas_resumen(df)
        assert result["total_pnl"] < 0
        assert result["pnl_pct_total"] < 0


# ─── calcular_rendimiento_global_anual ────────────────────────────────────────

class TestCalcularRendimientoGlobalAnual:
    @pytest.fixture
    def df_rend(self):
        """
        Fixture con todas las columnas que consume calcular_rendimiento_global_anual:
        Inv. ARS, P&L ARS, P&L USD aprox, Días en cartera, Rend. ARS %, Tipo.
        """
        return pd.DataFrame({
            "Tipo":             ["CEDEAR", "Acción Local"],
            "Inv. ARS":         [200_000.0, 50_000.0],
            "Valor ARS":        [250_000.0, 55_000.0],
            "P&L ARS":          [50_000.0, 5_000.0],
            "P&L USD aprox":    [3_000.0, 400.0],
            "Días en cartera":  [365, 180],
            "Rend. ARS %":      [25.0, 10.0],
            "N posiciones":     [5, 2],
        })

    def test_importa_sin_error(self):
        from services.cartera_service import calcular_rendimiento_global_anual
        assert callable(calcular_rendimiento_global_anual)

    def test_retorna_dict(self, df_rend):
        from services.cartera_service import calcular_rendimiento_global_anual
        result = calcular_rendimiento_global_anual(df_rend, pd.DataFrame())
        assert isinstance(result, dict)

    def test_tiene_cagr_global(self, df_rend):
        from services.cartera_service import calcular_rendimiento_global_anual
        result = calcular_rendimiento_global_anual(df_rend, pd.DataFrame())
        assert "cagr_global_ars" in result or any("cagr" in k.lower() for k in result)

    def test_df_vacio_no_lanza(self):
        from services.cartera_service import calcular_rendimiento_global_anual
        result = calcular_rendimiento_global_anual(pd.DataFrame(), pd.DataFrame())
        assert isinstance(result, dict)
