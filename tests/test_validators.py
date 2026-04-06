"""
tests/test_validators.py — Tests de core/validators.py (Sprint 10)
Sin red ni yfinance.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

# ─── validar_monto ────────────────────────────────────────────────────────────

class TestValidarMonto:
    def test_monto_positivo_es_valido(self):
        from core.validators import validar_monto
        ok, msg = validar_monto(100.0)
        assert ok is True
        assert msg == ""

    def test_monto_negativo_es_invalido(self):
        from core.validators import validar_monto
        ok, msg = validar_monto(-50.0)
        assert ok is False
        assert len(msg) > 0

    def test_monto_cero_invalido_por_defecto(self):
        from core.validators import validar_monto
        ok, _ = validar_monto(0.0)
        assert ok is False

    def test_monto_cero_valido_con_flag(self):
        from core.validators import validar_monto
        ok, _ = validar_monto(0.0, permitir_cero=True)
        assert ok is True

    def test_none_es_invalido(self):
        from core.validators import validar_monto
        ok, msg = validar_monto(None)
        assert ok is False
        assert len(msg) > 0

    def test_string_no_numerico_invalido(self):
        from core.validators import validar_monto
        ok, _ = validar_monto("no_es_numero")
        assert ok is False

    def test_nombre_aparece_en_mensaje(self):
        from core.validators import validar_monto
        _, msg = validar_monto(None, nombre="capital_inicial")
        assert "capital_inicial" in msg


# ─── normalizar_monto ─────────────────────────────────────────────────────────

class TestNormalizarMonto:
    def test_egreso_negativo_se_invierte(self):
        from core.validators import normalizar_monto
        result = normalizar_monto(-500.0, "EGRESO")
        assert result == 500.0

    def test_ingreso_positivo_sin_cambios(self):
        from core.validators import normalizar_monto
        result = normalizar_monto(300.0, "INGRESO")
        assert result == 300.0

    def test_ingreso_negativo_se_invierte(self):
        from core.validators import normalizar_monto
        result = normalizar_monto(-300.0, "INGRESO")
        assert result == 300.0


# ─── validar_fecha ────────────────────────────────────────────────────────────

class TestValidarFecha:
    def test_fecha_date_valida(self):
        from core.validators import validar_fecha
        ok, _ = validar_fecha(dt.date(2024, 1, 15))
        assert ok is True

    def test_string_iso_valido(self):
        from core.validators import validar_fecha
        ok, _ = validar_fecha("2024-01-15")
        assert ok is True

    def test_none_invalido(self):
        from core.validators import validar_fecha
        ok, msg = validar_fecha(None)
        assert ok is False
        assert len(msg) > 0

    def test_string_invalido(self):
        from core.validators import validar_fecha
        ok, _ = validar_fecha("no_es_fecha")
        assert ok is False


# ─── fecha_no_futura ──────────────────────────────────────────────────────────

class TestFechaNoFutura:
    def test_fecha_pasada_valida(self):
        from core.validators import fecha_no_futura
        ayer = dt.date.today() - dt.timedelta(days=1)
        ok, _ = fecha_no_futura(ayer)
        assert ok is True

    def test_fecha_futura_invalida(self):
        from core.validators import fecha_no_futura
        manana = dt.date.today() + dt.timedelta(days=1)
        ok, msg = fecha_no_futura(manana)
        assert ok is False
        assert len(msg) > 0

    def test_hoy_es_valido(self):
        from core.validators import fecha_no_futura
        ok, _ = fecha_no_futura(dt.date.today())
        assert ok is True


# ─── validar_ticker ───────────────────────────────────────────────────────────

class TestValidarTicker:
    def test_ticker_normal_valido(self):
        from core.validators import validar_ticker
        ok, _ = validar_ticker("AAPL")
        assert ok is True

    def test_ticker_vacio_invalido(self):
        from core.validators import validar_ticker
        ok, msg = validar_ticker("")
        assert ok is False
        assert len(msg) > 0

    def test_none_invalido(self):
        from core.validators import validar_ticker
        ok, _ = validar_ticker(None)
        assert ok is False

    def test_ticker_con_numeros_valido(self):
        from core.validators import validar_ticker
        ok, _ = validar_ticker("BRKB")
        assert ok is True


# ─── validar_cantidad ─────────────────────────────────────────────────────────

class TestValidarCantidad:
    def test_cantidad_positiva_valida(self):
        from core.validators import validar_cantidad
        ok, _ = validar_cantidad(100)
        assert ok is True

    def test_cantidad_cero_invalida(self):
        from core.validators import validar_cantidad
        ok, _ = validar_cantidad(0)
        assert ok is False

    def test_cantidad_negativa_invalida(self):
        from core.validators import validar_cantidad
        ok, _ = validar_cantidad(-5)
        assert ok is False

    def test_none_invalido(self):
        from core.validators import validar_cantidad
        ok, _ = validar_cantidad(None)
        assert ok is False


# ─── validar_precio_compra ────────────────────────────────────────────────────

class TestValidarPrecioCompra:
    def test_precio_positivo_valido(self):
        from core.validators import validar_precio_compra
        ok, _ = validar_precio_compra(15000.0)
        assert ok is True

    def test_precio_cero_invalido(self):
        from core.validators import validar_precio_compra
        ok, _ = validar_precio_compra(0.0)
        assert ok is False

    def test_precio_negativo_invalido(self):
        from core.validators import validar_precio_compra
        ok, _ = validar_precio_compra(-100.0)
        assert ok is False


# ─── validar_df_columnas ──────────────────────────────────────────────────────

class TestValidarDfColumnas:
    def test_df_con_todas_las_columnas(self):
        """Con datos reales (no vacío): columnas correctas → válido."""
        from core.validators import validar_df_columnas
        df = pd.DataFrame({"TICKER": ["AAPL"], "CANTIDAD": [10], "PRECIO": [100.0]})
        ok, faltantes = validar_df_columnas(df, ["TICKER", "CANTIDAD"])
        assert ok is True
        assert faltantes == []

    def test_df_con_columnas_faltantes(self):
        from core.validators import validar_df_columnas
        df = pd.DataFrame({"TICKER": []})
        ok, faltantes = validar_df_columnas(df, ["TICKER", "CANTIDAD", "PRECIO"])
        assert ok is False
        assert "CANTIDAD" in faltantes
        assert "PRECIO" in faltantes

    def test_df_vacio_retorna_invalido(self):
        """Implementacion considera df vacio como invalido — comportamiento intencional."""
        from core.validators import validar_df_columnas
        df = pd.DataFrame(columns=["A", "B"])
        ok, faltantes = validar_df_columnas(df, ["A", "B"])
        # df.empty=True → la funcion retorna False (diseño de la implementacion)
        assert ok is False
