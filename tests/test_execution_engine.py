"""
tests/test_execution_engine.py — Tests para 1_Scripts_Motor/execution_engine.py
Ejecutar: pytest tests/test_execution_engine.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "1_Scripts_Motor"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from execution_engine import calcular_nominales_cedear, generar_ordenes


class TestGenerarOrdenes:
    PESOS_OBJETIVO = {"AAPL": 0.50, "MSFT": 0.30, "KO": 0.20}
    PRECIOS_ARS    = {"AAPL": 18500, "MSFT": 18500, "KO": 22540}

    def test_sin_posiciones_genera_compras(self):
        capital_actual = {"AAPL": 0, "MSFT": 0, "KO": 0}
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual=capital_actual,
            capital_nuevo=100_000,
            precios_ars=self.PRECIOS_ARS,
            umbral_pct=0.0,
        )
        assert len(ordenes) > 0
        for o in ordenes:
            assert o["ACCION"] == "COMPRAR"

    def test_ordenes_son_positivas(self):
        capital_actual = {"AAPL": 0, "MSFT": 0, "KO": 0}
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual=capital_actual,
            capital_nuevo=100_000,
            precios_ars=self.PRECIOS_ARS,
        )
        for o in ordenes:
            assert o["NOMINALES"] > 0
            assert o["PRECIO_ARS"] > 0

    def test_sin_capital_sin_desviacion_no_genera_ordenes(self):
        # Cartera perfectamente balanceada → sin órdenes con umbral 5%
        capital_actual = {
            "AAPL": 50_000, "MSFT": 30_000, "KO": 20_000
        }
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual=capital_actual,
            capital_nuevo=0,
            precios_ars=self.PRECIOS_ARS,
            umbral_pct=0.05,
        )
        assert len(ordenes) == 0

    def test_capital_cero_total_devuelve_vacio(self):
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual={},
            capital_nuevo=0,
            precios_ars=self.PRECIOS_ARS,
        )
        assert ordenes == []

    def test_precio_cero_ticker_ignorado(self):
        precios_con_cero = {"AAPL": 18500, "MSFT": 0, "KO": 22540}
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual={},
            capital_nuevo=100_000,
            precios_ars=precios_con_cero,
        )
        tickers_con_orden = {o["TICKER"] for o in ordenes}
        assert "MSFT" not in tickers_con_orden

    def test_ordenes_ordenadas_por_monto_desc(self):
        capital_actual = {}
        ordenes = generar_ordenes(
            pesos_objetivo=self.PESOS_OBJETIVO,
            capital_actual=capital_actual,
            capital_nuevo=100_000,
            precios_ars=self.PRECIOS_ARS,
        )
        if len(ordenes) >= 2:
            montos = [o["TOTAL_ARS"] for o in ordenes]
            assert montos == sorted(montos, reverse=True)


class TestCalcularNominalesCedear:
    def test_calculo_exacto(self):
        # monto_usd=1000, precio_usd=200, ratio=20
        # precio_cedear_usd = 200/20 = 10
        # nominales = 1000/10 = 100
        resultado = calcular_nominales_cedear("AAPL", 1000.0, 200.0, 20)
        assert resultado == 100

    def test_precio_cero_devuelve_cero(self):
        assert calcular_nominales_cedear("AAPL", 1000.0, 0.0, 20) == 0

    def test_ratio_cero_devuelve_cero(self):
        assert calcular_nominales_cedear("AAPL", 1000.0, 200.0, 0) == 0

    def test_monto_pequeno_devuelve_cero(self):
        # monto_usd=0.01 → menos de 1 nominal
        assert calcular_nominales_cedear("AAPL", 0.01, 200.0, 20) == 0
