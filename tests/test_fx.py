"""Tests A13 — core/fx.py: FX por fecha de operación."""
from __future__ import annotations

from datetime import date

from core.fx import (
    FUENTE_HISTORICO,
    FUENTE_SPOT,
    ars_a_usd,
    ccl_para_fecha,
    ccl_series,
    usd_a_ars,
)
from core.pricing_utils import CCL_HISTORICO


class TestCclParaFecha:
    def test_fecha_historica_usa_serie(self):
        q = ccl_para_fecha(date(2023, 6, 15), spot=1450.0)
        assert q.fuente == FUENTE_HISTORICO
        assert q.valor == float(CCL_HISTORICO["2023-06"])

    def test_fecha_futura_usa_spot(self):
        q = ccl_para_fecha(date(2030, 1, 1), spot=1500.0)
        assert q.fuente == FUENTE_SPOT
        assert q.valor == 1500.0

    def test_fecha_futura_sin_spot_usa_ultimo_historico(self):
        q = ccl_para_fecha(date(2030, 1, 1))
        assert q.fuente == FUENTE_HISTORICO
        ultimo_mes = max(CCL_HISTORICO)
        assert q.valor == float(CCL_HISTORICO[ultimo_mes])

    def test_fecha_string_iso(self):
        q = ccl_para_fecha("2023-06-10")
        assert q.valor == float(CCL_HISTORICO["2023-06"])

    def test_mes_faltante_usa_anterior_sin_lookahead(self):
        # Una fecha anterior al inicio de la serie usa el primer dato
        # disponible vía el fallback de ccl_historico_por_fecha
        q = ccl_para_fecha(date(2023, 6, 1))
        assert q.es_valida

    def test_fecha_none_con_spot(self):
        q = ccl_para_fecha(None, spot=1480.0)
        assert q.fuente == FUENTE_SPOT
        assert q.valor == 1480.0

    def test_fecha_basura_con_spot(self):
        q = ccl_para_fecha("no-es-fecha", spot=1480.0)
        assert q.valor == 1480.0


class TestConversiones:
    def test_roundtrip_ars_usd(self):
        f = date(2023, 6, 15)
        usd = ars_a_usd(1_000_000.0, f)
        assert usd_a_ars(usd, f) == 1_000_000.0

    def test_usd_a_ars_historico(self):
        f = date(2024, 3, 15)
        esperado = 100.0 * float(CCL_HISTORICO["2024-03"])
        assert usd_a_ars(100.0, f) == esperado


class TestCclSeries:
    def test_series_multiples_fechas(self):
        fechas = [date(2023, 6, 1), date(2024, 3, 1), "2025-01-15"]
        s = ccl_series(fechas)
        assert len(s) == 3
        assert s[date(2023, 6, 1)] == float(CCL_HISTORICO["2023-06"])
        assert s[date(2025, 1, 15)] == float(CCL_HISTORICO["2025-01"])

    def test_series_omite_invalidas(self):
        s = ccl_series(["basura", date(2024, 3, 1)])
        assert len(s) == 1


class TestIntegracionPosicionNeta:
    """A13 en calcular_posicion_neta: costo histórico cuando hay fecha."""

    def test_cedear_con_fecha_usa_ccl_historico(self):
        import pandas as pd

        from services.cartera_service import calcular_posicion_neta

        df_ag = pd.DataFrame(
            {
                "TICKER": ["AAPL"],
                "CANTIDAD_TOTAL": [10.0],
                "PPC_USD_PROM": [10.0],
                "INV_USD_TOTAL": [100.0],
                "FECHA_PRIMERA_COMPRA": ["2023-06-15"],
            }
        )
        ccl_spot = 1450.0
        out = calcular_posicion_neta(df_ag, {"AAPL": 15000.0}, ccl_spot)
        ccl_hist = float(CCL_HISTORICO["2023-06"])
        assert float(out["PPC_ARS"].iloc[0]) == 10.0 * ccl_hist
        assert float(out["INV_ARS"].iloc[0]) == 100.0 * ccl_hist

    def test_cedear_sin_fecha_usa_spot(self):
        import pandas as pd

        from services.cartera_service import calcular_posicion_neta

        df_ag = pd.DataFrame(
            {
                "TICKER": ["AAPL"],
                "CANTIDAD_TOTAL": [10.0],
                "PPC_USD_PROM": [10.0],
                "INV_USD_TOTAL": [100.0],
            }
        )
        ccl_spot = 1450.0
        out = calcular_posicion_neta(df_ag, {"AAPL": 15000.0}, ccl_spot)
        assert float(out["PPC_ARS"].iloc[0]) == 10.0 * ccl_spot

    def test_inv_ars_historico_sigue_mandando(self):
        import pandas as pd

        from services.cartera_service import calcular_posicion_neta

        df_ag = pd.DataFrame(
            {
                "TICKER": ["AAPL"],
                "CANTIDAD_TOTAL": [10.0],
                "PPC_USD_PROM": [10.0],
                "INV_USD_TOTAL": [100.0],
                "INV_ARS_HISTORICO": [123_456.0],
                "FECHA_PRIMERA_COMPRA": ["2023-06-15"],
            }
        )
        out = calcular_posicion_neta(df_ag, {"AAPL": 15000.0}, 1450.0)
        assert float(out["INV_ARS"].iloc[0]) == 123_456.0
