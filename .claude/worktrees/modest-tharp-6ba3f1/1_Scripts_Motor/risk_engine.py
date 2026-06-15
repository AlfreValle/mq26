"""
risk_engine.py — Motor Cuantitativo Multi-Modelo
Master Quant 26 | Estrategia Capitales
Modelos: Sharpe, Sortino, CVaR (Rockafellar-Uryasev), Kelly,
         Paridad de Riesgo, Min Drawdown, Multi-Objetivo, Black-Litterman
Mejoras: Ledoit-Wolf shrinkage, Kelly multiactivo, Montecarlo con Cholesky
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    PESO_MAX_OPT,
    PESO_MIN_CONVICCION,
    PESO_MIN_OPT,
    PESOS_OPTIMIZADOR,
    RISK_FREE_RATE,
)

try:
    from sklearn.covariance import LedoitWolf
    _LEDOIT_DISPONIBLE = True
except ImportError:
    _LEDOIT_DISPONIBLE = False


def _prepare_covariance_psd(
    cov_df: pd.DataFrame,
    *,
    sym_tol: float = 1e-9,
    eig_floor: float = 1e-10,
) -> tuple[bool, str, pd.DataFrame, float]:
    """
    Valida y, si hace falta, estabiliza la covarianza a semidefinida positiva.

    Retorna (ok, mensaje, cov_df_usable, min_eig_final).
    Si ok es False, cov_df_usable es la entrada original (no optimizar ni exportar).
    """
    labels = cov_df.index.tolist()
    C = cov_df.values.astype(float)
    if C.size == 0:
        return False, "Covarianza vacía.", cov_df, float("nan")
    if not np.all(np.isfinite(C)):
        return False, "La matriz de covarianza contiene NaN o Inf.", cov_df, float("nan")

    C = (C + C.T) / 2.0
    evals, evecs = np.linalg.eigh(C)
    min_e0 = float(evals.min())
    msg_parts: list[str] = []
    C_work = C

    if min_e0 < -sym_tol:
        jitter = max(1e-10, -min_e0 * 1.01)
        repaired = False
        for _ in range(16):
            C_try = C + np.eye(C.shape[0]) * jitter
            if float(np.linalg.eigvalsh((C_try + C_try.T) / 2).min()) >= -sym_tol:
                C_work = C_try
                msg_parts.append(
                    f"Jitter diagonal λ={jitter:.2e} (λ_min antes {min_e0:.2e})."
                )
                repaired = True
                break
            jitter *= 2.0
        if not repaired:
            evals_clipped = np.maximum(evals, eig_floor)
            C_work = evecs @ np.diag(evals_clipped) @ evecs.T
            msg_parts.append(
                f"Proyección PSD: λ_min era {min_e0:.2e}; truncado a {eig_floor:.0e}."
            )

    min_ef = float(np.linalg.eigvalsh((C_work + C_work.T) / 2).min())
    if min_ef < -sym_tol * 100:
        return False, "No se obtuvo covarianza PSD estable tras correcciones.", cov_df, min_ef

    out = pd.DataFrame(C_work, index=labels, columns=labels)
    detail = " ".join(msg_parts) if msg_parts else "Covarianza PSD verificada (sin correcciones)."
    return True, detail, out, min_ef


class RiskEngine:
    """Motor de optimización de cartera con 8 modelos cuantitativos."""

    def __init__(
        self,
        datos_precios: pd.DataFrame,
        *,
        w_prev: dict[str, float] | None = None,
        lambda_turnover: float = 0.0,
        lambda_tc: float = 0.0,
        max_turnover_l1: float | None = None,
        sanitize_returns: bool = False,
        winsor_lower_q: float = 0.005,
        winsor_upper_q: float = 0.995,
    ):
        self.precios = datos_precios.copy()
        self.n = len(self.precios.columns)
        self.activos = self.precios.columns.tolist()
        self.lambda_turnover = float(lambda_turnover)
        self.lambda_tc = float(lambda_tc)
        self.max_turnover_l1 = None if max_turnover_l1 is None else float(max_turnover_l1)
        if w_prev:
            self._w_prev_vec = np.array(
                [float(w_prev.get(str(t), 0.0)) for t in self.activos], dtype=float
            )
            _s = float(self._w_prev_vec.sum())
            if _s > 1e-12:
                self._w_prev_vec = self._w_prev_vec / _s
            else:
                self._w_prev_vec = None
        else:
            self._w_prev_vec = None

        self.retornos = self.precios.pct_change(fill_method=None).dropna()
        self.returns_sanitize_report: dict | None = None
        if sanitize_returns:
            from core.returns_sanitize import winsorize_returns_panel

            self.retornos, self.returns_sanitize_report = winsorize_returns_panel(
                self.retornos, lower_q=winsor_lower_q, upper_q=winsor_upper_q
            )

        self.mean_ret = self.retornos.mean() * 252
        self.constraints = ({"type": "eq", "fun": lambda x: np.sum(x) - 1},)
        self.bounds = tuple((PESO_MIN_OPT, PESO_MAX_OPT) for _ in range(self.n))
        self.w0 = [1.0 / self.n] * self.n

        # Ledoit-Wolf shrinkage (B1): estimador robusto de covarianza
        if _LEDOIT_DISPONIBLE and len(self.retornos) >= self.n * 2:
            try:
                lw = LedoitWolf().fit(self.retornos.values)
                self.cov_matrix = pd.DataFrame(
                    lw.covariance_ * 252,
                    index=self.activos, columns=self.activos
                )
            except Exception:
                self.cov_matrix = self.retornos.cov() * 252
        else:
            self.cov_matrix = self.retornos.cov() * 252

        self.cov_psd_ok: bool
        self.cov_psd_message: str
        self.cov_psd_min_eigenvalue: float
        ok_cov, msg_cov, cov_use, min_eig = _prepare_covariance_psd(self.cov_matrix)
        self.cov_psd_ok = ok_cov
        self.cov_psd_message = msg_cov
        self.cov_psd_min_eigenvalue = min_eig
        if ok_cov:
            self.cov_matrix = cov_use
        else:
            self.cov_psd_message = msg_cov

    @property
    def lambda_turnover_cost(self) -> float:
        """λ conjunto para penalización lineal en ∑|w − w_prev| (turnover + costo proporcional al NAV movido)."""
        return self.lambda_turnover + self.lambda_tc

    def _turnover_penalty(self, w: np.ndarray) -> float:
        if self._w_prev_vec is None or self.lambda_turnover_cost <= 0:
            return 0.0
        w = np.asarray(w, dtype=float)
        return self.lambda_turnover_cost * float(np.sum(np.abs(w - self._w_prev_vec)))

    def _constraints_slsqp(self) -> tuple:
        c = [self.constraints[0]]
        if self._w_prev_vec is not None and self.max_turnover_l1 is not None:
            wp = np.array(self._w_prev_vec, dtype=float)
            mt = float(self.max_turnover_l1)
            c.append(
                {"type": "ineq", "fun": lambda w, _wp=wp, _mt=mt: _mt - float(np.sum(np.abs(w - _wp)))}
            )
        return tuple(c)

    def _limpiar(self, result, min_peso: float = None) -> dict:
        """Filtra pesos < umbral (B9: configurable desde config.PESO_MIN_CONVICCION),
        renormaliza y garantiza suma = 1.0 exacto."""
        umbral = min_peso if min_peso is not None else PESO_MIN_CONVICCION
        fallback = {t: round(1/self.n, 4) for t in self.activos}
        if not result.success:
            return fallback
        pesos = {t: p for t, p in zip(self.activos, result.x) if p >= umbral}
        total = sum(pesos.values())
        if total <= 0:
            return fallback
        pesos = {t: round(p / total, 4) for t, p in pesos.items()}
        diff = round(1.0 - sum(pesos.values()), 4)
        if diff != 0:
            pesos[max(pesos, key=pesos.get)] += diff
        return pesos

    # ── 1. SHARPE (Max Varianza Media) ────────────────────────────────────────
    def optimizar_sharpe(self) -> dict:
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        def obj(w):
            ret = np.sum(w * self.mean_ret)
            vol = np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w)))
            base = -(ret - RISK_FREE_RATE) / vol if vol > 0 else 0
            return base + self._turnover_penalty(w)
        return self._limpiar(
            minimize(obj, self.w0, bounds=self.bounds, constraints=self._constraints_slsqp(), method="SLSQP")
        )

    # ── 2. SORTINO ────────────────────────────────────────────────────────────
    def optimizar_sortino(self, mar: float = 0.0) -> dict:
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        ret_d = self.retornos.values
        mar_d = mar / 252
        def obj(w):
            ret_a   = np.sum(w * self.mean_ret)
            port_r  = np.dot(ret_d, w)
            down    = np.minimum(0, port_r - mar_d)
            down_v  = np.mean(down**2) * 252
            down_d  = np.sqrt(down_v)
            base = -(ret_a - RISK_FREE_RATE) / down_d if down_d > 0 else 0
            return base + self._turnover_penalty(w)
        return self._limpiar(
            minimize(obj, self.w0, bounds=self.bounds, constraints=self._constraints_slsqp(), method="SLSQP")
        )

    # ── 3. CVaR — Formulación convexa Rockafellar-Uryasev (más estable) ──────
    def optimizar_cvar(self, confianza: float = 0.95) -> dict:
        """
        CVaR via Rockafellar-Uryasev (2000).
        Variables: x = [w_1, ..., w_n, z] donde z es el VaR umbral auxiliar.
        Objetivo: minimizar z + (1/(T*(1-α))) * Σ max(−r_t·w − z, 0)
        Más estable numéricamente que minimizar CVaR directamente con scipy.
        """
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        ret_d = self.retornos.values
        T     = len(ret_d)
        alpha = 1.0 - confianza

        def obj_ru(xz):
            w = xz[:self.n]
            z = xz[self.n]
            port_r  = ret_d @ w
            losses  = np.maximum(-port_r - z, 0.0)
            cvar_ru = z + (1.0 / (T * alpha)) * np.sum(losses)
            return cvar_ru + self._turnover_penalty(w)

        # x = [w_1..w_n, z]; z puede ser negativo (es el VaR, que suele ser negativo).
        # La constraint sum=1 debe aplicarse SOLO a los pesos w[:n], no a z.
        cvar_constraints = [{"type": "eq", "fun": lambda xz: np.sum(xz[:self.n]) - 1}]
        if self._w_prev_vec is not None and self.max_turnover_l1 is not None:
            wp = np.array(self._w_prev_vec, dtype=float)
            mt = float(self.max_turnover_l1)
            cvar_constraints.append(
                {
                    "type": "ineq",
                    "fun": lambda xz, _wp=wp, _mt=mt: _mt - float(np.sum(np.abs(xz[: self.n] - _wp))),
                }
            )
        bounds_ru = list(self.bounds) + [(-1.0, 1.0)]
        w0_ru     = self.w0 + [float(np.percentile(self.retornos.values @ self.w0, alpha * 100))]
        return self._limpiar(minimize(obj_ru, w0_ru, method="SLSQP",
                                      bounds=bounds_ru, constraints=tuple(cvar_constraints)))

    # ── 4. KELLY ──────────────────────────────────────────────────────────────
    def optimizar_kelly(self) -> dict:
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        def obj(w):
            ret = np.sum(w * self.mean_ret)
            vol = np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w)))
            return -(ret - 0.5 * vol**2) + self._turnover_penalty(w)
        return self._limpiar(
            minimize(obj, self.w0, bounds=self.bounds, constraints=self._constraints_slsqp(), method="SLSQP")
        )

    # ── 5. PARIDAD DE RIESGO ──────────────────────────────────────────────────
    def optimizar_paridad_riesgo(self) -> dict:
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        bounds_pr = tuple((PESO_MIN_OPT, PESO_MAX_OPT) for _ in range(self.n))
        def obj(w):
            vol  = np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w)))
            mrc  = np.dot(self.cov_matrix, w) / vol
            rc   = w * mrc
            tgt  = vol / self.n
            return np.sum((rc - tgt)**2) + self._turnover_penalty(w)
        return self._limpiar(minimize(obj, self.w0, method="SLSQP",
                                       bounds=bounds_pr, constraints=self._constraints_slsqp()))

    # ── 5a. HRP (A16) — delega en core.hrp_weights ────────────────────────────
    def optimizar_hrp(self) -> dict:
        from core.hrp_weights import hrp_weights

        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        sigma = self.cov_matrix.values.astype(float)
        w = hrp_weights(sigma)
        return {t: round(float(wi), 6) for t, wi in zip(self.activos, w, strict=True)}

    def optimizar_erc(self) -> dict:
        from core.hrp_weights import solve_erc

        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        sigma = self.cov_matrix.values.astype(float)
        w = solve_erc(sigma)
        return {t: round(float(wi), 6) for t, wi in zip(self.activos, w, strict=True)}

    # ── 5b. MIN VARIANZA (baseline A10) ─────────────────────────────────────────
    def optimizar_min_varianza(self) -> dict:
        """Minimiza varianza de cartera sujeto a sum(w)=1 y long-only (mismo universo que Sharpe)."""
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}

        def obj_mv(w):
            return float(w @ self.cov_matrix.values @ w) + self._turnover_penalty(w)

        return self._limpiar(
            minimize(obj_mv, self.w0, method="SLSQP",
                     bounds=self.bounds, constraints=self._constraints_slsqp())
        )

    # ── 6. MIN DRAWDOWN ───────────────────────────────────────────────────────
    def optimizar_min_drawdown(self) -> dict:
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        ret_d = self.retornos.values
        def obj(w):
            port_r  = np.dot(ret_d, w)
            cum     = np.cumprod(1 + port_r)
            rolling_max = np.maximum.accumulate(cum)
            dd      = (cum - rolling_max) / rolling_max
            return -np.min(dd) + self._turnover_penalty(w)  # minimizar el drawdown máximo (es negativo)
        return self._limpiar(
            minimize(obj, self.w0, bounds=self.bounds, constraints=self._constraints_slsqp(), method="SLSQP")
        )

    # ── 7. MULTI-OBJETIVO (escalarización ponderada) ──────────────────────────
    def optimizar_multiobjetivo(
        self,
        *,
        pesos_componentes: dict[str, float] | None = None,
        lambda_aversion: float | None = None,
    ) -> dict:
        """
        Escalarización ponderada: componentes configurables (A8) y λ de aversión al riesgo (A9).
        Si lambda_aversion > 0 penaliza vol² además del score escalarizado.
        """
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        weights = dict(PESOS_OPTIMIZADOR)
        if pesos_componentes:
            for k, v in pesos_componentes.items():
                if k in weights and v is not None:
                    weights[k] = float(v)
        ssum = sum(max(0.0, float(v)) for v in weights.values())
        if ssum > 1e-12:
            weights = {k: max(0.0, float(weights[k])) / ssum for k in weights}
        lam_r = float(lambda_aversion) if lambda_aversion is not None else 0.0

        def _score_sharpe(w):
            ret = float(np.sum(w * self.mean_ret))
            vol = float(np.sqrt(w @ self.cov_matrix.values @ w))
            return (ret - RISK_FREE_RATE) / vol if vol > 0 else 0.0

        def _score_retorno_usd(w):
            return float(np.sum(w * self.mean_ret))

        def _score_preservacion_ars(w):
            vol = float(np.sqrt(w @ self.cov_matrix.values @ w))
            return -vol

        def _score_paridad(w):
            vol = float(np.sqrt(w @ self.cov_matrix.values @ w))
            if vol <= 0:
                return 0.0
            mrc = (self.cov_matrix.values @ w) / vol
            rc = w * mrc
            tgt = vol / self.n
            return -float(np.sum((rc - tgt) ** 2))

        def obj_mo(w):
            s = {
                "sharpe": _score_sharpe(w),
                "retorno_usd": _score_retorno_usd(w),
                "preservacion_ars": _score_preservacion_ars(w),
                "dividendos": _score_paridad(w),
            }
            combined = sum(weights.get(k, 0.0) * s[k] for k in s)
            vol_p = float(w @ self.cov_matrix.values @ w)
            pen_vol = 0.5 * lam_r * vol_p if lam_r > 0 else 0.0
            return -combined + pen_vol + self._turnover_penalty(w)

        return self._limpiar(minimize(obj_mo, self.w0, method="SLSQP",
                                      bounds=self.bounds, constraints=self._constraints_slsqp()))

    # ── 8. BLACK-LITTERMAN (B6) ───────────────────────────────────────────────
    def optimizar_black_litterman(
        self,
        views: dict = None,
        tau: float = 0.05,
        *,
        horizon_trading_days: int | None = None,
    ) -> dict:
        """
        Black-Litterman: combina equilibrio de mercado (CAPM prior) con views del asesor.
        Si views=None, devuelve pesos de mercado implícitos (capitalización relativa).
        views = {"AAPL": 0.15, "MSFT": 0.12} → retornos esperados por el asesor.
        También acepta valores (retorno, confianza) como en el Lab Quant UI.
        """
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        from core.black_litterman import black_litterman_with_absolute_views
        from core.portfolio_optimization import solve_black_litterman_max_sharpe
        from config import DIAS_TRADING

        sigma = self.cov_matrix.values
        w_mkt = np.array(self.w0, dtype=float)
        tau_use = float(tau)
        if horizon_trading_days is not None and int(horizon_trading_days) > 0:
            # A06: incertidumbre de views escala con horizonte (√T/√252)
            tau_use = float(tau) * np.sqrt(float(int(horizon_trading_days)) / float(DIAS_TRADING))

        views_simple: dict | None = None
        conf_map: dict[str, float] = {}
        if views:
            views_simple = {}
            for t, val in views.items():
                if t not in self.activos:
                    continue
                if isinstance(val, (list, tuple)) and len(val) >= 1:
                    try:
                        r = float(val[0])
                        c = float(val[1]) if len(val) >= 2 else 0.5
                    except (TypeError, ValueError):
                        continue
                    views_simple[t] = r
                    conf_map[t] = min(max(c, 0.05), 1.0)
                else:
                    try:
                        views_simple[t] = float(val)
                        conf_map[t] = 0.5
                    except (TypeError, ValueError):
                        continue
            if not views_simple:
                views_simple = None

        bl = black_litterman_with_absolute_views(
            self.mean_ret.values,
            sigma,
            w_mkt,
            tau_use,
            views_simple or {},
            self.activos,
            omega_mode="confidence" if conf_map and views_simple else "proportional",
            confidence=conf_map if conf_map else None,
            ridge=1e-9,
        )
        mu_bl = bl.mu_posterior

        res = solve_black_litterman_max_sharpe(
            mu_bl,
            sigma,
            rf=RISK_FREE_RATE,
            long_only=True,
            ridge=1e-8,
            w_prev=self._w_prev_vec,
            lambda_turnover_penalty=self.lambda_turnover_cost,
            max_turnover_l1=self.max_turnover_l1,
        )
        class _R:
            success = res.success
            x = res.weights

        return self._limpiar(_R())

    def optimizar_max_retorno_te(self, w_bench: dict | None = None, te_max: float = 0.06) -> dict:
        """Max retorno esperado con TE anual ≤ te_max respecto a benchmark w_bench (A8)."""
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        from core.portfolio_optimization import OptimizationProblem, solve_max_return_tracking_error

        sigma = self.cov_matrix.values
        if w_bench is None:
            b = np.ones(self.n, dtype=float) / self.n
        else:
            b = np.array([w_bench.get(t, 0.0) for t in self.activos], dtype=float)
            if b.sum() <= 1e-12:
                b = np.ones(self.n, dtype=float) / self.n
            else:
                b = b / b.sum()
        prob = OptimizationProblem(
            mu=self.mean_ret.values, Sigma=sigma, rf=RISK_FREE_RATE, long_only=True
        )
        res = solve_max_return_tracking_error(
            prob,
            b,
            float(te_max),
            w_prev=self._w_prev_vec,
            lambda_turnover_penalty=self.lambda_turnover_cost,
            max_turnover_l1=self.max_turnover_l1,
        )

        class _R:
            success = res.success
            x = res.weights

        return self._limpiar(_R())

    # ── Kelly multiactivo exacto (B8) ────────────────────────────────────────
    def kelly_multiactivo(self) -> dict:
        """
        Kelly exacto multiactivo: f* = Σ^-1 * μ (fracción óptima de cada activo).
        Normalizado para que los pesos sumen 1.
        """
        if not self.cov_psd_ok:
            return {t: round(1.0 / self.n, 4) for t in self.activos}
        try:
            sigma_inv = np.linalg.inv(self.cov_matrix.values)
            mu        = self.mean_ret.values - RISK_FREE_RATE
            f_star    = sigma_inv @ mu
            f_star    = np.clip(f_star, PESO_MIN_OPT * f_star.sum(),
                                PESO_MAX_OPT * f_star.sum())
            f_star    = np.maximum(f_star, 0)
            total     = f_star.sum()
            if total > 0:
                f_star = f_star / total
            pesos = {t: round(float(f_star[i]), 4) for i, t in enumerate(self.activos)}
            return pesos
        except np.linalg.LinAlgError:
            return self.optimizar_kelly()

    # ── FRONTERA EFICIENTE ───────────────────────────────────────────────────
    def efficient_frontier(self, n_puntos: int = 50) -> "pd.DataFrame":
        """
        Genera la Frontera Eficiente de Markowitz: n carteras que minimizan
        la volatilidad para cada nivel de retorno objetivo entre el mínimo y el
        máximo retorno esperado del universo.

        Sprint 1 — Bloomberg-level: el gráfico central de optimización institucional.

        Retorna DataFrame con columnas:
            retorno_anual_pct  — retorno esperado anualizado (%)
            volatilidad_pct    — volatilidad anualizada (%)
            sharpe             — ratio de Sharpe
            pesos              — dict {ticker: peso} de la cartera eficiente

        Invariante de calidad: volatilidad monotónicamente creciente con retorno.
        """
        if not self.cov_psd_ok:
            return pd.DataFrame(columns=["retorno_anual_pct", "volatilidad_pct", "sharpe", "pesos"])
        ret_min = float(self.mean_ret.min()) * 1.02
        ret_max = float(self.mean_ret.max()) * 0.98
        if ret_min >= ret_max:
            return pd.DataFrame(columns=["retorno_anual_pct", "volatilidad_pct", "sharpe", "pesos"])

        targets = np.linspace(ret_min, ret_max, n_puntos)
        puntos = []

        for target in targets:
            constraints = [
                {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},
                {"type": "eq", "fun": lambda w, r=target: float(np.dot(w, self.mean_ret)) - r},
            ]
            res = minimize(
                lambda w: float(w @ self.cov_matrix.values @ w),
                self.w0,
                method="SLSQP",
                bounds=self.bounds,
                constraints=constraints,
                options={"ftol": 1e-9, "maxiter": 1000},
            )
            if res.success and res.fun >= 0:
                vol = float(np.sqrt(res.fun))
                sharpe = (target - RISK_FREE_RATE) / vol if vol > 0 else 0.0
                puntos.append({
                    "retorno_anual_pct": round(target * 100, 3),
                    "volatilidad_pct":   round(vol * 100, 3),
                    "sharpe":            round(sharpe, 4),
                    "pesos": {
                        t: round(float(res.x[i]), 4)
                        for i, t in enumerate(self.activos)
                        if float(res.x[i]) >= 0.001
                    },
                })

        if not puntos:
            return pd.DataFrame(columns=["retorno_anual_pct", "volatilidad_pct", "sharpe", "pesos"])

        df = pd.DataFrame(puntos).sort_values("retorno_anual_pct").reset_index(drop=True)
        # Filtrar puntos dominados (volatilidad no monótona)
        min_vol_seen = float("inf")
        mask = []
        for v in df["volatilidad_pct"]:
            if v <= min_vol_seen + 0.01:  # tolerancia numérica 0.01%
                mask.append(True)
                min_vol_seen = min(min_vol_seen, v)
            else:
                mask.append(False)
        return df[mask].reset_index(drop=True)

    # ── DESPACHO POR NOMBRE ───────────────────────────────────────────────────
    def optimizar(self, modelo: str) -> dict:
        m = modelo.lower()
        if "sharpe"         in m: return self.optimizar_sharpe()
        if "sortino"        in m: return self.optimizar_sortino()
        if "cvar"           in m or "expected" in m: return self.optimizar_cvar()
        if "kelly"          in m: return self.optimizar_kelly()
        if "paridad"        in m or "parity"   in m: return self.optimizar_paridad_riesgo()
        if "hrp" in m or "hierarchical" in m:
            return self.optimizar_hrp()
        if "erc" in m:
            return self.optimizar_erc()
        if "min var"        in m or "min_var"  in m or "varianza" in m:
            return self.optimizar_min_varianza()
        if "drawdown" in m or "draw down" in m:
            return self.optimizar_min_drawdown()
        if "multi"          in m or "objetivo" in m: return self.optimizar_multiobjetivo()
        if "black"          in m or "litterman" in m: return self.optimizar_black_litterman()
        return self.optimizar_sharpe()  # default

    # ── MÉTRICAS ──────────────────────────────────────────────────────────────
    def calcular_metricas(self, pesos: dict) -> tuple:
        """Retorna (retorno_anual, volatilidad_anual, sharpe)."""
        w = np.array([pesos.get(t, 0) for t in self.activos])
        ret = float(np.sum(w * self.mean_ret))
        vol = float(np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w))))
        sh  = (ret - RISK_FREE_RATE) / vol if vol > 0 else 0.0
        return ret, vol, sh

    @staticmethod
    def calcular_hhi(pesos: dict) -> float:
        """Índice Herfindahl-Hirschman de concentración (B06). Suma w_i^2 en pesos normalizados."""
        w = np.array([float(v) for v in pesos.values()], dtype=float)
        if w.sum() > 1e-12:
            w = w / w.sum()
        w = w[w > 1e-15]
        return float(np.sum(w**2)) if w.size else 0.0

    def calcular_factor_exposure(self, pesos: dict) -> dict[str, float]:
        """
        B04: beta de la cartera respecto a SPY, QQQ y EEM (OLS univariada por factor si la serie existe).
        """
        out: dict[str, float] = {
            "beta_spy": 0.0,
            "beta_qqq": 0.0,
            "beta_eem": 0.0,
        }
        w = np.array([pesos.get(t, 0.0) for t in self.activos], dtype=float)
        if w.sum() > 1e-12:
            w = w / w.sum()
        port_r = (self.retornos[self.activos].values @ w).ravel()
        fac_map = {"SPY": "beta_spy", "QQQ": "beta_qqq", "EEM": "beta_eem"}
        for fac, bkey in fac_map.items():
            if fac not in self.retornos.columns:
                continue
            x = self.retornos[fac].values.ravel()
            mask = np.isfinite(port_r) & np.isfinite(x)
            if int(mask.sum()) < 10:
                continue
            xv = x[mask] - float(np.mean(x[mask]))
            yv = port_r[mask] - float(np.mean(port_r[mask]))
            vx = float(np.dot(xv, xv))
            if vx > 1e-18:
                out[bkey] = float(np.dot(xv, yv) / vx)
        return out

    def get_lineage(self, *, model_label: str = "RiskEngine", tenant_id: str | None = None) -> dict:
        """
        C05: manifiesto de linaje (hash de inputs + parámetros + versión de modelo).
        """
        from core.export_lineage import DEFAULT_MODEL_VERSION, build_export_manifest, digest_inputs

        dig = digest_inputs(
            activos=list(self.activos),
            n_obs=int(len(self.retornos)),
            cov_psd_ok=bool(self.cov_psd_ok),
            mean_ret_head=(float(self.mean_ret.values[0]) if len(self.mean_ret) else None),
        )
        return build_export_manifest(
            model_version=DEFAULT_MODEL_VERSION,
            optimization_method=model_label,
            inputs_digest=dig,
            parameters={
                "lambda_turnover": self.lambda_turnover,
                "lambda_tc": self.lambda_tc,
                "sanitize_returns": self.returns_sanitize_report is not None,
                "cov_psd_min_eigenvalue": float(self.cov_psd_min_eigenvalue)
                if np.isfinite(self.cov_psd_min_eigenvalue)
                else None,
            },
            tickers=list(self.activos),
            tenant_id=tenant_id,
        )

    def calcular_var_cvar(self, pesos: dict, confianza: float = 0.95) -> tuple:
        """
        Calcula VaR y CVaR históricos usando los pesos de la cartera.
        Retorna (var_pct, cvar_pct) como porcentajes negativos.
        """
        w       = np.array([pesos.get(t, 0) for t in self.activos])
        ret_p   = self.retornos[self.activos].values @ w
        alpha   = 1 - confianza
        var_val = float(np.percentile(ret_p, alpha * 100)) * 100
        cvar_val= float(ret_p[ret_p <= np.percentile(ret_p, alpha * 100)].mean()) * 100
        return var_val, cvar_val

    def calcular_alpha_vs_spy(self, pesos: dict) -> tuple:
        """Retorna (cum_cartera, cum_spy) como Series indexadas por fecha."""
        w = pd.Series({t: pesos.get(t, 0) for t in self.activos})
        activos_en_ret = [t for t in w.index if t in self.retornos.columns]
        w_valid = w[activos_en_ret]
        w_valid = w_valid / w_valid.sum()
        port_r  = (self.retornos[activos_en_ret] * w_valid).sum(axis=1)
        cum_p   = (1 + port_r).cumprod() * 100
        if "SPY" in self.precios.columns:
            spy_r = self.precios["SPY"].pct_change().fillna(0)
            cum_s = (1 + spy_r).cumprod() * 100
        else:
            cum_s = pd.Series([100.0] * len(cum_p), index=cum_p.index)
        return cum_p, cum_s

    def montecarlo(self, capital_inicial: float, anos: int = 3,
                   n_sim: int = 10_000, pesos: dict = None,
                   seed: int | None = None,
                   rng: np.random.Generator | None = None) -> np.ndarray:
        """
        Simulación de Montecarlo multivariada con descomposición de Cholesky (B3).
        Preserva la estructura de correlaciones entre activos en lugar de GBM univariado.

        seed / rng: para reproducibilidad (prioridad: rng si no es None; si no, seed;
        si ambos None, generador no determinista).
        """
        if pesos is None:
            pesos = self.optimizar_sharpe()
        w     = np.array([pesos.get(t, 0.0) for t in self.activos])
        total = w.sum()
        if total > 0:
            w = w / total

        _rng = rng if rng is not None else np.random.default_rng(seed)

        mu_d  = (self.mean_ret.values / 252)
        sig_d = self.cov_matrix.values / 252

        # Descomposición de Cholesky para correlaciones
        try:
            L = np.linalg.cholesky(sig_d + np.eye(self.n) * 1e-8)
        except np.linalg.LinAlgError:
            L = np.diag(np.sqrt(np.diag(sig_d)))

        dt    = 1.0
        pasos = anos * 252
        valor = np.full(n_sim, float(capital_inicial))
        trayectorias = np.zeros((pasos, n_sim))

        for t in range(pasos):
            z     = _rng.standard_normal((self.n, n_sim))
            shocks = L @ z  # (n_activos × n_sim)
            ret_act = mu_d[:, None] * dt + shocks * np.sqrt(dt)
            ret_port = w @ ret_act  # (n_sim,)
            valor   *= (1 + ret_port)
            trayectorias[t] = valor

        return trayectorias


# ─── DESCOMPOSICIÓN BETA (sistemático vs idiosincrático) ─────────────────────

def calcular_descomposicion_beta(
    retornos_cartera: pd.Series,
    retorno_benchmark: pd.Series,
    nombres_activos: list[str] | None = None,
    retornos_individuales: pd.DataFrame | None = None,
) -> dict:
    """
    Calcula la descomposición beta del portfolio y de cada activo.

    Beta = Cov(R_portfolio, R_benchmark) / Var(R_benchmark)

    Descomposición de riesgo:
      Riesgo total       = Varianza(R_portfolio)
      Riesgo sistemático = Beta² × Varianza(R_benchmark)
      Riesgo idiosincrático = Riesgo total - Riesgo sistemático

    Parámetros:
        retornos_cartera:   pd.Series de retornos diarios del portfolio
        retorno_benchmark:  pd.Series de retornos diarios del benchmark (ej: SPY)
        nombres_activos:    lista de tickers (opcional, para descomposición individual)
        retornos_individuales: DataFrame con columnas = tickers (opcional)

    Retorna:
        beta_portfolio:         beta del portfolio vs benchmark
        r2_portfolio:           R² (% de varianza explicado por el mercado)
        riesgo_total_anual:     volatilidad total anualizada (%)
        riesgo_sistematico_pct: % del riesgo total que es beta/mercado
        riesgo_idiosinc_pct:    % del riesgo total que es idiosincrático
        alpha_jensen:           retorno en exceso del esperado por CAPM (anualizado)
        por_activo:             dict con beta, r2, alpha por ticker (si se provee retornos_individuales)
    """
    try:
        # Alinear series temporalmente
        df_alin = pd.concat(
            [retornos_cartera.rename("port"), retorno_benchmark.rename("bench")], axis=1
        ).dropna()

        if len(df_alin) < 30:
            return _beta_vacio()

        R_p = df_alin["port"].values
        R_b = df_alin["bench"].values

        var_bench = float(np.var(R_b, ddof=1))
        cov_pb    = float(np.cov(R_p, R_b, ddof=1)[0, 1])

        beta  = cov_pb / var_bench if var_bench > 0 else 0.0
        r2    = float(np.corrcoef(R_p, R_b)[0, 1] ** 2)

        var_port   = float(np.var(R_p, ddof=1))
        var_sist   = (beta ** 2) * var_bench
        var_idios  = max(var_port - var_sist, 0.0)

        # Anualizar volatilidades
        vol_total  = float(np.sqrt(var_port  * 252)) * 100
        vol_sist   = float(np.sqrt(var_sist  * 252)) * 100
        vol_idios  = float(np.sqrt(var_idios * 252)) * 100

        pct_sist   = (var_sist  / var_port * 100) if var_port > 0 else 0.0
        pct_idios  = (var_idios / var_port * 100) if var_port > 0 else 0.0

        # Alpha de Jensen (retorno anualizado real - CAPM esperado)
        ret_port_anual  = float(np.mean(R_p)) * 252
        ret_bench_anual = float(np.mean(R_b)) * 252
        capm_esperado   = RISK_FREE_RATE + beta * (ret_bench_anual - RISK_FREE_RATE)
        alpha_jensen    = ret_port_anual - capm_esperado

        # Beta por activo individual (si se proveen retornos)
        por_activo = {}
        if retornos_individuales is not None and not retornos_individuales.empty:
            for ticker in retornos_individuales.columns:
                try:
                    df_act = pd.concat(
                        [retornos_individuales[ticker].rename("act"), retorno_benchmark.rename("bench")], axis=1
                    ).dropna()
                    if len(df_act) < 20:
                        continue
                    Ra = df_act["act"].values
                    Rb = df_act["bench"].values
                    vb = float(np.var(Rb, ddof=1))
                    c  = float(np.cov(Ra, Rb, ddof=1)[0, 1])
                    b_act  = c / vb if vb > 0 else 0.0
                    r2_act = float(np.corrcoef(Ra, Rb)[0, 1] ** 2)
                    alpha_act = float(np.mean(Ra)) * 252 - (RISK_FREE_RATE + b_act * (ret_bench_anual - RISK_FREE_RATE))
                    por_activo[ticker] = {
                        "beta":         round(b_act, 3),
                        "r2":           round(r2_act, 3),
                        "alpha_anual":  round(alpha_act * 100, 2),
                        "vol_anual":    round(float(np.std(Ra, ddof=1)) * np.sqrt(252) * 100, 2),
                    }
                except Exception:
                    pass

        return {
            "beta_portfolio":        round(beta, 3),
            "r2_portfolio":          round(r2, 3),
            "riesgo_total_anual":    round(vol_total, 2),
            "riesgo_sistematico_anual": round(vol_sist, 2),
            "riesgo_idiosinc_anual": round(vol_idios, 2),
            "riesgo_sistematico_pct": round(pct_sist, 1),
            "riesgo_idiosinc_pct":   round(pct_idios, 1),
            "alpha_jensen_anual":    round(alpha_jensen * 100, 2),
            "ret_portfolio_anual":   round(ret_port_anual * 100, 2),
            "ret_benchmark_anual":   round(ret_bench_anual * 100, 2),
            "por_activo":            por_activo,
            "n_observaciones":       len(df_alin),
        }
    except Exception as _e:
        return _beta_vacio()


def _beta_vacio() -> dict:
    return {
        "beta_portfolio": 0.0, "r2_portfolio": 0.0,
        "riesgo_total_anual": 0.0, "riesgo_sistematico_anual": 0.0,
        "riesgo_idiosinc_anual": 0.0, "riesgo_sistematico_pct": 0.0,
        "riesgo_idiosinc_pct": 0.0, "alpha_jensen_anual": 0.0,
        "ret_portfolio_anual": 0.0, "ret_benchmark_anual": 0.0,
        "por_activo": {}, "n_observaciones": 0,
    }
