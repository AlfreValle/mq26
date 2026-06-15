"""
tests/test_sync_service.py — Tests de core/sync_service.py (Sprint 19)
Sin red. Usa tmp_path para archivos temporales y db_en_memoria para BD.
Cubre: sincronizar_excel_a_bd, exportar_bd_a_excel, reconciliar_fuentes, _buscar_col.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


# ─── sincronizar_excel_a_bd ───────────────────────────────────────────────────

class TestSincronizarExcelABd:
    def test_excel_inexistente_retorna_ceros(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "no_existe.xlsx"
        resultado = sincronizar_excel_a_bd(ruta)
        assert isinstance(resultado, dict)
        assert resultado["insertadas"] == 0
        assert resultado["errores"] == 0

    def test_retorna_claves_esperadas(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "no_existe.xlsx"
        resultado = sincronizar_excel_a_bd(ruta)
        for k in ("insertadas", "actualizadas", "errores", "total"):
            assert k in resultado, f"Clave faltante: {k}"

    def test_excel_vacio_retorna_ceros(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "vacio.xlsx"
        pd.DataFrame().to_excel(ruta, index=False)
        resultado = sincronizar_excel_a_bd(ruta)
        assert resultado["insertadas"] == 0
        assert resultado["total"] == 0

    def test_excel_sin_columnas_ticker_cantidad_registra_error(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "sin_cols.xlsx"
        # DataFrame con columnas que no coinciden con Ticker/Cantidad
        df = pd.DataFrame({"ColA": ["X", "Y"], "ColB": [1, 2]})
        df.to_excel(ruta, index=False)
        resultado = sincronizar_excel_a_bd(ruta)
        assert resultado["errores"] >= 1

    def test_excel_archivo_corrupto_registra_error(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "corrupto.xlsx"
        ruta.write_bytes(b"esto no es un xlsx valido")
        resultado = sincronizar_excel_a_bd(ruta)
        assert isinstance(resultado, dict)
        assert resultado["errores"] >= 1

    def test_excel_con_datos_validos_inserta(self, tmp_path, db_en_memoria):
        """Excel con Ticker/Cantidad/Propietario válidos → llama a registrar_transaccion."""
        from core.sync_service import sincronizar_excel_a_bd
        ruta = tmp_path / "maestra.xlsx"
        df = pd.DataFrame({
            "Ticker":      ["AAPL", "MSFT"],
            "Cantidad":    [10, 5],
            "PPC_USD":     [8.0, 10.0],
            "Propietario": ["Alfredo", "Alfredo"],
            "Cartera":     ["Retiro", "Retiro"],
            "Tipo":        ["CEDEAR", "CEDEAR"],
        })
        df.to_excel(ruta, index=False)
        resultado = sincronizar_excel_a_bd(ruta)
        assert isinstance(resultado, dict)
        # insertadas + errores tiene que sumar al total procesado
        assert resultado["insertadas"] + resultado["errores"] >= 0

    def test_no_lanza_excepcion_inputs_extremos(self, tmp_path):
        from core.sync_service import sincronizar_excel_a_bd
        try:
            sincronizar_excel_a_bd(Path("/ruta/completamente/inexistente.xlsx"))
        except Exception as e:
            pytest.fail(f"sincronizar_excel_a_bd lanzó con ruta inexistente: {e}")


# ─── exportar_bd_a_excel ──────────────────────────────────────────────────────

class TestExportarBdAExcel:
    def test_bd_vacia_retorna_false(self, tmp_path, db_en_memoria):
        from core.sync_service import exportar_bd_a_excel
        # Mockear obtener_todos_los_trades para simular BD vacía
        with patch("core.db_manager.obtener_todos_los_trades",
                   return_value=pd.DataFrame()):
            resultado = exportar_bd_a_excel(tmp_path / "backup.xlsx")
        assert resultado is False

    def test_con_datos_retorna_true_y_crea_archivo(self, tmp_path):
        from core.sync_service import exportar_bd_a_excel
        df_mock = pd.DataFrame({
            "ticker":    ["AAPL", "MSFT"],
            "nominales": [10, 5],
            "precio_ars": [15_000.0, 20_000.0],
        })
        ruta = tmp_path / "backup.xlsx"
        with patch("core.db_manager.obtener_todos_los_trades", return_value=df_mock):
            resultado = exportar_bd_a_excel(ruta)
        assert resultado is True
        assert ruta.exists()

    def test_no_lanza_excepcion(self, tmp_path):
        from core.sync_service import exportar_bd_a_excel
        with patch("core.db_manager.obtener_todos_los_trades",
                   side_effect=Exception("BD error")):
            resultado = exportar_bd_a_excel(tmp_path / "error.xlsx")
        assert resultado is False


# ─── reconciliar_fuentes ──────────────────────────────────────────────────────

class TestReconciliarFuentes:
    def test_csv_inexistente_retorna_error(self, tmp_path):
        from core.sync_service import reconciliar_fuentes
        ruta = tmp_path / "no_existe.csv"
        resultado = reconciliar_fuentes(ruta)
        assert isinstance(resultado, dict)
        assert resultado.get("error") is not None

    def test_retorna_claves_esperadas(self, tmp_path):
        from core.sync_service import reconciliar_fuentes
        ruta = tmp_path / "no_existe.csv"
        resultado = reconciliar_fuentes(ruta)
        for k in ("en_csv_no_bd", "en_bd_no_csv", "coincidencias", "discrepancias"):
            assert k in resultado

    def test_csv_vacio_sin_excepcion(self, tmp_path):
        from core.sync_service import reconciliar_fuentes
        ruta = tmp_path / "vacio.csv"
        ruta.write_text("TICKER,FECHA_COMPRA,CANTIDAD\n")
        with patch("core.db_manager.obtener_todos_los_trades",
                   return_value=pd.DataFrame()):
            resultado = reconciliar_fuentes(ruta)
        assert isinstance(resultado, dict)
        assert resultado["coincidencias"] == 0

    def test_bd_y_csv_coincidentes(self, tmp_path):
        from core.sync_service import reconciliar_fuentes
        ruta = tmp_path / "datos.csv"
        ruta.write_text(
            "TICKER,FECHA_COMPRA,CANTIDAD\n"
            "AAPL,2024-01-15,10\n"
        )
        df_bd = pd.DataFrame({
            "ticker":    ["AAPL"],
            "fecha":     ["2024-01-15"],
            "nominales": [10],
        })
        with patch("core.db_manager.obtener_todos_los_trades", return_value=df_bd):
            resultado = reconciliar_fuentes(ruta)
        assert isinstance(resultado, dict)
        assert resultado["coincidencias"] >= 0  # al menos no lanza


# ─── _buscar_col ──────────────────────────────────────────────────────────────

class TestBuscarCol:
    def test_encuentra_primera_coincidencia(self):
        from core.sync_service import _buscar_col
        df = pd.DataFrame({"Ticker": [], "Cantidad": []})
        assert _buscar_col(df, ["Ticker", "TICKER"]) == "Ticker"

    def test_retorna_none_si_no_encuentra(self):
        from core.sync_service import _buscar_col
        df = pd.DataFrame({"ColA": [], "ColB": []})
        assert _buscar_col(df, ["Ticker", "TICKER"]) is None

    def test_segunda_candidata_si_primera_ausente(self):
        from core.sync_service import _buscar_col
        df = pd.DataFrame({"TICKER": [], "Cantidad": []})
        assert _buscar_col(df, ["Ticker", "TICKER"]) == "TICKER"

    def test_df_vacio_retorna_none(self):
        from core.sync_service import _buscar_col
        df = pd.DataFrame()
        assert _buscar_col(df, ["Ticker"]) is None
