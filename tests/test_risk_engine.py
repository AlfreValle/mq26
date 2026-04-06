"""
tests/test_risk_engine.py — Tests unitarios para 1_Scripts_Motor/risk_engine.py
Ejecutar: pytest tests/test_risk_engine.py -v
Usa datos sintéticos (sin red).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "1_Scripts_Motor"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from risk_engine import RiskEngine


def _datos_sinteticos(n_activos: int = 4, n_dias: int = 300, seed: int = 42) -> pd.DataFrame:
    """Genera precios sintéticos estacionarios para tests."""
    rng = np.random.default_rng(seed)
    retornos = rng.normal(0.0005, 0.015, size=(n_dias, n_activos))
    precios = 100 * np.exp(np.cumsum(retornos, axis=0))
    tickers = [f"ACT{i}" for i in range(n_activos)]
    return pd.DataFrame(precios, columns=tickers)


@pytest.fixture(scope="module")
def engine():
    return RiskEngine(_datos_sinteticos())


# ─── Propiedades comunes a todos los modelos ─────────────────────────────────
class TestPropiedadesGenerales:
    MODELOS = ["Sharpe", "Sortino", "CVaR", "Paridad de Riesgo", "Kelly"]

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_pesos_suman_uno(self, engine, modelo):
        pesos = engine.optimizar(modelo)
        assert sum(pesos.values()) == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_todos_los_pesos_positivos(self, engine, modelo):
        pesos = engine.optimizar(modelo)
        assert all(v >= 0 for v in pesos.values())

    @pytest.mark.parametrize("modelo", ["Sharpe", "Sortino", "CVaR", "Kelly"])
    def test_peso_maximo_no_supera_limite(self, engine, modelo):
        from config import PESO_MAX_OPT
        pesos = engine.optimizar(modelo)
        assert max(pesos.values()) <= PESO_MAX_OPT + 1e-4

    def test_paridad_riesgo_peso_maximo_60(self, engine):
        pesos = engine.optimizar("Paridad de Riesgo")
        assert max(pesos.values()) <= 0.60 + 1e-4

    @pytest.mark.parametrize("modelo", MODELOS)
    def test_devuelve_solo_activos_del_universo(self, engine, modelo):
        pesos = engine.optimizar(modelo)
        for t in pesos:
            assert t in engine.activos


# ─── Métricas ────────────────────────────────────────────────────────────────
class TestLineageC05:
    def test_get_lineage_tiene_digest_y_version(self, engine):
        lin = engine.get_lineage(model_label="pytest", tenant_id="t1")
        assert lin.get("mq26_model_version")
        assert lin.get("inputs_content_sha256")
        assert lin.get("optimization_method") == "pytest"
        assert lin.get("tenant_id") == "t1"


class TestMetricas:
    def test_calcular_metricas_devuelve_tres_valores(self, engine):
        pesos = engine.optimizar_sharpe()
        ret, vol, sh = engine.calcular_metricas(pesos)
        assert isinstance(ret, float)
        assert isinstance(vol, float)
        assert isinstance(sh, float)

    def test_volatilidad_no_negativa(self, engine):
        pesos = engine.optimizar_sharpe()
        _, vol, _ = engine.calcular_metricas(pesos)
        assert vol >= 0

    def test_var_cvar_negativo(self, engine):
        pesos = engine.optimizar_sharpe()
        var, cvar = engine.calcular_var_cvar(pesos)
        # Con datos normales negativos esperamos valores negativos
        assert var < 0
        assert cvar <= var  # CVaR siempre ≤ VaR (mayor pérdida esperada en la cola)


# ─── Modelo por defecto ───────────────────────────────────────────────────────
class TestModeloPorDefecto:
    def test_modelo_desconocido_usa_sharpe(self, engine):
        pesos_desconocido = engine.optimizar("modelo_inexistente")
        pesos_sharpe      = engine.optimizar("Sharpe")
        assert set(pesos_desconocido.keys()) == set(pesos_sharpe.keys())


# ─── Montecarlo ──────────────────────────────────────────────────────────────
class TestMontecarlo:
    def test_forma_salida(self, engine):
        capital = 100_000.0
        result = engine.montecarlo(capital, anos=1, n_sim=100)
        assert result.shape[0] == 252      # 252 días laborables
        assert result.shape[1] == 100

    def test_valores_positivos(self, engine):
        result = engine.montecarlo(100_000.0, anos=1, n_sim=50)
        assert np.all(result > 0)

    def test_reproducibilidad_misma_semilla(self, engine):
        p = engine.optimizar_sharpe()
        a = engine.montecarlo(100_000.0, anos=1, n_sim=200, pesos=p, seed=12345)
        b = engine.montecarlo(100_000.0, anos=1, n_sim=200, pesos=p, seed=12345)
        assert np.allclose(a, b)
        c = engine.montecarlo(100_000.0, anos=1, n_sim=200, pesos=p, seed=99999)
        assert not np.allclose(a, c)


class TestCovarianzaPSD:
    def test_cov_psd_ok_datos_sinteticos(self):
        eng = RiskEngine(_datos_sinteticos())
        assert eng.cov_psd_ok is True
        assert eng.cov_psd_min_eigenvalue > -1e-8

    def test_prepare_covariance_exportable(self):
        from risk_engine import _prepare_covariance_psd

        cov_bad = pd.DataFrame(
            [[1.0, 1.01], [1.01, 1.0]],
            index=["a", "b"],
            columns=["a", "b"],
        )
        ok, msg, out, me = _prepare_covariance_psd(cov_bad)
        assert ok is True
        assert me >= -1e-7
        assert len(msg) > 0
        assert out.shape == cov_bad.shape


class TestGoldenOptimizacion:
    """Golden tests ligeros: datos fijos, tolerancia amplia (solver estocástico numérico)."""

    @pytest.fixture
    def engine_golden(self):
        rng = np.random.default_rng(7)
        n, a = 400, 3
        r = rng.normal(0.0004, 0.012, size=(n, a))
        p = 100 * np.exp(np.cumsum(r, axis=0))
        df = pd.DataFrame(p, columns=["G0", "G1", "G2"])
        return RiskEngine(df)

    def test_sharpe_pesos_suman_uno(self, engine_golden):
        w = engine_golden.optimizar_sharpe()
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)

    def test_paridad_riesgo_stable(self, engine_golden):
        w = engine_golden.optimizar_paridad_riesgo()
        assert len(w) >= 2
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)

    def test_cvar_pesos_positivos(self, engine_golden):
        w = engine_golden.optimizar_cvar(0.95)
        assert all(v >= 0 for v in w.values())


class TestTurnoverYPenalizacion:
    def test_mayor_lambda_no_aumenta_l1_frente_a_prev(self):
        df = _datos_sinteticos(n_activos=4, n_dias=320, seed=17)
        tickers = df.columns.tolist()
        w_prev = {tickers[0]: 0.55, tickers[1]: 0.20, tickers[2]: 0.15, tickers[3]: 0.10}
        e0 = RiskEngine(df, w_prev=w_prev, lambda_turnover=0.0, lambda_tc=0.0)
        e1 = RiskEngine(df, w_prev=w_prev, lambda_turnover=3.0, lambda_tc=3.0)
        p0 = e0.optimizar_sharpe()
        p1 = e1.optimizar_sharpe()
        w0v = np.array([p0.get(t, 0.0) for t in tickers])
        w1v = np.array([p1.get(t, 0.0) for t in tickers])
        prev = np.array([w_prev[t] for t in tickers])
        l1_0 = float(np.sum(np.abs(w0v - prev)))
        l1_1 = float(np.sum(np.abs(w1v - prev)))
        assert l1_1 <= l1_0 + 0.03


class TestSanitizeRetornos:
    def test_sanitize_genera_reporte_con_salto_de_precio(self):
        df = _datos_sinteticos(n_activos=3, n_dias=250, seed=44)
        df.iloc[120, 0] = df.iloc[119, 0] * 1.35
        eng = RiskEngine(df, sanitize_returns=True, winsor_lower_q=0.01, winsor_upper_q=0.99)
        assert eng.returns_sanitize_report is not None
        assert eng.returns_sanitize_report.get("n_recortes_total", 0) >= 1


class TestMinVarianzaBaseline:
    def test_min_varianza_pesos_suman_1(self):
        e = RiskEngine(_datos_sinteticos())
        w = e.optimizar_min_varianza()
        assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)

    def test_min_varianza_menor_o_igual_vol_que_sharpe(self):
        e = RiskEngine(_datos_sinteticos())
        wv = e.optimizar_min_varianza()
        ws = e.optimizar_sharpe()
        _, vol_v, _ = e.calcular_metricas(wv)
        _, vol_s, _ = e.calcular_metricas(ws)
        assert vol_v <= vol_s + 1e-5


class TestHHIFactorMultiobj:
    def test_hhi_portfolio_uniforme_minimo(self):
        n = 5
        w = {f"ACT{i}": 1.0 / n for i in range(n)}
        assert RiskEngine.calcular_hhi(w) == pytest.approx(1.0 / n, rel=0.02)

    def test_hhi_un_activo_maximo(self):
        assert RiskEngine.calcular_hhi({"ACT0": 1.0}) == pytest.approx(1.0, abs=1e-9)

    def test_beta_spy_y_keys_factor_exposure(self):
        df = _datos_sinteticos(n_activos=3, n_dias=320, seed=99)
        df["SPY"] = (df.iloc[:, 0] * 0.98).clip(lower=10.0)
        e = RiskEngine(df)
        p = {e.activos[0]: 1.0}  # cartera 100% al activo correlacionado con SPY
        fac = e.calcular_factor_exposure(p)
        assert set(fac.keys()) == {"beta_spy", "beta_qqq", "beta_eem"}
        assert fac["beta_spy"] == pytest.approx(1.0, abs=0.2)

    def test_multiobjetivo_pesos_configurables(self):
        e = RiskEngine(_datos_sinteticos())
        w2 = e.optimizar_multiobjetivo(
            pesos_componentes={
                "sharpe": 1.0,
                "retorno_usd": 0.0,
                "preservacion_ars": 0.0,
                "dividendos": 0.0,
            },
            lambda_aversion=0.0,
        )
        assert sum(w2.values()) == pytest.approx(1.0, abs=1e-3)

    def test_lambda_aversion_aumenta_preservacion_vol(self):
        e = RiskEngine(_datos_sinteticos())
        w0 = e.optimizar_multiobjetivo(lambda_aversion=0.0)
        w1 = e.optimizar_multiobjetivo(lambda_aversion=8.0)
        _, v0, _ = e.calcular_metricas(w0)
        _, v1, _ = e.calcular_metricas(w1)
        assert v1 <= v0 + 0.02

    def test_bl_con_horizonte_suma_uno(self):
        df = _datos_sinteticos(4, n_dias=300, seed=3)
        e = RiskEngine(df)
        v = {"ACT0": 0.35}
        w_h = e.optimizar_black_litterman(views=v, tau=0.15, horizon_trading_days=126)
        assert sum(w_h.values()) == pytest.approx(1.0, abs=1e-2)
