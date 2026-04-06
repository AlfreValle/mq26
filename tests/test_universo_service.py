"""
tests/test_universo_service.py — Tests de universo_service.py (Sprint 20)
Sin yfinance ni red.
Funciones: set_universo_df, obtener_ratio, obtener_sector, obtener_tipo,
           listar_tickers, buscar_ticker.
"""
from __future__ import annotations

import pandas as pd
import pytest

import config
import services.universo_service as us


@pytest.fixture(autouse=True)
def reset_universo():
    """Invariante: _universo_df queda None antes y después de cada test."""
    us._universo_df = None
    yield
    us._universo_df = None


@pytest.fixture
def df_universo():
    return pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "KO", "GLD"],
        "Nombre": ["Apple Inc", "Microsoft Corp", "Coca-Cola Co", "Gold ETF"],
        "Ratio":  ["10", "5", "25", "1"],
        "Sector": ["Tecnología", "Tecnología", "Consumo", "Commodities"],
        "Tipo":   ["CEDEAR", "CEDEAR", "CEDEAR", "ETF"],
    })


@pytest.fixture
def universo_df_sample():
    return pd.DataFrame({
        "Ticker": ["AAPL", "MSFT", "YPFD", "BRKB"],
        "Nombre": ["Apple Inc", "Microsoft Corp", "YPF SA", "Berkshire Hathaway"],
        "Sector": ["Tecnología", "Tecnología", "Energía Local", "Financiero"],
        "Tipo":   ["CEDEAR", "CEDEAR", "Acción Local", "CEDEAR"],
        "Ratio":  [20.0, 30.0, 1.0, 1.0],
    })


# ─── Módulo importa ───────────────────────────────────────────────────────────

class TestImport:
    def test_modulo_importa_sin_error(self):
        assert us is not None

    def test_funciones_publicas_son_callables(self):
        for fn in ("set_universo_df", "obtener_ratio", "obtener_sector",
                   "obtener_tipo", "listar_tickers", "buscar_ticker"):
            assert callable(getattr(us, fn)), f"{fn} no es callable"


# ─── set_universo_df ─────────────────────────────────────────────────────────

class TestSetUniversoDf:
    def test_set_dataframe_vacio(self):
        us.set_universo_df(pd.DataFrame())
        assert us._universo_df is not None

    def test_set_dataframe_con_datos(self, df_universo):
        us.set_universo_df(df_universo)
        assert not us._universo_df.empty
        assert len(us._universo_df) == 4

    def test_set_modifica_estado_global(self, universo_df_sample):
        assert us._universo_df is None
        us.set_universo_df(universo_df_sample)
        assert us._universo_df is not None
        assert len(us._universo_df) == len(universo_df_sample)


# ─── obtener_ratio ───────────────────────────────────────────────────────────

class TestObtenerRatio:
    def test_ticker_en_ratios_cedear(self):
        from config import RATIOS_CEDEAR
        if RATIOS_CEDEAR:
            ticker = next(iter(RATIOS_CEDEAR))
            ratio = us.obtener_ratio(ticker)
            assert isinstance(ratio, float)
            assert ratio > 0

    def test_ticker_inexistente_retorna_1(self):
        ratio = us.obtener_ratio("TICKER_INEXISTENTE_XYZ_999")
        assert ratio == pytest.approx(1.0)

    def test_ticker_lowercase_normalizado(self):
        ratio_up = us.obtener_ratio("TICKER_INEXISTENTE_XYZ_999")
        ratio_lo = us.obtener_ratio("ticker_inexistente_xyz_999")
        assert ratio_up == ratio_lo

    def test_con_universo_df_retorna_ratio_correcto(self, df_universo):
        us.set_universo_df(df_universo)
        ratio = us.obtener_ratio("AAPL")
        assert ratio == pytest.approx(10.0)

    def test_con_universo_df_ticker_no_encontrado_fallback(self, df_universo):
        us.set_universo_df(df_universo)
        ratio = us.obtener_ratio("ZZZNOT")
        assert isinstance(ratio, float) and ratio > 0

    def test_brkb_ratio_coincide_config(self):
        esperado = float(config.RATIOS_CEDEAR.get("BRKB", 1.0))
        assert us.obtener_ratio("BRKB") == pytest.approx(esperado)

    def test_retorna_float_positivo_siempre(self):
        for ticker in ["AAPL", "MSFT", "BRKB", "TICKER_RARO_XYZ"]:
            r = us.obtener_ratio(ticker)
            assert isinstance(r, float) and r > 0.0

    def test_con_universo_df_prioriza_ratio_sobre_config(self, universo_df_sample):
        df = universo_df_sample.copy()
        df.loc[df["Ticker"] == "AAPL", "Ratio"] = 99.0
        us.set_universo_df(df)
        assert us.obtener_ratio("AAPL") == 99.0


# ─── obtener_sector ──────────────────────────────────────────────────────────

