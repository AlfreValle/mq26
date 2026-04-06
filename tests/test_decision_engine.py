"""
tests/test_decision_engine.py — Tests de decision_engine.py (Sprint 11)
Funciones 100% puras — sin yfinance ni red.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── calcular_costos_operacion ────────────────────────────────────

class TestCalcularCostosOperacion:
    def test_importa_sin_error(self):
        from services.decision_engine import calcular_costos_operacion
        assert callable(calcular_costos_operacion)

    def test_retorna_claves_requeridas(self):
        from services.decision_engine import calcular_costos_operacion
        r = calcular_costos_operacion("AAPL", "COMPRA", 10, 15_000.0)
        for k in ("ticker", "tipo_op", "nominales", "precio_ars",
                  "valor_nocional", "costo_total", "comision", "derechos", "spread"):
            assert k in r

    def test_valor_nocional_correcto(self):
        from services.decision_engine import calcular_costos_operacion
        r = calcular_costos_operacion("AAPL", "COMPRA", 10, 15_000.0)
        assert r["valor_nocional"] == pytest.approx(150_000.0)

    def test_costo_total_es_suma_componentes(self):
        from services.decision_engine import calcular_costos_operacion
        r = calcular_costos_operacion("AAPL", "COMPRA", 10, 15_000.0)
        assert abs(r["costo_total"] - (r["comision"] + r["derechos"] + r["spread"])) < 0.01

    def test_costo_total_proporcional_a_nominales(self):
        from services.decision_engine import calcular_costos_operacion
        r1 = calcular_costos_operacion("AAPL", "COMPRA", 10, 10_000.0)
        r2 = calcular_costos_operacion("AAPL", "COMPRA", 20, 10_000.0)
        assert r2["costo_total"] == pytest.approx(r1["costo_total"] * 2, rel=0.01)

    def test_costo_positivo_siempre(self):
        from services.decision_engine import calcular_costos_operacion
        for tipo in ("COMPRA", "VENTA"):
            r = calcular_costos_operacion("KO", tipo, 100, 5_000.0)
            assert r["costo_total"] > 0

    def test_comision_correcta(self):
        from services.decision_engine import calcular_costos_operacion
        r = calcular_costos_operacion("AAPL", "COMPRA", 10, 10_000.0, comision_pct=0.01)
        assert r["comision"] == pytest.approx(1_000.0)   # 10 * 10k * 0.01

    def test_costo_total_proporcional_a_precio(self):
        from services.decision_engine import calcular_costos_operacion

        r1 = calcular_costos_operacion("AAPL", "COMPRA", 10, 10_000.0)
        r2 = calcular_costos_operacion("AAPL", "COMPRA", 10, 20_000.0)
        assert r2["costo_total"] == pytest.approx(r1["costo_total"] * 2, rel=0.01)


# ─── filtrar_por_alpha_neto ───────────────────────────────────────

class TestFiltrarPorAlphaNeto:
    def test_importa_sin_error(self):
        from services.decision_engine import filtrar_por_alpha_neto
        assert callable(filtrar_por_alpha_neto)

    def test_lista_vacia_retorna_dfs_vacios(self):
        from services.decision_engine import filtrar_por_alpha_neto
        ej, bl = filtrar_por_alpha_neto([], {})
        assert isinstance(ej, pd.DataFrame)
        assert isinstance(bl, pd.DataFrame)
        assert ej.empty
        assert bl.empty

    def test_toda_orden_aparece_en_uno_de_los_dos(self):
        from services.decision_engine import filtrar_por_alpha_neto
        ordenes = [
            {"ticker": "AAPL", "tipo_op": "COMPRA", "nominales": 10,
             "precio_ars": 15_000.0, "peso_actual": 0.1, "peso_optimo": 0.15},
            {"ticker": "MSFT", "tipo_op": "COMPRA", "nominales": 5,
             "precio_ars": 20_000.0, "peso_actual": 0.1, "peso_optimo": 0.15},
        ]
        retornos = {"AAPL": 0.001, "MSFT": 0.0001}
        ej, bl = filtrar_por_alpha_neto(ordenes, retornos)
        total_ej = len(ej) if not ej.empty else 0
        total_bl = len(bl) if not bl.empty else 0
        assert total_ej + total_bl == len(ordenes)

    def test_ejecutables_tienen_alpha_neto_positivo(self):
        from services.decision_engine import filtrar_por_alpha_neto
        ordenes = [
            {"ticker": "AAPL", "tipo_op": "COMPRA", "nominales": 100,
             "precio_ars": 15_000.0, "peso_actual": 0.05, "peso_optimo": 0.25},
        ]
        # Retorno diario alto → alpha esperado supera costos
        retornos = {"AAPL": 0.002}
        ej, _ = filtrar_por_alpha_neto(ordenes, retornos)
        if not ej.empty:
            assert (ej["alpha_neto"] > 0).all()

    def test_bloqueadas_tienen_alpha_neto_no_positivo(self):
        from services.decision_engine import filtrar_por_alpha_neto
        ordenes = [
            {"ticker": "KO", "tipo_op": "COMPRA", "nominales": 1,
             "precio_ars": 5_000.0, "peso_actual": 0.05, "peso_optimo": 0.06},
        ]
        # Retorno casi cero → costos superan alpha → bloqueado
        retornos = {"KO": 0.00001}
        _, bl = filtrar_por_alpha_neto(ordenes, retornos)
        if not bl.empty:
            assert (bl["alpha_neto"] <= 0).all()

    def test_retorna_dataframes_con_columnas_decision(self):
        from services.decision_engine import filtrar_por_alpha_neto
        ordenes = [
            {"ticker": "AAPL", "tipo_op": "COMPRA", "nominales": 10,
             "precio_ars": 15_000.0},
        ]
        ej, bl = filtrar_por_alpha_neto(ordenes, {"AAPL": 0.001})
        df_completo = (pd.concat([ej, bl])
                       if not ej.empty or not bl.empty
                       else pd.DataFrame())
        if not df_completo.empty:
            assert "decision" in df_completo.columns

    def test_venta_con_sobreweight_puede_quedar_ejecutable(self):
        from services.decision_engine import filtrar_por_alpha_neto

        ordenes = [
            {
                "ticker": "AAPL",
                "tipo_op": "VENTA",
                "nominales": 100,
                "precio_ars": 10_000.0,
                "peso_actual": 0.30,
                "peso_optimo": 0.10,
            }
        ]
        ej, bl = filtrar_por_alpha_neto(ordenes, {"AAPL": 0.0001})
        assert len(ej) + len(bl) == 1


# ─── generar_reporte_decision ─────────────────────────────────────

class TestGenerarReporteDecision:
    def test_importa_sin_error(self):
        from services.decision_engine import generar_reporte_decision
        assert callable(generar_reporte_decision)

    def test_retorna_string(self):
        from services.decision_engine import generar_reporte_decision
        ej = pd.DataFrame({"ticker": ["AAPL"], "tipo_op": ["COMPRA"],
                           "alpha_neto": [5000.0], "valor_nocional": [150_000.0],
                           "costo_total": [1_000.0], "motivo": ["alpha_positivo"]})
        bl = pd.DataFrame({"ticker": ["KO"], "tipo_op": ["COMPRA"],
                           "alpha_neto": [-500.0], "valor_nocional": [10_000.0],
                           "costo_total": [200.0], "motivo": ["alpha_negativo"]})
        r = generar_reporte_decision(ej, bl)
        assert isinstance(r, str)

    def test_retorna_string_con_dfs_vacios(self):
        from services.decision_engine import generar_reporte_decision
        r = generar_reporte_decision(pd.DataFrame(), pd.DataFrame())
        assert isinstance(r, str)

    def test_menciona_capital_desplegado(self):
        from services.decision_engine import filtrar_por_alpha_neto, generar_reporte_decision
        ordenes = [{"ticker": "MSFT", "tipo_op": "COMPRA",
                    "nominales": 10, "precio_ars": 20000}]
        ej, bl = filtrar_por_alpha_neto(ordenes, {"MSFT": 0.003}, horizonte_dias=252)
        r = generar_reporte_decision(ej, bl)
        assert "Capital" in r or "capital" in r
