"""
services/stress_test.py — Stress testing con escenarios históricos (Sprint 3)
MQ26-DSS | Escenarios: crisis 2008, COVID, devaluación ARS 2023, dot-com, Fed 2022, custom.
Aplica shocks a SPY y CCL; diferencia activos locales ARS vs CEDEARs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from core.pricing_utils import es_instrumento_local_ars
except ImportError:
    def es_instrumento_local_ars(ticker: str, tipo: str = "") -> bool:
        return False


# Escenarios: delta_spy y delta_ccl en decimal (ej. -0.55 = -55% SPY, +0.80 = +80% CCL)
SCENARIOS: dict[str, dict[str, float]] = {
    "crisis_2008":   {"delta_spy": -0.55, "delta_ccl": 0.00},
    "covid_2020":    {"delta_spy": -0.35, "delta_ccl": -0.10},
    # B05: shocks representativos 2018/2020 para carteras CEDEAR (SPY + canal CCL).
    "devaluacion_2018": {"delta_spy": -0.50, "delta_ccl": 0.55},
    "pandemia_2020":    {"delta_spy": -0.48, "delta_ccl": 0.08},
    "deval_ars_23":  {"delta_spy":  0.03, "delta_ccl":  0.80},
    "dotcom_2000":   {"delta_spy": -0.78, "delta_ccl":  0.00},
    "fed_2022":      {"delta_spy": -0.25, "delta_ccl":  0.30},
}


class StressTestEngine:
    """
    Aplica shocks históricos o custom a la cartera actual.
    CEDEARs: valor en ARS sube con CCL (subyacente * ccl/ratio).
    Locales ARS: no se revalorizan por CCL; se puede aplicar shock local si se define.
    """

    def aplicar_escenario(
        self,
        df_pos: pd.DataFrame,
        ccl: float,
        escenario: str,
    ) -> dict:
        """
        Aplica un escenario por nombre. No muta df_pos (usa copia).
        Retorna dict con valor_original, valor_stress, pct_cambio, pct_perdida.
        """
        if df_pos is None or df_pos.empty or escenario not in SCENARIOS:
            return _empty_result(ccl)
        s = SCENARIOS[escenario]
        return self._aplicar_shocks(
            df_pos.copy(),
            ccl,
            s.get("delta_spy", 0.0),
            s.get("delta_ccl", 0.0),
        )

    def _aplicar_shocks(
        self,
        df_pos: pd.DataFrame,
        ccl: float,
        delta_spy: float,
        delta_ccl: float,
    ) -> dict:
        """Valor actual en ARS y valor bajo stress. Asume columnas TICKER, CANTIDAD, PRECIO_ARS o valor calculable."""
        if "VALOR_ARS" in df_pos.columns:
            valor_original = float(df_pos["VALOR_ARS"].sum())
        elif "PRECIO_ARS" in df_pos.columns and "CANTIDAD" in df_pos.columns:
            valor_original = float((df_pos["PRECIO_ARS"] * df_pos["CANTIDAD"]).sum())
        else:
            valor_original = 0.0

        valor_stress = 0.0
        for _, row in df_pos.iterrows():
            ticker = str(row.get("TICKER", ""))
            cant = float(row.get("CANTIDAD", 0))
            precio_ars = float(row.get("PRECIO_ARS", row.get("VALOR_ARS", 0) / max(cant, 1)))
            if cant <= 0:
                continue
            if es_instrumento_local_ars(ticker):
                valor_stress += cant * precio_ars
            else:
                valor_stress += cant * precio_ars * (1.0 + delta_ccl)
        if delta_spy != 0 and valor_stress > 0:
            # Calcular el peso real de CEDEARs (activos no locales) en la cartera.
            # Solo los CEDEARs correlacionan con SPY; los locales son inmunes al shock.
            # Invariante: delta_spy=0 → factor=1 → valor no cambia.
            # Invariante: peso_cedear=0 (100% local) → shock SPY = 0.
            total_v = float(df_pos["VALOR_ARS"].sum()) if "VALOR_ARS" in df_pos.columns else valor_original
            peso_cedear = 0.0
            if total_v > 0 and "VALOR_ARS" in df_pos.columns:
                for _, fila in df_pos.iterrows():
                    t = str(fila.get("TICKER", ""))
                    if not es_instrumento_local_ars(t):
                        peso_cedear += float(fila.get("VALOR_ARS", 0)) / total_v
            else:
                peso_cedear = 0.7  # fallback conservador cuando no hay VALOR_ARS

            factor_spy = 1.0 + delta_spy
            valor_stress = valor_stress * (1.0 - peso_cedear + peso_cedear * factor_spy)
        pct_cambio = (valor_stress / valor_original - 1.0) * 100.0 if valor_original > 0 else 0.0
        pct_perdida = -pct_cambio if pct_cambio < 0 else 0.0
        return {
            "valor_original": valor_original,
            "valor_stress": valor_stress,
            "pct_cambio": pct_cambio,
            "pct_perdida": pct_perdida,
        }

    def todos_los_escenarios(
        self,
        df_pos: pd.DataFrame,
        ccl: float,
    ) -> pd.DataFrame:
        """DataFrame con una fila por escenario: escenario, valor_original, valor_stress, pct_perdida."""
        if df_pos is None or df_pos.empty:
            return pd.DataFrame(columns=["escenario", "valor_original", "valor_stress", "pct_perdida"])
        rows = []
        for name in SCENARIOS:
            r = self.aplicar_escenario(df_pos, ccl, name)
            rows.append({
                "escenario": name,
                "valor_original": r.get("valor_original", 0),
                "valor_stress": r.get("valor_stress", 0),
                "pct_perdida": r.get("pct_perdida", 0),
            })
        return pd.DataFrame(rows)

    def escenario_custom(
        self,
        df_pos: pd.DataFrame,
        ccl: float,
        delta_spy: float,
        delta_ccl: float,
    ) -> dict:
        """Shocks custom en decimal (ej. -0.30 = -30% SPY). No muta df_pos."""
        if df_pos is None or df_pos.empty:
            return _empty_result(ccl)
        return self._aplicar_shocks(df_pos.copy(), ccl, delta_spy, delta_ccl)


def _empty_result(ccl: float) -> dict:
    return {
        "valor_original": 0.0,
        "valor_stress": 0.0,
        "pct_cambio": 0.0,
        "pct_perdida": 0.0,
    }
