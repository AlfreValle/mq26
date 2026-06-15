"""
services/attribution_engine.py — Attribution Brinson-Hood-Beebower + TWRR (Sprint 3)
MQ26-DSS | Descompone retorno activo en allocation, selection, interaction.
Invariante: allocation + selection + interaction == active_return (tolerancia 1e-6).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class AttributionEngine:
    """
    Attribution BHB por sector/activo.
    TWRR (Time-Weighted Return), Tracking Error, Information Ratio, Calmar.
    """

    def bhb(
        self,
        wp: pd.Series,
        wb: pd.Series,
        rp: pd.Series,
        rb: pd.Series,
    ) -> dict:
        """
        Brinson-Hood-Beebower. Invariante:
        allocation + selection + interaction == active_return (tolerancia 1e-6).
        wp, wb: pesos portfolio y benchmark por sector/activo.
        rp, rb: retornos portfolio y benchmark por sector/activo.
        """
        R_b = float((wb * rb).sum())
        allocation = (wp - wb) * (rb - R_b)
        selection = wb * (rp - rb)
        interaction = (wp - wb) * (rp - rb)
        active = float((wp * rp).sum() - (wb * rb).sum())
        return {
            "allocation": allocation,
            "selection": selection,
            "interaction": interaction,
            "active_total": active,
            "allocation_sum": float(allocation.sum()),
            "selection_sum": float(selection.sum()),
            "interaction_sum": float(interaction.sum()),
        }

    def twrr(
        self,
        df_trans: pd.DataFrame,
        precios_hist: dict[str, list[float]],
        ccl: float,
    ) -> dict:
        """
        TWRR con flujos. df_trans debe tener columnas de flujo y fechas.
        precios_hist: {ticker: [precio_0, precio_1, ...]} por período.
        Retorna dict con 'twrr_pct', 'periodos', etc.
        """
        # Stub: implementación completa requiere fechas y flujos alineados
        return {"twrr_pct": 0.0, "periodos": 0}

    def tracking_error(self, ret_port: pd.Series, ret_bench: pd.Series) -> float:
        """TE = std(ret_port - ret_bench) * sqrt(252) anualizado."""
        if ret_port.empty or ret_bench.empty or len(ret_port) != len(ret_bench):
            return 0.0
        diff = ret_port.values - ret_bench.values
        return float(np.nanstd(diff) * np.sqrt(252)) if len(diff) > 1 else 0.0

    def information_ratio(
        self,
        ret_port: pd.Series,
        ret_bench: pd.Series,
    ) -> float:
        """IR = alpha_anual / tracking_error."""
        te = self.tracking_error(ret_port, ret_bench)
        if te <= 0:
            return 0.0
        alpha = float((ret_port.mean() - ret_bench.mean()) * 252)
        return alpha / te

    def calmar_ratio(self, cagr_anual: float, max_drawdown: float) -> float:
        """Calmar = cagr_anual / abs(max_drawdown)."""
        if max_drawdown >= 0 or cagr_anual == 0:
            return 0.0
        return cagr_anual / abs(max_drawdown)

    def reporte_attribution(
        self,
        df_pos: pd.DataFrame,
        df_trans: pd.DataFrame | None = None,
        ccl: float = 1500.0,
    ) -> dict:
        """
        Attribution BHB: portfolio (pesos reales de PESO_PCT) vs benchmark equal-weight (1/N).
        Retornos: PNL_PCT realizado por ticker (mismo para ambos — la diferencia es la ponderación).
        Invariante: allocation_sum + selection_sum + interaction_sum == active_total (tol 1e-6).
        """
        if df_pos is None or df_pos.empty:
            return {}
        if "PESO_PCT" not in df_pos.columns or "PNL_PCT" not in df_pos.columns:
            return {}

        total_valor = df_pos["VALOR_ARS"].sum() if "VALOR_ARS" in df_pos.columns else 0.0
        if total_valor <= 0:
            return {}

        tickers = df_pos["TICKER"].values

        # Pesos del portfolio: PESO_PCT/100 (ya normalizado, suma 1)
        wp = pd.Series(df_pos["PESO_PCT"].values / 100.0, index=tickers)

        # Benchmark: equal-weight (1/N para cada ticker)
        n = len(df_pos)
        wb = pd.Series(1.0 / n, index=tickers)

        # Retornos realizados: PNL_PCT de cada ticker
        # El benchmark invirtió en los mismos activos; la diferencia es la ponderación
        rp = pd.Series(df_pos["PNL_PCT"].values, index=tickers)
        rb = pd.Series(df_pos["PNL_PCT"].values, index=tickers)

        res = self.bhb(wp, wb, rp, rb)
        return {
            "active_total":    res["active_total"],
            "allocation_sum":  res["allocation_sum"],
            "selection_sum":   res["selection_sum"],
            "interaction_sum": res["interaction_sum"],
        }
