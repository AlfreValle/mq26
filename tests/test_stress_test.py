"""
tests/test_stress_test.py — Tests del StressTestEngine (Sprint 3)
Sin llamadas a yfinance ni red. Usa DataFrames sintéticos.
Invariantes clave:
  - delta_spy=0, delta_ccl=0 → valor_stress ≈ valor_original
  - peso_cedear=0 (100% local) → shock SPY no modifica el valor
  - deval_ars_23: CCL +80% → CEDEARs suben en ARS
"""
from __future__ import annotations

import pandas as pd
import pytest

from services.stress_test import SCENARIOS, StressTestEngine


@pytest.fixture
def ste():
    return StressTestEngine()


@pytest.fixture
def df_cedears():
    """Cartera 100% CEDEARs — VALOR_ARS = PRECIO_ARS * CANTIDAD (coherente)."""
    df = pd.DataFrame({
        "TICKER":    ["AAPL", "MSFT", "KO"],
        "PRECIO_ARS": [15_000.0, 12_000.0, 22_000.0],
        "CANTIDAD":   [6.0,       6.0,       2.0],
        "ES_LOCAL":   [False,     False,     False],
    })
    df["VALOR_ARS"] = df["PRECIO_ARS"] * df["CANTIDAD"]  # 90k, 72k, 44k = 206k total
    return df


@pytest.fixture
def df_locales():
    """Cartera 100% acciones locales ARS — VALOR_ARS = PRECIO_ARS * CANTIDAD (coherente)."""
    df = pd.DataFrame({
        "TICKER":    ["YPFD", "GGAL"],
        "PRECIO_ARS": [4_800.0, 3_200.0],
        "CANTIDAD":   [16.0,    21.0],
        "ES_LOCAL":   [True,    True],
    })
    df["VALOR_ARS"] = df["PRECIO_ARS"] * df["CANTIDAD"]  # 76.8k + 67.2k = 144k total
    return df


# ─── escenario_custom ─────────────────────────────────────────────────────────

class TestEscenarioCustom:
    def test_sin_shock_valor_invariante(self, ste, df_cedears):
        """delta_spy=0, delta_ccl=0 → valor_stress ≈ valor_original."""
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, 0.0, 0.0)
        rel = abs(r["valor_stress"] - r["valor_original"]) / r["valor_original"]
        assert rel < 0.01

    def test_deval_ccl_sube_valor_cedears(self, ste, df_cedears):
        """CCL +80% → CEDEARs valen más en ARS."""
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, 0.0, 0.80)
        assert r["valor_stress"] > r["valor_original"]

    def test_crash_spy_reduce_valor_cedears(self, ste, df_cedears):
        """SPY -55% → cartera CEDEAR pierde valor."""
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, -0.55, 0.0)
        assert r["valor_stress"] < r["valor_original"]

    def test_locales_inmunes_a_spy(self, ste, df_locales):
        """Cartera 100% local: SPY shock no cambia el valor (peso_cedear=0)."""
        r = ste.escenario_custom(df_locales.copy(), 1465.0, -0.55, 0.0)
        rel = abs(r["valor_stress"] - r["valor_original"]) / r["valor_original"]
        assert rel < 0.01, f"Locales no deberían verse afectados por SPY. Rel: {rel:.4f}"

    def test_no_muta_df_original(self, ste, df_cedears):
        """escenario_custom no modifica el DataFrame de entrada."""
        df = df_cedears.copy()
        vals_antes = df["VALOR_ARS"].tolist()
        ste.escenario_custom(df, 1465.0, -0.30, 0.20)
        assert df["VALOR_ARS"].tolist() == vals_antes

    def test_pct_perdida_positivo_cuando_baja(self, ste, df_cedears):
        """Si el valor baja, pct_perdida es positivo."""
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, -0.50, 0.0)
        assert r["pct_perdida"] >= 0

    def test_pct_perdida_cero_cuando_sube(self, ste, df_cedears):
        """Si el valor sube, pct_perdida es 0."""
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, 0.0, 0.80)
        assert r["pct_perdida"] == pytest.approx(0.0)

    def test_retorna_claves_requeridas(self, ste, df_cedears):
        r = ste.escenario_custom(df_cedears.copy(), 1465.0, 0.0, 0.0)
        for k in ("valor_original", "valor_stress", "pct_cambio", "pct_perdida"):
            assert k in r

    def test_df_vacio_retorna_zeros(self, ste):
        r = ste.escenario_custom(pd.DataFrame(), 1465.0, -0.30, 0.0)
        assert r["valor_original"] == pytest.approx(0.0)
        assert r["valor_stress"] == pytest.approx(0.0)


# ─── todos_los_escenarios ─────────────────────────────────────────────────────

class TestTodosLosEscenarios:
    def test_devuelve_dataframe_con_todos_escenarios(self, ste, df_cedears):
        df = ste.todos_los_escenarios(df_cedears.copy(), 1465.0)
        assert len(df) == len(SCENARIOS)

    def test_columnas_requeridas(self, ste, df_cedears):
        df = ste.todos_los_escenarios(df_cedears.copy(), 1465.0)
        for col in ("escenario", "valor_original", "valor_stress", "pct_perdida"):
            assert col in df.columns

    def test_deval_ars_23_sube_valor_cedears(self, ste, df_cedears):
        """Devaluación ARG 2023: CCL +80% → CEDEARs suben en ARS."""
        df = ste.todos_los_escenarios(df_cedears.copy(), 1465.0)
        row = df[df["escenario"] == "deval_ars_23"].iloc[0]
        assert row["valor_stress"] > row["valor_original"]

    def test_crisis_2008_reduce_valor_cedears(self, ste, df_cedears):
        """Crisis 2008: SPY -55% → cartera CEDEAR pierde valor."""
        df = ste.todos_los_escenarios(df_cedears.copy(), 1465.0)
        row = df[df["escenario"] == "crisis_2008"].iloc[0]
        assert row["valor_stress"] < row["valor_original"]

    def test_df_vacio_retorna_dataframe_vacio(self, ste):
        df = ste.todos_los_escenarios(pd.DataFrame(), 1465.0)
        assert df.empty

    def test_escenarios_son_los_esperados(self, ste, df_cedears):
        df = ste.todos_los_escenarios(df_cedears.copy(), 1465.0)
        nombres = set(df["escenario"].tolist())
        assert nombres == set(SCENARIOS.keys())


# ─── aplicar_escenario ────────────────────────────────────────────────────────

class TestAplicarEscenario:
    def test_escenario_invalido_retorna_zeros(self, ste, df_cedears):
        r = ste.aplicar_escenario(df_cedears.copy(), 1465.0, "escenario_que_no_existe")
        assert r["valor_original"] == pytest.approx(0.0)

    def test_crisis_2008_existe_en_scenarios(self, ste, df_cedears):
        r = ste.aplicar_escenario(df_cedears.copy(), 1465.0, "crisis_2008")
        assert r["valor_original"] > 0

    def test_escenario_devaluacion_2018_retorno_negativo_cedears(self, ste, df_cedears):
        r = ste.aplicar_escenario(df_cedears.copy(), 1465.0, "devaluacion_2018")
        assert r["pct_cambio"] < -10.0

    def test_escenario_pandemia_2020_retorno_negativo_cedears(self, ste, df_cedears):
        r = ste.aplicar_escenario(df_cedears.copy(), 1465.0, "pandemia_2020")
        assert r["pct_cambio"] < -10.0