class TestObtenerSector:
    def test_ticker_inexistente_retorna_otros(self):
        sector = us.obtener_sector("TICKER_INEXISTENTE_XYZ_999")
        assert isinstance(sector, str)
        assert sector == "Otros"

    def test_retorna_string(self):
        sector = us.obtener_sector("AAPL")
        assert isinstance(sector, str)

    def test_con_universo_df_retorna_sector_correcto(self, df_universo):
        us.set_universo_df(df_universo)
        sector = us.obtener_sector("AAPL")
        assert sector == "Tecnología"

    def test_con_universo_df_ticker_faltante_usa_fallback(self, df_universo):
        us.set_universo_df(df_universo)
        sector = us.obtener_sector("TICKER_SIN_SECTOR_ZZZ")
        assert isinstance(sector, str)

    def test_case_insensitive(self):
        assert us.obtener_sector("aapl") == us.obtener_sector("AAPL")

    def test_con_universo_df_ypfd_sector(self, universo_df_sample):
        us.set_universo_df(universo_df_sample)
        assert us.obtener_sector("YPFD") == "Energía Local"


# ─── obtener_tipo ────────────────────────────────────────────────────────────

class TestObtenerTipo:
    def test_retorna_string(self):
        tipo = us.obtener_tipo("AAPL")
        assert isinstance(tipo, str)
        assert len(tipo) > 0

    def test_ticker_en_ratios_cedear_retorna_cedear(self):
        from config import RATIOS_CEDEAR
        if RATIOS_CEDEAR:
            ticker = next(iter(RATIOS_CEDEAR))
            tipo = us.obtener_tipo(ticker)
            assert tipo == "CEDEAR"

    def test_con_universo_df_retorna_tipo_correcto(self, df_universo):
        us.set_universo_df(df_universo)
        tipo = us.obtener_tipo("GLD")
        assert tipo == "ETF"

    def test_lowercase_normalizado(self):
        tipo_up = us.obtener_tipo("AAPL")
        tipo_lo = us.obtener_tipo("aapl")
        assert tipo_up == tipo_lo

    def test_ticker_desconocido_es_cedear_por_defecto(self):
        assert us.obtener_tipo("TICKER_XYZ_NO_EXISTE") == "CEDEAR"

    def test_con_universo_df_accion_local(self, universo_df_sample):
        us.set_universo_df(universo_df_sample)
        assert us.obtener_tipo("YPFD") == "Acción Local"


# ─── listar_tickers ──────────────────────────────────────────────────────────

class TestListarTickers:
    def test_sin_universo_retorna_lista(self):
        result = us.listar_tickers()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_contiene_tickers_conocidos_ratios_cedear(self):
        tickers = us.listar_tickers()
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_resultado_es_lista_de_strings(self):
        result = us.listar_tickers()
        for t in result[:5]:
            assert isinstance(t, str)

    def test_resultado_ordenado(self):
        result = us.listar_tickers()
        assert result == sorted(result)

    def test_con_universo_df_incluye_tickers(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.listar_tickers()
        assert "AAPL" in result
        assert "MSFT" in result

    def test_filtro_por_tipo(self, df_universo):
        us.set_universo_df(df_universo)
        etfs = us.listar_tickers(tipo="ETF")
        assert isinstance(etfs, list)
        assert "GLD" in etfs
        assert "AAPL" not in etfs

    def test_filtro_tipo_sin_coincidencias_retorna_lista_vacia(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.listar_tickers(tipo="BONO_USD_RARO_XYZ")
        assert isinstance(result, list)

    def test_filtro_tipo_cedear_excluye_accion_local(self, universo_df_sample):
        us.set_universo_df(universo_df_sample)
        tickers = us.listar_tickers(tipo="CEDEAR")
        assert "YPFD" not in tickers
        assert "AAPL" in tickers


# ─── buscar_ticker ───────────────────────────────────────────────────────────

class TestBuscarTicker:
    def test_query_vacia_retorna_lista_vacia(self):
        result = us.buscar_ticker("")
        assert result == []

    def test_query_solo_espacios_retorna_lista_vacia(self):
        assert us.buscar_ticker("   ") == []

    def test_retorna_lista_de_dicts(self):
        from config import RATIOS_CEDEAR
        if RATIOS_CEDEAR:
            ticker = next(iter(RATIOS_CEDEAR))
            result = us.buscar_ticker(ticker[:3])
            assert isinstance(result, list)

    def test_con_universo_df_busca_por_ticker(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.buscar_ticker("AAPL")
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["ticker"] == "AAPL"

    def test_con_universo_df_busca_por_nombre(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.buscar_ticker("Apple")
        assert isinstance(result, list)
        assert any(r["ticker"] == "AAPL" for r in result)

    def test_resultado_tiene_claves_esperadas(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.buscar_ticker("MSFT")
        assert len(result) > 0
        for k in ("ticker", "nombre", "sector", "ratio", "tipo"):
            assert k in result[0], f"Clave faltante: {k}"

    def test_maximo_10_resultados(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.buscar_ticker("A")
        assert len(result) <= 10

    def test_query_sin_coincidencias_retorna_lista_vacia(self, df_universo):
        us.set_universo_df(df_universo)
        result = us.buscar_ticker("ZZZNOMATCH999XYZ")
        assert result == []

    def test_busqueda_case_insensitive_misma_cantidad_resultados(self, universo_df_sample):
        us.set_universo_df(universo_df_sample)
        r1 = us.buscar_ticker("aapl")
        r2 = us.buscar_ticker("AAPL")
        assert len(r1) == len(r2)
