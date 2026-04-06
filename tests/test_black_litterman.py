"""Tests Black–Litterman: escala τ con horizonte (A06)."""
import numpy as np

from core.black_litterman import black_litterman_with_absolute_views


def test_omega_escala_con_horizonte_mu_posterior_distinto():
    """τ efectivo menor (horizonte corto) → incertidumbre views distinta → μ posterior distinto."""
    n = 4
    tickers = [f"T{i}" for i in range(n)]
    mu = np.array([0.08, 0.07, 0.09, 0.06])
    sigma = np.eye(n) * 0.04
    np.fill_diagonal(sigma, np.linspace(0.03, 0.05, n))
    sigma = (sigma + sigma.T) / 2
    w_mkt = np.ones(n) / n
    views = {"T0": 0.35}
    tau_short = 0.08 * np.sqrt(21 / 252)
    tau_long = 0.08 * np.sqrt(252 / 252)
    bl_s = black_litterman_with_absolute_views(
        mu, sigma, w_mkt, tau_short, views, tickers, omega_mode="proportional", ridge=1e-9,
    )
    bl_l = black_litterman_with_absolute_views(
        mu, sigma, w_mkt, tau_long, views, tickers, omega_mode="proportional", ridge=1e-9,
    )
    assert bl_s.Omega.shape == bl_l.Omega.shape
    assert not np.allclose(np.diag(bl_s.Omega), np.diag(bl_l.Omega))
    assert float(np.trace(bl_l.Omega)) > float(np.trace(bl_s.Omega))
