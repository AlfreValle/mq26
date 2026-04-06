"""
tests/test_precio_cache_service.py — Tests de precio_cache_service.py (Sprint 20)
Sin red. Usa tmp_path para el caché en disco.
Cubre: registrar_fallo_yf, yfinance_disponible, estado_circuit_breaker,
       get_historico_cacheado, guardar_historico_cache, limpiar_cache_expirado.
"""
from __future__ import annotations

import time

import pandas as pd
import pytest

import services.precio_cache_service as pcs


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Invariante: _fallos vacío al inicio y al final de cada test."""
    pcs._fallos.clear()
    yield
    pcs._fallos.clear()


@pytest.fixture
def cache_dir_tmp(tmp_path, monkeypatch):
    """Redirige el caché a un directorio temporal para no contaminar disco."""
    tmp_cache = tmp_path / "cache_precios"
    tmp_cache.mkdir()
    monkeypatch.setattr(pcs, "_CACHE_DIR", tmp_cache)
    return tmp_cache


@pytest.fixture
def df_precios():
    return pd.DataFrame(
        {"Close": [100.0, 101.0, 102.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )


# ─── Módulo importa ───────────────────────────────────────────────────────────

class TestImport:
    def test_modulo_importa_sin_error(self):
        assert pcs is not None

    def test_funciones_publicas_son_callables(self):
        for fn in ("registrar_fallo_yf", "yfinance_disponible",
                   "estado_circuit_breaker", "get_historico_cacheado",
                   "guardar_historico_cache", "limpiar_cache_expirado"):
            assert callable(getattr(pcs, fn)), f"{fn} no es callable"


# ─── registrar_fallo_yf ──────────────────────────────────────────────────────

class TestRegistrarFalloYf:
    def test_registra_fallo(self):
        pcs.registrar_fallo_yf()
        assert len(pcs._fallos) == 1

    def test_multiples_fallos(self):
        pcs.registrar_fallo_yf()
        pcs.registrar_fallo_yf()
        assert len(pcs._fallos) == 2

    def test_no_lanza_excepcion(self):
        try:
            pcs.registrar_fallo_yf()
        except Exception as e:
            pytest.fail(f"registrar_fallo_yf lanzó: {e}")


# ─── yfinance_disponible ─────────────────────────────────────────────────────

class TestYfinanceDisponible:
    def test_sin_fallos_retorna_true(self):
        assert pcs.yfinance_disponible() is True

    def test_un_fallo_sigue_disponible(self):
        pcs.registrar_fallo_yf()
        assert pcs.yfinance_disponible() is True

    def test_dos_fallos_sigue_disponible(self):
        pcs.registrar_fallo_yf()
        pcs.registrar_fallo_yf()
        assert pcs.yfinance_disponible() is True

    def test_tres_fallos_activan_circuit_breaker(self):
        for _ in range(pcs._MAX_FALLOS):
            pcs.registrar_fallo_yf()
        result = pcs.yfinance_disponible()
        assert result is False

    def test_retorna_bool(self):
        result = pcs.yfinance_disponible()
        assert isinstance(result, bool)

    def test_fallos_fuera_de_ventana_se_limpian(self):
        """Fallos más viejos que _VENTANA_S no cuentan para el circuit breaker."""
        ahora = time.monotonic()
        pcs._fallos.extend([ahora - 70, ahora - 65])
        assert pcs.yfinance_disponible() is True


# ─── estado_circuit_breaker ──────────────────────────────────────────────────

class TestEstadoCircuitBreaker:
    def test_retorna_dict(self):
        result = pcs.estado_circuit_breaker()
        assert isinstance(result, dict)

    def test_claves_esperadas(self):
        result = pcs.estado_circuit_breaker()
        for k in ("degradado", "fallos_recientes", "segundos_restantes"):
            assert k in result, f"Clave faltante: {k}"

    def test_sin_fallos_no_degradado(self):
        result = pcs.estado_circuit_breaker()
        assert result["degradado"] is False
        assert result["fallos_recientes"] == 0

    def test_con_fallos_cuenta_correcta(self):
        pcs.registrar_fallo_yf()
        pcs.registrar_fallo_yf()
        result = pcs.estado_circuit_breaker()
        assert result["fallos_recientes"] == 2

    def test_circuit_breaker_activo(self):
        for _ in range(pcs._MAX_FALLOS):
            pcs.registrar_fallo_yf()
        result = pcs.estado_circuit_breaker()
        assert result["degradado"] is True
        assert result["segundos_restantes"] > 0


# ─── get_historico_cacheado ──────────────────────────────────────────────────

class TestGetHistoricoCacheado:
    def test_sin_cache_retorna_none(self, cache_dir_tmp):
        result = pcs.get_historico_cacheado(("AAPL", "MSFT"), "90d")
        assert result is None

    def test_con_cache_guardado_retorna_dataframe(self, cache_dir_tmp, df_precios):
        tickers = ("AAPL",)
        pcs.guardar_historico_cache(tickers, "90d", df_precios)
        result = pcs.get_historico_cacheado(tickers, "90d")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    def test_forzar_true_ignora_cache(self, cache_dir_tmp, df_precios):
        tickers = ("KO",)
        pcs.guardar_historico_cache(tickers, "30d", df_precios)
        result = pcs.get_historico_cacheado(tickers, "30d", forzar=True)
        assert result is None

    def test_diferentes_periodos_distintos_caches(self, cache_dir_tmp, df_precios):
        tickers = ("GLD",)
        pcs.guardar_historico_cache(tickers, "30d", df_precios)
        result_30d = pcs.get_historico_cacheado(tickers, "30d")
        result_90d = pcs.get_historico_cacheado(tickers, "90d")
        assert result_30d is not None
        assert result_90d is None

    def test_get_historico_pickle_corrupto_retorna_none(self, tmp_path, monkeypatch):
        """Invariante: lectura corrupta no lanza; devuelve None."""
        monkeypatch.setattr(pcs, "_CACHE_DIR", tmp_path)
        ruta = pcs._clave_cache(("AAPL",), "90d")
        ruta.write_bytes(b"corrupted pickle data")
        assert pcs.get_historico_cacheado(("AAPL",), "90d") is None


# ─── guardar_historico_cache ─────────────────────────────────────────────────

class TestGuardarHistoricoCache:
    def test_guarda_y_crea_archivo(self, cache_dir_tmp, df_precios):
        tickers = ("MSFT",)
        pcs.guardar_historico_cache(tickers, "90d", df_precios)
        archivos = list(cache_dir_tmp.glob("hist_*.pkl"))
        assert len(archivos) == 1

    def test_df_none_no_guarda(self, cache_dir_tmp):
        pcs.guardar_historico_cache(("AAPL",), "90d", None)
        archivos = list(cache_dir_tmp.glob("hist_*.pkl"))
        assert len(archivos) == 0

    def test_df_vacio_no_guarda(self, cache_dir_tmp):
        pcs.guardar_historico_cache(("AAPL",), "90d", pd.DataFrame())
        archivos = list(cache_dir_tmp.glob("hist_*.pkl"))
        assert len(archivos) == 0

    def test_no_lanza_excepcion(self, cache_dir_tmp, df_precios):
        try:
            pcs.guardar_historico_cache(("TEST",), "7d", df_precios)
        except Exception as e:
            pytest.fail(f"guardar_historico_cache lanzó: {e}")

    def test_datos_preservados_tras_ciclo(self, cache_dir_tmp, df_precios):
        tickers = ("KO", "PEP")
        pcs.guardar_historico_cache(tickers, "60d", df_precios)
        recuperado = pcs.get_historico_cacheado(tickers, "60d")
        assert recuperado is not None
        assert list(recuperado.columns) == list(df_precios.columns)


# ─── limpiar_cache_expirado ──────────────────────────────────────────────────

class TestLimpiarCacheExpirado:
    def test_sin_archivos_retorna_cero(self, cache_dir_tmp):
        eliminados = pcs.limpiar_cache_expirado()
        assert eliminados == 0

    def test_archivo_reciente_no_se_elimina(self, cache_dir_tmp, df_precios):
        pcs.guardar_historico_cache(("AAPL",), "90d", df_precios)
        eliminados = pcs.limpiar_cache_expirado()
        assert eliminados == 0
        archivos = list(cache_dir_tmp.glob("hist_*.pkl"))
        assert len(archivos) == 1

    def test_retorna_entero(self, cache_dir_tmp):
        result = pcs.limpiar_cache_expirado()
        assert isinstance(result, int)
        assert result >= 0

    def test_archivo_expirado_se_elimina(self, cache_dir_tmp, df_precios):
        import time
        pcs.guardar_historico_cache(("OLD",), "90d", df_precios)
        archivos = list(cache_dir_tmp.glob("hist_*.pkl"))
        # Simular expiración modificando mtime
        for archivo in archivos:
            ts_viejo = time.time() - (pcs._TTL_HORAS + 1) * 3600
            import os
            os.utime(archivo, (ts_viejo, ts_viejo))
        eliminados = pcs.limpiar_cache_expirado()
        assert eliminados == 1
