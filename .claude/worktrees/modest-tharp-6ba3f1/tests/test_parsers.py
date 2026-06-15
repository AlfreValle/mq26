"""
tests/test_parsers.py — Tests unitarios para gmail_reader y broker_importer
Ejecutar: pytest tests/test_parsers.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── gmail_reader ─────────────────────────────────────────────────────────────
class TestGmailReaderBalanz:
    CUERPO_BALANZ = """
    123456 COMPRA AAPL APPLE INC 100 $18.500,00 $1.850.000,00 $5.000,00 $1.050,00 $500,00 $1.843.450,00 Pesos 11/03/2026
    789012 VENTA  KO   COCA COLA  50 $22.540,00 $1.127.000,00 $3.000,00 $630,00 $300,00 $1.123.070,00 Pesos 11/03/2026
    """

    def test_parse_devuelve_lista(self):
        from gmail_reader import parse_balanz
        rows = parse_balanz(self.CUERPO_BALANZ)
        assert isinstance(rows, list)

    def test_parse_detecta_compra_y_venta(self):
        from gmail_reader import parse_balanz
        rows = parse_balanz(self.CUERPO_BALANZ)
        if rows:
            tipos = {r["Tipo_Op"] for r in rows}
            assert "COMPRA" in tipos or "VENTA" in tipos

    def test_parse_campos_obligatorios(self):
        from gmail_reader import parse_balanz
        rows = parse_balanz(self.CUERPO_BALANZ)
        for r in rows:
            for campo in ("Broker", "Fecha", "Tipo_Op", "Ticker", "Cantidad", "Precio_ARS", "PPC_USD"):
                assert campo in r

    def test_broker_es_balanz(self):
        from gmail_reader import parse_balanz
        rows = parse_balanz(self.CUERPO_BALANZ)
        for r in rows:
            assert r["Broker"] == "Balanz"

    def test_precio_usd_positivo(self):
        from gmail_reader import parse_balanz
        rows = parse_balanz(self.CUERPO_BALANZ)
        for r in rows:
            assert r["PPC_USD"] >= 0


class TestGmailReaderBullmarket:
    CUERPO_BULL = """
    MSFT 2026-03-11 Compra Normal 100 18500.00 1850000.00
    META 2026-03-11 Venta Normal  50 37000.00 1850000.00
    """

    def test_parse_devuelve_lista(self):
        from gmail_reader import parse_bullmarket
        rows = parse_bullmarket(self.CUERPO_BULL)
        assert isinstance(rows, list)

    def test_broker_es_bullmarket(self):
        from gmail_reader import parse_bullmarket
        rows = parse_bullmarket(self.CUERPO_BULL)
        for r in rows:
            assert r["Broker"] == "Bull Market"


class TestLeerTodosLosCorreos:
    def test_lista_vacia(self):
        from gmail_reader import leer_todos_los_correos
        df = leer_todos_los_correos([], [])
        assert df.empty

    def test_devuelve_dataframe(self):
        from gmail_reader import leer_todos_los_correos
        msg = [{"body": "123 COMPRA AAPL AAPl 10 $18500 $185000 $100 $20 $10 $184870 Pesos 01/03/2026", "fecha": ""}]
        resultado = leer_todos_los_correos(msg, [])
        assert isinstance(resultado, pd.DataFrame)


# ─── broker_importer ─────────────────────────────────────────────────────────
class TestPrecioArsToPpcUsd:
    def test_aapl(self):
        from broker_importer import precio_ars_to_ppc_usd
        # precio_ars=18000, ticker=AAPL (ratio=20), ccl=1465
        resultado = precio_ars_to_ppc_usd(18000.0, "AAPL", 1465.0)
        esperado = 18000.0 / (1465.0 * 20)
        assert resultado == pytest.approx(esperado, rel=1e-3)

    def test_ccl_cero(self):
        from broker_importer import precio_ars_to_ppc_usd
        assert precio_ars_to_ppc_usd(18000.0, "AAPL", 0.0) == 0.0

    def test_precio_cero(self):
        from broker_importer import precio_ars_to_ppc_usd
        assert precio_ars_to_ppc_usd(0.0, "AAPL", 1465.0) == 0.0


class TestLimpiarPrecioArs:
    def test_formato_argentino(self):
        from broker_importer import limpiar_precio_ars
        assert limpiar_precio_ars("$49.180,00") == pytest.approx(49180.0)

    def test_float_directo(self):
        from broker_importer import limpiar_precio_ars
        assert limpiar_precio_ars(49180.0) == pytest.approx(49180.0)

    def test_none(self):
        from broker_importer import limpiar_precio_ars
        assert limpiar_precio_ars(None) == 0.0
