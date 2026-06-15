"""
tests/test_circuit_breaker.py — Tests de precio_cache_service.py (Sprint 12)
Circuit breaker y caché en disco — sin internet.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MQ26_PASSWORD", "test_password_123")


@pytest.fixture(autouse=True)
def limpiar_fallos():
    """Limpia el estado global del circuit breaker antes y después de cada test."""
    import services.precio_cache_service as pcs
    pcs._fallos.clear()
    yield
    pcs._fallos.clear()


# ─── TestCircuitBreaker ───────────────────────────────────────────

class TestCircuitBreaker:
    def test_disponible_sin_fallos(self):
        from services.precio_cache_service import yfinance_disponible
        assert yfinance_disponible() is True

    def test_disponible_con_dos_fallos(self):
        from services.precio_cache_service import registrar_fallo_yf, yfinance_disponible
        registrar_fallo_yf()
        registrar_fallo_yf()
        # 2 fallos < 3 (umbral) → sigue disponible
        assert yfinance_disponible() is True

    def test_no_disponible_con_tres_fallos(self):
        from services.precio_cache_service import registrar_fallo_yf, yfinance_disponible
        registrar_fallo_yf()
        registrar_fallo_yf()
        registrar_fallo_yf()
        # 3 fallos == umbral → circuit abierto
        assert yfinance_disponible() is False

    def test_estado_retorna_claves_requeridas(self):
        from services.precio_cache_service import estado_circuit_breaker
        estado = estado_circuit_breaker()
        for k in ("degradado", "fallos_recientes", "segundos_restantes"):
            assert k in estado

    def test_estado_degradado_es_bool(self):
        from services.precio_cache_service import estado_circuit_breaker
        estado = estado_circuit_breaker()
        assert isinstance(estado["degradado"], bool)

    def test_estado_degradado_true_tras_tres_fallos(self):
        from services.precio_cache_service import estado_circuit_breaker, registrar_fallo_yf
        registrar_fallo_yf()
        registrar_fallo_yf()
        registrar_fallo_yf()
        estado = estado_circuit_breaker()
        assert estado["degradado"] is True

    def test_fallos_recientes_incrementa(self):
        from services.precio_cache_service import estado_circuit_breaker, registrar_fallo_yf
        registrar_fallo_yf()
        assert estado_circuit_breaker()["fallos_recientes"] == 1
        registrar_fallo_yf()
        assert estado_circuit_breaker()["fallos_recientes"] == 2


# ─── TestCacheEnDisco ─────────────────────────────────────────────

class TestCacheEnDisco:
    @pytest.fixture(autouse=True)
    def redirigir_cache(self, monkeypatch, tmp_path):
        """Aisla el filesystem real redirigiendo _CACHE_DIR al tmp_path."""
        import services.precio_cache_service as pcs
        monkeypatch.setattr(pcs, "_CACHE_DIR", tmp_path)

    def test_get_inexistente_retorna_none(self):
        from services.precio_cache_service import get_historico_cacheado
        result = get_historico_cacheado(("AAPL",), "90d")
        assert result is None

    def test_guardar_y_recuperar_dataframe(self, tmp_path):
        from services.precio_cache_service import (
            get_historico_cacheado,
            guardar_historico_cache,
        )
        # _CACHE_DIR ya está redirigido a tmp_path por el fixture autouse
        df_original = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        guardar_historico_cache(("AAPL",), "90d", df_original)
        df_recuperado = get_historico_cacheado(("AAPL",), "90d")
        assert df_recuperado is not None
        assert list(df_recuperado["close"]) == [100.0, 101.0, 102.0]

    def test_limpiar_no_lanza(self):
        from services.precio_cache_service import limpiar_cache_expirado
        try:
            limpiar_cache_expirado()
        except Exception as e:
            pytest.fail(f"limpiar_cache_expirado lanzó: {e}")

    def test_limpiar_cache_expirado_retorna_entero(self):
        from services.precio_cache_service import limpiar_cache_expirado
        n = limpiar_cache_expirado()
        assert isinstance(n, int) and n >= 0
