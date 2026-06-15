"""
tests/test_attribution_engine.py — Tests del AttributionEngine (Sprint 3)
Invariante central: allocation_sum + selection_sum + interaction_sum == active_total (tol 1e-6)
Sin llamadas a yfinance ni red.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from services.attribution_engine import AttributionEngine


@pytest.fixture
def engine():
    return AttributionEngine()


@pytest.fixture
def df_pos_ejemplo():
    """DataFrame con columnas que produce calcular_posicion_neta()."""
    return pd.DataFrame({
        "TICKER":    ["AAPL", "MSFT", "KO"],
        "VALOR_ARS": [150_000.0, 100_000.0, 50_000.0],
        "INV_ARS":   [120_000.0,  90_000.0, 48_000.0],
        "PNL_PCT":   [0.25,       0.111,    0.042],
        "PESO_PCT":  [50.0,       33.33,    16.67],
        "ES_LOCAL":  [False,      False,    False],
    })


# ─── BHB ──────────────────────────────────────────────────────────────────────

class TestBHB:
    def test_invariante_alloc_sel_inter_igual_active(self, engine):
        """Invariante central: allocation+selection+interaction == active_total."""
        wp = pd.Series({"A": 0.6, "B": 0.4})
        wb = pd.Series({"A": 0.5, "B": 0.5})
        rp = pd.Series({"A": 0.12, "B": 0.08})
        rb = pd.Series({"A": 0.10, "B": 0.06})
        r = engine.bhb(wp, wb, rp, rb)
        total = r["allocation_sum"] + r["selection_sum"] + r["interaction_sum"]
        assert abs(total - r["active_total"]) < 1e-6

    def test_active_cero_cuando_portfolio_igual_benchmark(self, engine):
        """Si wp==wb y rp==rb → active_total == 0."""
        s = pd.Series({"A": 0.5, "B": 0.5})
        r = pd.Series({"A": 0.10, "B": 0.08})
        res = engine.bhb(s, s, r, r)
        assert abs(res["active_total"]) < 1e-10

    def test_retorna_todas_las_claves(self, engine):
        s = pd.Series({"A": 0.5, "B": 0.5})
        r = pd.Series({"A": 0.10, "B": 0.08})
        res = engine.bhb(s, s, r, r)
        for k in ("allocation", "selection", "interaction",
                  "active_total", "allocation_sum", "selection_sum", "interaction_sum"):
            assert k in res

    def test_invariante_tres_activos(self, engine):
        """Invariante con 3 activos y pesos distintos."""
        wp = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
        wb = pd.Series({"A": 1/3, "B": 1/3, "C": 1/3})
        rp = pd.Series({"A": 0.20, "B": 0.05, "C": -0.03})
        rb = pd.Series({"A": 0.20, "B": 0.05, "C": -0.03})
        r = engine.bhb(wp, wb, rp, rb)
        total = r["allocation_sum"] + r["selection_sum"] + r["interaction_sum"]
        assert abs(total - r["active_total"]) < 1e-6


# ─── Tracking Error ────────────────────────────────────────────────────────────

class TestTrackingError:
    def test_te_cero_con_retornos_identicos(self, engine):
        ret = pd.Series([0.01, -0.02, 0.03, 0.01, -0.01])
        assert engine.tracking_error(ret, ret) == pytest.approx(0.0, abs=1e-10)

    def test_te_positivo_con_diferencia(self, engine):
        rp = pd.Series([0.01, 0.02, 0.03, 0.04])
        rb = pd.Series([0.00, 0.01, 0.02, 0.03])
        assert engine.tracking_error(rp, rb) > 0

    def test_te_cero_con_series_vacias(self, engine):
        assert engine.tracking_error(pd.Series([], dtype=float),
                                     pd.Series([], dtype=float)) == 0.0

    def test_te_anualizado(self, engine):
        """TE debe estar anualizado (* sqrt(252)).
        Usa serie con variación real (no constante) para que std > 0.
        """
        rng = np.random.default_rng(42)
        # ret_port oscila alrededor de 0.01, ret_bench alrededor de 0.00
        rp = pd.Series(rng.normal(0.01, 0.005, 252))
        rb = pd.Series(rng.normal(0.00, 0.005, 252))
        te = engine.tracking_error(rp, rb)
        # TE debe ser positivo y estar en un rango razonable (anualizado)
        assert te > 0, "TE debe ser positivo con retornos distintos"
        # Con diferencias ~N(0.01, 0.007), TE anualizado ≈ 0.007*sqrt(252) ≈ 0.11
        assert 0.01 < te < 1.0, f"TE={te:.4f} fuera de rango esperado (0.01-1.0)"


# ─── Information Ratio ────────────────────────────────────────────────────────

class TestInformationRatio:
    def test_ir_cero_cuando_te_cero(self, engine):
        ret = pd.Series([0.01, 0.02, 0.01])
        assert engine.information_ratio(ret, ret) == pytest.approx(0.0)

    def test_ir_positivo_cuando_alpha_positivo(self, engine):
        rp = pd.Series([0.02, 0.03, 0.02, 0.03])
        rb = pd.Series([0.01, 0.01, 0.01, 0.01])
        assert engine.information_ratio(rp, rb) > 0


# ─── Calmar Ratio ─────────────────────────────────────────────────────────────

class TestCalmarRatio:
    def test_calmar_correcto(self, engine):
        assert engine.calmar_ratio(0.20, -0.10) == pytest.approx(2.0)

    def test_calmar_cero_sin_drawdown(self, engine):
        assert engine.calmar_ratio(0.20, 0.0) == pytest.approx(0.0)

    def test_calmar_cero_sin_retorno(self, engine):
        assert engine.calmar_ratio(0.0, -0.10) == pytest.approx(0.0)


# ─── reporte_attribution ──────────────────────────────────────────────────────

class TestReporteAttribution:
    def test_retorna_claves_requeridas(self, engine, df_pos_ejemplo):
        r = engine.reporte_attribution(df_pos_ejemplo, ccl=1465.0)
        for k in ("active_total", "allocation_sum", "selection_sum", "interaction_sum"):
            assert k in r

    def test_invariante_con_datos_reales(self, engine, df_pos_ejemplo):
        """Con datos reales: allocation+selection+interaction == active_total."""
        r = engine.reporte_attribution(df_pos_ejemplo, ccl=1465.0)
        total = r["allocation_sum"] + r["selection_sum"] + r["interaction_sum"]
        assert abs(total - r["active_total"]) < 1e-6

    def test_df_vacio_retorna_dict_vacio(self, engine):
        assert engine.reporte_attribution(pd.DataFrame()) == {}

    def test_no_retorna_todos_ceros_con_datos_validos(self, engine, df_pos_ejemplo):
        """Verifica que el stub fue eliminado: no retorna zeros con datos reales."""
        r = engine.reporte_attribution(df_pos_ejemplo, ccl=1465.0)
        # Con pesos [50/33/17] vs equal-weight [33/33/33] y retornos distintos,
        # al menos uno de los efectos BHB debe ser no-cero
        vals = [abs(r["allocation_sum"]), abs(r["selection_sum"]), abs(r["interaction_sum"])]
        assert any(v > 1e-10 for v in vals), "reporte_attribution sigue siendo el stub (todos zeros)"

    def test_active_total_es_float(self, engine, df_pos_ejemplo):
        r = engine.reporte_attribution(df_pos_ejemplo, ccl=1465.0)
        assert isinstance(r["active_total"], float)

    def test_sin_columnas_requeridas_retorna_vacio(self, engine):
        df = pd.DataFrame({"TICKER": ["AAPL"], "VALOR_ARS": [100_000.0]})
        assert engine.reporte_attribution(df, ccl=1465.0) == {}
